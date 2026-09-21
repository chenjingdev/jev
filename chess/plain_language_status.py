"""Test the same terminal chess states without using checkmate terminology."""
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
QUESTION_NAMES = ("danger", "escape")


def client():
    if not hasattr(LOCAL, "client"):
        LOCAL.client = TypeSafeClient()
    return LOCAL.client


def question_specs(side, condition, index):
    danger = [
        ("immediate_loss", f"The game has ended now: {side}'s king is attacked and no legal move can make it safe."),
        ("can_continue", f"The game has not ended: {side} has at least one legal move that leaves its king safe."),
        ("unknown", "I cannot reliably determine the result from the supplied position."),
    ]
    escape = [
        ("no_escape", f"{side}'s king is attacked, and no legal move can make it safe."),
        ("has_escape", f"{side} has at least one legal move after which its king is safe."),
        ("unknown", "I cannot reliably determine whether a legal escape exists from the supplied position."),
    ]
    if condition == "shuffle":
        random.Random(81000 + index).shuffle(danger)
        random.Random(82000 + index).shuffle(escape)
    return {
        "danger": Choice(
            instructions=(
                f"{side} is the side to move. Using the standard FEN in `fen` and standard chess rules, "
                f"classify whether {side} has already lost immediately, can continue safely, or cannot be determined."
            ),
            criteria=dict(danger),
        ),
        "escape": Choice(
            instructions=(
                f"{side} is the side to move. Using the standard FEN in `fen` and standard chess rules, "
                f"classify whether {side} has any legal move that makes its king safe."
            ),
            criteria=dict(escape),
        ),
    }


def expected_for(case):
    if case["expected"]:
        return {"danger": "immediate_loss", "escape": "no_escape"}
    return {"danger": "can_continue", "escape": "has_escape"}


def ask(case, condition="base"):
    if condition not in CONDITIONS:
        raise ValueError("Unknown condition")
    state, side = checkmate_prompt.explicit_state(case, "fen")
    questions = question_specs(side, condition, case["index"])
    started = time.perf_counter()
    response = client().system_one(model=MODEL, state=state, questions=questions)
    expected = expected_for(case)
    answers = {}
    for name in QUESTION_NAMES:
        answer = response.answers[name]
        answers[name] = {
            "expected": expected[name],
            "pick": answer.choice,
            "hit": answer.choice == expected[name],
            "probabilities": dict(answer.probabilities),
            "confidence": answer.confidence,
        }
    usage = response.usage
    request_questions = {
        name: {
            "type": "choice",
            "instructions": questions[name].instructions,
            "criteria": dict(questions[name].criteria),
        }
        for name in QUESTION_NAMES
    }
    return {
        **case,
        "condition": condition,
        "answers": answers,
        "latency_ms": round(1000 * (time.perf_counter() - started)),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "request": {"model": MODEL, "state": state, "questions": request_questions},
    }


def summarize(rows, name):
    positives = [row for row in rows if row["expected"]]
    negatives = [row for row in rows if not row["expected"]]
    choices = ("immediate_loss", "can_continue", "unknown") if name == "danger" else ("no_escape", "has_escape", "unknown")
    return {
        "hit": sum(row["answers"][name]["hit"] for row in rows),
        "n": len(rows),
        "terminal_picks": {choice: sum(row["answers"][name]["pick"] == choice for row in positives) for choice in choices},
        "escapable_picks": {choice: sum(row["answers"][name]["pick"] == choice for row in negatives) for choice in choices},
        "terminal_mean_probabilities": {
            choice: round(sum(row["answers"][name]["probabilities"][choice] for row in positives) / len(positives), 4)
            for choice in choices
        },
        "escapable_mean_probabilities": {
            choice: round(sum(row["answers"][name]["probabilities"][choice] for row in negatives) / len(negatives), 4)
            for choice in choices
        },
    }


def main():
    jobs = [(case, condition) for case in checkmate.cases() for condition in CONDITIONS]
    random.Random(92029).shuffle(jobs)
    trials = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(ask, *job) for job in jobs]
        for future in as_completed(futures):
            trials.append(future.result())
            if len(trials) % 40 == 0:
                print(f"{len(trials)}/{len(jobs)} complete", flush=True)
    summary = {}
    for name in QUESTION_NAMES:
        for condition in CONDITIONS:
            summary[f"{name}/{condition}"] = summarize([row for row in trials if row["condition"] == condition], name)
        summary[f"{name}/all"] = summarize(trials, name)
    result = {
        "model": MODEL,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "design": "Same 40 matched FEN positions; two jargon-free three-way Choice questions; repeat and option-order permutation; two independent questions per request.",
        "summary": summary,
        "trials": sorted(trials, key=lambda row: (row["condition"], row["index"], row["kind"])),
        "cost_usd": round(sum(row["input_tokens"] + row["output_tokens"] for row in trials) * USD_PER_TOKEN, 4),
    }
    (HERE / "results_plain_language_status.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(json.dumps({"summary": summary, "cost_usd": result["cost_usd"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
