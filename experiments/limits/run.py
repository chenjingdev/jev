"""Run the five limit axes against the real Jev API, one question per call.

    op run --env-file=<(echo 'TYPESAFE_API_KEY="op://Personal/typesafe jev key/credential"') \
      -- uv run python experiments/limits/run.py --dry-run

Every call is a single `sif.decide` with one Choice question, like the branch
experiment. The disk cache is on everywhere except axis 3, which repeats the
same question three times to measure flips: `sif/cache.py::_canonical` sorts the
criteria keys, so a cached repeat would replay the first answer instead of
asking again.

Results are keyed by call id and flushed to results.json as the run goes, so a
second run continues where the first stopped and retries anything recorded as an
error.
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
    TypeSafeAPIError,
    TypeSafeAuthenticationError,
    TypeSafeBadRequestError,
    TypeSafeError,
    TypeSafeUnprocessableEntityError,
)

MODEL = "jev-1.13.0"
RESULTS = HERE / "results.json"

#: Hard stops from the brief: the whole experiment stays inside these.
#: The input cap was raised from 4.5M to 5.5M after the dry run priced the five
#: axes at 5.16M; nothing in the plan was trimmed.
MAX_CALLS = 1500
MAX_INPUT_TOKENS = 5_500_000
PRICE_PER_MTOK = 0.042

#: A 24k-token state takes longer than the SDK's 10s default.
TIMEOUT = 120.0

#: Errors that mean the request itself is wrong, not that the API hiccuped.
FATAL = (TypeSafeAuthenticationError, TypeSafeBadRequestError, TypeSafeUnprocessableEntityError)

#: Statuses that mean "this request was too big", handled per axis instead of aborting.
TOO_BIG = (400, 413, 422)

AXES = ("width", "neighbors", "ambiguous", "traps", "length")


@dataclass(frozen=True)
class Task:
    """One API call."""

    call_id: str
    axis: str
    condition: str
    sample_id: str
    gold: str
    text: str
    n: int
    cache_on: bool
    tier: int | None = None
    position: str | None = None
    repeat: int | None = None
    family: str | None = None
    index: int = 0

    @property
    def instructions(self) -> str:
        return dataset.LONG_INSTRUCTIONS if self.axis == "length" else dataset.INSTRUCTIONS

    def criteria(self) -> dict[str, str | None]:
        if self.axis == "neighbors" and self.condition == "fam":
            members = dict(dataset.NEIGHBOR_FAMILIES)[self.family or ""]
            return dataset.family_options(members)
        return dataset.options_for(self.n)

    def state(self) -> str:
        if self.axis != "length":
            return self.text
        assert self.tier is not None and self.position is not None
        return dataset.long_state(self.index, self.text, self.tier, self.position)


# ---------------------------------------------------------------------- the plan


def plan() -> list[Task]:
    """Every planned call, cheapest axis first and the long states last."""
    top_tier = dataset.LENGTH_TIERS[-1]
    tasks: list[Task] = []

    # axis 1: width
    for n in dataset.N_VALUES:
        for sample in dataset.width_samples(n):
            tasks.append(Task(
                call_id=f"w|n{n:03d}|{sample.id}", axis="width", condition=f"n{n}",
                sample_id=sample.id, gold=sample.gold, text=sample.text, n=n, cache_on=True,
            ))

    # axis 2: neighbours, four siblings and then all eighty
    for family, sample in dataset.neighbor_samples():
        tasks.append(Task(
            call_id=f"nb|fam|{sample.id}", axis="neighbors", condition="fam",
            sample_id=sample.id, gold=sample.gold, text=sample.text, n=4, cache_on=True,
            family=family,
        ))
    for family, sample in dataset.neighbor_samples():
        tasks.append(Task(
            call_id=f"nb|all80|{sample.id}", axis="neighbors", condition="all80",
            sample_id=sample.id, gold=sample.gold, text=sample.text,
            n=dataset.REAL_CATEGORIES, cache_on=True, family=family,
        ))

    # axis 3: ambiguous, three repeats with the cache off
    for repeat in range(1, dataset.AMBIGUOUS_REPEATS + 1):
        for item in dataset.AMBIGUOUS:
            tasks.append(Task(
                call_id=f"amb|r{repeat}|{item.id}", axis="ambiguous", condition=f"r{repeat}",
                sample_id=item.id, gold="", text=item.text, n=20, cache_on=False, repeat=repeat,
            ))

    # axis 5: traps against twenty and against eighty
    for trap in dataset.TRAPS:
        tasks.append(Task(
            call_id=f"tr|n20|{trap.id}", axis="traps", condition="n20",
            sample_id=trap.id, gold=trap.gold, text=trap.text, n=20, cache_on=True,
        ))
    for trap in dataset.TRAPS:
        tasks.append(Task(
            call_id=f"tr|n80|{trap.id}", axis="traps", condition="n80",
            sample_id=trap.id, gold=trap.gold, text=trap.text,
            n=dataset.REAL_CATEGORIES, cache_on=True,
        ))

    # axis 4: one inquiry buried in filler
    samples = dataset.long_samples()
    for tier in dataset.LENGTH_TIERS:
        real = top_tier if tier == dataset.LENGTH_TIERS[-1] else tier
        for index, sample in enumerate(samples):
            tasks.append(Task(
                call_id=f"len|t{real}|middle|{sample.id}", axis="length", condition=f"t{real}",
                sample_id=sample.id, gold=sample.gold, text=sample.text, n=20, cache_on=True,
                tier=real, position="middle", index=index,
            ))
    for position in ("front", "end"):
        for index, sample in enumerate(samples):
            tasks.append(Task(
                call_id=f"len|t{top_tier}|{position}|{sample.id}", axis="length",
                condition=f"t{top_tier}", sample_id=sample.id, gold=sample.gold,
                text=sample.text, n=20, cache_on=True, tier=top_tier, position=position,
                index=index,
            ))
    return tasks


def probe_task(n: int) -> Task:
    """One cheap call used to bisect the largest option count the API accepts."""
    sample = dataset.width_samples(20)[0]
    return Task(
        call_id=f"probe|n{n:03d}", axis="probe", condition=f"n{n}", sample_id="probe",
        gold=sample.gold, text=sample.text, n=n, cache_on=False,
    )


def estimate(task: Task) -> float:
    """Estimated input tokens for one task."""
    return dataset.estimate_tokens(task.state(), task.criteria(), task.instructions)


# --------------------------------------------------------------------------- the log


def log_position() -> int:
    """Byte offset of the end of the sif call log."""
    path = Path(LOG_PATH)
    return path.stat().st_size if path.exists() else 0


def new_records(since: int) -> list[dict]:
    """Call-log records appended since byte offset `since`."""
    path = Path(LOG_PATH)
    if not path.exists():
        return []
    raw = path.read_bytes()
    chunk = raw[since:].decode("utf-8", errors="replace")
    return [json.loads(line) for line in chunk.splitlines() if line.strip()]


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
        known = [self.calls[cid] for cid in order if cid in self.calls]
        rest = [r for cid, r in self.calls.items() if cid not in set(order)]
        body = {"meta": self.meta, "calls": known + rest}
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)


# ----------------------------------------------------------------------- one call


def record_for(task: Task, decision, state: str, log: dict | None) -> dict:
    """Flatten one decision into the row stored in results.json.

    Zero probabilities are dropped: the API rounds to two decimals, so at N=255
    keeping them would be 255 zeros per call and nothing more.
    """
    probabilities = {name: value for name, value in decision.probabilities.items() if value > 0}
    ranked = sorted(decision.probabilities.items(), key=lambda kv: -kv[1])
    top3 = [[name, value] for name, value in ranked[:3]]
    top1, top1_p = ranked[0] if ranked else (None, 0.0)
    top2, top2_p = ranked[1] if len(ranked) > 1 else (None, 0.0)
    gold_prob = decision.probabilities.get(task.gold, 0.0) if task.gold else None
    gold_rank = (
        next((i + 1 for i, (name, _) in enumerate(ranked) if name == task.gold), None)
        if task.gold else None
    )
    usage = (log or {}).get("usage") or {}
    return {
        "call_id": task.call_id,
        "axis": task.axis,
        "condition": task.condition,
        "n": task.n,
        "tier": task.tier,
        "position": task.position,
        "repeat": task.repeat,
        "family": task.family,
        "sample_id": task.sample_id,
        "gold": task.gold or None,
        "text": task.text,
        "choice": decision.choice,
        "correct": (decision.choice == task.gold) if task.gold else None,
        "confidence": decision.confidence,
        "probabilities": probabilities,
        "top3": top3,
        "gold_prob": gold_prob,
        "gold_rank": gold_rank,
        "top1": top1,
        "top1_prob": top1_p,
        "top2": top2,
        "top2_prob": top2_p,
        "margin": top1_p - top2_p,
        "state_chars": len(state),
        "est_input_tokens": round(dataset.estimate_tokens(state, task.criteria(), task.instructions), 1),
        "latency_ms": (log or {}).get("latency_ms"),
        "cached": (log or {}).get("cached"),
        "model_resolved": (log or {}).get("model_resolved"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "ts": time.time(),
        "error": None,
    }


def error_row(task: Task, error: Exception, state_chars: int) -> dict:
    """The row stored when a call fails; keeps the status code and body."""
    status = getattr(error, "status", None)
    body = getattr(error, "body", None)
    if body is not None and not isinstance(body, str):
        body = json.dumps(body, ensure_ascii=False)[:800]
    elif isinstance(body, str):
        body = body[:800]
    return {
        "call_id": task.call_id,
        "axis": task.axis,
        "condition": task.condition,
        "n": task.n,
        "tier": task.tier,
        "position": task.position,
        "sample_id": task.sample_id,
        "gold": task.gold or None,
        "state_chars": state_chars,
        "status": status,
        "body": body,
        "ts": time.time(),
        "error": f"{type(error).__name__}: {error}",
    }


def too_big(error: Exception) -> bool:
    """True when the API refused the request for its size."""
    return isinstance(error, TypeSafeAPIError) and getattr(error, "status", None) in TOO_BIG


# --------------------------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print the plan and call no API")
    parser.add_argument("--axis", action="append", help="restrict to these axes")
    parser.add_argument("--n", type=int, action="append", help="restrict axis 1 to these branch counts")
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
    if args.dry_run:
        return dry_run(full, args.max_input_tokens)

    tasks = full
    if args.axis:
        wanted = {a.lower() for a in args.axis}
        tasks = [t for t in tasks if t.axis in wanted]
    if args.n:
        keep = set(args.n)
        tasks = [t for t in tasks if t.axis != "width" or t.n in keep]

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
    if len(full) > MAX_CALLS:
        print(f"ABORT: {len(full)} calls over the {MAX_CALLS} cap", file=sys.stderr)
        return 1

    store.meta.setdefault("model", MODEL)
    store.meta.setdefault("instructions", dataset.INSTRUCTIONS)
    store.meta.setdefault("long_instructions", dataset.LONG_INSTRUCTIONS)
    store.meta.setdefault("n_values", list(dataset.N_VALUES))
    store.meta.setdefault("length_tiers", list(dataset.LENGTH_TIERS))
    store.meta.setdefault("planned_calls", len(full))
    store.meta.setdefault("started", time.time())
    store.meta["last_started"] = time.time()

    cache_on: bool | None = None
    started = time.perf_counter()
    errors = 0
    input_tokens = sum(r.get("input_tokens") or 0 for r in store.calls.values())
    output_tokens = sum(r.get("output_tokens") or 0 for r in store.calls.values())
    #: Option counts and length tiers the API refused; the rest of that tier is skipped.
    refused_n: set[int] = set()
    refused_tier: set[int] = set()
    pending: list[Task] = list(todo)
    index = 0

    while pending:
        task = pending.pop(0)
        if task.axis == "width" and task.n in refused_n:
            continue
        if task.axis == "length" and task.tier in refused_tier:
            continue
        index += 1
        if task.cache_on != cache_on:
            sif.configure(cache=task.cache_on)
            cache_on = task.cache_on
        state = task.state()
        cursor = log_position()
        try:
            decision = sif.decide(state, task.criteria(), task.instructions)
        except TypeSafeError as error:
            row = error_row(task, error, len(state))
            store.calls[task.call_id] = row
            errors += 1
            store.flush(order)
            print(
                f"  error on {task.call_id}: {type(error).__name__} "
                f"status={row.get('status')} {row.get('body')}",
                file=sys.stderr,
            )
            if too_big(error):
                if task.axis == "width":
                    refused_n.add(task.n)
                    pending = [t for t in pending if not (t.axis == "width" and t.n == task.n)]
                    print(f"  N={task.n} refused; bisecting the ceiling", file=sys.stderr)
                    bisect_ceiling(store, order, task.n, refused_n)
                    continue
                if task.axis == "length":
                    refused_tier.add(task.tier or 0)
                    fallback = dataset.LENGTH_FALLBACK_TIER
                    retried = [t for t in pending if t.axis == "length" and t.tier == task.tier]
                    pending = [t for t in pending if not (t.axis == "length" and t.tier == task.tier)]
                    for old in [task] + retried:
                        pending.append(Task(
                            call_id=f"len|t{fallback}|{old.position}|{old.sample_id}",
                            axis="length", condition=f"t{fallback}", sample_id=old.sample_id,
                            gold=old.gold, text=old.text, n=old.n, cache_on=True,
                            tier=fallback, position=old.position, index=old.index,
                        ))
                    print(f"  tier {task.tier} refused; falling back to {fallback}", file=sys.stderr)
                    continue
            if isinstance(error, FATAL) or type(error) is TypeSafeError:
                print(f"ABORT: {type(error).__name__}: {error}", file=sys.stderr)
                return 2
            continue

        records = new_records(cursor)
        row = record_for(task, decision, state, records[-1] if records else None)
        store.calls[task.call_id] = row
        input_tokens += row.get("input_tokens") or 0
        output_tokens += row.get("output_tokens") or 0

        if index % 20 == 0 or not pending:
            store.flush(order)
        if index % 50 == 0 or not pending:
            elapsed = time.perf_counter() - started
            rate = index / elapsed if elapsed else 0
            remaining = len(pending) / rate if rate else 0
            live = [r for r in store.calls.values() if r.get("correct") is not None]
            accuracy = sum(1 for r in live if r["correct"]) / len(live) if live else 0
            print(
                f"  {index}/{index + len(pending)}  acc={accuracy:.3f}  in_tok={input_tokens:,}  "
                f"errors={errors}  {elapsed:,.0f}s elapsed, ~{remaining:,.0f}s left",
                flush=True,
            )
        if input_tokens > args.max_input_tokens:
            store.flush(order)
            print(
                f"ABORT: input tokens {input_tokens:,} over the {args.max_input_tokens:,} cap",
                file=sys.stderr,
            )
            return 3

    elapsed = time.perf_counter() - started
    store.meta["finished"] = time.time()
    store.meta["elapsed_s"] = round(store.meta.get("elapsed_s", 0.0) + elapsed, 3)
    store.meta["input_tokens"] = sum(r.get("input_tokens") or 0 for r in store.calls.values())
    store.meta["output_tokens"] = sum(r.get("output_tokens") or 0 for r in store.calls.values())
    store.meta["errors"] = sum(1 for r in store.calls.values() if r.get("error"))
    store.flush(order)

    latencies = [r["latency_ms"] for r in store.calls.values() if r.get("latency_ms") is not None]
    print(f"done: {len(store.calls)} records, {store.meta['errors']} errors, {elapsed:,.1f}s this run")
    total = store.meta["input_tokens"] + store.meta["output_tokens"]
    print(
        f"input tokens {store.meta['input_tokens']:,}  output tokens {store.meta['output_tokens']:,}  "
        f"(${total * PRICE_PER_MTOK / 1e6:.4f} at ${PRICE_PER_MTOK}/Mtok)"
    )
    if latencies:
        print(f"latency median {statistics.median(latencies):,.1f}ms")
    return 0


def bisect_ceiling(store: Store, order: list[str], refused: int, refused_n: set[int]) -> None:
    """Find the largest option count the API still accepts, 2-3 extra calls."""
    accepted = max(
        [r["n"] for r in store.calls.values()
         if r.get("axis") in ("width", "probe") and not r.get("error") and r.get("n")],
        default=2,
    )
    low, high = accepted, refused
    probes = 0
    while high - low > 1 and probes < 3:
        mid = (low + high) // 2
        task = probe_task(mid)
        probes += 1
        cursor = log_position()
        try:
            decision = sif.decide(task.text, task.criteria(), task.instructions)
        except TypeSafeError as error:
            store.calls[task.call_id] = error_row(task, error, len(task.text))
            high = mid
            print(f"  probe N={mid}: refused ({getattr(error, 'status', None)})", file=sys.stderr)
        else:
            records = new_records(cursor)
            store.calls[task.call_id] = record_for(
                task, decision, task.text, records[-1] if records else None
            )
            low = mid
            print(f"  probe N={mid}: accepted", file=sys.stderr)
        store.flush(order)
    store.meta["max_options_accepted"] = low
    store.meta["min_options_refused"] = high
    print(f"  option ceiling: accepted {low}, refused {high}", file=sys.stderr)
    store.flush(order)


def dry_run(tasks: list[Task], cap: int) -> int:
    """Print the planned calls and the token estimate without touching the API."""
    print(f"model: {MODEL}")
    print(f"instructions: {dataset.INSTRUCTIONS!r}")
    print(f"axis 4 instructions: {dataset.LONG_INSTRUCTIONS!r}")
    print(f"options: {len(dataset.CATEGORIES)} answerable + {len(dataset.DISTRACTORS)} distractors "
          f"= {len(dataset.ALL_CATEGORIES)}")
    print()
    groups: dict[tuple[str, str], list[Task]] = {}
    for task in tasks:
        groups.setdefault((task.axis, task.condition), []).append(task)

    header = f"{'axis':<10} {'condition':<12} {'opts':>5} {'calls':>6} {'est.in.tok':>12} {'per call':>9}"
    print(header)
    print("-" * len(header))
    total_calls = 0
    total_tokens = 0.0
    per_axis: dict[str, list[float]] = {}
    for axis in AXES:
        for (task_axis, condition), rows in groups.items():
            if task_axis != axis:
                continue
            tokens = sum(estimate(t) for t in rows)
            total_calls += len(rows)
            total_tokens += tokens
            per_axis.setdefault(axis, [0.0, 0.0])
            per_axis[axis][0] += len(rows)
            per_axis[axis][1] += tokens
            print(
                f"{axis:<10} {condition:<12} {rows[0].n:>5} {len(rows):>6} "
                f"{tokens:>12,.0f} {tokens / len(rows):>9,.0f}"
            )
    print("-" * len(header))
    for axis, (calls, tokens) in per_axis.items():
        print(f"{axis:<10} {'TOTAL':<12} {'':>5} {calls:>6.0f} {tokens:>12,.0f}")
    print("-" * len(header))
    print(f"{'ALL':<10} {'':<12} {'':>5} {total_calls:>6} {total_tokens:>12,.0f}")
    print()
    print(f"total calls          : {total_calls}   (cap {MAX_CALLS})")
    print(f"estimated input tok  : {total_tokens:,.0f}   (cap {cap:,})")
    print(f"estimated cost       : ${total_tokens * PRICE_PER_MTOK / 1e6:.4f} at ${PRICE_PER_MTOK}/Mtok input")
    print("cache: on everywhere except axis 3 (repeats) and the option-ceiling probes")
    over = total_calls > MAX_CALLS or total_tokens > cap
    print("OVER CAP - not running" if over else "within caps")
    print("dry run: no API call was made")
    return 1 if over else 0


if __name__ == "__main__":
    raise SystemExit(main())
