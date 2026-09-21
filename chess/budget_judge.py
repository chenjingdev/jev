"""Ask Jev, before any deep search, which positions deserve the deeper search.

Layer A of the budget experiment. `depth_gap.py` has already labelled each
position with `gap`: how much the depth-2 engine loses by not searching depth 4.
Here Jev sees only the position - never the gap, never an engine score, never a
candidate list - and answers a few chess questions. Each answer is then used as a
ranking and scored the same way `depth_gap.py` scores the code-only heuristic:
at a budget of k% of positions, how much of the total gap does this ranking pick
up, against chance (k%), against the heuristic, and against the oracle ceiling.

If no question beats the heuristic, the budget idea is dead at layer A and no
games need to be played. That is the point of running this first.

The state follows the representation that reached 37/40 on check detection:
every piece with colour, type, algebraic square and numeric column/rank, plus
the general movement rules written into the question text. No engine evaluation,
no legal-move list, no attack list, no gap - the first principle applies here as
everywhere else in this folder.
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import chess
from typesafe_sdk import Noul, Score, TypeSafeClient

from depth_gap import auc, heuristic_report, material_score, oracle_report, ranking_report

HERE = Path(__file__).resolve().parent
MODEL = os.environ.get('JEV_MODEL', 'jev-1.13.0')
LOCAL = threading.local()

RULES = (
    'Standard chess rules apply. A rook moves along its column or rank, a bishop along its '
    'diagonals, a queen along either, and a knight jumps to a square two columns and one rank '
    'away or two ranks and one column away. Rook, bishop and queen lines are blocked by any '
    'piece in between. A pawn captures one square diagonally forward, white towards higher '
    'ranks and black towards lower ranks. Columns are numbered a=1 to h=8.'
)

QUESTIONS = {
    'unresolved': Noul(instructions=(
        RULES + ' Material is about to change hands here: there are captures or capture threats '
        'on this position whose outcome is not yet settled, so the pieces standing now are not '
        'the pieces that will be standing a few moves from now.')),
    'free_piece': Noul(instructions=(
        RULES + ' At least one piece belonging to the side to move can be taken by the opponent '
        'right now without the opponent losing a piece of equal value in return.')),
    'trap': Noul(instructions=(
        RULES + ' A natural, sensible-looking move for the side to move would lose material here, '
        'because of a reply the opponent has available afterwards.')),
    'complexity': Score(criteria=[
        'Simple: few pieces are left and they barely interact, so the position plays itself and '
        'the same plan works whatever the opponent does.',
        'Ordinary: a normal middlegame where several pieces interact but the position holds '
        'together on general principles.',
        'Complicated: many pieces interact at once, several plans are live for both sides, and '
        'what happens on one part of the board changes what works on another.',
    ], instructions=RULES + ' How complicated is this position?'),
    'sharpness': Score(criteria=[
        'Quiet: pieces are not touching, nothing is under threat, and any reasonable move keeps '
        'the position roughly as it is.',
        'Tense: pieces face each other and threats exist, but nothing is forced yet.',
        'Sharp: captures, checks or threats dominate the position and the wrong move changes the '
        'material balance immediately.',
    ], instructions=RULES + ' How forcing is this position for the side to move?'),
}


def client():
    if not hasattr(LOCAL, 'client'):
        LOCAL.client = TypeSafeClient()
    return LOCAL.client


def state_for(fen: str, every_square: bool = False):
    """Pieces with algebraic and numeric coordinates; nothing derived from an engine.

    `every_square` lists all 64 squares, empty ones included, so the request is the
    same length whatever is left on the board. The default lists only occupied
    squares, which makes an emptier board a shorter prompt - and the first run
    found the answers running backwards against how full the board is, which that
    length difference could by itself explain.
    """
    board = chess.Board(fen)
    pieces = {}
    squares = chess.SQUARES if every_square else sorted(board.piece_map())
    for square in squares:
        piece = board.piece_at(square)
        name = chess.square_name(square)
        where = f'column {chess.square_file(square) + 1}, rank {chess.square_rank(square) + 1}'
        if piece is None:
            pieces[f'empty {name}'] = where
        else:
            colour = 'White' if piece.color else 'Black'
            pieces[f'{colour} {chess.piece_name(piece.piece_type)} {name}'] = where
    return {
        'side_to_move': 'White' if board.turn else 'Black',
        'pieces': pieces,
        'castling_rights': board.castling_xfen(),
        'en_passant': chess.square_name(board.ep_square) if board.ep_square is not None else None,
    }


def ask(row, every_square=False):
    started = time.perf_counter()
    result = client().system_one(model=MODEL, state=state_for(row['fen'], every_square), questions=QUESTIONS)
    answers = {}
    for key, answer in result.answers.items():
        # Noul answers carry `.noul` (probability the statement holds); Score answers carry
        # `.score` (position on the level scale). Both are already 0..1 rankable numbers.
        value = getattr(answer, 'noul', None)
        if value is None:
            value = getattr(answer, 'score', None)
        answers[key] = {'value': value, 'confidence': getattr(answer, 'confidence', None),
                        'probabilities': dict(getattr(answer, 'probabilities', {}) or {})}
    return {
        **row,
        'jev': {
            'answers': answers,
            'latency_ms': round((time.perf_counter() - started) * 1000, 2),
            'usage': {'input_tokens': result.usage.input_tokens, 'output_tokens': result.usage.output_tokens},
            'model': result.model,
        },
    }


def answer_value(row, key):
    value = row['jev']['answers'][key]['value']
    return -1.0 if value is None else value


def conditional_auc(rows, key, threshold, buckets=4):
    """AUC inside piece-count bands, so a ranking cannot win on game phase alone.

    material_score is close to a measure of how far the game has gone. A question
    that scores well overall but at chance inside each band is reading the phase,
    not the position - the same distinction the sliding-puzzle runs kept hitting.
    """
    counts = sorted(r['features']['piece_count'] for r in rows)
    if not counts:
        return None
    edges = [counts[min(len(counts) - 1, int(len(counts) * (i + 1) / buckets))] for i in range(buckets)]
    weighted, total = 0.0, 0
    per_band = []
    low = -1
    for high in sorted(set(edges)):
        band = [r for r in rows if low < r['features']['piece_count'] <= high]
        low = high
        value = auc(band, key, threshold) if band else None
        per_band.append({'max_piece_count': high, 'positions': len(band), 'auc': value})
        if value is not None:
            weighted += value * len(band)
            total += len(band)
    return {'pooled': round(weighted / total, 4) if total else None, 'bands': per_band}


def rank_of(rows, key):
    """Rank position within `rows`, so two scores on different scales can be added."""
    order = sorted(range(len(rows)), key=lambda i: key(rows[i]))
    ranks = [0] * len(rows)
    for place, index in enumerate(order):
        ranks[index] = place
    return ranks


def report(rows, threshold):
    """Every ranking side by side: chance, heuristic, each Jev question, oracle."""
    out = {f'heuristic.{name}': table for name, table in heuristic_report(rows, threshold).items()}
    out['oracle'] = oracle_report(rows, threshold)
    for key in QUESTIONS:
        out[f'jev.{key}'] = ranking_report(rows, threshold, lambda r, k=key: answer_value(r, k))
    # Does the model add anything on top of the code signal it has to beat? Ranks, not raw
    # values: a Noul is 0..1 and a Score is a position on its level scale.
    material_rank = rank_of(rows, lambda r: material_score(r['features']))
    for key in ('complexity', 'sharpness'):
        jev_rank = rank_of(rows, lambda r, k=key: answer_value(r, k))
        combined = {id(r): jev_rank[i] + material_rank[i] for i, r in enumerate(rows)}
        out[f'jev.{key}_plus_material'] = ranking_report(rows, threshold, lambda r: combined[id(r)])
    for name, table in out.items():
        table['conditional_auc'] = conditional_auc(rows, ranking_key(name, rows), threshold)
    return out


def ranking_key(name, rows):
    """The score function behind a report entry, for the conditional pass."""
    if name == 'oracle':
        return lambda r: r['gap']
    if name == 'heuristic.material':
        return lambda r: material_score(r['features'])
    if name == 'heuristic.tactical':
        from depth_gap import tactical_score
        return lambda r: tactical_score(r['features'])
    if name.endswith('_plus_material'):
        key = name[len('jev.'):-len('_plus_material')]
        material_rank = rank_of(rows, lambda r: material_score(r['features']))
        jev_rank = rank_of(rows, lambda r, k=key: answer_value(r, k))
        combined = {id(r): jev_rank[i] + material_rank[i] for i, r in enumerate(rows)}
        return lambda r: combined[id(r)]
    return lambda r, k=name[len('jev.'):]: answer_value(r, k)


def run(gap_file: Path, output: Path, limit: int, workers: int, threshold: int, every_square: bool = False):
    if output.exists():
        raise FileExistsError('Use a new output name to preserve previous evidence')
    source = json.loads(gap_file.read_text())
    rows = source['positions'][:limit] if limit else source['positions']
    done = []
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(ask, row, every_square): row for row in rows}
        for index, future in enumerate(as_completed(futures), 1):
            done.append(future.result())
            if index % 25 == 0:
                print(f'{index}/{len(rows)} {round(time.perf_counter() - started, 1)}s', flush=True)
    done.sort(key=lambda r: (r['match'], r['game'], r['ply']))
    usage = [r['jev']['usage'] for r in done]
    latency = sorted(r['jev']['latency_ms'] for r in done)
    payload = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'design': ('Jev ranks positions by how much they need a deeper search, seeing only the piece '
                   'placement. Rankings are scored against the depth-4 gap labels from depth_gap.py, '
                   'which Jev never sees. Chance, a code-only heuristic and the oracle ceiling are in '
                   'the same table.'),
        'model': MODEL,
        'gap_file': str(gap_file),
        'gap_config': source['config'],
        'gap_summary': source['summary'],
        'config': {'limit': limit, 'workers': workers, 'threshold': threshold,
                   'every_square': every_square},
        'questions': {key: {'type': type(q).__name__,
                            'instructions': q.instructions,
                            **({'criteria': list(q.criteria)} if getattr(q, 'criteria', None) else {})}
                      for key, q in QUESTIONS.items()},
        'rankings': report(done, threshold),
        'usage': {'requests': len(done),
                  'input_tokens': sum(u['input_tokens'] for u in usage),
                  'output_tokens': sum(u['output_tokens'] for u in usage),
                  'latency_ms_median': latency[len(latency) // 2] if latency else None},
        'elapsed_seconds': round(time.perf_counter() - started, 2),
        'positions': done,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps({'rankings': payload['rankings'], 'usage': payload['usage']}, ensure_ascii=False, indent=2), flush=True)
    return payload


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--gap-file', type=Path, default=HERE / 'budget' / 'depth-gap.json')
    p.add_argument('--output', type=Path, default=HERE / 'budget' / 'judge-01.json')
    p.add_argument('--limit', type=int, default=0, help='0 uses every labelled position')
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--threshold', type=int, default=30)
    p.add_argument('--every-square', action='store_true',
                   help='list all 64 squares so request length does not vary with how full the board is')
    args = p.parse_args()
    run(args.gap_file, args.output, args.limit, args.workers, args.threshold, args.every_square)
