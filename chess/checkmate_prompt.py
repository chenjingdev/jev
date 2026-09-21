"""Ablate explicit side-to-move wording and Noul versus forced Choice."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import random
import threading
import time

import chess
from typesafe_sdk import Choice, Noul, TypeSafeClient

import checkmate


HERE = Path(__file__).resolve().parent
MODEL = os.environ.get("JEV_MODEL", "jev-1.13.0")
USD_PER_TOKEN = 42 / 1e9
LOCAL = threading.local()


def client():
    if not hasattr(LOCAL, "client"):
        LOCAL.client = TypeSafeClient()
    return LOCAL.client


def explicit_state(case, encoding):
    board = chess.Board(case["fen"])
    side = "White" if board.turn else "Black"
    opponent = "Black" if board.turn else "White"
    if encoding == "fen":
        state = {
            "position_format": "standard chess FEN",
            "fen": case["fen"],
            "side_to_move": side,
            "opponent": opponent,
        }
    elif encoding == "pieces":
        state = checkmate.state_for(case, "pieces")
        state["side_to_move"] = side
        state["opponent"] = opponent
    else:
        raise ValueError("Unknown encoding")
    return state, side


def instruction(side, encoding):
    source = "the standard FEN in `fen`" if encoding == "fen" else "the complete square-to-piece map in `pieces`"
    return (
        f"{side} is the side to move. Using {source} and standard chess rules, is {side} currently checkmated? "
        f"Answer yes only if {side}'s king is in check and {side} has zero legal moves that escape check."
    )


def ask(case, encoding, primitive):
    state, side = explicit_state(case, encoding)
    instructions = instruction(side, encoding)
    if primitive == "noul":
        question = Noul(
            instructions=instructions,
            criteria={
                "true": f"Yes. {side}'s king is in check and {side} has no legal escape.",
                "false": f"No. {side}'s king is not in check or {side} has at least one legal escape.",
            },
        )
    elif primitive == "choice":
        question = Choice(
            instructions=instructions,
            criteria={
                "yes": f"{side}'s king is in check and {side} has no legal escape.",
                "no": f"{side}'s king is not in check or {side} has at least one legal escape.",
            },
        )
    else:
        raise ValueError("Unknown primitive")
    started = time.perf_counter()
    response = client().system_one(model=MODEL, state=state, questions={"checkmate": question})
    answer = response.answers["checkmate"]
    if primitive == "noul":
        yes_probability = answer.noul
        predicted = yes_probability >= 0.5
        raw = {"noul": answer.noul}
    else:
        yes_probability = answer.probabilities["yes"]
        predicted = answer.choice == "yes"
        raw = {
            "choice": answer.choice,
            "probabilities": dict(answer.probabilities),
            "confidence": answer.confidence,
        }
    usage = response.usage
    return {
        **case,
        "encoding": encoding,
        "primitive": primitive,
        "yes_probability": yes_probability,
        "predicted": predicted,
        "hit": predicted == case["expected"],
        "answer": raw,
        "latency_ms": round(1000 * (time.perf_counter() - started)),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "request": {"model": MODEL, "state": state, "instructions": instructions, "primitive": primitive},
    }


def summarize(rows):
    positives = [row for row in rows if row["expected"]]
    negatives = [row for row in rows if not row["expected"]]
    return {
        "hit": sum(row["hit"] for row in rows),
        "n": len(rows),
        "mate_yes": sum(row["predicted"] for row in positives),
        "mate_n": len(positives),
        "check_only_no": sum(not row["predicted"] for row in negatives),
        "check_only_n": len(negatives),
        "mate_mean_yes_probability": round(sum(row["yes_probability"] for row in positives) / len(positives), 4),
        "check_only_mean_yes_probability": round(sum(row["yes_probability"] for row in negatives) / len(negatives), 4),
    }


def main():
    jobs = [(case, encoding, primitive) for case in checkmate.cases() for encoding in ("fen", "pieces") for primitive in ("noul", "choice")]
    random.Random(92027).shuffle(jobs)
    trials = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(ask, *job) for job in jobs]
        for future in as_completed(futures):
            trials.append(future.result())
            if len(trials) % 40 == 0:
                print(f"{len(trials)}/{len(jobs)} complete", flush=True)
    summary = {}
    for encoding in ("fen", "pieces"):
        for primitive in ("noul", "choice"):
            summary[f"{encoding}/{primitive}"] = summarize(
                [row for row in trials if row["encoding"] == encoding and row["primitive"] == primitive]
            )
    result = {
        "model": MODEL,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "design": "Same 40 matched check positions; explicit side-to-move in state and question; Noul versus diagnostic yes/no Choice.",
        "summary": summary,
        "trials": sorted(trials, key=lambda row: (row["encoding"], row["primitive"], row["index"], row["kind"])),
        "cost_usd": round(sum(row["input_tokens"] + row["output_tokens"] for row in trials) * USD_PER_TOKEN, 4),
    }
    (HERE / "results_checkmate_prompt.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(json.dumps({"summary": summary, "cost_usd": result["cost_usd"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
