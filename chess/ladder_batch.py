"""Many-game weak-engine match: one subprocess per opening pair, N pairs in parallel.

Used for the 100-game runs (50 openings x color-swapped pair). Selector and depths are
passed through to jev_engine_match.py; the plain opponent may search a different depth.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import chess.pgn
from jev_engine_match import BASE_NAMES, HYBRID_NAMES, hybrid_name_for, checkpoint, summarize

HERE = Path(__file__).resolve().parent


def pair_job(index, opening, directory, args):
    path = directory / opening['name']
    cmd = [sys.executable, str(HERE / 'jev_engine_match.py'), '--output', str(path),
           '--seed', str(args.seed + index * 10000), '--selector', args.selector, '--base', 'weak',
           '--depth', str(args.depth), '--opponent-depth', str(args.opponent_depth),
           '--margin', str(args.margin), '--max-plies', str(args.max_plies), '--opening', *opening['uci']]
    with path.with_suffix('.log').open('w') as log:
        code = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT).returncode
    return index, opening, path, code


def analyze(payload, hybrid):
    wins = draws = losses = unfinished = 0
    pairs = []
    by_pair = {}
    for g in payload['games']:
        by_pair.setdefault(g['pair'], []).append(g)
    for pair, games in sorted(by_pair.items()):
        score = 0
        complete = len(games) == 2 and all(g['result'] != '*' for g in games)
        for g in games:
            if g['result'] == '*':
                unfinished += 1
                continue
            if g['result'] == '1/2-1/2':
                draws += 1
                score += .5
                continue
            won = (g['result'] == '1-0') == (g['white'] == hybrid)
            wins += won
            losses += not won
            score += won
        pairs.append({'pair': pair, 'opening': games[0]['opening_name'], 'complete': complete, 'hybrid_points': score})
    positive = sum(p['complete'] and p['hybrid_points'] > 1 for p in pairs)
    negative = sum(p['complete'] and p['hybrid_points'] < 1 for p in pairs)
    n = positive + negative
    p_value = min(1, 2 * sum(math.comb(n, k) for k in range(min(positive, negative) + 1)) / 2 ** n) if n else 1
    games = wins + draws + losses
    score = (wins + draws / 2) / games if games else None
    # Normal-approximation CI for the hybrid's score fraction; games within a pair are not independent, so this is optimistic.
    ci = None
    if games:
        se = math.sqrt(max(score * (1 - score), 1e-9) / games)
        ci = [round(max(0, score - 1.96 * se), 3), round(min(1, score + 1.96 * se), 3)]
    elo = None
    if score is not None and 0 < score < 1:
        elo = round(-400 * math.log10(1 / score - 1), 1)
    return {'wins': wins, 'draws': draws, 'losses': losses, 'unfinished': unfinished, 'games': games,
            'score_fraction': round(score, 4) if score is not None else None, 'score_ci95_normal': ci,
            'elo_diff_estimate': elo, 'pair_wins': positive, 'pair_losses': negative,
            'paired_sign_test_two_sided_p': round(p_value, 4), 'pairs': pairs}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--name', required=True)
    p.add_argument('--openings', type=Path, default=HERE / 'openings-50.json')
    p.add_argument('--selector', choices=sorted(HYBRID_NAMES), default='jev')
    p.add_argument('--depth', type=int, default=2)
    p.add_argument('--opponent-depth', type=int, default=None)
    p.add_argument('--margin', type=int, default=30)
    p.add_argument('--max-plies', type=int, default=400)
    p.add_argument('--workers', type=int, default=10)
    p.add_argument('--seed', type=int, default=73419)
    args = p.parse_args()
    if args.opponent_depth is None:
        args.opponent_depth = args.depth
    if Path(args.name).name != args.name:
        raise ValueError('Invalid name')
    openings = json.loads(args.openings.read_text())['openings']
    directory = HERE / 'matches' / args.name
    directory.mkdir(exist_ok=False)
    destination = directory.with_suffix('.json')
    hybrid = hybrid_name_for('weak', args.selector).replace('Weak', f'Weak{args.depth}')
    opponent = f'Weak{args.opponent_depth}'
    payload = {'status': 'running', 'created_at': datetime.now(timezone.utc).isoformat(),
               'design': (f'{len(openings)} fixed openings from {args.openings.name}, color-swapped pairs, one subprocess per pair, '
                          f'{args.workers} in parallel. Hybrid: depth-{args.depth} weak engine + selector={args.selector}, '
                          f'top-3 within {args.margin} units. Opponent: plain depth-{args.opponent_depth} weak engine. '
                          'Deterministic engines; Jev adds API time.'),
               'selector': args.selector, 'base_engine': 'weak', 'depth': args.depth, 'opponent_depth': args.opponent_depth,
               'margin': args.margin, 'openings_file': args.openings.name,
               'engine_a': {'name': hybrid}, 'engine_b': {'name': opponent}, 'workers': args.workers,
               'games': [], 'failures': []}
    checkpoint(destination, payload)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = [pool.submit(pair_job, i, op, directory, args) for i, op in enumerate(openings)]
        done = 0
        for future in as_completed(jobs):
            index, opening, path, code = future.result()
            done += 1
            if code:
                payload['failures'].append({'opening': opening['name'], 'log': str(path.with_suffix('.log'))})
            if path.with_suffix('.json').exists():
                d = json.loads(path.with_suffix('.json').read_text())
                for g in d['games']:
                    g.update(pair=index + 1, opening_name=opening['name'], seed=d['config']['seed'],
                             pair_game=g['game'], game=index * 2 + g['game'])
                    payload['games'].append(g)
            payload['games'].sort(key=lambda g: g['game'])
            payload['summary'] = summarize(payload)
            payload['analysis'] = analyze(payload, hybrid)
            checkpoint(destination, payload)
            a = payload['analysis']
            print(f"{done}/{len(openings)} {opening['name']} W{a['wins']} D{a['draws']} L{a['losses']}", flush=True)
    payload['status'] = 'failed' if payload['failures'] else 'complete'
    payload['elapsed_seconds'] = round(time.perf_counter() - started, 2)
    payload['points'] = payload['summary']['points']
    checkpoint(destination, payload)
    pgns = []
    for index, op in enumerate(openings):
        path = (directory / op['name']).with_suffix('.pgn')
        if not path.exists():
            continue
        stream = io.StringIO(path.read_text())
        for pair_game in (1, 2):
            game = chess.pgn.read_game(stream)
            if game is None:
                break
            game.headers['Round'] = str(index * 2 + pair_game)
            game.headers['Opening'] = op['name']
            pgns.append(str(game))
    directory.with_suffix('.pgn').write_text('\n\n'.join(pgns) + '\n')
    print(json.dumps({k: payload[k] for k in ('status', 'points', 'elapsed_seconds')} | {'analysis': {k: v for k, v in payload['analysis'].items() if k != 'pairs'}},
                     ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
