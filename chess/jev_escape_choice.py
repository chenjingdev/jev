"""Jev proposes one king-saving destination per friendly piece from all 64 squares."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import argparse
import json
import random

from typesafe_sdk import Choice

import checkmate
import jev_attack_layers as layers
import jev_attack_pipeline as pipeline


SQUARES = [f"{file}{rank}" for rank in range(1, 9) for file in "abcdefgh"]
SQUARE_CRITERIA = {square: {"destination": square,
                   "column": ord(square[0]) - 96, "rank": int(square[1])}
                   for square in SQUARES}
SQUARE_CRITERIA["none"] = "This exact piece has no legal destination that leaves its own king safe."


def fixtures(split):
    return [row for row in checkmate.cases() if
            (row["index"] <= 10 if split == "development" else row["index"] > 10)]


def state_for(fen):
    state = pipeline.parse_position(fen)
    fields = fen.split()
    state["castling_rights"] = fields[2]
    state["en_passant_target"] = fields[3]
    state.pop("target_king")
    return state


def request_for(case):
    state = state_for(case["fen"])
    side = state["side_to_move"]
    questions = {}
    for piece in state["pieces"]:
        if piece["color"] != side:
            continue
        questions["escape_" + piece["square"]] = {"type": "choice", "instructions": {
            "piece": pipeline.piece_text(piece),
            "movement_rule": pipeline.RULES[piece["kind"]],
            "question": (
                f"Which destination can this exact piece legally move to now so that, after the move, "
                f"the {side} king is not attacked by any opponent piece? Choose none only if this piece "
                "has no such destination. Consider captures, occupied squares, blockers, pins, and attacks "
                "on the king after the move. Do not choose the piece's current square."
            ),
        }, "criteria": SQUARE_CRITERIA}
    return {"model": pipeline.MODEL, "state": state, "questions": questions}


def run_one(case):
    request = request_for(case)
    result = layers.call_choices(request)
    proposals = []
    for key, answer in result["answers"].items():
        source = key.removeprefix("escape_")
        proposals.append({"source": source, "destination": answer["choice"],
                          "confidence": answer["confidence"], "probabilities": answer["probabilities"]})
    return {"index": case.get("index"), "kind": case.get("kind"), "fen": case["fen"],
            "expected_mate": case.get("expected"), "proposals": proposals, "stage": result}


def score(trial):
    import chess
    board = chess.Board(trial["fen"])
    legal_by_pair = {}
    for move in board.legal_moves:
        legal_by_pair.setdefault((chess.square_name(move.from_square), chess.square_name(move.to_square)), []).append(move.uci())
    any_non_none = False; any_true = False
    for proposal in trial["proposals"]:
        choice = proposal["destination"]
        proposal["expected_destinations"] = sorted({target for source, target in legal_by_pair if source == proposal["source"]})
        proposal["true_escape"] = choice != "none" and (proposal["source"], choice) in legal_by_pair
        proposal["choice_correct"] = proposal["true_escape"] or (choice == "none" and not proposal["expected_destinations"])
        any_non_none |= choice != "none"; any_true |= proposal["true_escape"]
    trial["raw_escape_predicted"] = any_non_none
    trial["oracle_filtered_escape"] = any_true
    trial["raw_mate_predicted"] = not any_non_none
    trial["oracle_filtered_mate"] = not any_true
    trial["raw_hit"] = trial["raw_mate_predicted"] == trial["expected_mate"]
    trial["oracle_filtered_hit"] = trial["oracle_filtered_mate"] == trial["expected_mate"]
    return trial


def summary(trials):
    proposals = [p for t in trials for p in t["proposals"]]
    mates = [t for t in trials if t["expected_mate"]]
    checks = [t for t in trials if not t["expected_mate"]]
    return {"piece_choices": {"hit": sum(p["choice_correct"] for p in proposals), "n": len(proposals),
                               "non_none": sum(p["destination"] != "none" for p in proposals),
                               "true_escapes": sum(p["true_escape"] for p in proposals)},
            "raw_board": {"hit": sum(t["raw_hit"] for t in trials), "n": len(trials),
                          "mate_correct": sum(t["raw_hit"] for t in mates), "mate_n": len(mates),
                          "check_only_correct": sum(t["raw_hit"] for t in checks), "check_only_n": len(checks)},
            "oracle_filtered_diagnostic": {"hit": sum(t["oracle_filtered_hit"] for t in trials), "n": len(trials),
                          "note": "Scoring diagnostic only. The oracle filter is never available to Jev or inference code."}}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--split", choices=("development", "evaluation"), required=True)
    args = parser.parse_args(); path = pipeline.HERE / f"results_jev_escape_choice_{args.split}.json"
    if path.exists(): raise SystemExit(f"Preserving existing run: {path}")
    cases = fixtures(args.split); random.Random(92265).shuffle(cases)
    with ThreadPoolExecutor(max_workers=4) as pool:
        trials = [score(f.result()) for f in as_completed([pool.submit(run_one, case) for case in cases])]
    stages = [t["stage"] for t in trials]
    result = {"created_at": datetime.now(timezone.utc).isoformat(), "model": pipeline.MODEL, "split": args.split,
              "design": "For each friendly piece, Choice over all 64 destination squares plus none. No legal move list or derived chess fact enters requests. Oracle filtering is reported only as a diagnostic upper bound after inference.",
              "summary": summary(trials), "requests": len(stages),
              "judgments": sum(len(s["answers"]) for s in stages),
              "input_tokens": sum(s["input_tokens"] for s in stages),
              "cost_usd": round(sum(s["input_tokens"] for s in stages) * 42 / 1e9, 6),
              "trials": sorted(trials, key=lambda t:(t["index"],t["kind"]))}
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k:v for k,v in result.items() if k != "trials"}, ensure_ascii=False))


if __name__ == "__main__": main()
