"""Many-pair 9x9 Go match: one subprocess per seed (colour-swapped pair), N in parallel.

Mirror of chess/ladder_batch.py. Variety comes from a seeded opening set (make_openings.py):
GNU Go's genmove is seed-independent, so without openings every plain game is the same game.
A plain-vs-plain pair is two identical games and always scores 1-1.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
from jev_go_match import checkpoint, hybrid_name_for

HERE = Path(__file__).resolve().parent


def pair_job(index, opening, directory, args):
    path = directory / opening['name']
    cmd = [sys.executable, str(HERE / 'jev_go_match.py'), '--output', str(path),
           '--seed', str(args.seed + index * 10007), '--selector', args.selector, '--level', str(args.level),
           '--margin', str(args.margin), '--max-plies', str(args.max_plies),
           *(['--min-confidence', str(args.min_confidence)] if args.min_confidence is not None else []),
           '--opening', *opening['moves']]
    with path.with_suffix('.log').open('w') as log:
        code = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT).returncode
    return index, opening, path, code


def analyze(games, hybrid):
    wins = losses = unfinished = 0
    margins = []
    by_pair = {}
    for g in games:
        by_pair.setdefault(g['pair'], []).append(g)
    pairs = []
    for pair, gs in sorted(by_pair.items()):
        score = 0
        for g in gs:
            if g['winner'] is None:
                unfinished += 1
                continue
            won = g[g['winner']] == hybrid
            wins += won
            losses += not won
            score += won
            margins.append(g['margin'] if won else -g['margin'])
        pairs.append({'pair': pair, 'hybrid_points': score, 'complete': len(gs) == 2 and all(g['winner'] for g in gs)})
    n = wins + losses
    rate = wins / n if n else None
    se = (rate * (1 - rate) / n) ** .5 if n else None
    return {'games': len(games), 'wins': wins, 'losses': losses, 'unfinished': unfinished,
            'win_rate': round(rate, 4) if rate is not None else None,
            'win_rate_ci95': [round(rate - 1.96 * se, 3), round(rate + 1.96 * se, 3)] if n else None,
            'mean_margin_for_hybrid': round(sum(margins) / len(margins), 2) if margins else None,
            'pairs_won': sum(p['hybrid_points'] == 2 for p in pairs), 'pairs_split': sum(p['hybrid_points'] == 1 for p in pairs),
            'pairs_lost': sum(p['hybrid_points'] == 0 for p in pairs), 'pairs': pairs}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--name', required=True)
    p.add_argument('--pairs', type=int, default=50)
    p.add_argument('--selector', choices=['jev', 'random', 'none'], default='jev')
    p.add_argument('--level', type=int, default=1)
    p.add_argument('--margin', type=float, default=2.0)
    p.add_argument('--max-plies', type=int, default=200)
    p.add_argument('--seed', type=int, default=20260922)
    p.add_argument('--min-confidence', type=float, default=None)
    p.add_argument('--parallel', type=int, default=8)
    p.add_argument('--openings', type=Path, default=HERE / 'openings-50.json')
    args = p.parse_args()
    out = HERE / 'matches' / args.name
    if out.with_suffix('.json').exists():
        raise FileExistsError('Use a new --name to preserve previous evidence')
    directory = HERE / 'matches' / args.name
    directory.mkdir(parents=True, exist_ok=True)
    hybrid = hybrid_name_for(args.level, args.selector, args.min_confidence)
    openings = json.loads(args.openings.read_text())['openings'][:args.pairs]
    payload = {'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'running', 'name': args.name,
               'config': {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()} | {'hybrid': hybrid, 'opponent': f'GnuGo L{args.level}', 'pairs': len(openings)}, 'games': [], 'failed_pairs': []}
    started = time.perf_counter()
    with ThreadPoolExecutor(args.parallel) as pool:
        futures = [pool.submit(pair_job, i, op, directory, args) for i, op in enumerate(openings)]
        for f in as_completed(futures):
            index, opening, path, code = f.result()
            if code != 0 or not path.with_suffix('.json').exists():
                payload['failed_pairs'].append({'pair': index, 'code': code})
                continue
            pair = json.loads(path.with_suffix('.json').read_text())
            for g in pair['games']:
                payload['games'].append({'pair': index, 'opening_name': opening['name'], 'opening': opening['moves'], 'seed': pair['config']['seed'], 'game': g['game'],
                                         'black': g['black'], 'white': g['white'], 'winner': g['winner'],
                                         'margin': g['margin'], 'score': g['score'], 'termination': g['termination'],
                                         'plies': g['plies'], 'file': path.with_suffix('.json').name})
            s = pair['summary']
            payload.setdefault('totals', {'decisions': 0, 'interventions': 0, 'gated': 0, 'jev_disagreed': 0, 'tokens': {'input': 0, 'output': 0}})
            for k in ('decisions', 'interventions', 'gated', 'jev_disagreed'):
                payload['totals'][k] += s[k]
            payload['totals']['tokens']['input'] += s['tokens']['input']
            payload['totals']['tokens']['output'] += s['tokens']['output']
            payload['analysis'] = analyze(payload['games'], hybrid)
            payload['elapsed_seconds'] = round(time.perf_counter() - started, 1)
            checkpoint(out.with_suffix('.json'), payload)
            a = payload['analysis']
            print(f"pair {index:03d} done: {a['wins']}-{a['losses']} ({len(payload['games'])} games)", flush=True)
    payload['status'] = 'complete' if not payload['failed_pairs'] else 'partial'
    payload['elapsed_seconds'] = round(time.perf_counter() - started, 1)
    checkpoint(out.with_suffix('.json'), payload)
    a = payload['analysis']
    print(json.dumps({k: a[k] for k in a if k != 'pairs'} | {'totals': payload.get('totals'), 'status': payload['status']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
