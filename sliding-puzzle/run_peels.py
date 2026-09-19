"""Peel-mode trials on 5×6: which line to peel next, and how many slides it costs.

    uv run python sliding-puzzle/run_peels.py --no-jev                                     # baselines, no key
    op run --env-file=sliding-puzzle/.env.tpl -- uv run python sliding-puzzle/run_peels.py   # → results_peels.json

Every order solves every board, so the metric is total slides. `oracle` is the best of the
35 fixed orders per board (hindsight); `myopic` peels whichever line is cheaper right now.
"""

from __future__ import annotations

import argparse
import itertools
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


def fixed_order(seq):
    def ch(board, region, lines):
        return {"r": "row", "c": "col"}[seq[region[0] + region[1]]]
    return ch


def myopic(g):
    def ch(board, region, lines):
        keep = frozenset(t for t in range(1, g.cells) if board[t - 1] == t and (g.rc(t - 1)[0] < region[0] or g.rc(t - 1)[1] < region[1]))
        return min(lines, key=lambda k: len(P.peel(g, board, keep, lines[k])[2]))
    return ch


def game(g, board, chooser, log=None):
    t0 = time.time()
    moves, order, trace = P.play_peels(g, board, chooser)
    out = {"board": board, "moves": moves, "order": order, "slides": [t["slides"] for t in trace], "seconds": round(time.time() - t0, 1)}
    if log is not None:
        out["latency_ms"] = [r["latency_ms"] for r in log]
        out["top_prob"] = [max(r["probabilities"].values()) for r in log]
        out["progress"] = [r["progress"] for r in log]
        # did Jev pick the line that is cheaper right now?
        agree = []
        keep, region = frozenset(), (0, 0)
        b = board
        for r, step in zip(log, [t for t in trace if not t["forced"]]):
            lines = P.region_lines(g, region)
            costs = {k: len(P.peel(g, b, keep, lines[k])[2]) for k in lines}
            agree.append(costs[r["choice"]] == min(costs.values()))
            b, keep, _ = P.peel(g, b, keep, lines[r["choice"]])
            region = (region[0] + 1, region[1]) if r["choice"] == "row" else (region[0], region[1] + 1)
        out["agree_myopic"] = agree
    return out


def run(name, g, boards, workers):
    if name == "oracle":
        seqs = ["".join(s) for s in set(itertools.permutations("rrrcccc"))]
        games = []
        for b in boards:
            best = min((game(g, b, fixed_order(s)) for s in seqs), key=lambda x: x["moves"])
            games.append(best)
        return games
    if name == "rows-first":
        return [game(g, b, fixed_order("rrrcccc")) for b in boards]
    if name == "cols-first":
        return [game(g, b, fixed_order("ccccrrr")) for b in boards]
    if name == "random":
        rng = random.Random(7)
        return [game(g, b, lambda bd, r, l: rng.choice(list(l))) for b in boards]
    if name == "myopic":
        return [game(g, b, myopic(g)) for b in boards]
    if name == "distance":  # the line with the smaller total distance from home, ties → row
        return [game(g, b, lambda bd, r, l: min(l, key=lambda k: (P.line_facts(g, bd, l[k])["distance_total"], k != "row"))) for b in boards]
    import brain

    def one(b):
        log = []
        return game(g, b, brain.peel_chooser(g, numbers=("nonumbers" not in name), hinted=("hinted" in name), log=log), log)

    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(one, boards))


def summarize(games):
    out = {"n": len(games), "moves_mean": round(statistics.mean(x["moves"] for x in games), 1),
           "moves_median": statistics.median(x["moves"] for x in games)}
    lat = [l for x in games for l in x.get("latency_ms", [])]
    if lat:
        out["calls"] = len(lat)
        out["latency_median_ms"] = statistics.median(lat)
        out["latency_p95_ms"] = sorted(lat)[int(len(lat) * 0.95)]
        out["top_prob_median"] = statistics.median(p for x in games for p in x["top_prob"])
        ag = [a for x in games for a in x["agree_myopic"]]
        out["agree_myopic"] = round(sum(ag) / len(ag), 2)
        out["row_share"] = round(sum(o == "row" for x in games for o in x["order"]) / sum(len(x["order"]) for x in games), 2)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boards", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--no-jev", action="store_true")
    ap.add_argument("--conditions", default="oracle,myopic,distance,rows-first,cols-first,random,jev,jev-hinted,jev-nonumbers")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    g = P.Grid()
    rng = random.Random(args.seed)
    boards = [g.shuffle(rng) for _ in range(args.boards)]
    conds = [c for c in args.conditions.split(",") if not (args.no_jev and c.startswith("jev"))]
    results = {"date": time.strftime("%Y-%m-%d"), "grid": [g.rows, g.cols], "boards": len(boards), "seed": args.seed,
               "manhattan_mean": round(statistics.mean(g.manhattan(b) for b in boards), 1), "conditions": {}}
    if args.keep and (HERE / "results_peels.json").exists():
        results = json.loads((HERE / "results_peels.json").read_text())
    for c in conds:
        t0 = time.time()
        games = run(c, g, boards, args.workers)
        s = summarize(games)
        results["conditions"][c] = {"summary": s, "games": games}
        print(f"{c:14s} slides mean {s['moves_mean']} median {s['moves_median']}"
              + (f"  agree myopic {s['agree_myopic']} rows {s['row_share']} calls {s['calls']} latency {s['latency_median_ms']}ms" if "calls" in s else "")
              + f"  ({time.time() - t0:.0f}s)")
        (HERE / "results_peels.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
