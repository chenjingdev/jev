"""Free tile choice: who orders the tiles so the puzzle gets solved, and in how many slides?

    uv run python sliding-puzzle/run_targets.py --grid 3x3 --no-jev     # 3×3: boards by optimal depth 8/12/16/20

    uv run python sliding-puzzle/run_targets.py --no-jev                                     # baselines, no key
    op run --env-file=sliding-puzzle/.env.tpl -- uv run python sliding-puzzle/run_targets.py   # → results_targets.json

A tile the executor cannot place (the fixed tiles trap it) ends the game unsolved, so the
metrics are solve rate, tiles placed before the failure, and slides on solved boards.
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


def human_order(g: P.Grid) -> list[int]:
    """Top rows left to right; the last two rows column by column (top then bottom); last 2×2."""
    order = list(range(1, (g.rows - 2) * g.cols + 1))
    r1, r2 = (g.rows - 2) * g.cols, (g.rows - 1) * g.cols
    for c in range(g.cols - 2):
        order += [r1 + c + 1, r2 + c + 1]
    return order + [r1 + g.cols - 1, r1 + g.cols, r2 + g.cols - 1]


def baseline(name, g, rng):
    if name == "human":
        h = human_order(g)
        return lambda b, c, k: next(t for t in h if t in c)
    if name == "fixed":
        return lambda b, c, k: min(c)
    if name == "closest":
        return lambda b, c, k: min(c, key=lambda t: (g.tile_facts(b, t)["distance"], t))
    if name == "random":
        return lambda b, c, k: rng.choice(c)
    raise ValueError(name)


def game(g, board, chooser, log):
    t0 = time.time()
    solved, moves, order, trace = g.play_targets(board, chooser)
    out = {"board": board, "solved": solved, "moves": moves, "placed": len([t for t in trace if t["slides"] is not None]),
           "order": order, "slides": [t["slides"] for t in trace], "seconds": round(time.time() - t0, 1)}
    if log is not None:
        out["latency_ms"] = [r["latency_ms"] for r in log if not r["forced"]]
        out["top_prob"] = [max(r["probabilities"].values()) for r in log if not r["forced"]]
        out["progress"] = [r["progress"] for r in log if not r["forced"]]
    return out


def run(name, g, boards, workers):
    if not name.startswith("jev"):
        ch = baseline(name, g, random.Random(7))
        return [game(g, b, ch, None) for b in boards]
    import brain

    def one(b):
        log = []
        ch = brain.target_chooser(g, numbers=("nonumbers" not in name), coached=("coached" in name), log=log)
        return game(g, b, ch, log)

    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(one, boards))


def summarize(games, human_order_list):
    solved = [x for x in games if x["solved"]]
    out = {"n": len(games), "solved": len(solved), "placed_median": statistics.median(x["placed"] for x in games),
           "placed_mean": round(statistics.mean(x["placed"] for x in games), 1)}
    if solved:
        out["moves_median"] = statistics.median(x["moves"] for x in solved)
        out["moves_mean"] = round(statistics.mean(x["moves"] for x in solved), 1)
    # how human-like the order was: fraction of decisions that matched the human order's next tile
    agree = []
    for x in games:
        done = set()
        for t in x["order"]:
            nxt = next(h for h in human_order_list if h not in done)
            agree.append(t == nxt)
            done.add(t)
    out["agree_human"] = round(sum(agree) / len(agree), 2) if agree else None
    lat = [l for x in games for l in x.get("latency_ms", [])]
    if lat:
        out["calls"] = len(lat)
        out["latency_median_ms"] = statistics.median(lat)
        out["latency_p95_ms"] = sorted(lat)[int(len(lat) * 0.95)]
        out["top_prob_median"] = statistics.median(p for x in games for p in x["top_prob"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boards", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--no-jev", action="store_true")
    ap.add_argument("--conditions", default="human,fixed,closest,random,jev,jev-coached,jev-nonumbers")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--grid", default="5x6", help="5x6 (random solvable boards) or 3x3 (15 boards per optimal depth 8/12/16/20)")
    args = ap.parse_args()
    rows, cols = (int(v) for v in args.grid.split("x"))
    g = P.Grid(rows, cols)
    rng = random.Random(args.seed)
    boards = [g.scramble(d, rng) for d in (8, 12, 16, 20) for _ in range(15)] if g.cells <= 9 else [g.shuffle(rng) for _ in range(args.boards)]
    out_name = f"results_{rows}x{cols}_tiles.json"
    conds = [c for c in args.conditions.split(",") if not (args.no_jev and c.startswith("jev"))]
    results = {"date": time.strftime("%Y-%m-%d"), "grid": [g.rows, g.cols], "boards": len(boards), "seed": args.seed,
               "manhattan_mean": round(statistics.mean(g.manhattan(b) for b in boards), 1), "conditions": {}}
    if args.keep and (HERE / out_name).exists():
        results = json.loads((HERE / out_name).read_text())
    for c in conds:
        t0 = time.time()
        games = run(c, g, boards, args.workers)
        s = summarize(games, human_order(g))
        results["conditions"][c] = {"summary": s, "games": games}
        print(f"{c:14s} solved {s['solved']}/{s['n']}  placed median {s['placed_median']}  "
              f"moves {s.get('moves_median', '-')}  agree human {s['agree_human']}"
              + (f"  calls {s['calls']} latency {s['latency_median_ms']}ms" if "calls" in s else "") + f"  ({time.time() - t0:.0f}s)")
        (HERE / out_name).write_text(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
