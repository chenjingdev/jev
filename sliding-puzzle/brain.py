"""What Jev is asked. Two modes.

Jev has no eyes (experiments/vision), so the code does the looking and Jev points.

Target mode (5×6, the current one): Jev picks **which tile to bring home next**; the code
brings it home with a BFS (puzzle.Grid.bring_home) and that tile becomes a wall. Jev sees
cheap facts about every remaining tile - where it is, where its home is, how far - and
never the BFS cost (that would make it a number comparator again, see reflex mode).
One `sif.ask()` per decision: `target` Choice + `progress` Score.

Reflex mode (3×3, v1): Jev picks the next slide from 1-3 candidates described by
distance and tiles-home numbers. It followed the numbers 1,149/1,151 times and lost only
on tie-breaking; kept for the README's first chapter.
"""

from __future__ import annotations

import random
import time

import sif

import puzzle as P

PROGRESS_LEVELS = ["scrambled", "some tiles home", "top rows done", "almost solved"]
PROGRESS_INSTRUCTIONS = "How close is the board to solved?"

# ---- target mode ------------------------------------------------------------

TARGET_INSTRUCTIONS = (
    "Sliding puzzle. The code will bring the chosen tile to its home square with the fewest slides "
    "and then keep it there; tiles already home stay fixed. Pick the tile to bring home next so that "
    "the whole puzzle gets solved in the fewest slides without trapping the remaining tiles."
)
COACHED_INSTRUCTIONS = TARGET_INSTRUCTIONS + (
    " Strategy: fill the top rows first, left to right, row by row. When only two rows remain, "
    "fill them column by column from the left, top tile then bottom tile. Never fix a tile whose "
    "row or column would leave a one-cell-wide corridor."
)
KIND_KO = {"corner": "모서리", "edge": "변", "center": "가운데"}


def describe_tile(f: dict, numbers: bool = True) -> str:
    if not numbers:
        return f"tile {f['tile']}"
    return (f"tile {f['tile']}: home row {f['goal_row']} col {f['goal_col']} ({f['goal_kind']}), "
            f"now row {f['row']} col {f['col']}, {f['distance']} away, "
            f"home neighbours in its row {f['row_mates_home']}, in its column {f['col_mates_home']}")


def target(g: P.Grid, board: tuple[int, ...], cands: list[int], keep: frozenset[int],
           numbers: bool = True, coached: bool = False) -> dict:
    facts = {t: g.tile_facts(board, t) for t in cands}
    if len(cands) == 1:
        t = cands[0]
        return {"choice": t, "forced": True, "probabilities": {str(t): 1.0}, "confidence": 1.0, "progress": None,
                "candidates": {str(t): {**facts[t], "text": describe_tile(facts[t], numbers)}}, "latency_ms": 0}
    criteria = {str(t): describe_tile(facts[t], numbers) for t in cands}
    state = {"rows": g.rows, "cols": g.cols, "board": g.rows_text(board), "goal": g.rows_text(g.solved()),
             "tiles_fixed": sorted(keep)}
    t0 = time.perf_counter()
    answers = sif.ask(state,
                      target=sif.options(criteria, COACHED_INSTRUCTIONS if coached else TARGET_INSTRUCTIONS),
                      progress=sif.scale(PROGRESS_LEVELS, PROGRESS_INSTRUCTIONS))
    latency = (time.perf_counter() - t0) * 1000
    a = answers["target"]
    return {
        "choice": int(a.choice), "forced": False,
        "probabilities": {k: round(float(p), 4) for k, p in a.probabilities.items()},
        "confidence": round(float(a.confidence), 4),
        "progress": round(float(answers["progress"].score), 3),
        "candidates": {str(t): {**facts[t], "text": criteria[str(t)]} for t in cands},
        "latency_ms": round(latency),
    }


def target_chooser(g: P.Grid, numbers: bool = True, coached: bool = False, log: list | None = None):
    def choose(board, cands, keep):
        r = target(g, board, cands, keep, numbers, coached)
        if log is not None:
            log.append(r)
        return r["choice"]

    return choose


# ---- reflex mode (v1, 3×3) ----------------------------------------------------

MOVE_INSTRUCTIONS = (
    "Sliding puzzle. Pick the slide that moves the board closest to solved: the lowest distance wins, "
    "more tiles home breaks ties."
)
LOOP_INSTRUCTIONS = "The recent slides are going back and forth over the same few boards instead of making progress"


def describe(f: dict, numbers: bool = True) -> str:
    head = f"tile {f['tile']} slides {f['direction']}"
    if not numbers:
        return head
    return head + f". distance {f['distance']} ({f['distance_delta']:+d}), tiles home {f['home']} ({f['home_delta']:+d})"


def step(g: P.Grid, board, last, seen, history: list[str], numbers: bool = True) -> dict:
    opts = g.moves(board)
    feats = {d: P.features(g, board, opts[d], last, d, seen) for d in opts}
    fresh = {d: f for d, f in feats.items() if not f["reverses"]}
    if len(fresh) == 1:  # a corner after a slide: nothing to decide, no request
        d = next(iter(fresh))
        return {"choice": d, "forced": True, "probabilities": {d: 1.0}, "confidence": 1.0, "looping": None,
                "progress": None, "candidates": {d: {**feats[d], "text": describe(feats[d], numbers)}}, "latency_ms": 0}
    feats = fresh
    criteria = {d: describe(feats[d], numbers) for d in feats}
    state = {"board": g.rows_text(board), "goal": g.rows_text(g.solved()), "recent_slides": history[-8:]}
    if numbers:
        state.update({"distance": g.cost(board), "tiles_home": g.tiles_home(board)})
    t0 = time.perf_counter()
    answers = sif.ask(state, move=sif.options(criteria, MOVE_INSTRUCTIONS), looping=LOOP_INSTRUCTIONS,
                      progress=sif.scale(PROGRESS_LEVELS, PROGRESS_INSTRUCTIONS))
    latency = (time.perf_counter() - t0) * 1000
    move = answers["move"]
    return {
        "choice": move.choice, "forced": False,
        "probabilities": {d: round(float(p), 4) for d, p in move.probabilities.items()},
        "confidence": round(float(move.confidence), 4),
        "looping": round(float(answers["looping"].noul), 4),
        "progress": round(float(answers["progress"].score), 3),
        "candidates": {d: {**feats[d], "text": criteria[d]} for d in feats},
        "latency_ms": round(latency),
    }


def picker(g: P.Grid, history: list[str], numbers: bool = True, log: list | None = None,
           sample: random.Random | None = None):
    def pick(board, last, seen):
        r = step(g, board, last, seen, history, numbers)
        d = r["choice"]
        if sample is not None and not r["forced"]:
            ds, ps = zip(*r["probabilities"].items())
            d = sample.choices(ds, weights=ps)[0]
        r["played"] = d
        history.append(f"tile {r['candidates'][d]['tile']} {d}")
        if log is not None:
            log.append(r)
        return d

    return pick


# ---- peel mode (5×6, the current one) ------------------------------------------
#
# Jev picks which line of the unsolved region to peel next: its top row or its left column.
# Every choice is executable (puzzle.play_peels), so the judgement shows only in the slide count.

PEEL_INSTRUCTIONS = (
    "Sliding puzzle. The unsolved part of the board is a rectangle; the code will peel one of its "
    "edge lines next, placing that line's tiles one by one and fixing them. Pick the line to peel "
    "now so that the whole puzzle takes the fewest slides."
)
HINTED_INSTRUCTIONS = PEEL_INSTRUCTIONS + (
    " A line costs roughly as many slides as its tiles' total distance from home, so the line with "
    "the smaller total distance is usually the cheaper one to peel now."
)
LINE_KO = {"row": "윗줄", "col": "왼쪽 열"}


def describe_line(name: str, f: dict, numbers: bool = True) -> str:
    head = "top row" if name == "row" else "left column"
    if not numbers:
        return f"{head}: tiles {f['tiles'][0]}-{f['tiles'][-1]}"
    return (f"{head}: tiles {f['tiles'][0]}-{f['tiles'][-1]} ({f['count']}), {f['home_already']} already in place, "
            f"distance from home total {f['distance_total']}, farthest {f['distance_max']}, blank {f['blank_to_line']} from the line")


def peel_choice(g: P.Grid, board, region, lines: dict, numbers: bool = True, hinted: bool = False) -> dict:
    facts = {k: P.line_facts(g, board, v) for k, v in lines.items()}
    criteria = {k: describe_line(k, facts[k], numbers) for k in lines}
    top, left = region
    state = {"rows": g.rows, "cols": g.cols, "board": g.rows_text(board), "goal": g.rows_text(g.solved()),
             "unsolved_region": f"rows {top + 1}-{g.rows}, cols {left + 1}-{g.cols}"}
    t0 = time.perf_counter()
    answers = sif.ask(state, line=sif.options(criteria, HINTED_INSTRUCTIONS if hinted else PEEL_INSTRUCTIONS),
                      progress=sif.scale(PROGRESS_LEVELS, PROGRESS_INSTRUCTIONS))
    latency = (time.perf_counter() - t0) * 1000
    a = answers["line"]
    return {"choice": a.choice, "probabilities": {k: round(float(p), 4) for k, p in a.probabilities.items()},
            "confidence": round(float(a.confidence), 4), "progress": round(float(answers["progress"].score), 3),
            "candidates": {k: {**facts[k], "text": criteria[k]} for k in lines}, "latency_ms": round(latency)}


def peel_chooser(g: P.Grid, numbers: bool = True, hinted: bool = False, log: list | None = None):
    def choose(board, region, lines):
        r = peel_choice(g, board, region, lines, numbers, hinted)
        if log is not None:
            log.append(r)
        return r["choice"]

    return choose
