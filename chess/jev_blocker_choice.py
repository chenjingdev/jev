"""Stress-test the blocker Choice layer on balanced clear/blocked rays."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import random
import time

import chess
from typesafe_sdk import Choice

import jev_attack_layers as layers
import jev_attack_pipeline as pipeline


def candidates():
    pool = {True: [], False: []}
    for split in ("development", "evaluation"):
        run = json.loads((pipeline.HERE / f"results_jev_attack_map_{split}.json").read_text())
        for trial in run["trials"]:
            if trial["kind"] != "check":
                continue
            state = trial["stages"][0]["request"]["state"]
            pieces = {p["square"]: p for p in state["pieces"]}
            for relation in trial["relations"]:
                source, target = pieces[relation["source"]], pieces[relation["target"]]
                dx, dy = target["column"] - source["column"], target["rank"] - source["rank"]
                if source["kind"] not in pipeline.SLIDERS or not layers.geometry_truth(source["kind"], source["color"], dx, dy):
                    continue
                blockers = [p["square"] for p in state["pieces"]
                            if p["square"] not in (source["square"], target["square"])
                            and layers.between_truth(source, target, p)]
                clear = not blockers
                pool[clear].append({"index": trial["index"], "state": state,
                    "source": source["square"], "target": target["square"], "clear": clear,
                    "blockers": blockers})
    selected = []
    for clear in (True, False):
        rows = pool[clear]
        random.Random(61300 + int(clear)).shuffle(rows)
        selected.extend(rows[:20])
    random.Random(61303).shuffle(selected)
    return selected


def request_for(row):
    pieces = {p["square"]: p for p in row["state"]["pieces"]}
    source, target = pieces[row["source"]], pieces[row["target"]]
    criteria = {p["square"]: {"piece": pipeline.piece_text(p),
                "meaning": "Choose this if it lies strictly between source and target."}
                for p in row["state"]["pieces"] if p["square"] not in (source["square"], target["square"])}
    criteria["none"] = "No occupied square lies strictly between source and target."
    return {"model": pipeline.MODEL, "state": row["state"], "questions": {"blocker": {
        "type": "choice", "instructions": {"source": pipeline.piece_text(source),
            "target": pipeline.piece_text(target), "rule": pipeline.SEGMENT_RULE,
            "question": "Which option is an occupied square strictly between source and target? Choose none only if no listed piece is between them."},
        "criteria": criteria}}}


def run_one(row):
    started = time.perf_counter(); request = request_for(row)
    question = request["questions"]["blocker"]
    response = pipeline.client().system_one(model=pipeline.MODEL, state=request["state"],
        questions={"blocker": Choice(instructions=question["instructions"], criteria=question["criteria"])})
    answer = response.answers["blocker"]
    hit = answer.choice == "none" if row["clear"] else answer.choice in row["blockers"]
    return {**row, "pick": answer.choice, "hit": hit,
            "probabilities": dict(answer.probabilities), "confidence": answer.confidence,
            "request": request, "resolved_model": response.model,
            "input_tokens": response.usage.input_tokens,
            "latency_ms": round(1000 * (time.perf_counter() - started))}


def main():
    path = pipeline.HERE / "results_jev_blocker_choice.json"
    if path.exists(): raise SystemExit(f"Preserving existing run: {path}")
    with ThreadPoolExecutor(max_workers=4) as pool:
        trials = [future.result() for future in as_completed([pool.submit(run_one, row) for row in candidates()])]
    clear = [t for t in trials if t["clear"]]; blocked = [t for t in trials if not t["clear"]]
    result = {"created_at": datetime.now(timezone.utc).isoformat(), "model": pipeline.MODEL,
              "design": "Balanced diagnostic: 20 geometrically aligned clear rays and 20 blocked rays, selected by reference geometry only for sampling. Labels/blockers never enter requests; every occupied non-endpoint square plus none is offered.",
              "summary": {"hit": sum(t["hit"] for t in trials), "n": len(trials),
                  "clear_none": sum(t["pick"] == "none" for t in clear), "clear_n": len(clear),
                  "blocked_correct_piece": sum(t["pick"] in t["blockers"] for t in blocked), "blocked_n": len(blocked)},
              "requests": len(trials), "judgments": len(trials),
              "cost_usd": round(sum(t["input_tokens"] for t in trials) * 42 / 1e9, 6),
              "trials": trials}
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k:v for k,v in result.items() if k != "trials"}, ensure_ascii=False))


if __name__ == "__main__": main()
