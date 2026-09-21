"""Atomic Noul test: is the side-to-move king currently in check?"""
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

import probe


HERE = Path(__file__).resolve().parent
MODEL = os.environ.get("JEV_MODEL", "jev-1.13.0")
USD_PER_TOKEN = 42 / 1e9
LOCAL = threading.local()


def client():
    if not hasattr(LOCAL, "client"):
        LOCAL.client = TypeSafeClient()
    return LOCAL.client


def cases():
    """Same parent and moving piece: one checking child and one quiet child."""
    result = []
    for index, row in enumerate(probe.positions(), 1):
        parent = probe.validate_position(row)
        checking_uci = row["nonmate_checks"][0]
        quiet_uci = None
        for uci in row["distractor_pool"]:
            move = chess.Move.from_uci(uci)
            if move not in parent.legal_moves:
                continue
            parent.push(move)
            gives_check = parent.is_check()
            parent.pop()
            if not gives_check:
                quiet_uci = uci
                break
        if quiet_uci is None:
            raise ValueError(f"No quiet counterpart for {row['puzzle_id']}")
        for kind, uci, expected in (("check", checking_uci, True), ("not_check", quiet_uci, False)):
            board = parent.copy()
            move = chess.Move.from_uci(uci)
            if move not in board.legal_moves:
                raise ValueError(f"Illegal child move: {row['puzzle_id']} {uci}")
            mover = board.piece_at(move.from_square)
            board.push(move)
            if board.is_check() != expected:
                raise ValueError(f"Wrong check label: {row['puzzle_id']} {uci}")
            if expected and board.is_checkmate():
                raise ValueError(f"Positive child unexpectedly ends the game: {row['puzzle_id']} {uci}")
            result.append({
                "index": index,
                "puzzle_id": row["puzzle_id"],
                "kind": kind,
                "expected": expected,
                "fen": board.fen(),
                "source_move": uci,
                "moving_piece": chess.piece_name(mover.piece_type),
            })
    return result


def state_for(case):
    board = chess.Board(case["fen"])
    side = "White" if board.turn else "Black"
    return (
        f"This is a chess game. {side} is the side to move. "
        f"Determine whether {side}'s king is currently in check from the following FEN. "
        f"FEN: {case['fen']}"
    ), side


def ask(case, repeat=0):
    state, side = state_for(case)
    instructions = f"{side}'s king is currently in check in the chess position described in the state."
    started = time.perf_counter()
    response = client().system_one(
        model=MODEL,
        state=state,
        questions={"in_check": Noul(instructions=instructions)},
    )
    probability = response.answers["in_check"].noul
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
            "questions": {"in_check": {"type": "noul", "instructions": instructions, "criteria": None}},
        },
    }


def summarize(rows):
    positives = [row for row in rows if row["expected"]]
    negatives = [row for row in rows if not row["expected"]]
    return {
        "hit": sum(row["hit"] for row in rows),
        "n": len(rows),
        "check_yes": sum(row["predicted"] for row in positives),
        "check_n": len(positives),
        "quiet_no": sum(not row["predicted"] for row in negatives),
        "quiet_n": len(negatives),
        "check_mean_probability": round(sum(row["probability"] for row in positives) / len(positives), 4),
        "quiet_mean_probability": round(sum(row["probability"] for row in negatives) / len(negatives), 4),
    }


def main():
    jobs = [(case, repeat) for case in cases() for repeat in range(3)]
    random.Random(92031).shuffle(jobs)
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
        "design": "20 matched parents; same piece makes a non-mating check or a quiet move; string state; bare atomic Noul; three repeats.",
        "summary": summary,
        "trials": sorted(trials, key=lambda row: (row["repeat"], row["index"], row["kind"])),
        "cost_usd": round(sum(row["input_tokens"] + row["output_tokens"] for row in trials) * USD_PER_TOKEN, 4),
    }
    (HERE / "results_check_detection.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(json.dumps({"summary": summary, "cost_usd": result["cost_usd"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
