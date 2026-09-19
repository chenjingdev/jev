"""Pure engine for a ROWS×COLS sliding puzzle. No Jev here.

A board is a tuple of ROWS*COLS ints, row-major, 0 = the blank. Solved is 1..ROWS*COLS-1 then 0.
Every move is "one tile slides into the blank"; a move is named by the direction the tile
travels (a tile below the blank slides *up*). Default 5 rows × 6 columns; the 3×3 helpers
(distance table, scramble by optimal depth) only work when the board has ≤ 9 cells.
"""

from __future__ import annotations

import random
from collections import deque

ROWS, COLS = 5, 6
DIRS = {"up": (1, 0), "down": (-1, 0), "left": (0, 1), "right": (0, -1)}  # where the sliding tile comes from
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}


class Grid:
    def __init__(self, rows: int = ROWS, cols: int = COLS):
        self.rows, self.cols, self.cells = rows, cols, rows * cols
        self._table = None

    def solved(self) -> tuple[int, ...]:
        return tuple(list(range(1, self.cells)) + [0])

    def rc(self, i: int) -> tuple[int, int]:
        return divmod(i, self.cols)

    def neighbours(self, i: int) -> dict[str, int]:
        """direction name -> index of the cell a tile would slide *from* into cell i."""
        r, c = self.rc(i)
        out = {}
        for name, (dr, dc) in DIRS.items():
            rr, cc = r + dr, c + dc
            if 0 <= rr < self.rows and 0 <= cc < self.cols:
                out[name] = rr * self.cols + cc
        return out

    def moves(self, board: tuple[int, ...]) -> dict[str, tuple[int, ...]]:
        b = board.index(0)
        out = {}
        for name, t in self.neighbours(b).items():
            nb = list(board)
            nb[b], nb[t] = nb[t], 0
            out[name] = tuple(nb)
        return out

    def tile_of(self, board: tuple[int, ...], direction: str) -> int:
        return board[self.neighbours(board.index(0))[direction]]

    def manhattan(self, board: tuple[int, ...]) -> int:
        d = 0
        for i, v in enumerate(board):
            if v:
                r, c = self.rc(i)
                gr, gc = self.rc(v - 1)
                d += abs(r - gr) + abs(c - gc)
        return d

    def linear_conflict(self, board: tuple[int, ...]) -> int:
        conflicts = 0
        for r in range(self.rows):
            goals = [self.rc(board[r * self.cols + c] - 1) for c in range(self.cols) if board[r * self.cols + c]]
            line = [gc for gr, gc in goals if gr == r]
            conflicts += sum(1 for i in range(len(line)) for j in range(i + 1, len(line)) if line[i] > line[j])
        for c in range(self.cols):
            goals = [self.rc(board[r * self.cols + c] - 1) for r in range(self.rows) if board[r * self.cols + c]]
            line = [gr for gr, gc in goals if gc == c]
            conflicts += sum(1 for i in range(len(line)) for j in range(i + 1, len(line)) if line[i] > line[j])
        return conflicts

    def cost(self, board: tuple[int, ...]) -> int:
        return self.manhattan(board) + 2 * self.linear_conflict(board)

    def tiles_home(self, board: tuple[int, ...]) -> int:
        return sum(1 for i, v in enumerate(board) if v and v == i + 1)

    def home_set(self, board: tuple[int, ...]) -> frozenset[int]:
        return frozenset(v for i, v in enumerate(board) if v and v == i + 1)

    def is_solvable(self, board: tuple[int, ...]) -> bool:
        seq = [v for v in board if v]
        inv = sum(1 for i in range(len(seq)) for j in range(i + 1, len(seq)) if seq[i] > seq[j])
        if self.cols % 2 == 1:
            return inv % 2 == 0
        blank_row_from_bottom = self.rows - board.index(0) // self.cols
        return (inv + blank_row_from_bottom) % 2 == 1

    def rows_text(self, board: tuple[int, ...]) -> list[str]:
        return [" ".join("_" if v == 0 else str(v) for v in board[r * self.cols:(r + 1) * self.cols]) for r in range(self.rows)]

    # ---- scrambles --------------------------------------------------------

    def shuffle(self, rng: random.Random) -> tuple[int, ...]:
        """A uniformly random solvable board (no optimal distance known)."""
        while True:
            b = list(range(self.cells))
            rng.shuffle(b)
            b = tuple(b)
            if self.is_solvable(b) and b != self.solved():
                return b

    def random_walk(self, steps: int, rng: random.Random) -> tuple[int, ...]:
        b = self.solved()
        last = None
        for _ in range(steps):
            opts = [d for d in self.moves(b) if d != last]
            d = rng.choice(opts)
            b = self.moves(b)[d]
            last = OPPOSITE[d]
        return b

    def distance_table(self) -> dict[tuple[int, ...], int]:
        """Optimal move count for every reachable board. 3×3 only (181,440 states)."""
        if self.cells > 9:
            raise ValueError("distance table is for boards with at most 9 cells")
        if self._table is None:
            goal = self.solved()
            dist = {goal: 0}
            q = deque([goal])
            while q:
                b = q.popleft()
                for nb in self.moves(b).values():
                    if nb not in dist:
                        dist[nb] = dist[b] + 1
                        q.append(nb)
            self._table = dist
        return self._table

    def scramble(self, depth: int, rng: random.Random) -> tuple[int, ...]:
        table = self.distance_table()
        return rng.choice([b for b, d in table.items() if d == depth])

    # ---- target mode: bring one tile home ----------------------------------

    def bring_home(self, board: tuple[int, ...], keep: frozenset[int], target: int, max_unlock: int = 4) -> list[str] | None:
        """Shortest slide sequence that puts `target` home and leaves every tile in `keep` home.

        Tiles in `keep` are walls; the blank and the target move among the rest (state = two
        positions, ≤ cells² states). When the walls make it impossible - the last tile of a row
        needs its neighbour to step aside - the kept tiles nearest the target's home are unlocked
        one at a time up to `max_unlock` and tracked in the state, constrained to be home at the end.
        """
        if target in keep or board[target - 1] == target:
            return []
        hr, hc = self.rc(target - 1)
        locked = sorted(keep, key=lambda t: abs(self.rc(t - 1)[0] - hr) + abs(self.rc(t - 1)[1] - hc))
        for k in range(0, max_unlock + 1):
            tracked = [target] + locked[:k]
            walls = frozenset(t - 1 for t in locked[k:])
            path = self._bfs(board, tracked, walls)
            if path is not None:
                return path
        return None

    def _bfs(self, board, tracked, walls):
        goal_pos = tuple(t - 1 for t in tracked)
        start = (tuple(board.index(t) for t in tracked), board.index(0))
        if start[0] == goal_pos:
            return []
        prev: dict = {start: None}
        q = deque([start])
        while q:
            s = q.popleft()
            pos, blank = s
            for name, cell in self.neighbours(blank).items():
                if cell in walls:
                    continue
                npos = tuple(blank if p == cell else p for p in pos)
                ns = (npos, cell)
                if ns in prev:
                    continue
                prev[ns] = (s, name)
                if npos == goal_pos:
                    path = []
                    while prev[ns] is not None:
                        ns, name = prev[ns]
                        path.append(name)
                    return path[::-1]
                q.append(ns)
        return None

    def apply(self, board: tuple[int, ...], path: list[str]) -> tuple[int, ...]:
        for d in path:
            board = self.moves(board)[d]
        return board

    def tile_facts(self, board: tuple[int, ...], t: int) -> dict:
        r, c = self.rc(board.index(t))
        gr, gc = self.rc(t - 1)
        home = self.home_set(board)
        row_mates = sum(1 for k in range(self.cols) if gr * self.cols + k + 1 != t and (gr * self.cols + k + 1) in home)
        col_mates = sum(1 for k in range(self.rows) if k * self.cols + gc + 1 != t and (k * self.cols + gc + 1) in home)
        kind = "corner" if (gr in (0, self.rows - 1) and gc in (0, self.cols - 1)) else "edge" if (gr in (0, self.rows - 1) or gc in (0, self.cols - 1)) else "center"
        return {"tile": t, "row": r + 1, "col": c + 1, "goal_row": gr + 1, "goal_col": gc + 1,
                "distance": abs(r - gr) + abs(c - gc), "goal_kind": kind, "row_mates_home": row_mates, "col_mates_home": col_mates}

    def play_targets(self, board, chooser, cap: int | None = None):
        """chooser(board, candidates, keep) -> tile. Returns (solved, moves, order, trace).
        A choice the executor cannot carry out (walls fragment the board) ends the game unsolved."""
        keep = frozenset()
        total, order, trace = 0, [], []
        for _ in range(cap or self.cells):
            if board == self.solved():
                return True, total, order, trace
            cands = [t for t in range(1, self.cells) if t not in keep]
            t = chooser(board, cands, keep)
            path = self.bring_home(board, keep, t)
            if path is None:
                trace.append({"tile": t, "slides": None, "path": [], "home_after": sorted(keep)})
                return False, total, order + [t], trace
            board = self.apply(board, path)
            keep = keep | {t}  # only chosen tiles become walls; tiles that landed home by chance stay free
            total += len(path)
            order.append(t)
            trace.append({"tile": t, "slides": len(path), "path": path, "home_after": sorted(keep)})
        return board == self.solved(), total, order, trace


# ---- v1 reflex mode helpers -----------------------------------------------------

def features(g: Grid, board, after, last, direction, seen) -> dict:
    return {
        "tile": g.tile_of(board, direction),
        "direction": direction,
        "distance": g.cost(after),
        "distance_delta": g.cost(after) - g.cost(board),
        "manhattan": g.manhattan(after),
        "home": g.tiles_home(after),
        "home_delta": g.tiles_home(after) - g.tiles_home(board),
        "conflict": g.linear_conflict(after),
        "reverses": last is not None and direction == OPPOSITE[last],
        "seen": seen.get(after, 0),
    }


def greedy_pick(g: Grid, board, last, seen, rng, veto_seen=False):
    """Lowest cost, never reverse unless forced, ties random."""
    opts = g.moves(board)
    cands = [d for d in opts if last is None or d != OPPOSITE[last]] or list(opts)
    if veto_seen:
        fresh = [d for d in cands if opts[d] not in seen]
        cands = fresh or cands
    best = min(g.cost(opts[d]) for d in cands)
    return rng.choice([d for d in cands if g.cost(opts[d]) == best])


def play(g: Grid, board, picker, cap=60):
    """Run `picker(board, last, seen)` until solved or cap. Returns (solved, moves, path)."""
    goal = g.solved()
    seen = {board: 1}
    last = None
    path = []
    for _ in range(cap):
        if board == goal:
            return True, len(path), path
        d = picker(board, last, seen)
        board = g.moves(board)[d]
        seen[board] = seen.get(board, 0) + 1
        last = d
        path.append(d)
    return board == goal, len(path), path


# ---- peel mode: Jev picks which line to peel next -------------------------------
#
# The unsolved region is always the bottom-right sub-rectangle (the blank's home is the
# bottom-right corner, so peeling from the bottom or the right would leave that corner
# as a pocket). Each decision peels the region's top row or left column; the executor
# places the line's tiles in order with bring_home. When the region is 2 tall only a column
# can go, when 2 wide only a row; the last 2×2 is finished tile by tile.

def region_lines(g: Grid, region: tuple[int, int]) -> dict[str, list[int]]:
    """region = (top, left) of the unsolved rectangle; returns line name -> tiles in order."""
    top, left = region
    out = {}
    h, w = g.rows - top, g.cols - left
    if h == 2 and w == 2:
        return out
    if h > 2:
        out["row"] = [top * g.cols + c + 1 for c in range(left, g.cols)]
    if w > 2:
        out["col"] = [r * g.cols + left + 1 for r in range(top, g.rows)]
    return out


def line_facts(g: Grid, board: tuple[int, ...], tiles: list[int]) -> dict:
    home = g.home_set(board)
    blank = g.rc(board.index(0))
    dist = [g.tile_facts(board, t)["distance"] for t in tiles]
    return {"tiles": tiles, "count": len(tiles), "home_already": sum(1 for t in tiles if t in home),
            "distance_total": sum(dist), "distance_max": max(dist),
            "blank_to_line": min(abs(blank[0] - g.rc(t - 1)[0]) + abs(blank[1] - g.rc(t - 1)[1]) for t in tiles)}


def peel(g: Grid, board: tuple[int, ...], keep: frozenset[int], tiles: list[int]) -> tuple[tuple[int, ...], frozenset[int], list[str]]:
    path_all: list[str] = []
    for t in tiles:
        path = g.bring_home(board, keep, t)
        if path is None:
            raise RuntimeError(f"peel failed at tile {t} keeping {sorted(keep)}")
        board = g.apply(board, path)
        keep = keep | {t}
        path_all += path
    return board, keep, path_all


def play_peels(g: Grid, board: tuple[int, ...], chooser):
    """chooser(board, region, lines) -> 'row' | 'col'. Returns (moves, order, trace)."""
    region = (0, 0)
    keep: frozenset[int] = frozenset()
    total, order, trace = 0, [], []
    while True:
        lines = region_lines(g, region)
        if not lines:
            break
        choice = chooser(board, region, lines) if len(lines) > 1 else next(iter(lines))
        board, keep, path = peel(g, board, keep, lines[choice])
        total += len(path)
        order.append(choice)
        trace.append({"line": choice, "tiles": lines[choice], "slides": len(path), "path": path, "forced": len(lines) == 1})
        region = (region[0] + 1, region[1]) if choice == "row" else (region[0], region[1] + 1)
    # last 2×2: three tiles, any order the BFS can do
    rest = [t for t in range(1, g.cells) if t not in keep]
    board, keep, path = peel(g, board, keep, rest)
    total += len(path)
    trace.append({"line": "end", "tiles": rest, "slides": len(path), "path": path, "forced": True})
    assert board == g.solved(), board
    return total, order, trace
