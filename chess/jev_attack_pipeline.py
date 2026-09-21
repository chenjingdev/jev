"""Jev-only attack judgments, orchestrated in Python; no engine at inference.

FEN parsing only recodes supplied facts. The engine is used separately to prepare
and score fixtures. No candidate is removed using ground-truth attack geometry.
All thresholds and the 10-parent development/10-parent evaluation split are fixed.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import random
import threading
import time

from typesafe_sdk import Noul, TypeSafeClient

HERE = Path(__file__).resolve().parent
MODEL = "jev-1.13.0"
LOCAL = threading.local()
THRESHOLD = 0.5
KINDS = dict(zip("pnbrqk", ("pawn", "knight", "bishop", "rook", "queen", "king")))
RULES = {
    "rook": "Same column OR same rank, with distinct endpoints.",
    "bishop": "Absolute column difference equals absolute rank difference, and both are nonzero.",
    "queen": "Same column OR same rank OR equal nonzero absolute column and rank differences; endpoints differ.",
    "knight": "Absolute column and rank differences are (1,2) or (2,1).",
    "king": "Each absolute coordinate difference is at most 1 and at least one is 1.",
    "pawn": "Absolute column difference is exactly 1; target rank minus source rank is +1 for White, -1 for Black.",
}
SLIDERS = {"rook", "bishop", "queen"}
SEGMENT_RULE = (
    "A point is strictly inside the segment only if all three squares are on the same "
    "horizontal, vertical, or diagonal line AND the point is between the endpoints. "
    "Horizontal: same rank, point column strictly between endpoint columns. "
    "Vertical: same column, point rank strictly between endpoint ranks. "
    "Diagonal: the point is on the endpoint diagonal and both coordinates are strictly between "
    "their respective endpoint coordinates. Endpoints and off-line points are false."
)


def client():
    if not hasattr(LOCAL, "client"):
        LOCAL.client = TypeSafeClient()
    return LOCAL.client


def parse_position(fen):
    """Representation conversion only: no attacks, legal moves, or filtering."""
    fields = fen.split()
    pieces = []
    for rank, row in zip(range(8, 0, -1), fields[0].split("/")):
        column = 1
        for token in row:
            if token.isdigit():
                column += int(token)
            else:
                pieces.append({"color": "White" if token.isupper() else "Black",
                               "kind": KINDS[token.lower()],
                               "square": chr(96 + column) + str(rank),
                               "column": column, "rank": rank})
                column += 1
        if column != 9:
            raise ValueError("Invalid rank")
    side = "White" if fields[1] == "w" else "Black"
    king, = [p for p in pieces if p["color"] == side and p["kind"] == "king"]
    return {"game": "standard chess", "side_to_move": side,
            "coordinate_key": "a=1, b=2, c=3, d=4, e=5, f=6, g=7, h=8; ranks 1 through 8",
            "target_king": king, "pieces": pieces}


def piece_text(piece):
    return f"{piece['color']} {piece['kind']} {piece['square']} (column {piece['column']}, rank {piece['rank']})"


def request_for(state):
    king = state["target_king"]
    target = piece_text(king)
    questions = {"direct": {"type": "noul", "instructions":
        f"In this chess position, is {target} currently attacked by any opposing piece? "
        "Use current occupied squares and standard piece attack rules. A pinned opponent still attacks squares."}}
    attackers = [p for p in state["pieces"] if p["color"] != king["color"]]
    for p in attackers:
        source = piece_text(p)
        rule = RULES[p["kind"]]
        sliding = p["kind"] in SLIDERS
        questions["attack_" + p["square"]] = {"type": "noul", "instructions": {
            "question": f"Does {source} currently attack {target}?",
            "movement_rule": rule,
            "occupancy_rule": "No piece may lie strictly between the two squares." if sliding else "Intermediate pieces do not block this attack.",
            "scope": "Attack map only. Ignore whether moving the attacking piece would expose its own king."
        }}
        questions["geometry_" + p["square"]] = {"type": "noul", "instructions": {
            "question": f"Ignoring all other pieces, does {source} attack {target} according to this movement rule?",
            "movement_rule": rule,
            "scope": "Check only the two endpoint coordinates. Ignore blockers and king safety."
        }}
        if sliding:
            questions["clear_" + p["square"]] = {"type": "noul", "instructions": {
                "question": f"Is the straight segment from {source} to {target} free of all other pieces?",
                "rule": SEGMENT_RULE,
                "scope": "Use all pieces in state. Endpoints do not block. If endpoints are not aligned horizontally, vertically or diagonally, answer false."
            }}
    return {"model": MODEL, "state": state, "questions": questions}


def call(request):
    started = time.perf_counter()
    response = client().system_one(model=request["model"], state=request["state"], questions={
        key: Noul(instructions=value["instructions"]) for key, value in request["questions"].items()
    })
    probabilities = {key: float(value.noul) for key, value in response.answers.items()}
    if set(probabilities) != set(request["questions"]):
        raise ValueError("Missing or extra answers")
    return {"request": request, "probabilities": probabilities,
            "resolved_model": response.model,
            "input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens,
            "latency_ms": round(1000 * (time.perf_counter() - started))}


def blockers_request(state, stage_one):
    questions, candidates = {}, []
    king = state["target_king"]
    for p in state["pieces"]:
        if p["color"] == king["color"] or p["kind"] not in SLIDERS:
            continue
        if stage_one["geometry_" + p["square"]] < THRESHOLD:
            continue
        candidates.append(p["square"])
        for obstacle in state["pieces"]:
            if obstacle["square"] in (p["square"], king["square"]):
                continue
            key = "block_" + p["square"] + "_" + obstacle["square"]
            questions[key] = {"type": "noul", "instructions": {
                "question": "Is point P strictly inside the straight line segment from A to B?",
                "A": {k: p[k] for k in ("column", "rank")},
                "B": {k: king[k] for k in ("column", "rank")},
                "P": {k: obstacle[k] for k in ("column", "rank")},
                "rule": SEGMENT_RULE,
            }}
    # Each question already contains its full local data. This shared state adds no answer.
    request = {"model": MODEL, "state": "Integer grid geometry. Coordinates are column and rank. Evaluate each point independently.", "questions": questions}
    return request, candidates


def infer(fen):
    """Only state facts enter this function. It cannot read an answer label."""
    state = parse_position(fen)
    first = call(request_for(state))
    p = first["probabilities"]
    request, candidates = blockers_request(state, p)
    second = call(request) if request["questions"] else None
    blockers = second["probabilities"] if second else {}
    attacker_outputs = []
    for piece in state["pieces"]:
        if piece["color"] == state["side_to_move"]:
            continue
        square = piece["square"]
        geometry = p["geometry_" + square]
        clear = p.get("clear_" + square, 1.0)
        local_blockers = {key: value for key, value in blockers.items() if key.startswith("block_" + square + "_")}
        blocker_present = max(local_blockers.values(), default=0.0)
        # For sliders rejected by Jev's geometry, no path judgments are needed.
        decomposed = geometry >= THRESHOLD and blocker_present < THRESHOLD
        attacker_outputs.append({"square": square, "kind": piece["kind"],
            "attack_probability": p["attack_" + square], "geometry_probability": geometry,
            "clear_probability": clear, "max_blocker_probability": blocker_present,
            "piece_verdict": p["attack_" + square] >= THRESHOLD,
            "geometry_path_verdict": geometry >= THRESHOLD and clear >= THRESHOLD,
            "pointwise_verdict": decomposed})
    return {"stages": [first] + ([second] if second else []), "attackers": attacker_outputs,
        "predictions": {"direct": p["direct"] >= THRESHOLD,
            "per_piece": any(a["piece_verdict"] for a in attacker_outputs),
            "geometry_path": any(a["geometry_path_verdict"] for a in attacker_outputs),
            "pointwise": any(a["pointwise_verdict"] for a in attacker_outputs)}}


def infer_check(fen):
    """Usable one-request path: one Jev judgment per opponent, boolean OR.

    There is deliberately no global probability: OR of thresholded model
    judgments is a decision rule, not a calibrated check probability.
    """
    request = request_for(parse_position(fen))
    request["questions"] = {key: q for key, q in request["questions"].items() if key.startswith("attack_")}
    result = call(request)
    attackers = [{"square": key.removeprefix("attack_"), "attack_probability": value,
                  "piece_verdict": value >= THRESHOLD}
                 for key, value in result["probabilities"].items()]
    return {"stages": [result], "attackers": attackers,
            "predictions": {"per_piece": any(a["piece_verdict"] for a in attackers)}}


def fixtures(split):
    # Ground truth is prepared separately, never passed to infer().
    import check_detection
    return [case for case in check_detection.cases() if
            (case["index"] <= 10 if split == "development" else case["index"] > 10)]


def evaluate(case, mode="compare"):
    inferred = (infer_check if mode == "per_piece" else infer)(case["fen"])
    import chess
    board = chess.Board(case["fen"])
    truth_squares = {chess.square_name(s) for s in board.attackers(not board.turn, board.king(board.turn))}
    for a in inferred["attackers"]:
        a["truth_attack"] = a["square"] in truth_squares
    return {"index": case["index"], "kind": case["kind"], "fen": case["fen"],
            "expected": case["expected"], "truth_attackers": sorted(truth_squares), **inferred}


def summary(trials):
    output = {}
    for method in trials[0]["predictions"]:
        output[method] = {
            "hit": sum(t["predictions"][method] == t["expected"] for t in trials), "n": len(trials),
            "tp": sum(t["predictions"][method] and t["expected"] for t in trials),
            "fn": sum(not t["predictions"][method] and t["expected"] for t in trials),
            "tn": sum(not t["predictions"][method] and not t["expected"] for t in trials),
            "fp": sum(t["predictions"][method] and not t["expected"] for t in trials)}
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("development", "evaluation"), required=True)
    parser.add_argument("--mode", choices=("compare", "per_piece"), default="compare")
    args = parser.parse_args()
    suffix = "_per_piece" if args.mode == "per_piece" else ""
    out = HERE / f"results_jev_attack_{args.split}{suffix}.json"
    if out.exists():
        raise SystemExit(f"Preserving existing run: {out}")
    jobs = fixtures(args.split)
    random.Random(92261).shuffle(jobs)
    trials = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(evaluate, case, args.mode) for case in jobs]):
            trials.append(future.result())
            print(f"{args.split}: {len(trials)}/{len(jobs)}", flush=True)
    stages = [s for t in trials for s in t["stages"]]
    result = {"model": MODEL, "created_at": datetime.now(timezone.utc).isoformat(), "split": args.split, "mode": args.mode,
        "threshold": THRESHOLD, "summary": summary(trials),
        "independent_parents": len({t["index"] for t in trials}),
        "requests": len(stages), "judgments": sum(len(s["probabilities"]) for s in stages),
        "input_tokens": sum(s["input_tokens"] for s in stages),
        "cost_usd": round(sum(s["input_tokens"] for s in stages) * 42 / 1e9, 6),
        "trials": sorted(trials, key=lambda t: (t["index"], t["kind"]))}
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "trials"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
