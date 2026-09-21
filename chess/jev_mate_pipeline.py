"""Jev-only checkmate experiment: per-attacker detection then per-defender evasion.

This still asks Jev to find possible moves internally. Python combines judgments
only; it does not generate legal moves or compute attack rays at inference time.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import argparse
import json
import random

import jev_attack_pipeline as attack

MOVE_RULES = {
    "rook": "Move any positive distance on one rank or file, with every intermediate square empty.",
    "bishop": "Move any positive distance diagonally, with every intermediate square empty.",
    "queen": "Move any positive distance on a rank, file or diagonal, with every intermediate square empty.",
    "knight": "Move with absolute column/rank differences (1,2) or (2,1), jumping over intermediate pieces.",
    "king": "Move to an adjacent square (coordinate differences each at most 1, not both zero). The destination must be unattacked after moving.",
    "pawn": "White moves toward increasing ranks, Black toward decreasing ranks. Move one step forward into an empty square, or two from the starting rank with both squares empty. Capture one step diagonally forward only onto an enemy piece. En passant requires the supplied target. Promote on the far rank.",
}


def first_request(fen):
    state = attack.parse_position(fen)
    fields = fen.split()
    state["castling_rights"] = fields[2]
    state["en_passant_target"] = fields[3]
    request = attack.request_for(state)
    request["questions"] = {key: question for key, question in request["questions"].items()
                             if key == "direct" or key.startswith("attack_")}
    request["questions"]["direct_mate"] = {"type": "noul", "instructions":
        f"Is {state['side_to_move']} checkmated in this position: its king is currently attacked and it has no legal move that removes all attacks on its king?"}
    return request


def second_request(first):
    original = first["request"]["state"]
    p = first["probabilities"]
    predicted_attackers = [dict(piece, attack_probability=p['attack_' + piece['square']])
                          for piece in original["pieces"] if piece["color"] != original["side_to_move"]
                          and p['attack_' + piece['square']] >= attack.THRESHOLD]
    state = {**original,
             "earlier_model_assessment": {"predicted_attackers": predicted_attackers,
                 "note": "These are fallible predictions by the same model, not verified facts. All piece coordinates above are the supplied position."}}
    king = attack.piece_text(state["target_king"])
    questions = {}
    for piece in state["pieces"]:
        if piece["color"] != state["side_to_move"]:
            continue
        questions["evasion_" + piece["square"]] = {"type": "noul", "instructions": {
            "question": f"Can {attack.piece_text(piece)} make at least one legal move that leaves the {state['side_to_move']} king safe from EVERY opposing piece?",
            "movement_rule": MOVE_RULES[piece["kind"]],
            "current_king": king,
            "legality": "Use standard chess rules and the complete piece list. Cannot land on a friendly piece, capture the opposing king, or leave your own king attacked. When moving, remove the piece from its old square and remove an enemy piece captured at the destination before assessing king safety. Castling is not allowed out of check.",
            "scope": "Evaluate only moves by this particular piece. True if at least one such legal move exists; false if none exist. Do not assume an escape merely because this type of piece can normally move."
        }}
    return {"model": attack.MODEL, "state": state, "questions": questions}


def infer(fen):
    first = attack.call(first_request(fen))
    second = attack.call(second_request(first))
    check = any(value >= attack.THRESHOLD for key, value in first["probabilities"].items() if key.startswith("attack_"))
    escape = any(value >= attack.THRESHOLD for value in second["probabilities"].values())
    return {"stages": [first, second], "check_predicted": check, "escape_predicted": escape,
            "predictions": {"direct": first["probabilities"]["direct_mate"] >= attack.THRESHOLD,
                            "per_piece_evasion": check and not escape}}


def fixtures(split):
    import checkmate
    return [case for case in checkmate.cases() if
            (case["index"] <= 10 if split == "development" else case["index"] > 10)]


def evaluate(case):
    result = infer(case["fen"])
    # Ground truth is calculated only after inference, for diagnostics.
    import chess
    board = chess.Board(case["fen"])
    truth_evasions = {}
    for move in board.legal_moves:
        truth_evasions.setdefault(chess.square_name(move.from_square), []).append(move.uci())
    return {"index": case["index"], "kind": case["kind"], "fen": case["fen"],
            "expected": case["expected"], "truth_evasions": truth_evasions, **result}


def summary(trials):
    output = {}
    for method in ("direct", "per_piece_evasion"):
        output[method] = {"hit": sum(t["predictions"][method] == t["expected"] for t in trials), "n": len(trials),
            "tp": sum(t["predictions"][method] and t["expected"] for t in trials),
            "fn": sum(not t["predictions"][method] and t["expected"] for t in trials),
            "tn": sum(not t["predictions"][method] and not t["expected"] for t in trials),
            "fp": sum(t["predictions"][method] and not t["expected"] for t in trials)}
    output["subtasks"] = {"check_detected": sum(t["check_predicted"] for t in trials),
                          "check_total": len(trials),
                          "escape_correct": sum(t["escape_predicted"] != t["expected"] for t in trials)}
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("development", "evaluation"), required=True)
    args = parser.parse_args()
    out = attack.HERE / f"results_jev_mate_{args.split}.json"
    if out.exists():
        raise SystemExit(f"Preserving existing run: {out}")
    jobs = fixtures(args.split)
    random.Random(92262).shuffle(jobs)
    trials = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(evaluate, case) for case in jobs]):
            trials.append(future.result())
            print(f"{args.split}: {len(trials)}/{len(jobs)}", flush=True)
    stages = [s for t in trials for s in t["stages"]]
    result = {"model": attack.MODEL, "created_at": datetime.now(timezone.utc).isoformat(), "split": args.split,
        "threshold": attack.THRESHOLD, "summary": summary(trials),
        "independent_parents": len({t["index"] for t in trials}),
        "requests": len(stages), "judgments": sum(len(s["probabilities"]) for s in stages),
        "input_tokens": sum(s["input_tokens"] for s in stages),
        "cost_usd": round(sum(s["input_tokens"] for s in stages) * 42 / 1e9, 6),
        "trials": sorted(trials, key=lambda t: (t["index"], t["kind"]))}
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "trials"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
