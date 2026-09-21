"""Run reproducible paired UCI-engine matches and save PGN plus JSON."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import time

import chess
import chess.engine
import chess.pgn


HERE = Path(__file__).resolve().parent
DEFAULT_SUNFISH = HERE / ".venv-sunfish" / "bin" / "sunfish-uci"


@dataclass(frozen=True)
class EngineSpec:
    name: str
    command: str
    nodes: int


def play_game(white: EngineSpec, black: EngineSpec, engines, game_number: int, max_plies: int):
    board = chess.Board()
    game = chess.pgn.Game()
    game.headers.update({
        "Event": "Jev chess engine smoke match",
        "Site": "local",
        "Date": datetime.now().strftime("%Y.%m.%d"),
        "Round": str(game_number),
        "White": white.name,
        "Black": black.name,
        "FEN": board.fen(),
        "SetUp": "1",
    })
    node = game
    moves = []
    game_token = object()
    while not board.is_game_over(claim_draw=True) and len(moves) < max_plies:
        spec = white if board.turn == chess.WHITE else black
        engine = engines[spec.name]
        started = time.perf_counter()
        result = engine.play(
            board,
            chess.engine.Limit(nodes=spec.nodes),
            game=game_token,
            info=chess.engine.INFO_ALL,
        )
        elapsed_ms = round(1000 * (time.perf_counter() - started), 2)
        if result.move is None or result.move not in board.legal_moves:
            raise RuntimeError(f"{spec.name} returned invalid move {result.move} at {board.fen()}")
        san = board.san(result.move)
        info = result.info
        moves.append({
            "ply": len(moves) + 1,
            "side": "white" if board.turn else "black",
            "engine": spec.name,
            "uci": result.move.uci(),
            "san": san,
            "elapsed_ms": elapsed_ms,
            "depth": info.get("depth"),
            "nodes": info.get("nodes"),
            "score": str(info.get("score")) if info.get("score") is not None else None,
        })
        board.push(result.move)
        node = node.add_variation(result.move)

    outcome = board.outcome(claim_draw=True)
    if outcome is None:
        result_text = "1/2-1/2"
        termination = "max_plies"
    else:
        result_text = outcome.result()
        termination = outcome.termination.name.lower()
    game.headers["Result"] = result_text
    game.headers["Termination"] = termination
    return {
        "game": game_number,
        "white": white.name,
        "black": black.name,
        "result": result_text,
        "termination": termination,
        "plies": len(moves),
        "final_fen": board.fen(),
        "moves": moves,
    }, game


def run_match(a: EngineSpec, b: EngineSpec, games: int, max_plies: int):
    if games < 2 or games % 2:
        raise ValueError("games must be a positive even number")
    if a.name == b.name:
        raise ValueError("engine names must be distinct")
    if a.nodes <= 0 or b.nodes <= 0:
        raise ValueError("node limits must be positive")
    engines = {
        a.name: chess.engine.SimpleEngine.popen_uci(a.command, timeout=10),
        b.name: chess.engine.SimpleEngine.popen_uci(b.command, timeout=10),
    }
    rows, pgn_games = [], []
    try:
        for number in range(1, games + 1):
            white, black = (a, b) if number % 2 else (b, a)
            row, game = play_game(white, black, engines, number, max_plies)
            rows.append(row)
            pgn_games.append(game)
            print(f"game {number}/{games}: {white.name}–{black.name} {row['result']} ({row['termination']}, {row['plies']} plies)", flush=True)
    finally:
        for engine in engines.values():
            engine.quit()
    points = {a.name: 0.0, b.name: 0.0}
    for row in rows:
        if row["result"] == "1-0":
            points[row["white"]] += 1
        elif row["result"] == "0-1":
            points[row["black"]] += 1
        else:
            points[row["white"]] += 0.5
            points[row["black"]] += 0.5
    return rows, pgn_games, points


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-a", default=str(DEFAULT_SUNFISH))
    parser.add_argument("--engine-b", default=str(DEFAULT_SUNFISH))
    parser.add_argument("--name-a", default="sunfish-1000")
    parser.add_argument("--name-b", default="sunfish-300")
    parser.add_argument("--nodes-a", type=int, default=1000)
    parser.add_argument("--nodes-b", type=int, default=300)
    parser.add_argument("--games", type=int, default=2)
    parser.add_argument("--max-plies", type=int, default=240)
    parser.add_argument("--output", type=Path, default=HERE / "matches" / "sunfish-smoke")
    args = parser.parse_args()
    a = EngineSpec(args.name_a, args.engine_a, args.nodes_a)
    b = EngineSpec(args.name_b, args.engine_b, args.nodes_b)
    started = time.perf_counter()
    rows, pgn_games, points = run_match(a, b, args.games, args.max_plies)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "design": "Paired colors from the standard initial position; fixed node budget per move; python-chess adjudicates standard terminal and claimable draw rules.",
        "engine_a": a.__dict__,
        "engine_b": b.__dict__,
        "games": rows,
        "points": points,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }
    args.output.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    args.output.with_suffix(".pgn").write_text("\n\n".join(str(game) for game in pgn_games) + "\n")
    print(json.dumps({"points": points, "elapsed_seconds": payload["elapsed_seconds"],
                      "json": str(args.output.with_suffix('.json')),
                      "pgn": str(args.output.with_suffix('.pgn'))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
