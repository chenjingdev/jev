"""Ask Jev for every enemy-piece -> friendly-piece attack relation.

Inference uses only supplied coordinates, general rules, and Jev. The rules
engine is imported only by fixture preparation and post-inference scoring.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from copy import deepcopy
import argparse
import json
import random
import time

import jev_attack_pipeline as pipeline

LABELS = ("tp", "fp", "tn", "fn")
DEFAULT_BATCH_SIZE = 64


def pair_question(source, target):
    return {"type": "noul", "instructions": {
        "question": f"Does {pipeline.piece_text(source)} currently attack {pipeline.piece_text(target)}?",
        "movement_rule": pipeline.RULES[source["kind"]],
        "occupancy_rule": "No piece may lie strictly between the two squares." if source["kind"] in pipeline.SLIDERS else "Intermediate pieces do not block this attack.",
        "scope": "Attack map only. Ignore whether moving the attacking piece would expose its own king."
    }}


def requests_for(fen, perspective=None, batch_size=DEFAULT_BATCH_SIZE):
    if not 1 <= batch_size <= 128:
        raise ValueError("Batch size must be 1..128")
    state = pipeline.parse_position(fen)
    state.pop("target_king")
    perspective = perspective or state["side_to_move"]
    if perspective not in ("White", "Black"):
        raise ValueError("Perspective must be White or Black")
    state["our_color"] = perspective
    friendly = [p for p in state["pieces"] if p["color"] == perspective]
    enemy = [p for p in state["pieces"] if p["color"] != perspective]
    pairs = [(source, target) for source in enemy for target in friendly]
    requests = []
    for start in range(0, len(pairs), batch_size):
        questions = {"attack_" + s["square"] + "_" + t["square"]: pair_question(s, t)
                     for s, t in pairs[start:start + batch_size]}
        requests.append({"model": pipeline.MODEL, "state": state, "questions": questions})
    return requests


def infer_attack_map(fen, perspective=None, batch_size=DEFAULT_BATCH_SIZE):
    started = time.perf_counter()
    requests = requests_for(fen, perspective, batch_size)
    stages = [pipeline.call(request) for request in requests]
    state = requests[0]["state"]
    lookup = {p["square"]: p for p in state["pieces"]}
    relations = []
    for stage in stages:
        for key, value in stage["probabilities"].items():
            _, source, target = key.split("_")
            relations.append({"source": source, "source_kind": lookup[source]["kind"],
                "target": target, "target_kind": lookup[target]["kind"],
                "probability": value, "predicted": value >= pipeline.THRESHOLD})
    targets = []
    for target in state["pieces"]:
        if target["color"] != state["our_color"]:
            continue
        incoming = [r for r in relations if r["target"] == target["square"] and r["predicted"]]
        targets.append({"square": target["square"], "kind": target["kind"],
            "predicted_attacked": bool(incoming),
            "predicted_attackers": [r["source"] for r in incoming]})
    return {"perspective": state["our_color"], "stages": stages, "relations": relations,
            "targets": targets, "latency_ms": round(1000 * (time.perf_counter() - started))}


def evaluate_board(case, batch_size=DEFAULT_BATCH_SIZE):
    inferred = infer_attack_map(case["fen"], batch_size=batch_size)
    # Strictly post-inference: labels and legal captures never enter requests.
    import chess
    board = chess.Board(case["fen"])
    for relation in inferred["relations"]:
        relation["expected"] = chess.parse_square(relation["target"]) in board.attacks(chess.parse_square(relation["source"]))
    for target in inferred["targets"]:
        truth = [r["source"] for r in inferred["relations"] if r["target"] == target["square"] and r["expected"]]
        target["truth_attackers"] = truth
        target["expected_attacked"] = bool(truth)
        target["exact_attackers_match"] = set(truth) == set(target["predicted_attackers"])
    return {"index": case["index"], "kind": case["kind"], "fen": case["fen"], **inferred}


def verification_requests(inferred, batch_size=DEFAULT_BATCH_SIZE):
    """Select by Jev predictions only; never by expected labels or ground truth."""
    original = inferred["stages"][0]["request"]["state"]
    state = {key: original[key] for key in ("game", "side_to_move", "coordinate_key", "pieces", "our_color")}
    pieces = {p["square"]: p for p in state["pieces"]}
    questions = []
    for relation in inferred["relations"]:
        if not relation["predicted"]:
            continue
        source, target = pieces[relation["source"]], pieces[relation["target"]]
        suffix = source["square"] + "_" + target["square"]
        questions.append(("geometry_" + suffix, {"type": "noul", "instructions": {
            "question": f"Ignoring all other pieces, does {pipeline.piece_text(source)} attack {pipeline.piece_text(target)} according to this movement rule?",
            "movement_rule": pipeline.RULES[source["kind"]],
            "scope": "Check only the two endpoint coordinates. Ignore blockers and king safety."
        }}))
        if source["kind"] in pipeline.SLIDERS:
            questions.append(("clear_" + suffix, {"type": "noul", "instructions": {
                "question": f"Is the straight segment from {pipeline.piece_text(source)} to {pipeline.piece_text(target)} free of all other pieces?",
                "rule": pipeline.SEGMENT_RULE,
                "scope": "Use all pieces in state. Endpoints do not block. If endpoints are not aligned horizontally, vertically or diagonally, answer false."
            }}))
    return [{"model": pipeline.MODEL, "state": state, "questions": dict(questions[start:start + batch_size])}
            for start in range(0, len(questions), batch_size)]


def verify_attack_map(inferred):
    started = time.perf_counter()
    requests = verification_requests(inferred)
    new_stages = [pipeline.call(request) for request in requests]
    values = {key: value for stage in new_stages for key, value in stage["probabilities"].items()}
    result = deepcopy(inferred)
    for relation in result["relations"]:
        relation["original_predicted"] = relation["predicted"]
        if not relation["predicted"]:
            continue
        suffix = relation["source"] + "_" + relation["target"]
        geometry, clear = values["geometry_" + suffix], values.get("clear_" + suffix, 1.0)
        relation["geometry_probability"] = geometry
        relation["clear_probability"] = clear
        relation["predicted"] = geometry >= pipeline.THRESHOLD and clear >= pipeline.THRESHOLD
    for target in result["targets"]:
        target["predicted_attackers"] = [r["source"] for r in result["relations"]
                                         if r["target"] == target["square"] and r["predicted"]]
        target["predicted_attacked"] = bool(target["predicted_attackers"])
        if "truth_attackers" in target:
            target["exact_attackers_match"] = set(target["truth_attackers"]) == set(target["predicted_attackers"])
    result["verification_stages"] = new_stages
    result["verification_latency_ms"] = round(1000 * (time.perf_counter() - started))
    return result


def metrics(rows, predicted="predicted", expected="expected"):
    counts = dict.fromkeys(LABELS, 0)
    for row in rows:
        key = ("tp" if row[expected] else "fp") if row[predicted] else ("fn" if row[expected] else "tn")
        counts[key] += 1
    tp, fp, tn, fn = (counts[k] for k in LABELS)
    n = tp + fp + tn + fn
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    specificity = tn / (tn + fp) if tn + fp else None
    return {**counts, "n": n, "accuracy": (tp + tn) / n if n else None,
            "always_no_accuracy": (tn + fp) / n if n else None,
            "precision": precision, "recall": recall, "specificity": specificity,
            "balanced_accuracy": (recall + specificity) / 2 if recall is not None and specificity is not None else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None}


def summarize(trials):
    relations = [r for t in trials for r in t["relations"]]
    targets = [r for t in trials for r in t["targets"]]
    return {"relations": metrics(relations),
            "attacked_targets": metrics(targets, "predicted_attacked", "expected_attacked"),
            "king_targets": metrics([r for r in targets if r["kind"] == "king"], "predicted_attacked", "expected_attacked"),
            "exact_attacker_sets": {"hit": sum(r["exact_attackers_match"] for r in targets), "n": len(targets)},
            "exact_boards": {"hit": sum(all(r["expected"] == r["predicted"] for r in t["relations"]) for t in trials), "n": len(trials)},
            "by_attacking_piece": {kind: metrics([r for r in relations if r["source_kind"] == kind])
                                   for kind in pipeline.RULES}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("development", "evaluation"), required=True)
    parser.add_argument("--verify", action="store_true", help="Verify previously predicted attacks using new Jev judgments")
    args = parser.parse_args()
    original_path = pipeline.HERE / f"results_jev_attack_map_{args.split}.json"
    out = original_path.with_stem(original_path.stem + "_verified") if args.verify else original_path
    if out.exists():
        raise SystemExit(f"Preserving existing run: {out}")
    cases = json.loads(original_path.read_text())["trials"] if args.verify else pipeline.fixtures(args.split)
    random.Random(92263).shuffle(cases)
    trials = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        fn = verify_attack_map if args.verify else evaluate_board
        for future in as_completed([pool.submit(fn, case) for case in cases]):
            trials.append(future.result())
            print(f"{args.split}: {len(trials)}/{len(cases)} boards", flush=True)
    stages = [s for t in trials for s in t["verification_stages" if args.verify else "stages"]]
    result = {"model": pipeline.MODEL, "created_at": datetime.now(timezone.utc).isoformat(),
        "design": "All enemy pieces x all friendly pieces; attack map including pinned attackers, not legal captures; threshold fixed at .5; no candidate filtering by geometry or engine.",
        "verification": args.verify,
        "cost_scope": "New verification requests only; original requests are reused from saved results." if args.verify else "Initial all-pairs requests.",
        "split": args.split, "parents": len({t["index"] for t in trials}), "boards": len(trials),
        "batch_size": DEFAULT_BATCH_SIZE, "threshold": pipeline.THRESHOLD,
        "summary": summarize(trials), "requests": len(stages),
        "judgments": sum(len(s["probabilities"]) for s in stages),
        "input_tokens": sum(s["input_tokens"] for s in stages),
        "cost_usd": round(sum(s["input_tokens"] for s in stages) * 42 / 1e9, 6),
        "trials": sorted(trials, key=lambda t: (t["index"], t["kind"]))}
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "trials"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
