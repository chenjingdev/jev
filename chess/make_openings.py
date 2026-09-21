"""Generate a fixed set of short, roughly balanced openings for many-game weak-engine matches.

Deterministic engines replay the same game from the same opening, so 100 games need
50 distinct openings. Each opening is 6 plies: at every ply a seeded RNG picks one of the
weak depth-2 engine's top-3 moves. Stockfish then filters for balance (|cp| <= limit) and
uniqueness. Stockfish is used only to select the sample; nothing here reaches Jev.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import random
import chess
import chess.engine
from weak_engine import candidates

HERE = Path(__file__).resolve().parent


def generate(count, plies, seed, engine_path, nodes, cp_limit):
    rng = random.Random(seed)
    openings, seen, tried = [], set(), 0
    with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
        engine.configure({'Threads': 1, 'Hash': 64})
        while len(openings) < count:
            tried += 1
            board = chess.Board()
            moves = []
            for _ in range(plies):
                rows, _ = candidates(board, depth=2)
                move = rng.choice([r['move'] for r in rows])
                board.push_uci(move)
                moves.append(move)
            key = board.board_fen() + ' ' + ('w' if board.turn else 'b')
            if key in seen or board.is_game_over():
                continue
            info = engine.analyse(board, chess.engine.Limit(nodes=nodes))
            cp = info['score'].white().score(mate_score=10000)
            if abs(cp) > cp_limit:
                continue
            seen.add(key)
            openings.append({'name': f'op{len(openings) + 1:02d}', 'uci': moves, 'fen': board.fen(), 'stockfish_cp_white': cp})
    return {'seed': seed, 'plies': plies, 'count': count, 'tried': tried,
            'balance_filter': {'engine': engine_path, 'nodes': nodes, 'abs_cp_max': cp_limit},
            'note': 'Openings chosen from weak depth-2 top-3 moves by a seeded RNG; Stockfish used only to reject unbalanced positions.',
            'openings': openings}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--count', type=int, default=50)
    p.add_argument('--plies', type=int, default=6)
    p.add_argument('--seed', type=int, default=20260921)
    p.add_argument('--engine', default='/opt/homebrew/bin/stockfish')
    p.add_argument('--nodes', type=int, default=100000)
    p.add_argument('--cp-limit', type=int, default=100)
    p.add_argument('--output', type=Path, default=HERE / 'openings-50.json')
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError(a.output)
    result = generate(a.count, a.plies, a.seed, a.engine, a.nodes, a.cp_limit)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(len(result['openings']), 'openings; tried', result['tried'])
