"""Run the branch-count experiment against the real Jev API, one question per call.

    op run --env-file=<(echo 'TYPESAFE_API_KEY="op://Personal/typesafe jev key/credential"') \
      -- uv run python experiments/branches/run.py --dry-run

Every call is a single `sif.decide` with one Choice question. Conditions A, B and D
run with the disk cache on; C and E run with it off, because the cache key sorts the
criteria keys (`sif/cache.py::_canonical` uses ``sort_keys=True``) and would serve a
shuffled or repeated question from the A answer instead of calling the API.

Results are keyed by call id and flushed to results.json as the run goes, so a second
run continues where the first stopped and retries anything recorded as an error.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dataset  # noqa: E402
import sif  # noqa: E402
from sif.log import DEFAULT_PATH as LOG_PATH  # noqa: E402
from typesafe_sdk import (  # noqa: E402
    TypeSafeAuthenticationError,
    TypeSafeBadRequestError,
    TypeSafeError,
    TypeSafeUnprocessableEntityError,
)

MODEL = "jev-1.13.0"
RESULTS = HERE / "results.json"

#: Hard stops from the brief: the whole experiment stays inside these.
MAX_CALLS = 2000
MAX_INPUT_TOKENS = 1_500_000
PRICE_PER_MTOK = 0.042

#: Token estimate, calibrated against real `usage.input_tokens` from live calls.
TOKEN_BASE = 250.0
TOKEN_PER_KOREAN_CHAR = 0.9
TOKEN_PER_OTHER_CHAR = 0.28

#: Errors that mean the request itself is wrong; retrying 1,600 times helps nobody.
FATAL = (TypeSafeAuthenticationError, TypeSafeBadRequestError, TypeSafeUnprocessableEntityError)


@dataclass(frozen=True)
class Task:
    """One API call: a message judged under one condition at one branch count."""

    call_id: str
    n: int
    condition: str
    variant: str
    sample: dataset.Sample
    seed: int | None
    cache_on: bool


def plan() -> list[Task]:
    """Every call, ordered so the cache setting flips twice per branch count."""
    tasks: list[Task] = []
    for n in dataset.N_VALUES:
        samples = dataset.samples_for(n)
        for condition in ("A", "B", "D"):
            for sample in samples:
                tasks.append(
                    Task(f"n{n:02d}|{condition}|0|{sample.id}", n, condition, "0", sample, None, True)
                )
        for seed in dataset.C_SEEDS:
            for sample in samples:
                tasks.append(
                    Task(f"n{n:02d}|C|s{seed}|{sample.id}", n, "C", f"s{seed}", sample, seed, False)
                )
        for repeat in range(1, dataset.E_REPEATS + 1):
            for sample in samples:
                tasks.append(
                    Task(f"n{n:02d}|E|r{repeat}|{sample.id}", n, "E", f"r{repeat}", sample, None, False)
                )
    return tasks


def _is_korean(char: str) -> bool:
    return "가" <= char <= "힣" or "ㄱ" <= char <= "ㆎ"


def estimate_tokens(text: str, criteria: dict[str, str | None]) -> float:
    """Rough input-token estimate for one call, used only by --dry-run."""
    payload = dataset.INSTRUCTIONS + text + json.dumps(criteria, ensure_ascii=False)
    korean = sum(1 for char in payload if _is_korean(char))
    return TOKEN_BASE + korean * TOKEN_PER_KOREAN_CHAR + (len(payload) - korean) * TOKEN_PER_OTHER_CHAR


# --------------------------------------------------------------------------- the log

def log_position() -> int:
    """Byte offset of the end of the sif call log."""
    path = Path(LOG_PATH)
    return path.stat().st_size if path.exists() else 0


def new_records(since: int) -> tuple[list[dict], int]:
    """Call-log records appended since byte offset `since` (sliced as bytes: Korean)."""
    path = Path(LOG_PATH)
    if not path.exists():
        return [], since
    raw = path.read_bytes()
    chunk = raw[since:].decode("utf-8", errors="replace")
    records = [json.loads(line) for line in chunk.splitlines() if line.strip()]
    return records, len(raw)


# ------------------------------------------------------------------------- results io

@dataclass
class Store:
    """results.json as a call_id -> record map, flushed atomically."""

    path: Path
    calls: dict[str, dict] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            body = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"warning: {self.path} is unreadable; starting over", file=sys.stderr)
            return
        self.meta = body.get("meta", {})
        for record in body.get("calls", []):
            self.calls[record["call_id"]] = record

    def done(self) -> set[str]:
        """Call ids already recorded without an error; errors are retried."""
        return {cid for cid, record in self.calls.items() if not record.get("error")}

    def flush(self, order: list[str]) -> None:
        ordered = [self.calls[cid] for cid in order if cid in self.calls]
        body = {"meta": self.meta, "calls": ordered}
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)


# ----------------------------------------------------------------------------- one call

def record_for(task: Task, decision, criteria, lookup, log: dict | None) -> dict:
    """Flatten one decision into the per-call row stored in results.json."""
    order = list(criteria)
    canonical = {lookup.get(label, label): value for label, value in decision.probabilities.items()}
    ranked = sorted(canonical.items(), key=lambda kv: -kv[1])
    top1, top1_p = ranked[0] if ranked else (None, 0.0)
    top2, top2_p = ranked[1] if len(ranked) > 1 else (None, 0.0)
    gold_prob = canonical.get(task.sample.gold, 0.0)
    gold_rank = next((i + 1 for i, (name, _) in enumerate(ranked) if name == task.sample.gold), None)
    choice = lookup.get(decision.choice, decision.choice)
    usage = (log or {}).get("usage") or {}
    return {
        "call_id": task.call_id,
        "n": task.n,
        "condition": task.condition,
        "variant": task.variant,
        "seed": task.seed,
        "sample_id": task.sample.id,
        "gold": task.sample.gold,
        "text": task.sample.text,
        "choice_label": decision.choice,
        "choice": choice,
        "correct": choice == task.sample.gold,
        "confidence": decision.confidence,
        "probabilities": canonical,
        "gold_prob": gold_prob,
        "gold_rank": gold_rank,
        "top1": top1,
        "top1_prob": top1_p,
        "top2": top2,
        "top2_prob": top2_p,
        "margin": top1_p - top2_p,
        "order": [lookup.get(label, label) for label in order],
        "gold_pos": next((i for i, label in enumerate(order) if lookup.get(label, label) == task.sample.gold), None),
        "choice_pos": next((i for i, label in enumerate(order) if label == decision.choice), None),
        "latency_ms": (log or {}).get("latency_ms"),
        "cached": (log or {}).get("cached"),
        "model_resolved": (log or {}).get("model_resolved"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "ts": time.time(),
        "error": None,
    }


# --------------------------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print the plan and call no API")
    parser.add_argument("--n", type=int, action="append", help="restrict to these branch counts")
    parser.add_argument("--condition", action="append", help="restrict to these conditions")
    parser.add_argument("--limit", type=int, help="stop after this many new calls")
    parser.add_argument("--fresh", action="store_true", help="ignore results.json and start over")
    args = parser.parse_args()

    tasks = plan()
    if args.n:
        tasks = [t for t in tasks if t.n in set(args.n)]
    if args.condition:
        wanted = {c.upper() for c in args.condition}
        tasks = [t for t in tasks if t.condition in wanted]

    full = plan()
    if args.dry_run:
        return dry_run(full)

    sif.configure(model=MODEL, cache=True, log=True)

    store = Store(RESULTS)
    if not args.fresh:
        store.load()
    order = [t.call_id for t in full]
    done = store.done()
    todo = [t for t in tasks if t.call_id not in done]
    if args.limit:
        todo = todo[: args.limit]

    total_estimate = sum(
        estimate_tokens(t.sample.text, dataset.build_options(t.n, t.condition, t.seed)[0]) for t in todo
    )
    print(f"plan: {len(full)} calls total, {len(done)} already done, {len(todo)} to run")
    print(f"estimated input tokens for this run: {total_estimate:,.0f}")
    if len(full) > MAX_CALLS:
        print(f"ABORT: {len(full)} calls over the {MAX_CALLS} cap", file=sys.stderr)
        return 1

    store.meta.setdefault("model", MODEL)
    store.meta.setdefault("instructions", dataset.INSTRUCTIONS)
    store.meta.setdefault("n_values", list(dataset.N_VALUES))
    store.meta.setdefault("planned_calls", len(full))
    store.meta.setdefault("started", time.time())
    store.meta["last_started"] = time.time()

    cache_on: bool | None = None
    started = time.perf_counter()
    errors = 0
    input_tokens = sum(r.get("input_tokens") or 0 for r in store.calls.values())
    output_tokens = sum(r.get("output_tokens") or 0 for r in store.calls.values())

    for index, task in enumerate(todo, start=1):
        if task.cache_on != cache_on:
            sif.configure(cache=task.cache_on)
            cache_on = task.cache_on
        criteria, lookup = dataset.build_options(task.n, task.condition, task.seed)
        cursor = log_position()
        try:
            decision = sif.decide(task.sample.text, criteria, dataset.INSTRUCTIONS)
        except TypeSafeError as error:
            records, _ = new_records(cursor)
            store.calls[task.call_id] = {
                "call_id": task.call_id,
                "n": task.n,
                "condition": task.condition,
                "variant": task.variant,
                "sample_id": task.sample.id,
                "gold": task.sample.gold,
                "ts": time.time(),
                "error": f"{type(error).__name__}: {error}",
            }
            errors += 1
            store.flush(order)
            if isinstance(error, FATAL) or type(error) is TypeSafeError:
                print(f"ABORT: {type(error).__name__}: {error}", file=sys.stderr)
                return 2
            print(f"  error on {task.call_id}: {type(error).__name__}", file=sys.stderr)
            continue
        records, _ = new_records(cursor)
        log = records[-1] if records else None
        row = record_for(task, decision, criteria, lookup, log)
        store.calls[task.call_id] = row
        input_tokens += row.get("input_tokens") or 0
        output_tokens += row.get("output_tokens") or 0

        if index % 20 == 0 or index == len(todo):
            store.flush(order)
        if index % 50 == 0 or index == len(todo):
            elapsed = time.perf_counter() - started
            rate = index / elapsed if elapsed else 0
            remaining = (len(todo) - index) / rate if rate else 0
            live = [r for r in store.calls.values() if r.get("correct") is not None]
            accuracy = sum(1 for r in live if r["correct"]) / len(live) if live else 0
            print(
                f"  {index}/{len(todo)}  acc={accuracy:.3f}  in_tok={input_tokens:,}  "
                f"errors={errors}  {elapsed:,.0f}s elapsed, ~{remaining:,.0f}s left",
                flush=True,
            )
        if input_tokens > MAX_INPUT_TOKENS:
            store.flush(order)
            print(f"ABORT: input tokens {input_tokens:,} over the {MAX_INPUT_TOKENS:,} cap", file=sys.stderr)
            return 3

    elapsed = time.perf_counter() - started
    store.meta["finished"] = time.time()
    store.meta["elapsed_s"] = round(store.meta.get("elapsed_s", 0.0) + elapsed, 3)
    store.meta["input_tokens"] = input_tokens
    store.meta["output_tokens"] = output_tokens
    store.meta["errors"] = sum(1 for r in store.calls.values() if r.get("error"))
    store.flush(order)

    latencies = [r["latency_ms"] for r in store.calls.values() if r.get("latency_ms") is not None]
    print(f"done: {len(store.calls)} records, {store.meta['errors']} errors, {elapsed:,.1f}s this run")
    print(f"input tokens {input_tokens:,}  output tokens {output_tokens:,}  "
          f"(${(input_tokens + output_tokens) * PRICE_PER_MTOK / 1e6:.4f} at ${PRICE_PER_MTOK}/Mtok)")
    if latencies:
        print(f"latency median {statistics.median(latencies):,.1f}ms")
    return 0


def dry_run(tasks: list[Task]) -> int:
    """Print the planned calls and the token estimate without touching the API."""
    print(f"model: {MODEL}   instructions: {dataset.INSTRUCTIONS!r}")
    print(f"messages per branch count: {dataset.sample_counts()}  (total {sum(dataset.sample_counts().values())})")
    print()
    header = f"{'N':>3}  {'samples':>7}  {'A':>4} {'B':>4} {'C':>4} {'D':>4} {'E':>4}  {'calls':>6}  {'est.in.tok':>11}"
    print(header)
    print("-" * len(header))
    total_calls = 0
    total_tokens = 0.0
    for n in dataset.N_VALUES:
        rows = [t for t in tasks if t.n == n]
        per = {c: sum(1 for t in rows if t.condition == c) for c in dataset.CONDITIONS}
        tokens = sum(
            estimate_tokens(t.sample.text, dataset.build_options(t.n, t.condition, t.seed)[0]) for t in rows
        )
        total_calls += len(rows)
        total_tokens += tokens
        print(
            f"{n:>3}  {len(dataset.samples_for(n)):>7}  {per['A']:>4} {per['B']:>4} {per['C']:>4} "
            f"{per['D']:>4} {per['E']:>4}  {len(rows):>6}  {tokens:>11,.0f}"
        )
    print("-" * len(header))
    print(f"{'':>3}  {'':>7}  {'':>4} {'':>4} {'':>4} {'':>4} {'':>4}  {total_calls:>6}  {total_tokens:>11,.0f}")
    print()
    print(f"total calls          : {total_calls}   (cap {MAX_CALLS})")
    print(f"estimated input tok  : {total_tokens:,.0f}   (cap {MAX_INPUT_TOKENS:,})")
    print(f"estimated cost       : ${total_tokens * PRICE_PER_MTOK / 1e6:.4f} at ${PRICE_PER_MTOK}/Mtok")
    print(f"cache on for A/B/D, off for C/E (the cache key sorts criteria keys, so shuffles collide)")
    over = total_calls > MAX_CALLS or total_tokens > MAX_INPUT_TOKENS
    print("OVER CAP - not running" if over else "within caps")
    print("dry run: no API call was made")
    return 1 if over else 0


if __name__ == "__main__":
    raise SystemExit(main())
