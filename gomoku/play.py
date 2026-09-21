"""Headless games for the numbers: the engine bot (black) against Jev (white).

    op run --env-file=<(echo 'TYPESAFE_API_KEY="op://Agent/typesafe jev key/credential"') \
      -- uv run python gomoku/play.py --games 6 --workers 3        # -> results.json

Per Jev move it records whether a winning point or a must-block point was on
the sheet and whether Jev took it, whether Jev agreed with the engine's first
choice, latency and tokens. `--black random` plays a random black instead.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import brain  # noqa: E402
import engine as E  # noqa: E402
import neurons  # noqa: E402
from opus import opus_black  # noqa: E402
from rapfi import rapfi_black  # noqa: E402

MAX_MOVES = 160


def random_black(board: E.Board, rng: random.Random) -> dict:
    ranked = E.candidates(board, E.BLACK, cap=225)
    return rng.choice(ranked)


def play_game(seed: int, black: str, sheet: str = "labelled", which: str = "single", cap: int = 24, deep: bool = False,
              rapfi_ms: int = 1000, rapfi_strength: int = 100, white: str = "jev", rapfi_depth: int = 0) -> dict:
    rng = random.Random(seed)
    board = E.new_board()
    moves: list[dict] = []
    opus_log: list[dict] = []
    last: str | None = None
    result = "unfinished"
    n = 0
    for n in range(1, MAX_MOVES + 1):
        player = E.BLACK if n % 2 else E.WHITE
        side = black if player == E.BLACK else white  # who plays this colour
        if side == "bot":
            pick = E.bot_move(board, player, rng)
        elif side.startswith("opus"):
            pick = opus_black(board, last, rng, sheet=side == "opus-sheet", log=opus_log)
        elif side == "rapfi":
            pick = rapfi_black(board, rng, opus_log, ms=rapfi_ms, strength=rapfi_strength, depth=rapfi_depth, player=player)
        elif side == "random":
            pick = random_black(board, rng)
        else:  # Jev
            # Jev's prompts are written for white. As black (free rules only: renju would give the
            # wrong side the bans) Jev sees the board with the colours swapped and plays "white".
            seen = board if player == E.WHITE else [[E.other(v) if v else E.EMPTY for v in row] for row in board]
            res = neurons.think(seen, E.WHITE, last, n, cap=cap, sheet_kind=sheet, deep=deep) if which == "neurons" else brain.think(seen, E.WHITE, last, n, cap=cap, sheet=sheet, deep=deep)
            ranked = res["candidates"]
            pick = next(a for a in ranked if a["id"] == res["choice"])
            if player == E.BLACK:
                ranked = [E.analyze(board, a["r"], a["c"], player) for a in ranked]  # facts in the real colours
                pick = next(a for a in ranked if a["id"] == res["choice"])
            win_on_sheet = any(a["wins"] for a in ranked)
            block_on_sheet = any(a["must_block"] for a in ranked)
            urgent_on_sheet = any(a["urgent"] for a in ranked) and not win_on_sheet and not block_on_sheet
            moves.append(
                {
                    "n": n,
                    "choice": pick["id"],
                    "p": res["probabilities"].get(pick["id"]),
                    "confidence": res["confidence"],
                    "candidates": len(ranked),
                    "engine_top": ranked[0]["id"],
                    "agree": pick["id"] == ranked[0]["id"],
                    "rank": next(i for i, a in enumerate(ranked) if a["id"] == pick["id"]),
                    "win_on_sheet": win_on_sheet,
                    "took_win": win_on_sheet and pick["wins"],
                    "block_on_sheet": block_on_sheet and not win_on_sheet,
                    "took_block": block_on_sheet and not win_on_sheet and pick["must_block"],
                    "urgent_on_sheet": urgent_on_sheet,
                    "took_urgent": urgent_on_sheet and pick["urgent"],
                    "threat": res["threat"],
                    "standing": res["standing"],
                    "latency_ms": res["latency_ms"],
                    "input_tokens": res["input_tokens"],
                    "output_tokens": res["output_tokens"],
                    "layers": res.get("layers"),
                }
            )
        board[pick["r"]][pick["c"]] = player
        last = pick["id"]
        if E.wins_at(board, pick["r"], pick["c"], player) or E.winner(board) == player:
            result = E.NAME[player]
            break
    return {"seed": seed, "black": black, "white": white, "sheet": sheet, "brain": which, "result": result, "length": n, "moves": moves,
            "opus": opus_log or None, "rapfi": {"ms": rapfi_ms, "strength": rapfi_strength, "depth": rapfi_depth} if black == "rapfi" else None}


def summarize(games: list[dict]) -> dict:
    moves = [m for g in games for m in g["moves"] if m["latency_ms"]]
    def rate(key_hit: str, key_seen: str) -> str:
        seen = [m for m in moves if m[key_seen]]
        return f"{sum(1 for m in seen if m[key_hit])}/{len(seen)}"
    return {
        "games": len(games),
        "white_wins": sum(1 for g in games if g["result"] == "white"),
        "black_wins": sum(1 for g in games if g["result"] == "black"),
        "unfinished": sum(1 for g in games if g["result"] == "unfinished"),
        "mean_length": round(statistics.mean(g["length"] for g in games), 1),
        "jev_moves": len(moves),
        "agree_with_engine_top": f"{sum(1 for m in moves if m['agree'])}/{len(moves)}",
        "median_rank_of_pick": statistics.median(m["rank"] for m in moves) if moves else None,
        "took_win_when_offered": rate("took_win", "win_on_sheet"),
        "took_block_when_needed": rate("took_block", "block_on_sheet"),
        "took_urgent_when_needed": rate("took_urgent", "urgent_on_sheet"),
        "threat_when_block_needed": round(statistics.mean(m["threat"] for m in moves if m["block_on_sheet"]), 2) if any(m["block_on_sheet"] for m in moves) else None,
        "threat_otherwise": round(statistics.mean(m["threat"] for m in moves if not m["block_on_sheet"]), 2) if moves else None,
        "mean_p_of_pick": round(statistics.mean(m["p"] for m in moves), 2) if moves else None,
        "latency_ms_median": statistics.median(m["latency_ms"] for m in moves) if moves else None,
        "latency_ms_p95": sorted(m["latency_ms"] for m in moves)[int(len(moves) * 0.95)] if moves else None,
        "input_tokens_mean": round(statistics.mean(m["input_tokens"] for m in moves)) if moves else None,
        "output_tokens_mean": round(statistics.mean(m["output_tokens"] for m in moves)) if moves else None,
        "cost_usd_total": round(sum(m["input_tokens"] + m["output_tokens"] for m in moves) * brain.USD_PER_TOKEN, 4),
        **layer_stats(moves),
        **opus_stats(games),
    }


def opus_stats(games: list[dict]) -> dict:
    """Black-side stats for an outside player (Opus or Rapfi); the log lives under `opus` either way."""
    log = [o for g in games for o in (g.get("opus") or [])]
    if not log:
        return {}
    who = "rapfi" if games[0].get("rapfi") or games[0].get("white") == "rapfi" else "opus"
    stats = {
        f"{who}_moves": len(log),
        f"{who}_illegal_fallbacks": sum(1 for o in log if not o["legal"]),
        f"{who}_retries": sum(1 for o in log if o["tries"] > 1),
        f"{who}_seconds_median": round(statistics.median(o["seconds"] for o in log), 2),
    }
    if who == "rapfi":
        depths = [o["depth"] for o in log if o.get("depth")]
        stats["rapfi_depth_median"] = statistics.median(depths) if depths else None
    return stats


def layer_stats(moves: list[dict]) -> dict:
    layered = [m["layers"] for m in moves if m.get("layers")]
    if not layered:
        return {}
    fired = {name: sum(1 for L in layered if name in L["fired"]) for name in neurons.SENSORS}
    danger_needed = [m for m in moves if m.get("layers") and (m["block_on_sheet"] or m["urgent_on_sheet"])]
    return {
        "fired_counts": fired,
        "none_fired": sum(1 for L in layered if not L["fired"]),
        "danger_fired_when_needed": f"{sum(1 for m in danger_needed if 'danger' in m['layers']['fired'])}/{len(danger_needed)}",
        "danger_fired_otherwise": f"{sum(1 for m in moves if m.get('layers') and 'danger' in m['layers']['fired'] and not (m['block_on_sheet'] or m['urgent_on_sheet']))}/{len(layered) - len(danger_needed)}",
        "changed_habit": sum(1 for L in layered if L["changed_habit"]),
        "vetoed_proposals": sum(len(L["vetoed"]) for L in layered),
        "mean_proposals": round(sum(len(L["proposals"]) for L in layered) / len(layered), 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=6)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--black", choices=("bot", "random", "opus", "opus-sheet", "rapfi", "jev"), default="bot",
                        help="opus = Claude Opus via `claude -p` reading the board; opus-sheet = same plus the engine's notes; "
                             "rapfi = the Gomocup engine (run rapfi_setup.sh first)")
    parser.add_argument("--white", choices=("jev", "bot", "rapfi"), default="jev", help="bot = the engine bot instead of Jev (no API calls); rapfi = Rapfi as white. With --black jev, Jev takes the first move")
    parser.add_argument("--rapfi-ms", type=int, default=1000, help="Rapfi's time per move in ms")
    parser.add_argument("--rapfi-strength", type=int, default=100, help="Rapfi's handicap level 0-100 (100 = full; barely matters against these opponents)")
    parser.add_argument("--rapfi-depth", type=int, default=0, help="cap Rapfi's search depth (0 = none)")
    parser.add_argument("--sheet", choices=brain.SHEETS, default="labelled", help="how much of the engine Jev sees")
    parser.add_argument("--brain", choices=("single", "neurons"), default="single", help="one request a move, or the three-layer brain")
    parser.add_argument("--cap", type=int, default=24, help="how many candidates the sheet keeps")
    parser.add_argument("--deep", action="store_true", help="add the two-ply facts (forced wins by fours) to Jev's sheet; measured worse, off by default")
    parser.add_argument("--key", help="results key (default from black/sheet/brain)")
    parser.add_argument("--rule", choices=("renju", "free"), default="renju", help="free = five or more wins for both, no bans (needed for --black jev)")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", default=str(HERE / "results.json"))
    args = parser.parse_args()

    if args.black == "jev" and args.rule == "renju":
        parser.error("--black jev needs --rule free: Jev's prompts are written for white, so the board is colour-swapped")
    E.RENJU = args.rule == "renju"
    started = time.time()
    games: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(play_game, args.seed + i, args.black, args.sheet, args.brain, args.cap, args.deep, args.rapfi_ms, args.rapfi_strength, args.white, args.rapfi_depth) for i in range(args.games)]
        for f in as_completed(futures):
            g = f.result()
            games.append(g)
            print(f"game {g['seed']}: {g['result']} in {g['length']} moves", flush=True)
    games.sort(key=lambda g: g["seed"])
    summary = summarize(games)
    out = Path(args.out)
    previous = json.loads(out.read_text()) if out.exists() else {}
    key = args.black if args.sheet == "labelled" else f"{args.black}-{args.sheet}"
    if args.brain == "neurons":
        key = f"{args.black}-neurons-{args.sheet}"
    if args.black == "rapfi":
        key += f"-s{args.rapfi_strength}-{args.rapfi_ms}ms" + (f"-d{args.rapfi_depth}" if args.rapfi_depth else "")
    if args.white != "jev":
        key += f"-vs-{args.white}"
    if args.black == "jev":
        key = f"jev-black-vs-{args.white}"
    if args.rule == "free":
        key += "-free"
    if args.white == "rapfi":
        key += f"-{args.rapfi_ms}ms" + (f"-d{args.rapfi_depth}" if args.rapfi_depth else "")
    if args.key:
        key = args.key
    previous[key] = {"summary": summary, "games": games, "seconds": round(time.time() - started)}
    out.write_text(json.dumps(previous, ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
