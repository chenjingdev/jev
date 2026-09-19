"""v1 reflex mode on 3×3: who solves the board one slide at a time - random, greedy, Jev, Jev without numbers.

    op run --env-file=sliding-puzzle/.env.tpl -- uv run python sliding-puzzle/run_trials.py
    uv run python sliding-puzzle/run_trials.py --no-jev          # baselines only, no key

Boards are drawn by optimal distance (8/12/16/20 moves), the same boards for every condition.
Writes results.json: per-condition solve rate, median moves and moves/optimal, and every game.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import puzzle as P  # noqa: E402

HERE = Path(__file__).resolve().parent
DEPTHS = (8, 12, 16, 20)
G = P.Grid(3, 3)


def run_baseline(name, boards, cap, seed):
    rng = random.Random(seed)
    games = []
    for depth, b in boards:
        if name == "random":
            pick = lambda bd, last, seen: rng.choice(list(G.moves(bd)))  # noqa: E731
        else:
            pick = lambda bd, last, seen: P.greedy_pick(G, bd, last, seen, rng, veto_seen=(name == "greedy+veto"))  # noqa: E731
        ok, n, path = P.play(G, b, pick, cap)
        games.append({"depth": depth, "board": b, "solved": ok, "moves": n})
    return games


def best_available(r):
    """True/False if Jev took a lowest-distance option; None if all options tied."""
    best = min(f["distance"] for f in r["candidates"].values())
    good = [d for d, f in r["candidates"].items() if f["distance"] == best]
    if len(good) == len(r["candidates"]):
        return None
    return r["played"] in good


def run_jev(name, boards, cap, workers):
    import brain

    numbers = name != "jev-nonumbers"

    def one(item):
        depth, b = item
        history, log = [], []
        t0 = time.time()
        sample = random.Random(hash(b)) if name == "jev-sample" else None
        ok, n, path = P.play(G, b, brain.picker(G, history, numbers=numbers, log=log, sample=sample), cap)
        return {
            "depth": depth, "board": b, "solved": ok, "moves": n, "seconds": round(time.time() - t0, 1),
            "latency_ms": [r["latency_ms"] for r in log if not r["forced"]],
            "forced": sum(1 for r in log if r["forced"]),
            "looping": [r["looping"] for r in log if not r["forced"]],
            "vetoed": sum(1 for r in log if r.get("vetoed")),
            "top_prob": [max(r["probabilities"].values()) for r in log if not r["forced"]],
            "distance_delta": [r["candidates"][r["played"]]["distance_delta"] for r in log],
            "revisit": [bool(r["candidates"][r["played"]]["seen"]) for r in log if not r["forced"]],
            "took_best": [best_available(r) for r in log if not r["forced"]],
            "path": path,
        }

    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(one, boards))


def summarize(games):
    out = {}
    for depth in [None, *DEPTHS]:
        g = [x for x in games if depth is None or x["depth"] == depth]
        solved = [x for x in g if x["solved"]]
        row = {"n": len(g), "solved": len(solved), "rate": round(len(solved) / len(g), 2) if g else None}
        if solved:
            row["median_moves"] = statistics.median(x["moves"] for x in solved)
            row["median_ratio"] = round(statistics.median(x["moves"] / x["depth"] for x in solved), 2)
        out["all" if depth is None else str(depth)] = row
    tb = [t for x in games for t in x.get("took_best", []) if t is not None]
    if tb:
        out["took_best_rate"] = round(sum(tb) / len(tb), 2)
        out["took_best_n"] = len(tb)
    lat = [l for x in games for l in x.get("latency_ms", [])]
    if lat:
        out["calls"] = len(lat)
        out["latency_median_ms"] = statistics.median(lat)
        out["latency_p95_ms"] = sorted(lat)[int(len(lat) * 0.95)]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-depth", type=int, default=15)
    ap.add_argument("--cap", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--no-jev", action="store_true")
    ap.add_argument("--conditions", default="random,greedy,greedy+veto,jev,jev-sample,jev-nonumbers")
    ap.add_argument("--keep", action="store_true", help="merge into the existing results.json instead of starting over")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    boards = [(d, G.scramble(d, rng)) for d in DEPTHS for _ in range(args.per_depth)]
    conditions = [c for c in args.conditions.split(",") if not (args.no_jev and c.startswith("jev"))]

    results = {"date": time.strftime("%Y-%m-%d"), "boards": len(boards), "cap": args.cap, "seed": args.seed, "conditions": {}}
    if args.keep and (HERE / "results.json").exists():
        results = json.loads((HERE / "results.json").read_text())
    for c in conditions:
        t0 = time.time()
        games = run_baseline(c, boards, args.cap, args.seed) if not c.startswith("jev") else run_jev(c, boards, args.cap, args.workers)
        s = summarize(games)
        results["conditions"][c] = {"summary": s, "games": games}
        print(f"{c:15s} solved {s['all']['solved']}/{s['all']['n']}  "
              + "  ".join(f"d{d}:{s[str(d)]['solved']}/{s[str(d)]['n']}" for d in DEPTHS)
              + f"  median moves {s['all'].get('median_moves')}  ratio {s['all'].get('median_ratio')}"
              + (f"  took best {s['took_best_rate']}" if "took_best_rate" in s else "") + f"  ({time.time() - t0:.0f}s)")
        (HERE / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
