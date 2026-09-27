"""Counterfactual replay for 9x9 Go batches: value of each selector intervention against
the same deterministic GNU Go opponent.

For every decision where the selector's move differs from the engine's, replay the game up
to that point, then finish two branches with plain GNU Go on both sides: one after the
selector's move, one after the engine's move. Outcome is 1/0 for the hybrid side (no draws
with komi 7.5). Mirror of chess/counterfactual_replay.py; no API call is needed.

GNU Go's answer depends on the position AND on its query history (persistent reading caches),
so the replay issues the same GTP queries the match did at every prefix ply (reg_genmove,
top_moves, is_legal) before playing the recorded move. Without that, 2-4 games per 100 fail
the identity check sum(deltas) == actual - plain.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import statistics
from gnugo import GnuGo
from jev_go_match import result_for

HERE = Path(__file__).resolve().parent


def other(color):
    return 'white' if color == 'black' else 'black'


def finish(engine, color, hybrid_color, max_plies=200):
    """Both sides plain from the current position; returns hybrid outcome (1.0 / 0.0).
    Same query sequence per ply as jev_go_match.run: ranked_moves, is_legal, play."""
    passes = 0
    for _ in range(max_plies):
        base, _rows = engine.ranked_moves(color)
        if base != 'PASS':
            engine.is_legal(color, base)
        engine.play(color, base)
        passes = passes + 1 if base == 'PASS' else 0
        color = other(color)
        if passes >= 2:
            winner, _ = result_for(engine.final_score())
            return 1.0 if winner == hybrid_color else 0.0
    return None


def branch(level, seed, prefix, color, move, hybrid_color):
    with GnuGo(level=level, seed=seed) as e:
        for c, v, queried in prefix:
            if queried:  # replay the match's queries so the engine's cache history matches
                e.ranked_moves(c)
                if v != 'PASS':
                    e.is_legal(c, v)
            e.play(c, v)
        e.ranked_moves(color)
        if move != 'PASS':
            e.is_legal(color, move)
        e.play(color, move)
        return finish(e, other(color), hybrid_color)


def job(args):
    level, seed, prefix, color, sel, base, hybrid_color, meta = args
    a = branch(level, seed, prefix, color, sel, hybrid_color)
    b = branch(level, seed, prefix, color, base, hybrid_color)
    return {**meta, 'selector_move': sel, 'engine_move': base, 'selector_outcome': a, 'engine_outcome': b,
            'delta': None if a is None or b is None else a - b}


def collect_jobs(directory):
    jobs = []
    for path in sorted(directory.glob('op-*.json')):
        pair = json.loads(path.read_text())
        level, seed = pair['config']['level'], pair['config']['seed']
        hybrid = pair['engine_a']['name']
        for g in pair['games']:
            if g['winner'] is None:
                continue  # unfinished game (failed pair): no actual outcome to compare against
            hybrid_color = 'black' if g['black'] == hybrid else 'white'
            prefix = []
            for m in g['moves']:
                d = m.get('jev') or m.get('random_control')
                if d:
                    sel = d.get('jev_move', d['selected_move'])
                    if sel != d['base_move']:
                        meta = {'file': path.name, 'game': g['game'], 'ply': m['ply'], 'confidence': d.get('confidence'),
                                'gated': d.get('gated', False), 'played': d['selected_move'] == sel,
                                'actual': 1.0 if g['winner'] == hybrid_color else 0.0}
                        jobs.append((level, seed, list(prefix), m['side'], sel, d['base_move'], hybrid_color, meta))
                prefix.append((m['side'], m['move'], not m.get('opening')))
    return jobs


def block(rows):
    deltas = [r['delta'] for r in rows if r['delta'] is not None]
    if not deltas:
        return {'n': 0}
    se = statistics.pstdev(deltas) / len(deltas) ** .5 if len(deltas) > 1 else 0.0
    return {'n': len(deltas), 'selector_move_outcome': round(statistics.mean(r['selector_outcome'] for r in rows), 4),
            'engine_move_outcome': round(statistics.mean(r['engine_outcome'] for r in rows), 4),
            'better': sum(d > 0 for d in deltas), 'same': sum(d == 0 for d in deltas), 'worse': sum(d < 0 for d in deltas),
            'net_per_decision': round(statistics.mean(deltas), 4), 'se_approx': round(se, 4)}


def summarize(rows):
    out = {'all_disagreements': block(rows)}
    if any(r['gated'] for r in rows):
        out['played'] = block([r for r in rows if r['played']])
        out['gated_out'] = block([r for r in rows if not r['played']])
    if any(r['confidence'] is not None for r in rows):
        bands = [(0, .1), (.1, .2), (.2, .3), (.3, .4), (.4, .5), (.5, 1.01)]
        out['by_confidence'] = {f'{lo:.1f}-{min(hi, 1):.1f}': block([r for r in rows if r['confidence'] is not None and lo <= r['confidence'] < hi])
                                for lo, hi in bands}
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('name')
    p.add_argument('--workers', type=int, default=10)
    p.add_argument('--suffix', default='counterfactual', help='output is matches/<name>.<suffix>.json')
    a = p.parse_args()
    directory = HERE / 'matches' / a.name
    out = HERE / 'matches' / f'{a.name}.{a.suffix}.json'
    if out.exists():
        raise FileExistsError('Use a new name to preserve previous evidence')
    jobs = collect_jobs(directory)
    print(f'{a.name}: {len(jobs)} disagreements', flush=True)
    with ProcessPoolExecutor(a.workers) as pool:
        rows = list(pool.map(job, jobs, chunksize=4))
    payload = {'name': a.name, 'disagreements': len(rows), 'summary': summarize(rows), 'rows': rows}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(json.dumps(payload['summary'], ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
