"""Can Jev see the board at all? A white four is on the board and it is white's move:
does Jev find the one empty point that completes five?

    op run --env-file=<(echo 'TYPESAFE_API_KEY="op://Agent/typesafe jev key/credential"') \
      -- uv run python gomoku/sight.py --positions 20          # -> results_sight.json

Positions come from actual alternating engine self-play, starting at h8. We retain
white-to-move positions with a contiguous white four and one winning empty point.
The complete played history is preserved and replay-validated; no scattered noise
stones or invented move order. This is a selected tactical puzzle set, not a
representative estimate of overall playing strength.
"""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
from functools import lru_cache
import json
import random
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import brain  # noqa: E402
import engine as E  # noqa: E402
from typesafe_sdk import Choice  # noqa: E402

ASK = (
    "The state is a gomoku position (15x15, five in a row wins) with white to move. "
    "White already has four stones in a row somewhere on the board with exactly one empty point "
    "that would make them five. The options are empty points named by column letter and row number. "
    "Pick the point that completes white's five."
)
BOARD_ROWS = "`board` lists the rows top to bottom: X is a black stone, O a white stone, . an empty point; column letters a-o above, row numbers on the left (renju notation, row 1 at the bottom)."
BOARD_STONES = "`white_stones` and `black_stones` list every stone in renju notation: column letter a-o, row number 1-15 with 1 at the bottom."
BOARD_RECORD = "`record` is the game record with the colours written out: the moves in the order they were played, numbered, black first, each a colour and a point in renju notation (column letter a-o, row number 1-15 with 1 at the bottom)."
BOARD_SEQUENCE = "`moves` is the game record using numbered algebraic coordinates: moves in the order they were played, black first and the colours alternating, so odd moves are black and even moves are white; each point is a column letter a-o and a row number 1-15 with 1 at the bottom."
BOARD_COMPACT = "`moves` contains the played moves concatenated without numbers or separators, e.g. h8i9g7. Each move is a letter a-o followed by a row 1-15 (1 at the bottom). Black plays first, then colours alternate."
BOARD_SPACED = "`moves` contains the played coordinates separated by spaces, black first, then colours alternate. Each move is a letter a-o followed by a row 1-15 (1 at the bottom)."
BOARD_SGF = "`sgf` is an SGF game record: GM[4] is gomoku/renju, SZ[15] is a 15x15 board, B and W are black and white moves. SGF points use two letters a-o: column from left, row from top (aa is top-left). Answer options use letter-number coordinates with row 1 at the bottom: SGF aa = a15, hh = h8, oo = o1."
BOARD_SGF_NATIVE = "`sgf` is an SGF game record: GM[4] is gomoku/renju, SZ[15] is a 15x15 board, B and W are black and white moves. Both the record and answer options use SGF two-letter coordinates a-o: column from left, row from top (aa is top-left, hh is centre, oo is bottom-right)."
REPS = ("rows", "stones", "record", "sequence", "compact", "spaced", "sgf", "sgf_native")
BOARD_NOTE = {"rows": BOARD_ROWS, "stones": BOARD_STONES, "record": BOARD_RECORD, "sequence": BOARD_SEQUENCE, "compact": BOARD_COMPACT, "spaced": BOARD_SPACED, "sgf": BOARD_SGF, "sgf_native": BOARD_SGF_NATIVE}


@dataclass
class Position:
    board: E.Board
    hole: tuple[int, int]
    moves: list[str]
    player: int = E.WHITE


def winning_points(board: E.Board, player: int) -> list[tuple[int, int]]:
    return [(r, c) for r in range(E.SIZE) for c in range(E.SIZE)
            if board[r][c] == E.EMPTY and E.wins_at(board, r, c, player)
            and not E.forbidden(board, r, c, player)]


def validate(position: Position) -> None:
    """Reject corrupt history/colour/turn/target data before any API request."""
    replay = E.new_board()
    if not position.moves or position.moves[0] != "h8" or position.player not in (E.BLACK, E.WHITE) or len(position.moves) % 2 != (1 if position.player == E.WHITE else 0):
        raise ValueError("Expected a centre opening and correct turn (white to move after black)")
    for i, at in enumerate(position.moves):
        r, c = E.parse_coord(at)
        player = E.BLACK if i % 2 == 0 else E.WHITE
        if not E.inside(r, c) or replay[r][c] or E.forbidden(replay, r, c, player):
            raise ValueError(f"Illegal move {i + 1}: {at}")
        replay[r][c] = player
        if E.winner(replay):
            raise ValueError("History already contains a finished game")
    if replay != position.board:
        raise ValueError("History does not reconstruct the displayed board")
    if winning_points(replay, position.player) != [position.hole]:
        raise ValueError("Expected exactly one winning point")
    r, c = position.hole
    if not any(E.line_through(replay, r, c, position.player, d)[0] == 5 and
               max(E._run(replay, r, c, *d, position.player)[0],
                   E._run(replay, r, c, -d[0], -d[1], position.player)[0]) == 4
               for d in E.DIRECTIONS):
        raise ValueError("Expected a contiguous four next to the target")


def make_position(rng: random.Random, to_move: int = E.WHITE) -> Position:
    """Play both sides using the existing tactical bot; retain a real pre-win turn.

    Legality follows this project's simplified renju engine, not tournament
    opening protocols or a complete recursive renju forbidden-move judge.
    """
    for _ in range(200):
        board, moves = E.new_board(), []
        for n in range(100):
            player = E.BLACK if n % 2 == 0 else E.WHITE
            if player == to_move:
                wins = winning_points(board, player)
                if len(wins) == 1:
                    position = Position(board, wins[0], moves, player)
                    try:
                        validate(position)
                    except ValueError:
                        pass
                    else:
                        # Black puzzles include a genuine forbidden distractor.
                        if player == E.WHITE or E.forbidden_points(board, E.BLACK):
                            return position
            ranked = E.candidates(board, player, cap=12)
            if not ranked:
                break
            best = ranked[0]["score"]
            move = rng.choice([a for a in ranked if a["score"] >= best - 5])
            board[move["r"]][move["c"]] = player
            moves.append(move["id"])
            if E.winner(board):
                break
    raise ValueError("No suitable self-play position found within 200 games")


@lru_cache(maxsize=128)
def position_for_seed(seed: int, player: int = E.WHITE) -> Position:
    return make_position(random.Random(seed), player)


def varied_candidates(board: E.Board, player: int = E.WHITE) -> dict[str, str]:
    """Internal role -> coordinate selection. Roles are never sent to Jev."""
    wins = winning_points(board, player)
    if len(wins) != 1:
        raise ValueError("Five-choice puzzle requires exactly one winning point")
    chosen = {"target": E.coord(*wins[0])}
    rng = random.Random("varied-five-v1:" + str(player) + str(board))
    pool, forbidden = [], []
    for r in range(E.SIZE):
        for c in range(E.SIZE):
            if board[r][c] or not E.neighbours(board, r, c, 2):
                continue
            why = E.forbidden(board, r, c, player)
            if why:
                forbidden.append((E.coord(r, c), why))
            elif E.coord(r, c) != chosen["target"]:
                pool.append(E.analyze(board, r, c, player))

    def select(role, score):
        ranked = sorted((a for a in pool if a['id'] not in chosen.values()), key=score, reverse=True)
        if not ranked:
            raise ValueError("Not enough distinct candidate points")
        # Strong candidates for this role, then prefer another area of the board.
        positive = [a for a in ranked if score(a) > 0]
        shortlist = (positive or ranked)[:8]
        def distance(a):
            return min(max(abs(a['r']-r),abs(a['c']-c)) for r,c in map(E.parse_coord,chosen.values()))
        farthest = max(map(distance,shortlist))
        chosen[role] = rng.choice([a for a in shortlist if distance(a)==farthest])['id']

    select('attack', lambda a: sum(E.WEIGHT[n] for n in a['attack'] if n in ('open four','four','open three','three')))
    select('defend', lambda a: sum(E.WEIGHT[n] for n in a['defence']))
    select('develop', lambda a: sum(E.WEIGHT[n] for n in a['attack'] if n in ('open two','two')))
    if player == E.BLACK and forbidden:
        threes = [at for at,why in forbidden if why == 'double three']
        chosen['forbidden'] = rng.choice(threes or [at for at,_ in forbidden])
    else:
        select('other', lambda a: E.neighbours(board,a['r'],a['c'],1))
    return chosen


def opponent_five(board: E.Board, player: int = E.WHITE) -> dict[str, None]:
    choices = list(varied_candidates(board, player).values())
    random.Random("varied-order-v1:" + str(board)).shuffle(choices)
    return {at: None for at in choices}


def options_for(board: E.Board, kind: str, player: int = E.WHITE) -> dict[str, str | None]:
    if kind == "five":
        return opponent_five(board, player)
    if kind == "all":
        return {E.coord(r, c): None for r in range(E.SIZE) for c in range(E.SIZE) if board[r][c] == E.EMPTY}
    if kind == "near":
        return {E.coord(r, c): None for r in range(E.SIZE) for c in range(E.SIZE) if board[r][c] == E.EMPTY and E.neighbours(board, r, c, 2)}
    if kind == "sheet":
        ranked = E.candidates(board, player, cap=24)
        return {a["id"]: None for a in ranked}
    raise ValueError("Unknown options kind")


def sgf_coord(at: str) -> str:
    r, c = E.parse_coord(at)
    return E.COLS[c] + E.COLS[r]


def rotate_coord(at: str, turns: int) -> str:
    r, c = E.parse_coord(at)
    for _ in range(turns % 4):
        r, c = c, E.SIZE - 1 - r
    return E.coord(r, c)


def rotate_position(position: Position, turns: int) -> Position:
    moves = [rotate_coord(at, turns) for at in position.moves]
    board = E.new_board()
    for i, at in enumerate(moves):
        r, c = E.parse_coord(at)
        board[r][c] = E.BLACK if i % 2 == 0 else E.WHITE
    return Position(board, E.parse_coord(rotate_coord(E.coord(*position.hole), turns)), moves, position.player)


def state_for(position: Position, rep: str) -> dict:
    board = position.board
    if rep not in REPS:
        raise ValueError("Unknown board representation")
    state = {"game": "gomoku, 15x15, five in a row wins", "to_move": E.NAME[position.player]}
    if rep == "rows":
        state["board"] = E.render(board)
    elif rep in ("compact", "spaced"):
        state["moves"] = ("" if rep == "compact" else " ").join(position.moves)
    elif rep in ("sgf", "sgf_native"):
        state["sgf"] = "(;GM[4]FF[4]SZ[15]" + "".join(
            f";{'B' if i % 2 == 0 else 'W'}[{sgf_coord(at)}]" for i, at in enumerate(position.moves)) + ")"
    elif rep == "record":
        state["record"] = [f"{i + 1}. {E.NAME[E.BLACK if i % 2 == 0 else E.WHITE]} {at}" for i, at in enumerate(position.moves)]
    elif rep == "sequence":
        state["moves"] = " ".join(f"{i + 1}.{at}" for i, at in enumerate(position.moves))
    else:
        state["white_stones"] = [E.coord(r, c) for r in range(E.SIZE) for c in range(E.SIZE) if board[r][c] == E.WHITE]
        state["black_stones"] = [E.coord(r, c) for r in range(E.SIZE) for c in range(E.SIZE) if board[r][c] == E.BLACK]
    return state


def ask(position: Position, kind: str, rep: str, probabilities: bool = False, *, option_order: list[str] | None = None, audit: bool = False) -> dict:
    # Engine pattern checks temporarily place stones: each concurrent request owns its board.
    position = copy.deepcopy(position)
    validate(position)
    board, hole = position.board, position.hole
    if kind not in ("all", "near", "sheet", "five"):
        raise ValueError("Unknown options kind")
    options = options_for(board, kind, position.player)
    if option_order is not None:
        if len(option_order) != len(options) or set(option_order) != set(options):
            raise ValueError("Option order must contain exactly the same empty points")
        options = {at: None for at in option_order}
    labels = {sgf_coord(at) if rep == "sgf_native" else at: at for at in options}
    options = {label: None for label in labels}
    target = E.coord(*hole)
    question = ASK.replace("named by column letter and row number", "named by SGF two-letter coordinates") if rep == "sgf_native" else ASK
    if position.player == E.BLACK:
        question = question.replace("white", "black").replace("White", "Black")
        question += " Renju rules: black must make exactly five; double-three, double-four and overline moves are forbidden (an exact five takes priority over double threats). Pick a legal move."
    instructions = question + " " + BOARD_NOTE[rep]
    state = state_for(position, rep)
    started = time.perf_counter()
    res = brain.client().system_one(state=state, model=brain.MODEL,
                                    questions={"point": Choice(instructions=instructions, criteria=options)})
    ans = res.answers["point"]
    pick = labels[ans.choice]
    distribution = {labels[k]: v for k, v in ans.probabilities.items()}
    pr, pc = E.parse_coord(pick)
    usage = getattr(res, "usage", None)
    out = {
        "kind": kind, "rep": rep, "player": E.NAME[position.player], "target": target, "target_offered": target in labels.values(), "pick": pick, "hit": pick == target,
        "p_target": round(distribution.get(target, 0.0), 4), "p_pick": round(ans.probabilities.get(ans.choice, 0.0), 4),
        "distance": max(abs(pr - hole[0]), abs(pc - hole[1])), "options": len(options),
        "latency_ms": round((time.perf_counter() - started) * 1000), "input_tokens": usage.input_tokens if usage else 0,
        "output_tokens": usage.output_tokens if usage else 0, "moves": position.moves,
    }
    if probabilities:  # for the page: the whole distribution, to paint on the board
        out["probabilities"] = {k: round(v, 4) for k, v in distribution.items()}
    if audit:
        out["request"] = {"state": state, "model": brain.MODEL, "questions": {"point": {"type": "choice", "instructions": instructions, "criteria": options}}}
        out["raw_choice"] = ans.choice
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--positions", type=int, default=20)
    parser.add_argument("--player", choices=("white", "black"), default="white")
    parser.add_argument("--kinds", default="all,near,sheet")
    parser.add_argument("--reps", default="sequence,stones,rows,record")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", default=str(HERE / "results_sight.json"))
    args = parser.parse_args()

    positions, seeds, seen = [], [], set()
    for seed in range(args.seed, args.seed + max(args.positions * 20, 1)):
        position = position_for_seed(seed) if args.player == "white" else position_for_seed(seed, E.BLACK)
        identity = tuple(tuple(row) for row in position.board)
        if identity in seen:
            continue
        seen.add(identity)
        positions.append(position)
        seeds.append(seed)
        if len(positions) == args.positions:
            break
    if args.positions < 1 or len(positions) != args.positions:
        parser.error("Could not select the requested number of distinct positions")
    jobs = [(p, k, r) for p in positions for k in args.kinds.split(",") for r in args.reps.split(",")]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        trials = list(pool.map(lambda j: ask(*j), jobs))
    summary = {}
    for kind in args.kinds.split(","):
        for rep in args.reps.split(","):
            t = [x for x in trials if x["kind"] == kind and x["rep"] == rep]
            summary[f"{kind}/{rep}"] = {
                "hit": f"{sum(x['hit'] for x in t)}/{len(t)}",
                "target_offered": sum(x["target_offered"] for x in t),
                "hit_when_offered": f"{sum(x['hit'] for x in t)}/{sum(x['target_offered'] for x in t)}",
                "p_target_mean": round(statistics.mean(x["p_target"] for x in t), 3),
                "distance_median": statistics.median(x["distance"] for x in t),
                "options_mean": round(statistics.mean(x["options"] for x in t)),
                "latency_ms_median": statistics.median(x["latency_ms"] for x in t),
                "input_tokens_mean": round(statistics.mean(x["input_tokens"] for x in t)),
            }
    chance = round(statistics.mean(1 / x["options"] for x in trials), 4)
    out = {"positions": args.positions, "generator": "selfplay-v2", "player": args.player, "seed": args.seed, "position_seeds": seeds, "model": brain.MODEL, "chance_mean": chance,
           "dataset": [{"moves": p.moves, "board": p.board, "target": E.coord(*p.hole), "player": E.NAME[p.player]} for p in positions], "summary": summary,
           "cost_usd": round(sum((x["input_tokens"] + x["output_tokens"]) for x in trials) * brain.USD_PER_TOKEN, 4), "trials": trials}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k not in ("trials", "dataset")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
