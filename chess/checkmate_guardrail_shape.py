"""Checkmate test shaped exactly like the successful guardrail: string state + bare Noul."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import random
import threading
import time

import chess
from typesafe_sdk import Noul, TypeSafeClient

import checkmate


HERE = Path(__file__).resolve().parent
MODEL = os.environ.get("JEV_MODEL", "jev-1.13.0")
USD_PER_TOKEN = 42 / 1e9
LOCAL = threading.local()


def client():
    if not hasattr(LOCAL, "client"):
        LOCAL.client = TypeSafeClient()
    return LOCAL.client


def state_for(case):
    board = chess.Board(case["fen"])
    side = "White" if board.turn else "Black"
    return (
        f"This is a chess game. {side} is the side to move. "
        f"Determine whether the following FEN is a checkmate position for {side}. "
        f"FEN: {case['fen']}"
    ), side


def ask(case, repeat=0):
    state, side = state_for(case)
    instructions = f"{side} is checkmated in the chess position described in the state."
    started = time.perf_counter()
    response = client().system_one(
        model=MODEL,
        state=state,
        questions={"result": Noul(instructions=instructions)},
    )
    probability = response.answers["result"].noul
    predicted = probability >= 0.5
    usage = response.usage
    return {
        **case,
        "repeat": repeat,
        "probability": probability,
        "predicted": predicted,
        "hit": predicted == case["expected"],
        "latency_ms": round(1000 * (time.perf_counter() - started)),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "request": {
            "model": MODEL,
            "state": state,
            "questions": {
                "result": {"type": "noul", "instructions": instructions, "criteria": None}
            },
        },
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
        "mate_mean_probability": round(sum(row["probability"] for row in positives) / len(positives), 4),
        "check_only_mean_probability": round(sum(row["probability"] for row in negatives) / len(negatives), 4),
    }


def main():
    jobs = [(case, repeat) for case in checkmate.cases() for repeat in range(3)]
    random.Random(92030).shuffle(jobs)
    trials = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(ask, *job) for job in jobs]
        for future in as_completed(futures):
            trials.append(future.result())
            if len(trials) % 40 == 0:
                print(f"{len(trials)}/{len(jobs)} complete", flush=True)
    summary = {f"repeat_{repeat + 1}": summarize([row for row in trials if row["repeat"] == repeat]) for repeat in range(3)}
    summary["all"] = summarize(trials)
    result = {
        "model": MODEL,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "design": "Guardrail-shaped request: all task context and FEN in one state string; one short assertion Noul without criteria; three repeats.",
        "summary": summary,
        "trials": sorted(trials, key=lambda row: (row["repeat"], row["index"], row["kind"])),
        "cost_usd": round(sum(row["input_tokens"] + row["output_tokens"] for row in trials) * USD_PER_TOKEN, 4),
    }
    (HERE / "results_checkmate_guardrail_shape.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(json.dumps({"summary": summary, "cost_usd": result["cost_usd"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
