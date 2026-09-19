"""Pure engine for an N×N sliding puzzle. No Jev here.

A board is a tuple of N*N ints, row-major, 0 = the blank. Solved is 1..N*N-1 then 0.
Every move is "one tile slides into the blank"; a move is named by the direction the tile
travels (a tile below the blank slides *up*).
"""

from __future__ import annotations

import random
from collections import deque
from functools import lru_cache

N = 3
DIRS = {"up": (1, 0), "down": (-1, 0), "left": (0, 1), "right": (0, -1)}  # where the sliding tile comes from
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}


def solved(n: int = N) -> tuple[int, ...]:
    return tuple(list(range(1, n * n)) + [0])


def moves(board: tuple[int, ...], n: int = N) -> dict[str, tuple[int, ...]]:
    """direction -> board after that tile slides into the blank."""
    b = board.index(0)
    br, bc = divmod(b, n)
    out = {}
    for name, (dr, dc) in DIRS.items():
        r, c = br + dr, bc + dc
        if 0 <= r < n and 0 <= c < n:
            t = r * n + c
            nb = list(board)
            nb[b], nb[t] = nb[t], 0
            out[name] = tuple(nb)
    return out


def tile_of(board: tuple[int, ...], direction: str, n: int = N) -> int:
    b = board.index(0)
    dr, dc = DIRS[direction]
    br, bc = divmod(b, n)
    return board[(br + dr) * n + bc + dc]


def manhattan(board: tuple[int, ...], n: int = N) -> int:
    d = 0
    for i, v in enumerate(board):
        if v:
            g = v - 1
            d += abs(i // n - g // n) + abs(i % n - g % n)
    return d


def linear_conflict(board: tuple[int, ...], n: int = N) -> int:
    """Pairs of tiles in their goal row/column but in reversed order. Each costs 2 extra moves."""
    conflicts = 0
    for line in range(n):
        for axis in (0, 1):
            cells = [line * n + k if axis == 0 else k * n + line for k in range(n)]
            goal_pos = [(board[c] - 1) for c in cells if board[c]]
            in_line = [(g // n if axis == 0 else g % n) == line for g in goal_pos]
            order = [(g % n if axis == 0 else g // n) for g, ok in zip(goal_pos, in_line) if ok]
            for i in range(len(order)):
                for j in range(i + 1, len(order)):
                    if order[i] > order[j]:
                        conflicts += 1
    return conflicts


def tiles_home(board: tuple[int, ...]) -> int:
    return sum(1 for i, v in enumerate(board) if v and v == i + 1)


def is_solvable(board: tuple[int, ...], n: int = N) -> bool:
    seq = [v for v in board if v]
    inv = sum(1 for i in range(len(seq)) for j in range(i + 1, len(seq)) if seq[i] > seq[j])
    if n % 2 == 1:
        return inv % 2 == 0
    blank_row_from_bottom = n - board.index(0) // n
    return (inv + blank_row_from_bottom) % 2 == 1


@lru_cache(maxsize=None)
def distance_table(n: int = N) -> dict[tuple[int, ...], int]:
    """Optimal move count for every reachable board (3×3: 181,440 states, about a second)."""
    goal = solved(n)
    dist = {goal: 0}
    q = deque([goal])
    while q:
        b = q.popleft()
        for nb in moves(b, n).values():
            if nb not in dist:
                dist[nb] = dist[b] + 1
                q.append(nb)
    return dist


def optimal(board: tuple[int, ...], n: int = N) -> int:
    return distance_table(n)[board]


def scramble(depth: int, rng: random.Random, n: int = N) -> tuple[int, ...]:
    """A board whose optimal solution is exactly `depth` moves (3×3 only; uses the table)."""
    table = distance_table(n)
    pool = [b for b, d in table.items() if d == depth]
    return rng.choice(pool)


def random_walk(steps: int, rng: random.Random, n: int = N) -> tuple[int, ...]:
    """Random legal moves from solved, never immediately undoing. Works for any n."""
    b = solved(n)
    last = None
    for _ in range(steps):
        opts = [d for d in moves(b, n) if d != last]
        d = rng.choice(opts)
        b = moves(b, n)[d]
        last = OPPOSITE[d]
    return b


def rows(board: tuple[int, ...], n: int = N) -> list[str]:
    return [" ".join("_" if v == 0 else str(v) for v in board[r * n:(r + 1) * n]) for r in range(n)]


# ---- baselines ------------------------------------------------------------

def cost(board: tuple[int, ...], n: int = N) -> int:
    """Manhattan + 2 per linear conflict: the 'distance' Jev and greedy both read."""
    return manhattan(board, n) + 2 * linear_conflict(board, n)


def features(board: tuple[int, ...], after: tuple[int, ...], last: str | None, direction: str,
             seen: dict[tuple[int, ...], int], n: int = N) -> dict:
    return {
        "tile": tile_of(board, direction, n),
        "direction": direction,
        "distance": cost(after, n),
        "distance_delta": cost(after, n) - cost(board, n),
        "manhattan": manhattan(after, n),
        "home": tiles_home(after),
        "home_delta": tiles_home(after) - tiles_home(board),
        "conflict": linear_conflict(after, n),
        "reverses": last is not None and direction == OPPOSITE[last],
        "seen": seen.get(after, 0),
    }


def greedy_pick(board, last, seen, rng, n=N, veto_seen=False):
    """Lowest Manhattan(+2*conflict), never reverse unless forced, ties random."""
    opts = moves(board, n)
    cands = [d for d in opts if last is None or d != OPPOSITE[last]] or list(opts)
    if veto_seen:
        fresh = [d for d in cands if opts[d] not in seen]
        cands = fresh or cands
    best = min(cost(opts[d], n) for d in cands)
    return rng.choice([d for d in cands if cost(opts[d], n) == best])


def play(board, picker, cap=60, n=N):
    """Run `picker(board, last, seen)` until solved or cap. Returns (solved, moves, path)."""
    goal = solved(n)
    seen = {board: 1}
    last = None
    path = []
    for _ in range(cap):
        if board == goal:
            return True, len(path), path
        d = picker(board, last, seen)
        board = moves(board, n)[d]
        seen[board] = seen.get(board, 0) + 1
        last = d
        path.append(d)
    return board == goal, len(path), path
