"""Seeded 9x9 openings: each ply sampled uniformly from GNU Go's own near-best moves.

GNU Go's genmove is seed-independent, so plain-vs-plain from the empty board is always the
same game; openings supply the variety, as in chess. Sampling from the engine's shortlist
(within --margin of its top value, at most --width moves) keeps openings sensible rather
than uniformly random. Symmetric duplicates are reported but not removed.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import random
from gnugo import GnuGo

HERE = Path(__file__).resolve().parent


def transforms(size=9):
    cols = 'ABCDEFGHJ'
    def parse(v):
        return cols.index(v[0]), int(v[1:]) - 1
    def fmt(c, r):
        return f'{cols[c]}{r + 1}'
    n = size - 1
    fns = [lambda c, r: (c, r), lambda c, r: (n - c, r), lambda c, r: (c, n - r), lambda c, r: (n - c, n - r),
           lambda c, r: (r, c), lambda c, r: (n - r, c), lambda c, r: (r, n - c), lambda c, r: (n - r, n - c)]
    def canon(moves):
        return min(tuple(fmt(*f(*parse(m))) for m in moves) for f in fns)
    return canon


def make(count, plies, seed, level, margin, width):
    rng = random.Random(seed)
    canon = transforms()
    out = []
    for i in range(count):
        with GnuGo(level=level, seed=1) as e:
            color = 'black'
            moves = []
            for _ in range(plies):
                base, rows = e.ranked_moves(color)
                if base == 'PASS':
                    break
                best = rows[0]['value']
                pool = [r['move'] for r in rows if best - r['value'] <= margin][:width]
                mv = rng.choice(pool)
                e.play(color, mv)
                moves.append(mv)
                color = 'white' if color == 'black' else 'black'
        out.append({'name': f'op-{i:03d}', 'moves': moves, 'canonical': canon(moves)})
    distinct = len({tuple(o['canonical']) for o in out})
    return {'seed': seed, 'plies': plies, 'level': level, 'margin': margin, 'width': width,
            'count': count, 'distinct_up_to_symmetry': distinct, 'openings': out}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, default=HERE / 'openings-50.json')
    p.add_argument('--count', type=int, default=50)
    p.add_argument('--plies', type=int, default=4)
    p.add_argument('--seed', type=int, default=20260922)
    p.add_argument('--level', type=int, default=1)
    p.add_argument('--margin', type=float, default=3.0)
    p.add_argument('--width', type=int, default=6)
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError('Use a new output name')
    payload = make(a.count, a.plies, a.seed, a.level, a.margin, a.width)
    a.output.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in payload.items() if k != 'openings'}))
