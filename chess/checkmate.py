"""Test whether Jev can distinguish checkmate from check with an escape."""
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
INSTRUCTIONS = (
    "Is the current chess position checkmate for the side to move? "
    "Checkmate means that the side to move is in check and has no legal move that escapes check."
)
CRITERIA = {
    "true": "The side to move is in check and has zero legal moves.",
    "false": "The side to move is not in check, or at least one legal move escapes check.",
}


def client():
    if not hasattr(LOCAL, "client"):
        LOCAL.client = TypeSafeClient()
    return LOCAL.client


def cases():
    """Build one mate and one check-only child from each validated parent."""
    result = []
    for index, row in enumerate(probe.positions(), 1):
        parent = probe.validate_position(row)
        moves = (("mate", row["mate"], True), ("check_only", row["nonmate_checks"][0], False))
        for kind, uci, expected in moves:
            board = parent.copy()
            move = chess.Move.from_uci(uci)
            if move not in board.legal_moves:
                raise ValueError(f"Illegal child move: {row['puzzle_id']} {uci}")
            board.push(move)
            if not board.is_check():
                raise ValueError(f"Child is not check: {row['puzzle_id']} {uci}")
            if board.is_checkmate() != expected:
                raise ValueError(f"Wrong child label: {row['puzzle_id']} {uci}")
            if not expected and board.legal_moves.count() == 0:
                raise ValueError(f"Negative child has no escape: {row['puzzle_id']} {uci}")
            result.append({
                "index": index,
                "puzzle_id": row["puzzle_id"],
                "kind": kind,
                "expected": expected,
                "fen": board.fen(),
                "legal_replies": board.legal_moves.count(),
                "source_move": uci,
            })
    return result


def state_for(case, encoding):
    board = chess.Board(case["fen"])
    if encoding == "fen":
        return {"fen": case["fen"]}
    if encoding == "pieces":
        return {
            "pieces": {
                chess.square_name(square): ("white" if piece.color else "black")
                + " "
                + chess.piece_name(piece.piece_type)
                for square, piece in sorted(board.piece_map().items())
            },
            "turn": "white" if board.turn else "black",
            "castling": board.castling_xfen(),
            "en_passant": chess.square_name(board.ep_square) if board.ep_square is not None else None,
        }
    raise ValueError("Unknown encoding")


def ask(case, encoding="fen", repeat=0):
    state = state_for(case, encoding)
    question = Noul(instructions=INSTRUCTIONS, criteria=CRITERIA)
    started = time.perf_counter()
    response = client().system_one(
        model=MODEL,
        state=state,
        questions={"is_checkmate": question},
    )
    probability = response.answers["is_checkmate"].noul
    predicted = probability >= 0.5
    usage = response.usage
    return {
        **case,
        "encoding": encoding,
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
                "is_checkmate": {
                    "type": "noul",
                    "instructions": INSTRUCTIONS,
                    "criteria": CRITERIA,
                }
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
        "brier": round(
            sum((row["probability"] - int(row["expected"])) ** 2 for row in rows) / len(rows), 4
        ),
    }


def main():
    jobs = [(case, encoding, repeat) for case in cases() for encoding in ("fen", "pieces") for repeat in range(3)]
    random.Random(92026).shuffle(jobs)
    trials = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(ask, *job) for job in jobs]
        for future in as_completed(futures):
            trials.append(future.result())
            if len(trials) % 40 == 0:
                print(f"{len(trials)}/{len(jobs)} complete", flush=True)
    summary = {}
    for encoding in ("fen", "pieces"):
        summary[encoding] = summarize([row for row in trials if row["encoding"] == encoding])
        for repeat in range(3):
            summary[f"{encoding}/repeat_{repeat + 1}"] = summarize(
                [row for row in trials if row["encoding"] == encoding and row["repeat"] == repeat]
            )
    result = {
        "model": MODEL,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "design": (
            "20 matched parents. Each produces one true checkmate child and one checking child with legal escapes; "
            "FEN versus code-decoded piece map; three repeats; Noul threshold 0.5."
        ),
        "summary": summary,
        "trials": sorted(trials, key=lambda row: (row["encoding"], row["repeat"], row["index"], row["kind"])),
        "cost_usd": round(sum(row["input_tokens"] + row["output_tokens"] for row in trials) * USD_PER_TOKEN, 4),
    }
    (HERE / "results_checkmate.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(json.dumps({"summary": summary, "cost_usd": result["cost_usd"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
