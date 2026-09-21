"""Sequential Jev layers for one piece-to-piece attack relation.

No chess geometry is computed during inference. Python exposes coordinates,
routes prior Jev choices into later questions, exhaustively supplies possible
blockers, and combines typed answers. Chess rules are used only after inference
for scoring the fixed diagnostic sample.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import json
import random
import time

import chess
from typesafe_sdk import Choice

import jev_attack_pipeline as pipeline
import jev_attack_polarity as polarity


HERE = Path(__file__).resolve().parent
DELTA_OPTIONS = {str(value): f"The signed difference is exactly {value}." for value in range(-7, 8)}
GEOMETRY_OPTIONS = {
    "valid": "The supplied coordinate differences satisfy this piece's attack movement rule.",
    "invalid": "The supplied coordinate differences do not satisfy this piece's attack movement rule.",
}
BETWEEN_OPTIONS = {
    "between": "The candidate square lies strictly between the two endpoints on their straight horizontal, vertical, or diagonal segment.",
    "not_between": "The candidate is an endpoint, off the endpoint line, or outside the open segment between them.",
}


def call_choices(request):
    started = time.perf_counter()
    response = pipeline.client().system_one(
        model=request["model"],
        state=request["state"],
        questions={key: Choice(instructions=value["instructions"], criteria=value["criteria"])
                   for key, value in request["questions"].items()},
    )
    answers = {}
    for key, value in response.answers.items():
        answers[key] = {"choice": value.choice, "probabilities": dict(value.probabilities),
                        "confidence": value.confidence}
    return {"request": request, "answers": answers, "resolved_model": response.model,
            "input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens,
            "latency_ms": round(1000 * (time.perf_counter() - started))}


def relation_inputs(sample):
    pieces = {piece["square"]: piece for piece in sample["state"]["pieces"]}
    return [(pieces[row["source"]], pieces[row["target"]]) for row in sample["relations"]]


def delta_request(sample):
    questions = {}
    for index, (source, target) in enumerate(relation_inputs(sample)):
        common = {"source": pipeline.piece_text(source), "target": pipeline.piece_text(target),
                  "coordinate_definition": "column and rank are integers shown in parentheses"}
        questions[f"r{index}_file_delta"] = {"type": "choice", "instructions": {
            **common, "question": "What is target column minus source column?"
        }, "criteria": DELTA_OPTIONS}
        questions[f"r{index}_rank_delta"] = {"type": "choice", "instructions": {
            **common, "question": "What is target rank minus source rank?"
        }, "criteria": DELTA_OPTIONS}
    return {"model": pipeline.MODEL, "state": "Integer coordinate subtraction for chessboard squares.",
            "questions": questions}


def geometry_request(sample, delta_stage):
    questions = {}
    for index, (source, target) in enumerate(relation_inputs(sample)):
        dx = int(delta_stage["answers"][f"r{index}_file_delta"]["choice"])
        dy = int(delta_stage["answers"][f"r{index}_rank_delta"]["choice"])
        questions[f"r{index}_geometry"] = {"type": "choice", "instructions": {
            "source_piece": pipeline.piece_text(source), "target_piece": pipeline.piece_text(target),
            "model_selected_file_delta": dx, "model_selected_rank_delta": dy,
            "movement_rule": pipeline.RULES[source["kind"]],
            "question": "Do the selected signed coordinate differences satisfy the source piece's attack movement rule? Ignore every other piece."
        }, "criteria": GEOMETRY_OPTIONS}
    return {"model": pipeline.MODEL, "state": "Apply the supplied chess movement rule to the earlier model's selected coordinate differences.",
            "questions": questions}


def blocker_request(sample, geometry_stage):
    questions = {}
    inputs = relation_inputs(sample)
    for index, (source, target) in enumerate(inputs):
        if source["kind"] not in pipeline.SLIDERS or geometry_stage["answers"][f"r{index}_geometry"]["choice"] != "valid":
            continue
        for obstacle in sample["state"]["pieces"]:
            if obstacle["square"] in (source["square"], target["square"]):
                continue
            questions[f"r{index}_obstacle_{obstacle['square']}"] = {"type": "choice", "instructions": {
                "endpoint_A": {"column": source["column"], "rank": source["rank"]},
                "endpoint_B": {"column": target["column"], "rank": target["rank"]},
                "candidate": {"square": obstacle["square"], "column": obstacle["column"], "rank": obstacle["rank"]},
                "rule": pipeline.SEGMENT_RULE,
                "question": "Is the candidate strictly inside the open straight segment from endpoint A to endpoint B?"
            }, "criteria": BETWEEN_OPTIONS}
    return {"model": pipeline.MODEL, "state": "Integer grid segment membership. Evaluate each candidate independently.",
            "questions": questions}


def blocker_picker_request(sample, geometry_stage):
    questions = {}
    for index, (source, target) in enumerate(relation_inputs(sample)):
        if source["kind"] not in pipeline.SLIDERS or geometry_stage["answers"][f"r{index}_geometry"]["choice"] != "valid":
            continue
        criteria = {piece["square"]: {"piece": pipeline.piece_text(piece),
                    "meaning": "Choose this if it lies strictly between the source and target."}
                    for piece in sample["state"]["pieces"] if piece["square"] not in (source["square"], target["square"])}
        criteria["none"] = "No occupied square lies strictly between source and target."
        questions[f"r{index}_blocker"] = {"type": "choice", "instructions": {
            "source": pipeline.piece_text(source), "target": pipeline.piece_text(target),
            "rule": pipeline.SEGMENT_RULE,
            "question": "Which option is an occupied square strictly between source and target? Choose none only if no listed piece is between them."
        }, "criteria": criteria}
    return {"model": pipeline.MODEL, "state": sample["state"], "questions": questions}


def infer(sample):
    delta = call_choices(delta_request(sample))
    geometry = call_choices(geometry_request(sample, delta))
    blocker_request_value = blocker_request(sample, geometry)
    blockers = call_choices(blocker_request_value) if blocker_request_value["questions"] else None
    picker_request = blocker_picker_request(sample, geometry)
    picker = call_choices(picker_request) if picker_request["questions"] else None
    outputs = []
    for index, (source, target) in enumerate(relation_inputs(sample)):
        dx = int(delta["answers"][f"r{index}_file_delta"]["choice"])
        dy = int(delta["answers"][f"r{index}_rank_delta"]["choice"])
        geometry_valid = geometry["answers"][f"r{index}_geometry"]["choice"] == "valid"
        between = []
        if blockers:
            prefix = f"r{index}_obstacle_"
            between = [key.removeprefix(prefix) for key, answer in blockers["answers"].items()
                       if key.startswith(prefix) and answer["choice"] == "between"]
        picker_choice = picker["answers"][f"r{index}_blocker"]["choice"] if picker and f"r{index}_blocker" in picker["answers"] else None
        exhaustive = geometry_valid and (source["kind"] not in pipeline.SLIDERS or not between)
        picker_prediction = geometry_valid and (source["kind"] not in pipeline.SLIDERS or picker_choice == "none")
        outputs.append({"source": source["square"], "source_kind": source["kind"],
                        "target": target["square"], "target_kind": target["kind"],
                        "selected_file_delta": dx, "selected_rank_delta": dy,
                        "geometry_valid": geometry_valid, "predicted_blockers": between,
                        "picker_choice": picker_choice,
                        "exhaustive_prediction": exhaustive, "picker_prediction": picker_prediction})
    stages = [delta, geometry] + ([blockers] if blockers else []) + ([picker] if picker else [])
    return {"relations": outputs, "stages": stages}


def geometry_truth(kind, color, dx, dy):
    ax, ay = abs(dx), abs(dy)
    if kind == "rook": return (dx == 0) != (dy == 0)
    if kind == "bishop": return ax == ay and ax > 0
    if kind == "queen": return ((dx == 0) != (dy == 0)) or (ax == ay and ax > 0)
    if kind == "knight": return (ax, ay) in ((1, 2), (2, 1))
    if kind == "king": return max(ax, ay) == 1
    return ax == 1 and dy == (1 if color == "White" else -1)


def between_truth(a, b, p):
    dx, dy = b["column"] - a["column"], b["rank"] - a["rank"]
    px, py = p["column"] - a["column"], p["rank"] - a["rank"]
    if not ((dx == 0) or (dy == 0) or (abs(dx) == abs(dy))): return False
    if dx == 0: return px == 0 and 0 < py / dy < 1
    if dy == 0: return py == 0 and 0 < px / dx < 1
    return px * dy == py * dx and 0 < px / dx < 1


def evaluate(sample):
    result = infer(sample)
    pieces = {piece["square"]: piece for piece in sample["state"]["pieces"]}
    for output, label in zip(result["relations"], sample["relations"]):
        source, target = pieces[output["source"]], pieces[output["target"]]
        true_dx, true_dy = target["column"] - source["column"], target["rank"] - source["rank"]
        output["expected_attack"] = label["expected"]
        output["true_file_delta"] = true_dx; output["true_rank_delta"] = true_dy
        output["file_delta_hit"] = output["selected_file_delta"] == true_dx
        output["rank_delta_hit"] = output["selected_rank_delta"] == true_dy
        output["true_geometry"] = geometry_truth(source["kind"], source["color"], true_dx, true_dy)
        output["geometry_hit"] = output["geometry_valid"] == output["true_geometry"]
        actual_blockers = [piece["square"] for piece in sample["state"]["pieces"]
                           if piece["square"] not in (source["square"], target["square"])
                           and between_truth(source, target, piece)] if output["true_geometry"] and source["kind"] in pipeline.SLIDERS else []
        output["true_blockers"] = actual_blockers
        output["blocker_set_hit"] = set(output["predicted_blockers"]) == set(actual_blockers)
        output["picker_hit"] = (output["picker_choice"] == "none" and not actual_blockers) or output["picker_choice"] in actual_blockers
        output["exhaustive_hit"] = output["exhaustive_prediction"] == label["expected"]
        output["picker_prediction_hit"] = output["picker_prediction"] == label["expected"]
    return {"index": sample["index"], **result}


def confusion(rows, field):
    return {"hit": sum(row[field] == row["expected_attack"] for row in rows), "n": len(rows),
            "tp": sum(row[field] and row["expected_attack"] for row in rows),
            "fp": sum(row[field] and not row["expected_attack"] for row in rows),
            "tn": sum(not row[field] and not row["expected_attack"] for row in rows),
            "fn": sum(not row[field] and row["expected_attack"] for row in rows)}


def main():
    path = HERE / "results_jev_attack_layers.json"
    if path.exists(): raise SystemExit(f"Preserving existing run: {path}")
    samples = polarity.samples(); random.Random(92264).shuffle(samples)
    with ThreadPoolExecutor(max_workers=4) as pool:
        trials = [future.result() for future in as_completed([pool.submit(evaluate, sample) for sample in samples])]
    rows = [row for trial in trials for row in trial["relations"]]
    picker_rows = [row for row in rows if row["picker_choice"] is not None]
    baseline = json.loads((HERE / "results_jev_attack_polarity.json").read_text())["summary"]
    stages = [stage for trial in trials for stage in trial["stages"]]
    result = {"created_at": datetime.now(timezone.utc).isoformat(), "model": pipeline.MODEL,
              "design": "Sequential Choice layers on the same balanced 40-relation polarity sample: signed deltas, movement geometry, exhaustive blocker membership, blocker picker. Truth used only after inference.",
              "summary": {"baseline_positive_noul": {"hit": baseline["positive_correct"], "n": 40},
                  "delta": {"file_hit": sum(r["file_delta_hit"] for r in rows), "rank_hit": sum(r["rank_delta_hit"] for r in rows), "n": 40},
                  "geometry": {"hit": sum(r["geometry_hit"] for r in rows), "n": 40},
                  "blockers": {"exact_set_hit": sum(r["blocker_set_hit"] for r in rows), "exact_set_n": len(rows),
                      "picker_hit": sum(r["picker_hit"] for r in picker_rows), "picker_n": len(picker_rows)},
                  "exhaustive_final": confusion(rows, "exhaustive_prediction"),
                  "picker_final": confusion(rows, "picker_prediction")},
              "requests": len(stages), "judgments": sum(len(s["answers"]) for s in stages),
              "input_tokens": sum(s["input_tokens"] for s in stages),
              "cost_usd": round(sum(s["input_tokens"] for s in stages) * 42 / 1e9, 6),
              "trials": sorted(trials, key=lambda t: t["index"])}
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "trials"}, ensure_ascii=False))


if __name__ == "__main__": main()
