"""Three-way checkmate Choice: checkmate, not checkmate, or unknown."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import random
import threading
import time

from typesafe_sdk import Choice, TypeSafeClient

import checkmate
import checkmate_prompt


HERE = Path(__file__).resolve().parent
MODEL = os.environ.get("JEV_MODEL", "jev-1.13.0")
USD_PER_TOKEN = 42 / 1e9
LOCAL = threading.local()
CONDITIONS = ("base", "repeat", "shuffle")


def client():
    if not hasattr(LOCAL, "client"):
        LOCAL.client = TypeSafeClient()
    return LOCAL.client


def criteria_for(side, condition, index):
    items = [
        ("checkmate", f"{side}'s king is in check and {side} has zero legal moves that escape check."),
        ("not_checkmate", f"{side}'s king is not in check, or {side} has at least one legal move that escapes check."),
        ("unknown", "I cannot reliably determine checkmate from the supplied position."),
    ]
    if condition == "shuffle":
        random.Random(73000 + index).shuffle(items)
    return dict(items)


def ask(case, condition="base"):
    if condition not in CONDITIONS:
        raise ValueError("Unknown condition")
    state, side = checkmate_prompt.explicit_state(case, "fen")
    instructions = (
        f"{side} is the side to move. Using the standard FEN in `fen` and standard chess rules, "
        f"classify {side}'s current status as checkmate, not checkmate, or unknown."
    )
    criteria = criteria_for(side, condition, case["index"])
    started = time.perf_counter()
    response = client().system_one(
        model=MODEL,
        state=state,
        questions={"status": Choice(instructions=instructions, criteria=criteria)},
    )
    answer = response.answers["status"]
    expected_choice = "checkmate" if case["expected"] else "not_checkmate"
    usage = response.usage
    return {
        **case,
        "condition": condition,
        "expected_choice": expected_choice,
        "pick": answer.choice,
        "hit": answer.choice == expected_choice,
        "probabilities": dict(answer.probabilities),
        "confidence": answer.confidence,
        "latency_ms": round(1000 * (time.perf_counter() - started)),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "request": {
            "model": MODEL,
            "state": state,
            "questions": {
                "status": {"type": "choice", "instructions": instructions, "criteria": criteria}
            },
        },
    }


def summarize(rows):
    positives = [row for row in rows if row["expected"]]
    negatives = [row for row in rows if not row["expected"]]
    return {
        "hit": sum(row["hit"] for row in rows),
        "n": len(rows),
        "mate_picks": {choice: sum(row["pick"] == choice for row in positives) for choice in ("checkmate", "not_checkmate", "unknown")},
        "check_only_picks": {choice: sum(row["pick"] == choice for row in negatives) for choice in ("checkmate", "not_checkmate", "unknown")},
        "mate_mean_probabilities": {
            choice: round(sum(row["probabilities"][choice] for row in positives) / len(positives), 4)
            for choice in ("checkmate", "not_checkmate", "unknown")
        },
        "check_only_mean_probabilities": {
            choice: round(sum(row["probabilities"][choice] for row in negatives) / len(negatives), 4)
            for choice in ("checkmate", "not_checkmate", "unknown")
        },
    }


def main():
    jobs = [(case, condition) for case in checkmate.cases() for condition in CONDITIONS]
    random.Random(92028).shuffle(jobs)
    trials = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(ask, *job) for job in jobs]
        for future in as_completed(futures):
            trials.append(future.result())
            if len(trials) % 40 == 0:
                print(f"{len(trials)}/{len(jobs)} complete", flush=True)
    summary = {condition: summarize([row for row in trials if row["condition"] == condition]) for condition in CONDITIONS}
    summary["all"] = summarize(trials)
    result = {
        "model": MODEL,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "design": "Same 40 matched FEN positions; explicit side to move; three-way Choice with checkmate, not_checkmate, and unknown; repeat and option-order permutation.",
        "summary": summary,
        "trials": sorted(trials, key=lambda row: (row["condition"], row["index"], row["kind"])),
        "cost_usd": round(sum(row["input_tokens"] + row["output_tokens"] for row in trials) * USD_PER_TOKEN, 4),
    }
    (HERE / "results_checkmate_three_way.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(json.dumps({"summary": summary, "cost_usd": result["cost_usd"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
