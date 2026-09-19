"""Jev picks the next slide. One `sif.ask()` per step, three questions.

Jev has no eyes (experiments/vision), so the code does the looking: it enumerates the
2-4 legal slides and writes one line of consequences per slide. Jev reads the lines
and points at one. The numbers are the whole game - strip them and Jev is at chance
(the `jev-nonumbers` condition in `run_trials.py`).

Two earlier wordings, both measured in run_trials.py (see README):
- "prefer a fresh board even if a little worse" + a "board seen before" tag: Jev took the
  +1 slide almost half the time, 10/60 solved. Greedy with the same veto also got worse.
- "do not reverse the previous slide unless it is the only option" as an instruction: Jev
  reversed anyway whenever the reverse was the only -1, 7/60 solved with 2-cycles
  (right, left, right, left ...). So the reverse is now removed from the options by code,
  like greedy does, and a step with a single option is played without asking.

- move     Choice over the legal slides, each option described by its consequences
- looping  Noul: the last few slides are going back and forth over the same boards
- progress Score on 4 levels: how close the board looks to solved (display only)
"""

from __future__ import annotations

import random
import time

import sif

import puzzle as P

MOVE_INSTRUCTIONS = (
    "Sliding puzzle. Pick the slide that moves the board closest to solved: the lowest distance wins, "
    "more tiles home breaks ties."
)
LOOP_INSTRUCTIONS = "The recent slides are going back and forth over the same few boards instead of making progress"
PROGRESS_LEVELS = ["scrambled", "some tiles home", "one row done", "almost solved"]
PROGRESS_INSTRUCTIONS = "How close is the board to solved?"

KO = {"up": "위로", "down": "아래로", "left": "왼쪽으로", "right": "오른쪽으로"}


def describe(f: dict, numbers: bool = True) -> str:
    """One line per candidate slide; this is what Jev reads."""
    head = f"tile {f['tile']} slides {f['direction']}"
    if not numbers:
        return head
    parts = [
        f"distance {f['distance']} ({f['distance_delta']:+d})",
        f"tiles home {f['home']} ({f['home_delta']:+d})",
    ]
    return head + ". " + ", ".join(parts)


def step(board: tuple[int, ...], last: str | None, seen: dict, history: list[str],
         numbers: bool = True, n: int = P.N) -> dict:
    opts = P.moves(board, n)
    feats = {d: P.features(board, opts[d], last, d, seen, n) for d in opts}
    fresh = {d: f for d, f in feats.items() if not f["reverses"]}
    if len(fresh) == 1:  # a corner after a slide: nothing to decide, no request
        d = next(iter(fresh))
        return {"choice": d, "forced": True, "probabilities": {d: 1.0}, "confidence": 1.0, "looping": None,
                "progress": None, "candidates": {d: {**feats[d], "text": describe(feats[d], numbers)}}, "latency_ms": 0}
    feats = fresh
    criteria = {d: describe(feats[d], numbers) for d in feats}
    state = {
        "board": P.rows(board, n),
        "goal": P.rows(P.solved(n), n),
        "distance": P.manhattan(board, n) if numbers else None,
        "tiles_home": P.tiles_home(board) if numbers else None,
        "recent_slides": history[-8:],
    }
    if not numbers:
        state = {k: v for k, v in state.items() if v is not None}
    t0 = time.perf_counter()
    answers = sif.ask(
        state,
        move=sif.options(criteria, MOVE_INSTRUCTIONS),
        looping=LOOP_INSTRUCTIONS,
        progress=sif.scale(PROGRESS_LEVELS, PROGRESS_INSTRUCTIONS),
    )
    latency = (time.perf_counter() - t0) * 1000
    move = answers["move"]
    return {
        "choice": move.choice,
        "forced": False,
        "probabilities": {d: round(float(p), 4) for d, p in move.probabilities.items()},
        "confidence": round(float(move.confidence), 4),
        "looping": round(float(answers["looping"].noul), 4),
        "progress": round(float(answers["progress"].score), 3),
        "candidates": {d: {**feats[d], "text": criteria[d]} for d in feats},
        "latency_ms": round(latency),
    }


def picker(history: list[str], numbers: bool = True, veto_seen: bool = False, log: list | None = None,
           sample: random.Random | None = None, n: int = P.N):
    """Adapter for `puzzle.play`. `veto_seen`: when Jev says looping, refuse boards seen before.
    `sample`: draw the slide from Jev's distribution instead of taking the top one."""

    def pick(board, last, seen):
        r = step(board, last, seen, history, numbers, n)
        d = r["choice"]
        if sample is not None and not r["forced"]:
            ds, ps = zip(*r["probabilities"].items())
            d = sample.choices(ds, weights=ps)[0]
        r["vetoed"] = False
        if veto_seen and r["looping"] >= 0.5 and r["candidates"][d]["seen"]:
            fresh = [c for c, f in r["candidates"].items() if not f["seen"]]
            if fresh:
                d = max(fresh, key=lambda c: r["probabilities"].get(c, 0))
                r["vetoed"] = True
        r["played"] = d
        history.append(f"tile {r['candidates'][d]['tile']} {d}")
        if log is not None:
            log.append(r)
        return d

    return pick
