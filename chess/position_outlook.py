"""Coarse chess outlook: danger, neutral, or advantage."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import random
import threading
import time

import chess
from typesafe_sdk import Choice, Score, TypeSafeClient

import probe


HERE = Path(__file__).resolve().parent
MODEL = os.environ.get("JEV_MODEL", "jev-1.13.0")
USD_PER_TOKEN = 42 / 1e9
LOCAL = threading.local()
CONDITIONS = ("base", "repeat", "shuffle")
LEVELS = (
    "Danger: the side to move is already lost, faces an immediate decisive loss, or has no safe continuation.",
    "Neutral: the position is roughly balanced and neither side has a clear immediate decisive advantage.",
    "Advantage: the side to move has a clear tactical or material advantage and strong winning chances.",
)


def client():
    if not hasattr(LOCAL, "client"):
        LOCAL.client = TypeSafeClient()
    return LOCAL.client


def cases():
    """Matched extremes: mate-in-one side to move, then the mated opponent."""
    result = []
    for index, row in enumerate(probe.positions(), 1):
        parent = probe.validate_position(row)
        result.append({
            "index": index,
            "puzzle_id": row["puzzle_id"],
            "kind": "advantage",
            "expected": "advantage",
            "fen": parent.fen(),
        })
        child = parent.copy()
        child.push(chess.Move.from_uci(row["mate"]))
        if not child.is_checkmate():
            raise ValueError(f"Expected terminal child: {row['puzzle_id']}")
        result.append({
            "index": index,
            "puzzle_id": row["puzzle_id"],
            "kind": "danger",
            "expected": "danger",
            "fen": child.fen(),
        })
    return result


def choice_criteria(condition, index):
    items = [
        ("danger", LEVELS[0]),
        ("neutral", LEVELS[1]),
        ("advantage", LEVELS[2]),
    ]
    if condition == "shuffle":
        random.Random(85000 + index).shuffle(items)
    return dict(items)


def state_for(case):
    board = chess.Board(case["fen"])
    side = "White" if board.turn else "Black"
    return (
        f"This is a chess game. {side} is the side to move. "
        f"Judge {side}'s overall position from the following FEN. FEN: {case['fen']}"
    ), side


def ask(case, condition="base"):
    if condition not in CONDITIONS:
        raise ValueError("Unknown condition")
    state, side = state_for(case)
    instructions = f"Classify the overall outlook for {side}, the side to move."
    questions = {
        "outlook_choice": Choice(instructions=instructions, criteria=choice_criteria(condition, case["index"])),
        "outlook_score": Score(instructions=instructions, criteria=list(LEVELS)),
    }
    started = time.perf_counter()
    response = client().system_one(model=MODEL, state=state, questions=questions)
    choice = response.answers["outlook_choice"]
    score = response.answers["outlook_score"]
    score_level_index = max(score.probabilities, key=score.probabilities.get)
    score_level = ("danger", "neutral", "advantage")[score_level_index]
    usage = response.usage
    return {
        **case,
        "condition": condition,
        "choice": {
            "pick": choice.choice,
            "hit": choice.choice == case["expected"],
            "probabilities": dict(choice.probabilities),
            "confidence": choice.confidence,
        },
        "score": {
            "value": score.score,
            "level": score_level,
            "hit": score_level == case["expected"],
            "probabilities": dict(score.probabilities),
            "confidence": score.confidence,
        },
        "latency_ms": round(1000 * (time.perf_counter() - started)),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "request": {
            "model": MODEL,
            "state": state,
            "questions": {
                "outlook_choice": {"type": "choice", "instructions": instructions, "criteria": dict(questions["outlook_choice"].criteria)},
                "outlook_score": {"type": "score", "instructions": instructions, "criteria": list(LEVELS)},
            },
        },
    }


def summarize(rows, primitive):
    danger = [row for row in rows if row["expected"] == "danger"]
    advantage = [row for row in rows if row["expected"] == "advantage"]
    key = "pick" if primitive == "choice" else "level"
    result = {
        "hit": sum(row[primitive]["hit"] for row in rows),
        "n": len(rows),
        "danger_picks": {label: sum(row[primitive][key] == label for row in danger) for label in ("danger", "neutral", "advantage")},
        "advantage_picks": {label: sum(row[primitive][key] == label for row in advantage) for label in ("danger", "neutral", "advantage")},
    }
    if primitive == "score":
        result["danger_mean_score"] = round(sum(row["score"]["value"] for row in danger) / len(danger), 4)
        result["advantage_mean_score"] = round(sum(row["score"]["value"] for row in advantage) / len(advantage), 4)
    return result


def main():
    jobs = [(case, condition) for case in cases() for condition in CONDITIONS]
    random.Random(92032).shuffle(jobs)
    trials = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(ask, *job) for job in jobs]
        for future in as_completed(futures):
            trials.append(future.result())
            if len(trials) % 40 == 0:
                print(f"{len(trials)}/{len(jobs)} complete", flush=True)
    summary = {}
    for primitive in ("choice", "score"):
        for condition in CONDITIONS:
            summary[f"{primitive}/{condition}"] = summarize([row for row in trials if row["condition"] == condition], primitive)
        summary[f"{primitive}/all"] = summarize(trials, primitive)
    result = {
        "model": MODEL,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "design": "20 matched extremes: side to move has unique mate in one (advantage) versus opponent already mated (danger); Choice and ordered Score in each request; three conditions.",
        "summary": summary,
        "trials": sorted(trials, key=lambda row: (row["condition"], row["index"], row["kind"])),
        "cost_usd": round(sum(row["input_tokens"] + row["output_tokens"] for row in trials) * USD_PER_TOKEN, 4),
    }
    (HERE / "results_position_outlook.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(json.dumps({"summary": summary, "cost_usd": result["cost_usd"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
