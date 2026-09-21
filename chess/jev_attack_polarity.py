"""Check opposite Noul propositions on the same piece pairs, without label input."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from copy import deepcopy
import json
import random

import jev_attack_map as graph
import jev_attack_pipeline as pipeline


def samples():
    """One true attack and one non-attack per parent, same source piece.

    Select using reference labels, not Jev probabilities. Labels are used only
    to assemble a balanced diagnostic test; all model input is copied unlabeled.
    """
    boards = []
    for split in ("development", "evaluation"):
        result = json.loads((pipeline.HERE / f"results_jev_attack_map_{split}.json").read_text())
        boards.extend(t for t in result["trials"] if t["kind"] == "check")
    selected = []
    for board in sorted(boards, key=lambda b: b["index"]):
        rng = random.Random(44019 + board["index"])
        positive = rng.choice([r for r in board["relations"] if r["expected"]])
        negative = rng.choice([r for r in board["relations"] if not r["expected"] and r["source"] == positive["source"]])
        selected.append({"index": board["index"], "state": board["stages"][0]["request"]["state"],
                         "relations": [positive, negative]})
    return selected


def request_for(sample):
    state = sample["state"]
    lookup = {p["square"]: p for p in state["pieces"]}
    questions = {}
    for i, relation in enumerate(sample["relations"]):
        source, target = lookup[relation["source"]], lookup[relation["target"]]
        positive = graph.pair_question(source, target)
        negative = deepcopy(positive)
        negative["instructions"]["question"] = (
            f"{pipeline.piece_text(source)} does NOT currently attack {pipeline.piece_text(target)}. "
            "Is this statement true?"
        )
        questions[f"r{i}_positive"] = positive
        questions[f"r{i}_negative"] = negative
    return {"model": pipeline.MODEL, "state": state, "questions": questions}


def run_one(sample):
    result = pipeline.call(request_for(sample))
    rows = []
    for i, relation in enumerate(sample["relations"]):
        p = result["probabilities"][f"r{i}_positive"]
        q = result["probabilities"][f"r{i}_negative"]
        rows.append({"source": relation["source"], "target": relation["target"],
            "expected_attack": relation["expected"], "positive_probability": p, "negative_probability": q,
            "positive_verdict": p >= .5, "negative_verdict": q >= .5,
            "both_yes": p >= .5 and q >= .5, "both_no": p < .5 and q < .5,
            "opposite_verdicts": (p >= .5) != (q >= .5), "probability_sum": p + q})
    return {"index": sample["index"], "relations": rows, "call": result}


def main():
    path = pipeline.HERE / "results_jev_attack_polarity.json"
    if path.exists():
        raise SystemExit(f"Preserving existing run: {path}")
    with ThreadPoolExecutor(max_workers=4) as pool:
        trials = [future.result() for future in as_completed([pool.submit(run_one, sample) for sample in samples()])]
    rows = [r for t in trials for r in t["relations"]]
    stats = {"pairs": len(rows), "true_attacks": sum(r["expected_attack"] for r in rows),
             "positive_correct": sum(r["positive_verdict"] == r["expected_attack"] for r in rows),
             "negative_correct": sum(r["negative_verdict"] != r["expected_attack"] for r in rows),
             "both_yes": sum(r["both_yes"] for r in rows), "both_no": sum(r["both_no"] for r in rows),
             "opposite_verdicts": sum(r["opposite_verdicts"] for r in rows),
             "mean_sum_error": sum(abs(r["probability_sum"] - 1) for r in rows) / len(rows)}
    for label, truth in (("attack", True), ("nonattack", False)):
        group = [r for r in rows if r["expected_attack"] == truth]
        stats[label] = {"n": len(group),
            "positive_yes": sum(r["positive_verdict"] for r in group),
            "negative_yes": sum(r["negative_verdict"] for r in group)}
    result = {"created_at": datetime.now(timezone.utc).isoformat(), "model": pipeline.MODEL,
              "design": "Balanced 20 attacks and 20 same-source non-attacks; one pair of targets per parent. Truth labels select samples only, never enter API requests. Positive and negative propositions evaluated independently. This is a diagnostic subset, not full-map accuracy.",
              "summary": stats, "requests": len(trials), "judgments": 2 * len(rows),
              "cost_usd": round(sum(t["call"]["input_tokens"] for t in trials) * 42 / 1e9, 6),
              "trials": sorted(trials, key=lambda t: t["index"])}
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "trials"}))


if __name__ == "__main__":
    main()
