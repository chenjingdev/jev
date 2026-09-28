"""Read-only reanalysis of saved Go experiments; no API or engine calls.

Run from the repository root:
  .venv/bin/python go/reports/audit_methodology_20260922.py > /tmp/go-methodology-audit.json
Requires NumPy. Percentile cluster bootstrap, 50,000 samples, fixed seed.
"""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

GO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GO))
from make_openings import transforms

canonical = transforms()
hashes = {}


def read(name):
    path = GO / "matches" / name
    raw = path.read_bytes()
    hashes[name] = hashlib.sha256(raw).hexdigest()
    return json.loads(raw)


def bootstrap(values, keys):
    """Resample whole opening families, retaining every row and its weight."""
    groups = defaultdict(list)
    for value, key in zip(values, keys):
        groups[key].append(value)
    totals = np.array([[sum(v), len(v)] for v in groups.values()])
    rng = np.random.default_rng(20260922)
    indices = rng.integers(0, len(totals), (50000, len(totals)))
    sampled = totals[indices].sum(axis=1)
    means = sampled[:, 0] / sampled[:, 1]
    return {
        "rows": len(values), "clusters": len(groups),
        "estimate": float(np.mean(values)),
        "ci95_percentile": np.quantile(means, [.025, .975]).tolist(),
    }


positions = read("discrim-103.json")["positions"]
reversed_rows = {r["id"]: r for r in read("discrim-103-reversed.json")["rows"]}
assert set(reversed_rows) == {p["id"] for p in positions}
scores = {}
for condition in ("bare", "reasons", "status"):
    values = []
    for p in positions:
        forward = p["answers"][condition]
        reverse = reversed_rows[p["id"]]["reversed_answers"][condition]
        assert forward["order_shown"] == list(reversed(reverse["order_shown"]))
        values.append((int(forward["choice"] == p["winning_move"])
                       + int(reverse["choice"] == p["winning_move"])) / 2)
    scores[condition] = np.array(values)

opening_sequences = [tuple(v for _, v, queried in p["prefix"] if not queried) for p in positions]
keys = [canonical(moves) for moves in opening_sequences]
engine = np.array([p["engine_move"] == p["winning_move"] for p in positions])
random_ids = [i for i, p in enumerate(positions) if p["run"] == "l1rand-100"]
out = {
    "method": "Average the two option orders per position; resample complete symmetry-canonical opening families. Exploratory, outcome-selected sample; CIs do not establish population generalization.",
    "bootstrap_seed": 20260922, "bootstrap_samples": 50000,
    "position_count": len(positions),
    "distinct_exact_openings": len(set(opening_sequences)),
    "distinct_opening_families": len(set(keys)),
    "original_candidate_counts": dict(Counter(len(p["shortlist"]) for p in positions)),
    "accuracy": {c: bootstrap(v, keys) for c, v in scores.items()},
    "reasons_minus_bare": bootstrap(scores["reasons"] - scores["bare"], keys),
    "status_minus_reasons": bootstrap(scores["status"] - scores["reasons"], keys),
    "reasons_minus_engine": bootstrap(scores["reasons"] - engine, keys),
    "random_origin_accuracy": {c: float(v[random_ids].mean()) for c, v in scores.items()},
    "random_origin_gain": bootstrap((scores["reasons"] - scores["bare"])[random_ids], [keys[i] for i in random_ids]),
}
runs = {n: read(f"{n}.json") for n in ("l1jev-100", "l1jev-100b", "l1rand-100")}
pair_scores = {n: {r["pair"]: r["hybrid_points"] / 2 for r in d["analysis"]["pairs"]} for n, d in runs.items()}
opening_keys = {g["pair"]: canonical(g["opening"]) for g in runs["l1rand-100"]["games"]}
out["match_accuracy"] = {n: bootstrap(list(s.values()), [opening_keys[i] for i in s]) for n, s in pair_scores.items()}
out["paired_match_difference_vs_random"] = {}
for n in ("l1jev-100", "l1jev-100b"):
    ids = sorted(pair_scores[n].keys() & pair_scores["l1rand-100"].keys())
    out["paired_match_difference_vs_random"][n] = bootstrap(
        [pair_scores[n][i] - pair_scores["l1rand-100"][i] for i in ids],
        [opening_keys[i] for i in ids],
    )
same_result = same_moves = count = 0
for i in sorted(pair_scores["l1jev-100"].keys() & pair_scores["l1jev-100b"].keys()):
    first = read(f"l1jev-100/op-{i:03d}.json")
    second = read(f"l1jev-100b/op-{i:03d}.json")
    for a, b in zip(first["games"], second["games"]):
        count += 1
        same_result += a["winner"] == b["winner"]
        same_moves += [m["move"] for m in a["moves"]] == [m["move"] for m in b["moves"]]
out["replicate_overlap"] = {"matched_games": count, "same_winner": same_result, "identical_move_sequence": same_moves}
out["source_sha256"] = hashes
print(json.dumps(out, ensure_ascii=False, indent=2))
