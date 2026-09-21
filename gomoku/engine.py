"""Gomoku engine: board, win check, and the "answer sheet" for Jev.

Pure functions, no I/O. The board is a list of 15 rows, each a list of ints:
0 empty, 1 black, 2 white. Coordinates are (row, col), row 0 at the top.

The engine does the seeing. For every empty point worth playing it writes one
line of facts - what a stone there makes (five, open four, three ...) and what
it stops the opponent from making - and ranks them. Jev only picks among them.

Rules are renju's for black (RENJU = True): black may not make a double three,
a double four or an overline (six or more), and wins only with exactly five;
white has no restrictions and wins with five or more. Patterns are read on
contiguous stones only, so a split three (X.XX) is not seen as a three - the
forbidden-move check inherits that approximation.
"""

from __future__ import annotations

import random

SIZE = 15
EMPTY, BLACK, WHITE = 0, 1, 2
NAME = {BLACK: "black", WHITE: "white"}
COLS = "abcdefghijklmno"
DIRECTIONS = ((0, 1), (1, 0), (1, 1), (1, -1))
DIRECTION_NAME = {(0, 1): "horizontal", (1, 0): "vertical", (1, 1): "diagonal", (1, -1): "anti-diagonal"}

# Pattern weights, attack. Defence uses the same table scaled down: a point where
# the opponent would *complete* something (five, open four) is forced; a point
# where they would merely *start* something (an open three) is pre-emptive and
# worth far less than building a line of one's own.
WEIGHT = {
    "five": 100_000,
    "open four": 10_000,
    "four": 1_200,
    "open three": 1_000,
    "three": 80,
    "open two": 40,
    "two": 8,
}
DEFENCE_SCALE = {"five": 0.5, "open four": 0.45, "four": 0.5, "open three": 0.35, "three": 0.2, "open two": 0.15, "two": 0.1}
FORCING = {"five", "open four", "four"}
RENJU = True  # black: no 3-3, no 4-4, no overline; exactly five wins

Board = list[list[int]]


def new_board() -> Board:
    return [[EMPTY] * SIZE for _ in range(SIZE)]


def other(player: int) -> int:
    return BLACK if player == WHITE else WHITE


def inside(r: int, c: int) -> bool:
    return 0 <= r < SIZE and 0 <= c < SIZE


def coord(r: int, c: int) -> str:
    """Renju notation: column letter a-o, row number 1-15 with 1 at the bottom (row index 0 is the top)."""
    return f"{COLS[c]}{SIZE - r}"


def parse_coord(text: str) -> tuple[int, int]:
    return SIZE - int(text[1:]), COLS.index(text[0])


def stones(board: Board) -> int:
    return sum(1 for row in board for v in row if v)


# ------------------------------------------------------------------ win check


def _run(board: Board, r: int, c: int, dr: int, dc: int, player: int) -> tuple[int, bool]:
    """Stones of `player` in one direction from (r, c) exclusive, and whether the end is open."""
    n = 0
    rr, cc = r + dr, c + dc
    while inside(rr, cc) and board[rr][cc] == player:
        n += 1
        rr += dr
        cc += dc
    return n, inside(rr, cc) and board[rr][cc] == EMPTY


def line_through(board: Board, r: int, c: int, player: int, direction: tuple[int, int]) -> tuple[int, int]:
    """Length of the line `player` would have through (r, c) and how many ends are open."""
    dr, dc = direction
    a, open_a = _run(board, r, c, dr, dc, player)
    b, open_b = _run(board, r, c, -dr, -dc, player)
    return 1 + a + b, int(open_a) + int(open_b)


def _is_win_length(length: int, player: int) -> bool:
    return length == 5 if (RENJU and player == BLACK) else length >= 5


def wins_at(board: Board, r: int, c: int, player: int) -> bool:
    """True if a `player` stone at (r, c) completes five (white: five or more)."""
    return any(_is_win_length(line_through(board, r, c, player, d)[0], player) for d in DIRECTIONS)


def winner(board: Board) -> int:
    for r in range(SIZE):
        for c in range(SIZE):
            p = board[r][c]
            if p and any(_is_win_length(line_through(board, r, c, p, d)[0], p) for d in DIRECTIONS):
                return p
    return EMPTY


def winning_line(board: Board) -> list[tuple[int, int]]:
    """The five (or more) stones that won, for drawing."""
    for r in range(SIZE):
        for c in range(SIZE):
            p = board[r][c]
            if not p:
                continue
            for dr, dc in DIRECTIONS:
                if inside(r - dr, c - dc) and board[r - dr][c - dc] == p:
                    continue  # not the start of the run
                cells = []
                rr, cc = r, c
                while inside(rr, cc) and board[rr][cc] == p:
                    cells.append((rr, cc))
                    rr += dr
                    cc += dc
                if _is_win_length(len(cells), p):
                    return cells
    return []


# -------------------------------------------------------------------- patterns


def pattern(length: int, open_ends: int, player: int = WHITE) -> str | None:
    """Name of a contiguous run. Used for the weak shapes; fours and threes come from `shape`."""
    if length >= 5:
        if RENJU and player == BLACK and length > 5:
            return None  # overline: not a win for black, and forbidden
        return "five"
    if length == 4:
        return "open four" if open_ends == 2 else ("four" if open_ends == 1 else None)
    if length == 3:
        return "open three" if open_ends == 2 else ("three" if open_ends == 1 else None)
    if length == 2:
        return "open two" if open_ends == 2 else ("two" if open_ends == 1 else None)
    return None


def _five_cells(board: Board, r: int, c: int, player: int, direction: tuple[int, int]) -> list[tuple[int, int]]:
    """Empty cells on the line where one more `player` stone makes a five that contains (r, c).

    (r, c) must already hold the stone. Two cells = an open four, one = a four;
    this is what makes split shapes like X.XXX count as fours."""
    dr, dc = direction
    cells = []
    for k in range(-4, 5):
        if k == 0:
            continue
        rr, cc = r + dr * k, c + dc * k
        if not inside(rr, cc) or board[rr][cc] != EMPTY:
            continue
        if any(board[r + dr * j][c + dc * j] != player for j in range(min(0, k) + 1, max(0, k))):
            continue  # a gap or an enemy stone between: no single five holds both
        if _is_win_length(line_through(board, rr, cc, player, direction)[0], player):
            cells.append((rr, cc))
    return cells


def shape(board: Board, r: int, c: int, player: int, direction: tuple[int, int]) -> str | None:
    """What the `player` stone at (r, c) forms along `direction`, gaps included.

    (r, c) must already hold the stone. Five, then fours by the number of cells
    that complete five (two = open four), then an open three when one more stone
    makes an open four, then the contiguous names for the rest."""
    length, open_ends = line_through(board, r, c, player, direction)
    if _is_win_length(length, player):
        return "five"
    if RENJU and player == BLACK and length > 5:
        return None
    fives = _five_cells(board, r, c, player, direction)
    if len(fives) >= 2:
        return "open four"
    if len(fives) == 1:
        return "four"
    dr, dc = direction
    for k in range(-3, 4):
        if k == 0:
            continue
        rr, cc = r + dr * k, c + dc * k
        if not inside(rr, cc) or board[rr][cc] != EMPTY:
            continue
        if any(board[r + dr * j][c + dc * j] != player for j in range(min(0, k) + 1, max(0, k))):
            continue
        board[rr][cc] = player
        opens = len(_five_cells(board, r, c, player, direction)) >= 2
        board[rr][cc] = EMPTY
        if opens:
            return "open three"
    name = pattern(length, open_ends, player)
    return "three" if name == "open three" else name  # a contiguous three no stone can open is a closed three at best


def patterns_at(board: Board, r: int, c: int, player: int) -> list[tuple[str, tuple[int, int]]]:
    """What a `player` stone at (r, c) would form, per direction, strongest first."""
    board[r][c] = player
    found = [(name, d) for d in DIRECTIONS if (name := shape(board, r, c, player, d))]
    board[r][c] = EMPTY
    found.sort(key=lambda item: -WEIGHT[item[0]])
    return found


def forbidden(board: Board, r: int, c: int, player: int) -> str | None:
    """Renju: why `player` may not play (r, c), or None. Only black is restricted.

    A stone that completes exactly five is always allowed (five beats the bans).
    Simplification: a three counts as open even when the stone that would open
    it is itself forbidden."""
    if not RENJU or player != BLACK or board[r][c] != EMPTY:
        return None
    lengths = [line_through(board, r, c, player, d) for d in DIRECTIONS]
    if any(length == 5 for length, _ in lengths):
        return None
    if any(length >= 6 for length, _ in lengths):
        return "overline"
    names = [name for name, _ in patterns_at(board, r, c, player)]
    if sum(1 for n in names if n in ("four", "open four")) >= 2:
        return "double four"
    if sum(1 for n in names if n == "open three") >= 2:
        return "double three"
    return None


def neighbours(board: Board, r: int, c: int, radius: int = 1) -> int:
    n = 0
    for dr in range(-radius, radius + 1):
        for dc in range(-radius, radius + 1):
            if (dr or dc) and inside(r + dr, c + dc) and board[r + dr][c + dc]:
                n += 1
    return n


def analyze(board: Board, r: int, c: int, player: int) -> dict:
    """Facts about playing (r, c) as `player`: attack, defence, score, one-line description."""
    opp = other(player)
    attack = patterns_at(board, r, c, player)
    defence = [] if forbidden(board, r, c, opp) else patterns_at(board, r, c, opp)  # a point the opponent may not play threatens nothing
    score = 0.0
    for name, _ in attack:
        score += WEIGHT[name]
    for name, _ in defence:
        score += WEIGHT[name] * DEFENCE_SCALE[name]
    # two simultaneous threats are worth more than their sum: black cannot answer both
    strong = [name for name, _ in attack if name in ("open three", "four", "open four")]
    double = len(strong) >= 2
    opp_strong = [name for name, _ in defence if name in ("open three", "four", "open four")]
    opp_double = len(opp_strong) >= 2
    if double:
        score += 6_000
    if opp_double:
        score += 3_000
    near = neighbours(board, r, c, 1)
    score += near * 3 + neighbours(board, r, c, 2) - (abs(r - 7) + abs(c - 7)) * 0.5

    wins = any(name == "five" for name, _ in attack)
    must_block = any(name == "five" for name, _ in defence)
    urgent = any(name == "open four" for name, _ in defence) or opp_double
    parts: list[str] = []
    if wins:
        parts.append("WINS: completes five in a row")
    if must_block:
        parts.append(f"MUST BLOCK: {NAME[opp]} completes five here on the next move")
    if double and not wins:
        parts.append(f"DOUBLE THREAT: makes {' and '.join(('an ' if n[0] in 'aeiou' else 'a ') + n for n in strong)} at once; {NAME[opp]} cannot stop both")
    if opp_double and not must_block:
        parts.append(f"URGENT: {NAME[opp]} plays here next and gets {' and '.join(('an ' if n[0] in 'aeiou' else 'a ') + n for n in opp_strong)} at once; block now")
    for name, d in defence:  # the verdict words go first, whatever else the stone does
        if name == "open four" and not opp_double:
            parts.append(f"URGENT: {NAME[opp]} plays here next and gets an open four ({DIRECTION_NAME[d]}) that cannot be stopped; block now")
    for name, d in attack:
        where = DIRECTION_NAME[d]
        if name == "open four":
            parts.append(f"makes an open four ({where}): wins next move whatever {NAME[opp]} does")
        elif name == "four":
            parts.append(f"makes a four ({where}) that {NAME[opp]} must answer")
        elif name == "open three":
            parts.append(f"makes an open three ({where})")
        elif name == "three":
            parts.append(f"makes a closed three ({where})")
        elif name == "open two":
            parts.append(f"makes an open two ({where})")
    for name, d in defence:
        where = DIRECTION_NAME[d]
        if name == "four" and not opp_double:
            parts.append(f"also takes a point where {NAME[opp]} could make a four ({where})")
        elif name == "open three" and not opp_double:
            parts.append(f"also takes a point where {NAME[opp]} could start an open three ({where})")
    if not parts:
        parts.append(f"{near} adjacent stone{'s' if near != 1 else ''}" if near else "no adjacent stones")
    return {
        "id": coord(r, c),
        "r": r,
        "c": c,
        "score": round(score, 1),
        "wins": wins,
        "must_block": must_block,
        "urgent": urgent,
        "double": double,
        "forced_win": False,
        "watch": False,
        "attack": [name for name, _ in attack],
        "defence": [name for name, _ in defence],
        "desc": "; ".join(parts),
    }


# ------------------------------------------------------------ two-ply lookahead


def _four_block_point(board: Board, r: int, c: int, player: int, direction: tuple[int, int]) -> tuple[int, int] | None:
    """For a four `player` would have through (r, c): the one empty cell that completes five."""
    board[r][c] = player
    cells = _five_cells(board, r, c, player, direction)
    board[r][c] = EMPTY
    return cells[0] if len(cells) == 1 else None


def _decisive(names: list[str]) -> bool:
    """A stone that wins on the spot or leaves a shape the opponent cannot hold in one move."""
    if "five" in names or "open four" in names:
        return True
    return sum(1 for n in names if n in ("open three", "four", "open four")) >= 2


def vcf(board: Board, player: int, depth: int = 3, radius: int = 1) -> list[tuple[tuple[int, int], tuple[int, int] | None]] | None:
    """Victory by continuous fours: a sequence of `player` fours the opponent must
    answer, ending in a five, an open four or a double threat. Returns the
    sequence as (point, forced reply) pairs, or None. Approximate: the forced
    replies are assumed not to create counter-threats. Depth counts the fours played before the final blow.
    """
    opp = other(player)
    for r in range(SIZE):
        for c in range(SIZE):
            if board[r][c] != EMPTY or neighbours(board, r, c, radius) == 0 or forbidden(board, r, c, player):
                continue
            pats = patterns_at(board, r, c, player)
            names = [n for n, _ in pats]
            if _decisive(names):
                return [((r, c), None)]
            if depth == 0 or "four" not in names:
                continue
            direction = next(d for n, d in pats if n == "four")
            q = _four_block_point(board, r, c, player, direction)
            if q is None:
                continue
            if forbidden(board, q[0], q[1], opp) or wins_at(board, q[0], q[1], opp):
                continue  # the reply wins for them, or they cannot legally block: not a clean force
            board[r][c] = player
            board[q[0]][q[1]] = opp
            rest = vcf(board, player, depth - 1, radius) if not forbidden(board, q[0], q[1], opp) else None
            board[q[0]][q[1]] = EMPTY
            board[r][c] = EMPTY
            if rest:
                return [((r, c), q)] + rest
    return None


def vcf_starts(board: Board, player: int, depth: int = 1) -> dict[tuple[int, int], list]:
    """Every first move from which `player` has a vcf, with its sequence.

    Depth 1 by default: one four, the forced reply, then a decisive stone. Deeper
    chains are legal to ask for but the approximation (replies never counter-
    threaten) gets less reliable with every four.
    """
    opp = other(player)
    out: dict[tuple[int, int], list] = {}
    for r in range(SIZE):
        for c in range(SIZE):
            if board[r][c] != EMPTY or neighbours(board, r, c, 1) == 0 or forbidden(board, r, c, player):
                continue
            pats = patterns_at(board, r, c, player)
            names = [n for n, _ in pats]
            if _decisive(names):
                continue  # already on the sheet as a win / double
            if "four" not in names:
                continue
            direction = next(d for n, d in pats if n == "four")
            q = _four_block_point(board, r, c, player, direction)
            if q is None or forbidden(board, q[0], q[1], opp) or wins_at(board, q[0], q[1], opp):
                continue
            board[r][c] = player
            board[q[0]][q[1]] = opp
            rest = vcf(board, player, depth - 1)
            board[q[0]][q[1]] = EMPTY
            board[r][c] = EMPTY
            if rest:
                out[(r, c)] = [((r, c), q)] + rest
    return out


def deepen(board: Board, player: int, ranked: list[dict]) -> list[dict]:
    """Add the two-ply facts to a candidate list: forced wins for `player`, and
    the points that stop the opponent's forced wins. Used for Jev's sheet only;
    the bot never sees this."""
    opp = other(player)
    mine = vcf_starts(board, player)
    theirs = vcf_starts(board, opp)
    by_pos = {(a["r"], a["c"]): a for a in ranked}

    def describe(seq: list) -> str:
        steps = " then ".join(f"{coord(*p)} (forcing {coord(*q)})" if q else coord(*p) for p, q in seq)
        return steps

    for pos, seq in mine.items():
        a = by_pos.get(pos)
        if a is None:
            a = analyze(board, pos[0], pos[1], player)
            ranked.append(a)
            by_pos[pos] = a
        final = seq[-1][0]
        a["forced_win"] = True
        a["score"] += 8_000  # above a plain four, below an open four / double (10,000+): those win a tempo sooner
        a["desc"] = f"FORCED WIN: a four here that {NAME[opp]} must answer at {coord(*seq[0][1])}, then {coord(*final)} wins by force; " + a["desc"]
    for pos, seq in theirs.items():
        q = seq[0][1]
        final = seq[-1][0]
        for point, role in ((pos, "start"), (q, "block"), (final, "end")):
            a = by_pos.get(point)
            if a is None:
                if board[point[0]][point[1]] != EMPTY or forbidden(board, point[0], point[1], player):
                    continue
                a = analyze(board, point[0], point[1], player)
                ranked.append(a)
                by_pos[point] = a
            if a.get("wins") or a.get("forced_win"):
                continue
            if not a.get("watch"):
                a["watch"] = True
                a["score"] += 2_000  # below an immediate URGENT point (4,500): that threat is one tempo sooner
            text = {
                "start": f"WATCH: {NAME[opp]} could start a forced win here (a four {NAME[player]} must answer at {coord(*q)}, then {coord(*final)}); taking this point prevents it",
                "block": f"WATCH: {NAME[opp]} could start a forced win at {coord(*pos)}; a stone here removes the forcing four",
                "end": f"WATCH: {NAME[opp]} could start a forced win at {coord(*pos)} that ends here at {coord(*final)}; taking this point prevents it",
            }[role]
            a["desc"] = a["desc"] + "; " + text
    ranked.sort(key=lambda a: -a["score"])
    return ranked


# ------------------------------------------------------------------ candidates


def candidates(board: Board, player: int, cap: int = 24, radius: int = 2, deep: bool = False) -> list[dict]:
    """Empty points within `radius` of a stone, ranked by the engine, at most `cap`.

    On an empty board the only candidate is the centre. Forcing moves (win now,
    block a five) are always kept even beyond the cap. `deep` adds the two-ply
    facts (forced wins by continuous fours, and the points that stop the
    opponent's) - Jev's sheet uses it, the bot does not.
    """
    if stones(board) == 0:
        return [analyze(board, 7, 7, player)]
    seen: set[tuple[int, int]] = set()
    out: list[dict] = []
    for r in range(SIZE):
        for c in range(SIZE):
            if board[r][c] != EMPTY or neighbours(board, r, c, radius) == 0 or forbidden(board, r, c, player):
                continue
            seen.add((r, c))
            out.append(analyze(board, r, c, player))
    out.sort(key=lambda a: -a["score"])
    if deep:
        out = deepen(board, player, out)
    kept = out[:cap]
    for a in out[cap:]:
        if a["wins"] or a["must_block"] or a["urgent"] or a.get("forced_win") or a.get("watch"):
            kept.append(a)
    return kept


def threats(board: Board, player: int) -> list[str]:
    """Sentences about what the opponent of `player` already has on the board."""
    opp = other(player)
    lines: list[str] = []
    seen: set[tuple[tuple[int, int], int]] = set()
    for r in range(SIZE):
        for c in range(SIZE):
            if board[r][c] != opp:
                continue
            for d in DIRECTIONS:
                dr, dc = d
                name = shape(board, r, c, opp, d)
                line = {(0, 1): r, (1, 0): c, (1, 1): r - c, (1, -1): r + c}[d]  # one report per line and shape
                if name in ("open three", "four", "open four", "five") and (d, line, name) not in seen:
                    seen.add((d, line, name))
                    lines.append(f"{NAME[opp]} has {'an' if name[0] in 'aeiou' else 'a'} {name} from {coord(r, c)} ({DIRECTION_NAME[d]})")
    return lines


def forbidden_points(board: Board, player: int = BLACK) -> dict[str, str]:
    """Every empty point `player` may not play, with the reason. For the page."""
    out: dict[str, str] = {}
    for r in range(SIZE):
        for c in range(SIZE):
            why = forbidden(board, r, c, player)
            if why:
                out[coord(r, c)] = why
    return out


def render(board: Board) -> list[str]:
    """Rows as strings: . empty, X black, O white. Context only - Jev decides from the facts."""
    sym = {EMPTY: ".", BLACK: "X", WHITE: "O"}
    return ["   " + " ".join(COLS)] + [f"{SIZE - r:>2} " + " ".join(sym[v] for v in row) for r, row in enumerate(board)]


# -------------------------------------------------------------------- the bot


def bot_move(board: Board, player: int, rng: random.Random | None = None) -> dict:
    """The engine playing on its own: best-scored candidate, ties broken at random."""
    rng = rng or random.Random()
    ranked = candidates(board, player, cap=12)
    best = ranked[0]["score"]
    top = [a for a in ranked if a["score"] >= best - 5]
    return rng.choice(top)
