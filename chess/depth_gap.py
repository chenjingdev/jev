"""Label positions by how much the depth-2 engine loses for not searching deeper.

Zero API calls. For every sampled position the depth-2 side actually faced in the
recorded 100-game matches, score every root move at depth 4 and record

    gap = raw4(best move at depth 4) - raw4(move the depth-2 search picked)

in the weak engine's own units, side-to-move point of view. `gap >= threshold`
marks a position where spending two more plies would have changed the move for a
real reason; gap 0 means the depth-2 choice survives the deeper look.

The point of the label is the budget experiment: if a selector can spot the high
gap positions in advance, a fixed node budget can be moved onto them. This file
also computes the code-only heuristics that are the honest competitor for that
job (a capture is available, one of my pieces is hanging), so a later Jev run is
measured against a five-line function and not only against chance.

Mate scores are not centipawns; gaps are clipped to CLIP the same way referee.py
clips, and positions whose depth-2 pick is a mate score are flagged.
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import chess

from weak_engine import MATE, VALUE, rank_moves

HERE = Path(__file__).resolve().parent
CLIP = 1000
DEFAULT_MATCHES = ('d2plain-vs-d4-100', 'd2rand-vs-d2-100')


def positions_from_match(path: Path, depth: int = 2):
    """FEN plus provenance for every ply the depth-`depth` side was to move."""
    payload = json.loads(path.read_text())
    rows = []
    for game in payload['games']:
        for move in game['moves']:
            if move.get('depth') != depth:
                continue
            rows.append({
                'fen': move['fen_before'],
                'match': path.stem,
                'game': game['game'],
                'ply': move['ply'],
                'opening': game.get('opening_name'),
                'played_uci': move['uci'],
            })
    return rows


def dedupe(rows):
    """One row per distinct FEN; keeps the first sighting and counts the rest."""
    seen = {}
    for row in rows:
        key = row['fen']
        if key in seen:
            seen[key]['duplicates'] += 1
            continue
        seen[key] = {**row, 'duplicates': 0}
    return list(seen.values())


def hanging(board: chess.Board):
    """Own pieces the opponent attacks with no defender, largest value first."""
    out = []
    for square, piece in board.piece_map().items():
        if piece.color != board.turn or piece.piece_type == chess.KING:
            continue
        if not board.attackers(not board.turn, square):
            continue
        if board.attackers(board.turn, square):
            continue
        out.append({'square': chess.square_name(square), 'value': VALUE[piece.piece_type]})
    return sorted(out, key=lambda r: -r['value'])


def heuristics(board: chess.Board):
    """Code-only signals a selector could use without any model."""
    captures = [m for m in board.legal_moves if board.is_capture(m)]
    checks = [m for m in board.legal_moves if board.gives_check(m)]
    loose = hanging(board)
    captured_values = []
    for move in captures:
        victim = board.piece_at(move.to_square)
        captured_values.append(VALUE[victim.piece_type] if victim else VALUE[chess.PAWN])
    return {
        'in_check': board.is_check(),
        'captures_available': len(captures),
        'best_capture_value': max(captured_values, default=0),
        'checks_available': len(checks),
        'hanging_pieces': len(loose),
        'max_hanging_value': loose[0]['value'] if loose else 0,
        'legal_moves': board.legal_moves.count(),
        'piece_count': len(board.piece_map()),
    }


def tactical_score(features):
    """What a five-line "this position looks sharp" function says."""
    return max(features['max_hanging_value'], features['best_capture_value']) + (300 if features['in_check'] else 0)


def material_score(features):
    """How much material is still on the board, the strongest code-only signal measured.

    Measured on the first 400 labelled positions: piece count separates high-gap from
    low-gap positions at AUC 0.724, while every tactical feature sits at chance or below
    (best capture 0.501, captures available 0.494, hanging piece 0.442, in check 0.409,
    and the tactical score above 0.374, i.e. worse than a coin). Legal move count is the
    runner-up at 0.654. A selector therefore has to beat "the board is still full", not
    "something is hanging".
    """
    return features['piece_count'] * 100 + features['legal_moves']


def heuristic_score(features):
    """The code-only control the model has to beat."""
    return material_score(features)


def auc(rows, key, threshold):
    """Probability a high-gap position outranks a low-gap one; 0.5 is chance."""
    scored = [(key(r), r['gap'] >= threshold) for r in rows]
    positive = [s for s, hit in scored if hit]
    negative = [s for s, hit in scored if not hit]
    if not positive or not negative:
        return None
    wins = sum((a > b) + 0.5 * (a == b) for a in positive for b in negative)
    return round(wins / (len(positive) * len(negative)), 4)


def clip(raw):
    if raw >= MATE - 1000:
        return CLIP
    if raw <= -(MATE - 1000):
        return -CLIP
    return max(-CLIP, min(CLIP, raw))


def measure(fen: str, shallow: int, deep: int):
    board = chess.Board(fen)
    started = time.perf_counter()
    ranked_shallow = rank_moves(board, shallow)
    shallow_ms = (time.perf_counter() - started) * 1000
    started = time.perf_counter()
    ranked_deep = rank_moves(board, deep)
    deep_ms = (time.perf_counter() - started) * 1000
    picked = ranked_shallow[0]['move']
    by_move = {row['move']: row for row in ranked_deep}
    gap = clip(ranked_deep[0]['raw']) - clip(by_move[picked]['raw'])
    shallow_tie = sum(1 for row in ranked_shallow if row['raw'] == ranked_shallow[0]['raw'])
    return {
        'shallow_move': picked,
        'deep_move': ranked_deep[0]['move'],
        'move_changed': picked != ranked_deep[0]['move'],
        'gap': gap,
        'shallow_mate': abs(ranked_shallow[0]['raw']) >= MATE - 1000,
        'deep_mate': abs(ranked_deep[0]['raw']) >= MATE - 1000,
        'shallow_ties_at_top': shallow_tie,
        'shallow_ms': round(shallow_ms, 2),
        'deep_ms': round(deep_ms, 2),
        'features': heuristics(board),
    }


def summarize(rows, threshold):
    gaps = sorted(r['gap'] for r in rows)
    n = len(rows)
    positive = [g for g in gaps if g >= threshold]
    changed = sum(r['move_changed'] for r in rows)
    changed_zero_gap = sum(1 for r in rows if r['move_changed'] and r['gap'] == 0)
    return {
        'positions': n,
        'threshold': threshold,
        'base_rate': round(len(positive) / n, 4) if n else None,
        'mean_gap': round(sum(gaps) / n, 2) if n else None,
        'gap_quantiles': {q: gaps[min(n - 1, int(n * q))] for q in (0.5, 0.75, 0.9, 0.95, 0.99)} if n else {},
        'move_changed_rate': round(changed / n, 4) if n else None,
        'move_changed_but_zero_gap': changed_zero_gap,
        'deep_time_ratio': round(sum(r['deep_ms'] for r in rows) / max(1e-9, sum(r['shallow_ms'] for r in rows)), 1),
        'mean_shallow_ms': round(sum(r['shallow_ms'] for r in rows) / n, 2) if n else None,
        'mean_deep_ms': round(sum(r['deep_ms'] for r in rows) / n, 2) if n else None,
    }


def ranking_report(rows, threshold, key, fractions=(0.1, 0.2, 0.3, 0.5)):
    """How much of the deep-search value a ranking captures at each budget share.

    `key(row)` is any score that claims to rank positions by how badly they need
    the deeper search. Chance is the fraction itself; `oracle` uses the true gap
    and is the ceiling any selector could reach at that budget.
    """
    labelled = [(key(r), r['gap'] >= threshold, r['gap']) for r in rows]
    total_positive = sum(1 for _, hit, _ in labelled if hit)
    total_gap = sum(gap for _, _, gap in labelled)
    out = []
    for fraction in fractions:
        k = max(1, int(len(labelled) * fraction))
        top = sorted(labelled, key=lambda t: -t[0])[:k]
        out.append({
            'fraction': fraction,
            'positions': k,
            'precision': round(sum(1 for _, hit, _ in top if hit) / k, 4),
            'recall': round(sum(1 for _, hit, _ in top if hit) / total_positive, 4) if total_positive else None,
            'gap_captured': round(sum(gap for _, _, gap in top) / total_gap, 4) if total_gap else None,
            'chance_recall': fraction,
        })
    return {'auc': auc(rows, key, threshold), 'budgets': out}


def heuristic_report(rows, threshold, fractions=(0.1, 0.2, 0.3, 0.5)):
    """Both code-only controls: the material one that works and the tactical one that does not."""
    return {'material': ranking_report(rows, threshold, lambda r: material_score(r['features']), fractions),
            'tactical': ranking_report(rows, threshold, lambda r: tactical_score(r['features']), fractions)}


def oracle_report(rows, threshold, fractions=(0.1, 0.2, 0.3, 0.5)):
    return ranking_report(rows, threshold, lambda r: r['gap'], fractions)


def run(output: Path, matches, sample: int, seed: int, shallow: int, deep: int, threshold: int):
    pool = []
    for name in matches:
        pool.extend(positions_from_match(HERE / 'matches' / f'{name}.json', depth=shallow))
    unique = dedupe(pool)
    random.Random(seed).shuffle(unique)
    chosen = unique[:sample] if sample else unique
    rows = []
    started = time.perf_counter()
    for index, row in enumerate(chosen, 1):
        rows.append({**row, **measure(row['fen'], shallow, deep)})
        if index % 25 == 0:
            print(f'{index}/{len(chosen)} {round(time.perf_counter() - started, 1)}s', flush=True)
    payload = {
        'design': (f'Positions the depth-{shallow} side faced in recorded matches, deduped by FEN and sampled. '
                   f'gap = depth-{deep} score of the best move minus depth-{deep} score of the move the '
                   f'depth-{shallow} search picked, in weak-engine units, clipped to +-{CLIP}. No API calls.'),
        'matches': list(matches),
        'config': {'sample': sample, 'seed': seed, 'shallow_depth': shallow, 'deep_depth': deep,
                   'threshold': threshold, 'clip': CLIP},
        'pool': {'plies': len(pool), 'unique_fens': len(unique), 'measured': len(chosen)},
        'summary': summarize(rows, threshold),
        'heuristic_control': heuristic_report(rows, threshold),
        'oracle_ceiling': oracle_report(rows, threshold),
        'elapsed_seconds': round(time.perf_counter() - started, 2),
        'positions': rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({'summary': payload['summary'], 'heuristic_control': payload['heuristic_control'],
                      'oracle_ceiling': payload['oracle_ceiling'], 'pool': payload['pool']},
                     ensure_ascii=False, indent=2), flush=True)
    return payload


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, default=HERE / 'budget' / 'depth-gap.json')
    p.add_argument('--matches', nargs='*', default=list(DEFAULT_MATCHES))
    p.add_argument('--sample', type=int, default=400, help='0 measures every unique position')
    p.add_argument('--seed', type=int, default=20260921)
    p.add_argument('--shallow', type=int, default=2)
    p.add_argument('--deep', type=int, default=4)
    p.add_argument('--threshold', type=int, default=30, help='units of gap that count as "deeper mattered"')
    args = p.parse_args()
    run(args.output, args.matches, args.sample, args.seed, args.shallow, args.deep, args.threshold)
