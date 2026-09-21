"""Verify Jev-proposed escape destinations using only further Jev layers."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import argparse
import json
import random

from typesafe_sdk import Choice

import jev_attack_layers as attack_layers
import jev_attack_pipeline as pipeline
import jev_escape_choice as chooser
from jev_mate_pipeline import MOVE_RULES


MOVE_OPTIONS = {
    "valid": "The source piece can move to the destination by its movement and capture rules, considering destination occupancy but ignoring intermediate blockers and later king safety.",
    "invalid": "The movement shape or destination occupancy makes this move invalid even before checking intermediate blockers or later king safety.",
}


def source_trials(split, source="choice"):
    return json.loads((pipeline.HERE / f"results_jev_escape_{source}_{split}.json").read_text())["trials"]


def verification_input(trial):
    # Copy only model-visible state and model proposals. Ground truth fields stay out.
    state = deepcopy(trial["stage"]["request"]["state"])
    proposals = [{"source": p["source"], "destination": p["destination"]}
                 for p in trial["proposals"] if p["destination"] != "none"]
    return {"state": state, "proposals": proposals}


def delta_request(data):
    pieces = {p["square"]: p for p in data["state"]["pieces"]}
    questions = {}
    for index, proposal in enumerate(data["proposals"]):
        source = pieces[proposal["source"]]; target = proposal["destination"]
        target_data = {"square": target, "column": ord(target[0]) - 96, "rank": int(target[1])}
        common = {"source": pipeline.piece_text(source), "target": target_data}
        questions[f"p{index}_file_delta"] = {"type": "choice", "instructions": {
            **common, "question": "What is target column minus source column?"},
            "criteria": attack_layers.DELTA_OPTIONS}
        questions[f"p{index}_rank_delta"] = {"type": "choice", "instructions": {
            **common, "question": "What is target rank minus source rank?"},
            "criteria": attack_layers.DELTA_OPTIONS}
    return {"model": pipeline.MODEL, "state": "Integer coordinate subtraction for chess moves.", "questions": questions}


def movement_request(data, delta):
    state = data["state"]; pieces = {p["square"]: p for p in state["pieces"]}
    questions = {}
    for index, proposal in enumerate(data["proposals"]):
        source = pieces[proposal["source"]]; destination = proposal["destination"]
        occupant = pieces.get(destination)
        questions[f"p{index}_movement"] = {"type": "choice", "instructions": {
            "piece": pipeline.piece_text(source), "destination": destination,
            "destination_occupant": pipeline.piece_text(occupant) if occupant else "empty",
            "model_selected_file_delta": int(delta["answers"][f"p{index}_file_delta"]["choice"]),
            "model_selected_rank_delta": int(delta["answers"][f"p{index}_rank_delta"]["choice"]),
            "movement_rule": MOVE_RULES[source["kind"]],
            "castling_rights": state["castling_rights"], "en_passant_target": state["en_passant_target"],
            "question": "Is the selected move valid by movement shape and destination occupancy? Ignore intermediate blockers and whether the king is safe after the move; those are checked later. Capturing a king or friendly piece is invalid."
        }, "criteria": MOVE_OPTIONS}
    return {"model": pipeline.MODEL, "state": state, "questions": questions}


def blocker_request(data, movement):
    state = data["state"]; pieces = {p["square"]: p for p in state["pieces"]}; questions = {}
    for index, proposal in enumerate(data["proposals"]):
        source = pieces[proposal["source"]]; destination = proposal["destination"]
        if source["kind"] not in pipeline.SLIDERS or movement["answers"][f"p{index}_movement"]["choice"] != "valid":
            continue
        target = {"square": destination, "column": ord(destination[0])-96, "rank": int(destination[1])}
        criteria = {p["square"]: {"piece": pipeline.piece_text(p), "meaning": "Choose if strictly between source and destination."}
                    for p in state["pieces"] if p["square"] not in (source["square"], destination)}
        criteria["none"] = "No occupied square lies strictly between source and destination."
        questions[f"p{index}_blocker"] = {"type": "choice", "instructions": {
            "source": pipeline.piece_text(source), "destination": target,
            "rule": pipeline.SEGMENT_RULE,
            "question": "Which option is an occupied square strictly between source and destination? Choose none only if no listed piece is between them."
        }, "criteria": criteria}
    return {"model": pipeline.MODEL, "state": state, "questions": questions}


def transformed_state(state, source_square, destination):
    """Uniformly apply coordinates; this does not decide whether the move is legal."""
    result = deepcopy(state); pieces = result["pieces"]
    moving = next(p for p in pieces if p["square"] == source_square)
    pieces[:] = [p for p in pieces if p["square"] not in (source_square, destination)]
    moving = deepcopy(moving); moving.update({"square": destination,
        "column": ord(destination[0]) - 96, "rank": int(destination[1])})
    if moving["kind"] == "pawn" and moving["rank"] in (1, 8): moving["kind"] = "queen"
    pieces.append(moving); pieces.sort(key=lambda p: p["square"])
    result["side_to_move"] = "Black" if state["side_to_move"] == "White" else "White"
    return result


def king_attack_sample(state_after, original_side):
    king = next(p for p in state_after["pieces"] if p["color"] == original_side and p["kind"] == "king")
    relations = [{"source": p["square"], "target": king["square"]}
                 for p in state_after["pieces"] if p["color"] != original_side]
    return {"state": state_after, "relations": relations}


def verify_trial(trial):
    data = verification_input(trial)
    if not data["proposals"]:
        return {"index": trial.get("index"), "kind": trial.get("kind"), "fen": trial["fen"],
                "expected_mate": trial.get("expected_mate"), "verified": [],
                "verified_escape_predicted": False, "verified_mate_predicted": True, "stages": []}
    delta = attack_layers.call_choices(delta_request(data))
    movement = attack_layers.call_choices(movement_request(data, delta))
    blocker_req = blocker_request(data, movement)
    blockers = attack_layers.call_choices(blocker_req) if blocker_req["questions"] else None
    verified=[]; attack_stages=[]; state=data["state"]
    for index, proposal in enumerate(data["proposals"]):
        move_valid = movement["answers"][f"p{index}_movement"]["choice"] == "valid"
        source = next(p for p in state["pieces"] if p["square"] == proposal["source"])
        blocker_choice = None
        if source["kind"] in pipeline.SLIDERS and move_valid:
            blocker_choice = blockers["answers"][f"p{index}_blocker"]["choice"]
            move_valid = blocker_choice == "none"
        attacked = None
        if move_valid:
            after = transformed_state(state, proposal["source"], proposal["destination"])
            attack_result = attack_layers.infer(king_attack_sample(after, state["side_to_move"]))
            attack_stages.extend(attack_result["stages"])
            attacked = any(r["picker_prediction"] for r in attack_result["relations"])
        verified.append({**proposal, "movement_valid": move_valid, "blocker_choice": blocker_choice,
                         "king_attacked_after": attacked,
                         "verified_escape": move_valid and attacked is False})
    any_escape=any(v["verified_escape"] for v in verified)
    return {"index": trial.get("index"), "kind": trial.get("kind"), "fen": trial["fen"],
            "expected_mate": trial.get("expected_mate"), "verified": verified,
            "verified_escape_predicted": any_escape, "verified_mate_predicted": not any_escape,
            "stages": [delta,movement]+([blockers] if blockers else [])+attack_stages}


def infer_mate(fen):
    """Run the fair Jev-only inference path with no reference label available."""
    chosen = chooser.run_one({"fen": fen})
    verified = verify_trial(chosen)
    return {"mate": verified["verified_mate_predicted"],
            "escape": verified["verified_escape_predicted"],
            "proposals": verified["verified"], "stages": [chosen["stage"], *verified["stages"]]}


def infer_mate_beam(fen):
    """Full fair path: 64-square Choice, Jev top-10 refinement, Jev verification."""
    import jev_escape_beam as beam
    chosen = chooser.run_one({"fen": fen})
    refined = beam.run_one(chosen)
    verified = verify_trial(refined)
    return {"mate": verified["verified_mate_predicted"],
            "escape": verified["verified_escape_predicted"],
            "proposals": verified["verified"],
            "stages": [chosen["stage"], refined["stage"], *verified["stages"]]}


def score(result):
    import chess
    board=chess.Board(result["fen"]); legal={(chess.square_name(m.from_square),chess.square_name(m.to_square)) for m in board.legal_moves}
    for proposal in result["verified"]:
        proposal["true_escape"]=(proposal["source"],proposal["destination"]) in legal
    result["hit"]=result["verified_mate_predicted"]==result["expected_mate"]
    return result


def summary(rows):
    proposals=[p for r in rows for p in r["verified"]]; mates=[r for r in rows if r["expected_mate"]]; checks=[r for r in rows if not r["expected_mate"]]
    return {"boards":{"hit":sum(r["hit"] for r in rows),"n":len(rows),
                      "mate_correct":sum(r["hit"] for r in mates),"mate_n":len(mates),
                      "check_only_correct":sum(r["hit"] for r in checks),"check_only_n":len(checks)},
            "proposals":{"n":len(proposals),"movement_valid":sum(p["movement_valid"] for p in proposals),
                         "verified_escape":sum(p["verified_escape"] for p in proposals),
                         "true_escape":sum(p["true_escape"] for p in proposals),
                         "verified_true_escape":sum(p["verified_escape"] and p["true_escape"] for p in proposals),
                         "verified_false_escape":sum(p["verified_escape"] and not p["true_escape"] for p in proposals)}}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--split",choices=("development","evaluation"),required=True)
    parser.add_argument("--source",choices=("choice","beam"),default="choice");args=parser.parse_args()
    suffix="" if args.source=="choice" else "_beam"
    path=pipeline.HERE/f"results_jev_escape_verify_{args.split}{suffix}.json"
    if path.exists():raise SystemExit(f"Preserving existing run: {path}")
    rows=source_trials(args.split,args.source);random.Random(92266).shuffle(rows)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=[score(f.result()) for f in as_completed([pool.submit(verify_trial,row) for row in rows])]
    stages=[s for r in results for s in r["stages"]]
    output={"created_at":datetime.now(timezone.utc).isoformat(),"model":pipeline.MODEL,"split":args.split,
            "source":args.source,
            "design":"Verify Jev-selected non-none destinations using sequential Jev Choices for deltas, movement/destination validity, slider blocker, and per-opponent attack relation after a uniform state transform. No legal moves or derived truth enter requests.",
            "summary":summary(results),"requests":len(stages),"judgments":sum(len(s["answers"]) for s in stages),
            "input_tokens":sum(s["input_tokens"] for s in stages),"cost_usd":round(sum(s["input_tokens"] for s in stages)*42/1e9,6),
            "trials":sorted(results,key=lambda r:(r["index"],r["kind"]))}
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in output.items() if k!="trials"},ensure_ascii=False))


if __name__=="__main__":main()
