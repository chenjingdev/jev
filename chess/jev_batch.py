"""Ten new games: five fixed opening pairs; three isolated pair jobs in parallel."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import io
import math
from pathlib import Path
import subprocess
import sys
import time
import chess.pgn
from jev_engine_match import BASE_NAMES, HYBRID_NAMES, hybrid_name_for, checkpoint, summarize

HERE = Path(__file__).resolve().parent
OPENINGS = [
    ('open-game', ['e2e4', 'e7e5', 'g1f3', 'b8c6']),
    ('sicilian', ['e2e4', 'c7c5', 'g1f3', 'd7d6']),
    ('queens-gambit', ['d2d4', 'd7d5', 'c2c4', 'e7e6']),
    ('indian', ['d2d4', 'g8f6', 'c2c4', 'g7g6']),
    ('english', ['c2c4', 'e7e5', 'b1c3', 'g8f6']),
]


def pair_job(index, name, opening, directory, selector='jev', base='stockfish', margin=35, max_plies=400, depth=2):
    path = directory / name
    with path.with_suffix('.log').open('w') as log:
        result = subprocess.run([sys.executable, str(HERE / 'jev_engine_match.py'),
                                 '--output', str(path), '--seed', str(73419 + index * 10000),
                                 '--selector', selector, '--base', base, '--margin', str(margin),
                                 '--max-plies', str(max_plies), '--depth', str(depth), '--opening', *opening],
                                stdout=log, stderr=subprocess.STDOUT)
    return index, name, path, result.returncode


def analyze(payload):
    hybrid = payload.get('engine_a', {}).get('name', HYBRID_NAMES['jev'])
    wins = draws = losses = unfinished = 0
    pairs = []
    for pair in range(5):
        games = [g for g in payload['games'] if g['pair'] == pair + 1]
        score = 0
        complete = len(games) == 2 and all(g['result'] != '*' for g in games)
        for g in games:
            if g['result'] == '*': unfinished += 1; continue
            if g['result'] == '1/2-1/2': draws += 1; score += .5; continue
            won = (g['result'] == '1-0') == (g['white'] == hybrid)
            if won: wins += 1; score += 1
            else: losses += 1
        pairs.append({'opening': OPENINGS[pair][0], 'complete': complete, 'jev_points': score,
                      'opponent_points': 2-score if complete else None})
    positive = sum(p['complete'] and p['jev_points'] > 1 for p in pairs)
    negative = sum(p['complete'] and p['jev_points'] < 1 for p in pairs)
    n = positive + negative
    p_value = min(1, 2 * sum(math.comb(n, k) for k in range(min(positive, negative) + 1)) / 2**n) if n else 1
    return {'wins': wins, 'draws': draws, 'losses': losses, 'unfinished': unfinished,
            'pairs': pairs, 'pair_wins': positive, 'pair_losses': negative,
            'paired_sign_test_two_sided_p': p_value,
            'interpretation': f'Exploratory only: five fixed opening pairs, selector={payload.get("selector", "jev")}. Ten games cannot separate small strength differences; compare per-decision referee scores across arms.'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--name', default='jev-ten-01')
    p.add_argument('--selector', choices=sorted(HYBRID_NAMES), default='jev')
    p.add_argument('--base', choices=sorted(BASE_NAMES), default='stockfish')
    p.add_argument('--margin', type=int, default=None, help='35cp for stockfish, 30 weak-engine units otherwise')
    p.add_argument('--max-plies', type=int, default=400)
    p.add_argument('--depth', type=int, default=2, help='weak engine depth')
    args = p.parse_args()
    margin = args.margin if args.margin is not None else (35 if args.base == 'stockfish' else 30)
    if Path(args.name).name != args.name: raise ValueError('Invalid name')
    directory = HERE / 'matches' / args.name
    directory.mkdir(exist_ok=False)
    destination = directory.with_suffix('.json')
    if destination.exists(): raise FileExistsError(destination)
    payload = {'status': 'running', 'created_at': datetime.now(timezone.utc).isoformat(),
               'design': (f'Five preselected four-ply opening positions, paired colors; three isolated pair jobs in parallel. '
                          f'Base engine={args.base} (stockfish: 5000 nodes, MultiPV=3; weak: depth-{args.depth} material+PST, top-3). '
                          f'Shortlist margin={margin}. Selector={args.selector}. All ten games are new.'),
               'selector': args.selector, 'base_engine': args.base, 'margin': margin, 'depth': args.depth if args.base == 'weak' else None,
               'engine_a': {'name': hybrid_name_for(args.base, args.selector).replace('Weak', f'Weak{args.depth}')},
               'engine_b': {'name': BASE_NAMES[args.base].replace('Weak', f'Weak{args.depth}')},
               'openings': OPENINGS, 'games': [], 'failures': [], 'workers': 3}
    checkpoint(destination, payload)
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [pool.submit(pair_job, i, name, opening, directory, args.selector, args.base, margin, args.max_plies, args.depth)
                for i, (name, opening) in enumerate(OPENINGS)]
        for future in as_completed(jobs):
            index, name, path, code = future.result()
            if code:
                payload['failures'].append({'opening': name, 'log': str(path.with_suffix('.log'))})
            if path.with_suffix('.json').exists():
                d = json.loads(path.with_suffix('.json').read_text())
                for g in d['games']:
                    g.update(pair=index+1, opening_name=name, seed=d['config']['seed'],
                             pair_game=g['game'], game=index*2+g['game'])
                    payload['games'].append(g)
            payload['games'].sort(key=lambda g: g['game'])
            payload['summary'] = summarize(payload)
            payload['analysis'] = analyze(payload)
            checkpoint(destination, payload)
            print(name, 'finished', payload['summary'], flush=True)
    payload['status'] = 'failed' if payload['failures'] else 'complete'
    payload['elapsed_seconds'] = round(time.perf_counter()-started, 2)
    payload['points'] = payload['summary']['points']
    checkpoint(destination, payload)
    pgns = []
    for index, (name, _) in enumerate(OPENINGS):
        path = (directory / name).with_suffix('.pgn')
        if not path.exists(): continue
        stream = io.StringIO(path.read_text())
        for pair_game in (1, 2):
            game = chess.pgn.read_game(stream)
            if game is None: break
            game.headers['Round'] = str(index * 2 + pair_game)
            game.headers['Opening'] = name
            pgns.append(str(game))
    directory.with_suffix('.pgn').write_text('\n\n'.join(pgns) + '\n')
    print(json.dumps({'status':payload['status'], 'summary':payload['summary'], 'analysis':payload['analysis'],
                      'elapsed_seconds':payload['elapsed_seconds']}, indent=2), flush=True)


if __name__ == '__main__': main()
