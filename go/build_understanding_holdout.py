"""Prospective positions from plain GNU Go, selected without Jev picks or outcomes."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import random

from discrimination_test import features
from gnugo import GnuGo, shortlist
from make_openings import make, transforms
from understanding_probe import save

HERE = Path(__file__).resolve().parent


def collect_game(job):
    index, opening, seed, per_opening = job
    prefix, positions, passes = [], [], 0
    with GnuGo(level=1, seed=seed) as engine:
        colour = 'black'
        for move in opening['moves']:
            engine.play(colour, move)
            prefix.append((colour, move, False))
            colour = 'white' if colour == 'black' else 'black'
        for ply in range(len(prefix) + 1, 201):
            base, ranked = engine.ranked_moves(colour)
            options = shortlist(ranked, 2.0)
            if len(options) >= 2:
                positions.append({'id': f'holdout/op-{index:03d}/p{ply}', 'level': 1, 'seed': seed,
                                  'color': colour, 'moves': sorted(options), 'engine_move': base,
                                  'prefix': list(prefix), 'ply': ply, 'opening': opening['moves'],
                                  'opening_canonical': opening['canonical']})
            if base != 'PASS':
                assert engine.is_legal(colour, base)
            engine.play(colour, base)
            prefix.append((colour, base, True))
            passes = passes + 1 if base == 'PASS' else 0
            colour = 'white' if colour == 'black' else 'black'
            if passes >= 2:
                break
    # Position selection uses only opening id, ply, and seeded random sampling.
    rng = random.Random(f'{seed}-position-sample')
    selected = rng.sample(positions, min(per_opening, len(positions)))
    return {'opening_index': index, 'eligible_positions': len(positions),
            'termination': 'two_passes' if passes >= 2 else 'limit',
            'positions': sorted(selected, key=lambda p: p['ply'])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--openings', type=int, default=30)
    ap.add_argument('--per-opening', type=int, default=6)
    ap.add_argument('--seed', type=int, default=915270)
    ap.add_argument('--workers', type=int, default=8)
    args = ap.parse_args()
    if min(args.openings, args.per_opening, args.workers) < 1:
        ap.error('Counts must be positive')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x'):
        pass
    prior_raw = (HERE / 'openings-50.json').read_bytes()
    prior = json.loads(prior_raw)
    canonical = transforms()
    excluded = {canonical(o['moves']) for o in prior['openings']}
    generated = make(args.openings * 8, 6, args.seed, 1, 3.0, 6)
    chosen, seen = [], set(excluded)
    for o in generated['openings']:
        key = canonical(o['moves'])
        if key in seen:
            continue
        seen.add(key)
        chosen.append(o)
        if len(chosen) == args.openings:
            break
    if len(chosen) != args.openings:
        raise ValueError('Insufficient new opening families; do not reuse old ones')
    payload = {'design': 'Plain engine positions; new symmetry-canonical openings; no outcome selection.',
               'seed': args.seed, 'excluded_openings_sha256': hashlib.sha256(prior_raw).hexdigest(),
               'openings': chosen, 'status': 'collecting', 'positions': []}
    save(args.output, payload)
    jobs = [(i, o, args.seed + 10007 * i, args.per_opening) for i, o in enumerate(chosen)]
    with ProcessPoolExecutor(args.workers) as pool:
        games = list(pool.map(collect_game, jobs))
        positions = [p for g in games for p in g['positions']]
        collected = list(pool.map(features, positions))
    for p, f in zip(positions, collected):
        if p['engine_move'] != f['engine_move_now']:
            raise ValueError(f'Engine replay mismatch at {p["id"]}')
        p['features'] = f
    payload.update(status='complete', positions=positions,
                   games=[{k: v for k, v in g.items() if k != 'positions'} for g in games])
    save(args.output, payload)
    print(f'{len(chosen)} new opening families, {len(positions)} sampled positions; all base moves reproduced')


if __name__ == '__main__':
    main()
