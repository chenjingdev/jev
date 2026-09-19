"""Run the two vision axes against the real Jev API, one Choice per call.

    uv run python experiments/vision/run.py --dry-run
    op run --env-file=<(echo 'TYPESAFE_API_KEY="op://Personal/typesafe jev key/credential"') \
      -- uv run python experiments/vision/run.py --axis encode --format names --limit 20

Same shape as experiments/limits: every call is one `sif.decide`, results are
keyed by call id and flushed to results.json as the run goes, so a stopped run
continues and recorded errors are retried. The cache is on: every call here
asks a distinct question once.
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

MAX_CALLS = 3000
MAX_INPUT_TOKENS = 3_000_000
PRICE_PER_MTOK = 0.042
TIMEOUT = 60.0

FATAL = (TypeSafeAuthenticationError, TypeSafeBadRequestError, TypeSafeUnprocessableEntityError)

AXES = ("encode", "grid", "pixel")


@dataclass(frozen=True)
class Task:
    """One API call."""

    call_id: str
    axis: str
    fmt: str
    question: str      # encode: pos | mode; pixel: digit
    sample_id: str
    gold: str
    state: dict
    criteria: dict[str, str | None]
    instructions: str
    size: int = 0
    palette: int = 0
    row: int = 0
    col: int = 0


# ---------------------------------------------------------------------- the plan


def plan() -> list[Task]:
    """Every planned call: the readable spellings first, base64 after, MNIST last."""
    tasks: list[Task] = []
    for fmt in dataset.ENCODE_FORMATS:
        for size in dataset.GRID_SIZES:
            for palette in dataset.PALETTE_SIZES:
                criteria = dataset.color_options(palette)
                for grid in dataset.make_grids(size, palette):
                    state = dataset.encode_state(grid, fmt)
                    for question in dataset.ENCODE_QUESTIONS:
                        tasks.append(Task(
                            call_id=f"enc|{fmt}|{question}|{grid.id}", axis="encode", fmt=fmt,
                            question=question, sample_id=grid.id,
                            gold=grid.target if question == "pos" else grid.mode,
                            state=state, criteria=criteria,
                            instructions=dataset.encode_instructions(grid, fmt, question),
                            size=size, palette=palette, row=grid.row, col=grid.col,
                        ))
    for cols, rows in dataset.GRID_SHAPES:
        for grid in dataset.make_feature_grids(cols, rows):
            for fmt in dataset.GRID_FORMATS:
                state = dataset.feature_state(grid, fmt)
                for question in dataset.GRID_QUESTIONS:
                    tasks.append(Task(
                        call_id=f"grid|{fmt}|{question}|{grid.id}", axis="grid", fmt=fmt,
                        question=question, sample_id=grid.id, gold=dataset.feature_gold(grid, question),
                        state=state, criteria=dataset.feature_criteria(grid, question),
                        instructions=dataset.feature_instructions(grid, fmt, question),
                        size=cols * 100 + rows, row=grid.row, col=grid.col,
                    ))
    digits = dataset.load_digits()
    for fmt in dataset.PIXEL_FORMATS:
        for digit in digits:
            tasks.append(Task(
                call_id=f"pix|{fmt}|{digit.id}", axis="pixel", fmt=fmt, question="digit",
                sample_id=digit.id, gold=str(digit.label),
                state=dataset.pixel_state(digit, fmt), criteria=dataset.DIGIT_OPTIONS,
                instructions=dataset.pixel_instructions(fmt), size=dataset.PIXEL_SIZE,
            ))
    return tasks


def estimate(task: Task) -> float:
    return dataset.estimate_tokens(task.state, task.criteria, task.instructions)


def dry_run(tasks: list[Task], cap: int) -> int:
    by_key: dict[tuple[str, str], list[Task]] = {}
    for t in tasks:
        by_key.setdefault((t.axis, t.fmt), []).append(t)
    total = 0.0
    print(f"{'axis':7} {'format':12} {'calls':>6} {'est tokens':>11} {'chars/state':>12}")
    for (axis, fmt), group in by_key.items():
        tokens = sum(estimate(t) for t in group)
        total += tokens
        chars = statistics.mean(len(json.dumps(t.state)) for t in group)
        print(f"{axis:7} {fmt:12} {len(group):6} {tokens:11,.0f} {chars:12,.0f}")
    print(f"{'total':7} {'':12} {len(tasks):6} {total:11,.0f}")
    print(f"~${total * PRICE_PER_MTOK / 1e6:.3f} input at ${PRICE_PER_MTOK}/Mtok; cap {cap:,}")
    sample = next(t for t in tasks if t.axis == "grid" and t.question == "find_col" and t.size == 3218)
    print("\nexample call:")
    print(" ", sample.instructions)
    print(" ", json.dumps(sample.state, ensure_ascii=False))
    print(" ", json.dumps(sample.criteria))
    print("  gold:", sample.gold)
    return 0


# --------------------------------------------------------------------------- the log


def log_position() -> int:
    path = Path(LOG_PATH)
    return path.stat().st_size if path.exists() else 0


def new_records(since: int) -> list[dict]:
    path = Path(LOG_PATH)
    if not path.exists():
        return []
    chunk = path.read_bytes()[since:].decode("utf-8", errors="replace")
    return [json.loads(line) for line in chunk.splitlines() if line.strip()]


# ------------------------------------------------------------------------- results io


@dataclass
class Store:
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
        return {cid for cid, record in self.calls.items() if not record.get("error")}

    def flush(self, order: list[str]) -> None:
        known = [self.calls[cid] for cid in order if cid in self.calls]
        rest = [r for cid, r in self.calls.items() if cid not in set(order)]
        body = {"meta": self.meta, "calls": known + rest}
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)


# ----------------------------------------------------------------------- one call


def record_for(task: Task, decision, log: dict | None) -> dict:
    ranked = sorted(decision.probabilities.items(), key=lambda kv: -kv[1])
    top1, top1_p = ranked[0] if ranked else (None, 0.0)
    top2_p = ranked[1][1] if len(ranked) > 1 else 0.0
    usage = (log or {}).get("usage") or {}
    return {
        "call_id": task.call_id,
        "axis": task.axis,
        "format": task.fmt,
        "question": task.question,
        "size": task.size,
        "palette": task.palette,
        "row": task.row,
        "col": task.col,
        "sample_id": task.sample_id,
        "gold": task.gold,
        "choice": decision.choice,
        "correct": decision.choice == task.gold,
        "confidence": decision.confidence,
        "probabilities": {k: v for k, v in decision.probabilities.items() if v > 0},
        "gold_prob": decision.probabilities.get(task.gold, 0.0),
        "gold_rank": next((i + 1 for i, (name, _) in enumerate(ranked) if name == task.gold), None),
        "top1": top1,
        "top1_prob": top1_p,
        "margin": top1_p - top2_p,
        "state_chars": len(json.dumps(task.state)),
        "latency_ms": (log or {}).get("latency_ms"),
        "cached": (log or {}).get("cached"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "ts": time.time(),
        "error": None,
    }


def error_row(task: Task, error: Exception) -> dict:
    body = getattr(error, "body", None)
    if body is not None and not isinstance(body, str):
        body = json.dumps(body, ensure_ascii=False)[:800]
    elif isinstance(body, str):
        body = body[:800]
    return {
        "call_id": task.call_id,
        "axis": task.axis,
        "format": task.fmt,
        "question": task.question,
        "size": task.size,
        "palette": task.palette,
        "sample_id": task.sample_id,
        "gold": task.gold,
        "status": getattr(error, "status", None),
        "body": body,
        "ts": time.time(),
        "error": f"{type(error).__name__}: {error}",
    }


# --------------------------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print the plan and call no API")
    parser.add_argument("--axis", action="append", choices=AXES, help="restrict to these axes")
    parser.add_argument("--format", action="append", help="restrict to these spellings")
    parser.add_argument("--question", action="append", help="restrict to pos / mode / digit")
    parser.add_argument("--limit", type=int, help="stop after this many new calls")
    parser.add_argument("--fresh", action="store_true", help="ignore results.json and start over")
    parser.add_argument("--max-input-tokens", type=int, default=MAX_INPUT_TOKENS)
    args = parser.parse_args()

    problems = dataset.validate()
    if problems:
        for problem in problems:
            print(f"dataset: {problem}", file=sys.stderr)
        return 1

    full = plan()
    if len(full) > MAX_CALLS:
        print(f"ABORT: {len(full)} calls over the {MAX_CALLS} cap", file=sys.stderr)
        return 1
    if args.dry_run:
        return dry_run(full, args.max_input_tokens)

    tasks = full
    if args.axis:
        tasks = [t for t in tasks if t.axis in set(args.axis)]
    if args.format:
        tasks = [t for t in tasks if t.fmt in set(args.format)]
    if args.question:
        tasks = [t for t in tasks if t.question in set(args.question)]

    sif.configure(model=MODEL, cache=True, log=True, timeout=TIMEOUT)

    store = Store(RESULTS)
    if not args.fresh:
        store.load()
    order = [t.call_id for t in full]
    done = store.done()
    todo = [t for t in tasks if t.call_id not in done]
    if args.limit:
        todo = todo[: args.limit]

    print(f"plan: {len(full)} calls total, {len(done)} already done, {len(todo)} to run")
    print(f"estimated input tokens for this run: {sum(estimate(t) for t in todo):,.0f}")

    store.meta.setdefault("model", MODEL)
    store.meta.setdefault("planned_calls", len(full))
    store.meta.setdefault("started", time.time())
    store.meta["last_started"] = time.time()

    started = time.perf_counter()
    errors = 0
    input_tokens = sum(r.get("input_tokens") or 0 for r in store.calls.values())
    for index, task in enumerate(todo, 1):
        cursor = log_position()
        try:
            decision = sif.decide(task.state, task.criteria, task.instructions)
        except TypeSafeError as error:
            row = error_row(task, error)
            store.calls[task.call_id] = row
            errors += 1
            store.flush(order)
            print(
                f"  error on {task.call_id}: {type(error).__name__} "
                f"status={row.get('status')} {row.get('body')}",
                file=sys.stderr,
            )
            if isinstance(error, FATAL) or type(error) is TypeSafeError:
                print(f"ABORT: {type(error).__name__}: {error}", file=sys.stderr)
                return 2
            continue

        records = new_records(cursor)
        row = record_for(task, decision, records[-1] if records else None)
        store.calls[task.call_id] = row
        input_tokens += row.get("input_tokens") or 0

        last = index == len(todo)
        if index % 20 == 0 or last:
            store.flush(order)
        if index % 50 == 0 or last:
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
        if input_tokens > args.max_input_tokens:
            store.flush(order)
            print(f"ABORT: input tokens {input_tokens:,} over the cap", file=sys.stderr)
            return 3

    elapsed = time.perf_counter() - started
    store.meta["finished"] = time.time()
    store.meta["elapsed_s"] = round(store.meta.get("elapsed_s", 0.0) + elapsed, 3)
    store.meta["input_tokens"] = sum(r.get("input_tokens") or 0 for r in store.calls.values())
    store.meta["output_tokens"] = sum(r.get("output_tokens") or 0 for r in store.calls.values())
    store.meta["errors"] = sum(1 for r in store.calls.values() if r.get("error"))
    store.flush(order)

    total = store.meta["input_tokens"] + store.meta["output_tokens"]
    print(f"done: {len(store.calls)} records, {store.meta['errors']} errors, {elapsed:,.1f}s this run")
    print(
        f"input tokens {store.meta['input_tokens']:,}  output tokens {store.meta['output_tokens']:,}  "
        f"(${total * PRICE_PER_MTOK / 1e6:.4f} at ${PRICE_PER_MTOK}/Mtok)"
    )
    latencies = [r["latency_ms"] for r in store.calls.values() if r.get("latency_ms") is not None]
    if latencies:
        print(f"latency median {statistics.median(latencies):,.1f}ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
