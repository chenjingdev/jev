"""Paired Stockfish+Jev smoke match; engine scores never enter API requests."""
from __future__ import annotations
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import time
import chess
import chess.engine
import chess.pgn
from typesafe_sdk import Choice, TypeSafeClient

HERE = Path(__file__).resolve().parent
MODEL = 'jev-1.13.0'
INSTRUCTIONS = (
    'You are playing standard chess as `side_to_move`. Choose the move that gives '
    'your side the best practical position, considering king safety, piece activity, '
    'coordination and useful threats. `pieces` lists the current occupied squares. '
    'Options are moves in UCI notation: origin square followed by destination square, '
    'with an optional promotion letter. Choose one option using the supplied position.'
)


def make_request(board, candidates, seed):
    moves = sorted(candidates)
    if len(moves) < 2 or len(set(moves)) != len(moves):
        raise ValueError('Need at least two distinct candidates')
    if any(chess.Move.from_uci(m) not in board.legal_moves for m in moves):
        raise ValueError('Illegal candidate')
    random.Random(seed).shuffle(moves)
    return {
        'model': MODEL,
        'state': {
            'side_to_move': 'white' if board.turn else 'black',
            'pieces': {chess.square_name(s): ('white ' if p.color else 'black ') + chess.piece_name(p.piece_type)
                       for s, p in sorted(board.piece_map().items())},
            'castling_rights': board.castling_xfen(),
            'en_passant': chess.square_name(board.ep_square) if board.ep_square is not None else None,
        },
        'questions': {'move': {'type': 'choice', 'instructions': INSTRUCTIONS,
                               'criteria': {m: None for m in moves}}},
    }


def shortlist(ranked, margin):
    # A forced mate score is not comparable to centipawns; keep the engine move.
    if ranked[0]['cp'] is None:
        return [ranked[0]['move']]
    best = ranked[0]['cp']
    return [r['move'] for r in ranked if r['cp'] is not None and best - r['cp'] <= margin]


def collect_candidates(engine, board, nodes):
    """Use one completed MultiPV depth, never mixed depths at the node cutoff."""
    count = min(3, board.legal_moves.count())
    depths = {}
    completed = {}
    observed_nodes = 0
    started = time.perf_counter()
    engine.configure({'Clear Hash': None})
    with engine.analysis(board, chess.engine.Limit(nodes=nodes), multipv=count,
                         info=chess.engine.INFO_ALL) as stream:
        for info in stream:
            observed_nodes = max(observed_nodes, info.get('nodes', 0))
            if not info.get('pv') or 'score' not in info or 'depth' not in info:
                continue
            depth = info['depth']
            rank = info.get('multipv', 1)
            # A new rank-1 report starts another pass, even at the same depth.
            # Snapshot completed passes so a partial reorder cannot corrupt them.
            if rank == 1:
                depths[depth] = {}
            if info.get('lowerbound') or info.get('upperbound'):
                continue
            score = info['score'].pov(board.turn)
            depths.setdefault(info['depth'], {})[info.get('multipv', 1)] = {
                'move': info['pv'][0].uci(), 'cp': score.score(), 'mate': score.mate(),
                'pv': [m.uci() for m in info['pv']], 'rank': info.get('multipv', 1),
            }
            rows = depths[depth]
            if rank == count and set(rows) == set(range(1, count + 1)) and len({r['move'] for r in rows.values()}) == count:
                completed[depth] = dict(rows)
    if not completed:
        raise RuntimeError('No complete MultiPV iteration; raise node budget')
    depth = max(completed)
    ranked = [completed[depth][i] for i in range(1, count + 1)]
    if len({r['move'] for r in ranked}) != count:
        raise RuntimeError('Duplicate MultiPV moves')
    if any(chess.Move.from_uci(r['move']) not in board.legal_moves for r in ranked):
        raise RuntimeError('Illegal engine candidate')
    return ranked, {'depth': depth, 'nodes': observed_nodes,
                    'elapsed_ms': round((time.perf_counter() - started) * 1000, 2)}


def ask_jev(client, request, base):
    q = request['questions']['move']
    started = time.perf_counter()
    result = client.system_one(model=request['model'], state=request['state'],
                              questions={'move': Choice(instructions=q['instructions'], criteria=q['criteria'])})
    answer = result.answers['move']
    if answer.choice not in q['criteria'] or set(answer.probabilities) != set(q['criteria']):
        raise ValueError('Jev response does not match candidates')
    return {
        'base_move': base, 'selected_move': answer.choice,
        'intervention': answer.choice != base, 'enabled': True,
        'latency_ms': round((time.perf_counter() - started) * 1000, 2),
        'confidence': answer.confidence,
        'candidates': [{'move': m, 'probability': p, 'selected': m == answer.choice}
                       for m, p in answer.probabilities.items()],
        'request': request,
        'response': {'model': result.model,
                     'answers': {'move': {'type': 'choice', 'choice': answer.choice,
                                          'confidence': answer.confidence,
                                          'probabilities': dict(answer.probabilities)}},
                     'usage': {'input_tokens': result.usage.input_tokens,
                               'output_tokens': result.usage.output_tokens}},
    }


HYBRID_NAMES = {'jev': 'Stockfish + Jev', 'random': 'Stockfish + Random', 'none': 'Stockfish (plain)'}
BASE_NAMES = {'stockfish': 'Stockfish', 'weak': 'Weak'}


def hybrid_name_for(base, selector):
    if selector == 'none':
        return f"{BASE_NAMES[base]} (plain)"
    return f"{BASE_NAMES[base]} + {'Jev' if selector == 'jev' else 'Random'}"


def random_pick(options, base, seed, number, ply):
    """Uniform choice among the same shortlist Jev would see; no API call."""
    choice = random.Random(f'pick-{seed}-{number}-{ply}').choice(sorted(options))
    return {'base_move': base, 'selected_move': choice, 'intervention': choice != base,
            'options': sorted(options), 'selector': 'random'}


def checkpoint(path, payload):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    tmp.replace(path)


def summarize(payload):
    hybrid = payload.get('engine_a', {}).get('name', HYBRID_NAMES['jev'])
    opponent = payload.get('engine_b', {}).get('name', 'Stockfish')
    calls = [m['jev'] for g in payload['games'] for m in g['moves'] if m.get('jev')]
    randoms = [m['random_control'] for g in payload['games'] for m in g['moves'] if m.get('random_control')]
    points = {hybrid: 0, opponent: 0}
    for g in payload['games']:
        if g['result'] == '1-0': points[g['white']] += 1
        elif g['result'] == '0-1': points[g['black']] += 1
        elif g['result'] == '1/2-1/2':
            points[g['white']] += .5
            points[g['black']] += .5
    latency = [c['latency_ms'] for c in calls]
    return {'points': points, 'calls': len(calls), 'interventions': sum(c['intervention'] for c in calls),
            'jev_total_ms': round(sum(latency), 2),
            'jev_mean_ms': round(sum(latency) / len(latency), 2) if latency else None,
            'tokens': sum(c['response']['usage']['input_tokens'] + c['response']['usage']['output_tokens'] for c in calls),
            'random_picks': len(randoms), 'random_interventions': sum(c['intervention'] for c in randoms),
            'finished_games': sum(g['result'] != '*' for g in payload['games'])}


def run(output, engine_path, nodes=5000, margin=35, max_plies=400, opening=(), seed=73419, selector='jev', base='stockfish', depth=2, opponent_depth=None):
    if nodes < 1 or margin < 0 or max_plies < 1 or selector not in HYBRID_NAMES or base not in BASE_NAMES or depth < 1:
        raise ValueError('Invalid match configuration')
    if opponent_depth is None:
        opponent_depth = depth
    if opponent_depth < 1 or (base != 'weak' and opponent_depth != depth):
        raise ValueError('opponent_depth only applies to the weak base')
    hybrid_name = hybrid_name_for(base, selector)
    base_name = BASE_NAMES[base]
    if base == 'weak':
        hybrid_name = hybrid_name.replace('Weak', f'Weak{depth}')
        base_name = f'Weak{opponent_depth}'
    if base == 'weak':
        from weak_engine import candidates as weak_candidates
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.with_suffix('.json').exists():
        raise FileExistsError('Use a new output name to preserve previous evidence')
    payload = {'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'running', 'model': MODEL,
               'design': 'Two color-swapped games from the same configured opening. Both use Stockfish MultiPV=3, identical node budgets, Threads=1, Hash=16, cleared per turn. The selector (Jev or a seeded uniform random control) only picks among cp candidates within margin; no scores/ranks/base/PVs sent to Jev. Node limits may overshoot. Jev adds API time; not an equal-wall-time comparison. Shortlisting is engine assistance, not independent chess reasoning.',
               'selector': selector, 'base_engine': base,
               'config': {'engine': engine_path, 'nodes': nodes, 'margin_cp': margin, 'max_plies': max_plies,
                          'multipv': 3, 'threads': 1, 'hash_mb': 16, 'seed': seed, 'opening_uci': list(opening),
                          'selector': selector, 'base_engine': base},
               'engine_a': {'name': hybrid_name, 'nodes': nodes if base == 'stockfish' else None},
               'engine_b': {'name': base_name, 'nodes': nodes if base == 'stockfish' else None}, 'games': []}
    if base == 'weak':
        payload['design'] = ('Two color-swapped games from the same configured opening. Both sides use the same deterministic '
                             f'depth-{depth} material+PST engine (weak_engine.py); it leaves tactical mistakes a selector could avoid. '
                             'The selector (Jev or seeded uniform random) picks among the top-3 root moves within margin of the best, '
                             'in the weak engine\'s own units. No scores/ranks/base sent to Jev. Jev adds API time.')
        payload['config'].update({'engine': 'weak_engine.py', 'nodes': None, 'depth': depth, 'opponent_depth': opponent_depth,
                                  'multipv': 3, 'margin_units': margin})
        if opponent_depth != depth:
            payload['design'] += f' Asymmetric: hybrid side searches depth {depth}, plain opponent depth {opponent_depth}.'
    pgns = []
    started = time.perf_counter()
    try:
        with ExitStack() as stack:
            client = stack.enter_context(TypeSafeClient(timeout=20)) if selector == 'jev' else None
            engines = []
            if base == 'stockfish':
                engines = [stack.enter_context(chess.engine.SimpleEngine.popen_uci(engine_path)) for _ in range(2)]
                for engine in engines: engine.configure({'Threads': 1, 'Hash': 16})
                payload['engine_id'] = engines[0].id
            for number in (1, 2):
                hybrid_color = chess.WHITE if number == 1 else chess.BLACK
                board = chess.Board()
                for uci in opening:
                    board.push_uci(uci)
                row = {'game': number, 'white': hybrid_name if hybrid_color else base_name,
                       'black': base_name if hybrid_color else hybrid_name,
                       'initial_fen': board.fen(), 'opening_uci': list(opening),
                       'result': '*', 'termination': 'in_progress', 'moves': [], 'plies': 0, 'final_fen': board.fen()}
                payload['games'].append(row)
                pgn = chess.pgn.Game()
                pgn.setup(board)
                pgn.headers.update({'Event': f'{hybrid_name} paired match', 'White': row['white'],
                                    'Black': row['black'], 'Round': str(number)})
                node = pgn
                for ply in range(1, max_plies + 1):
                    if board.is_game_over(claim_draw=True): break
                    hybrid = board.turn == hybrid_color
                    if base == 'stockfish':
                        ranked, telemetry = collect_candidates(engines[0 if hybrid else 1], board, nodes)
                    else:
                        started_move = time.perf_counter()
                        ranked, telemetry = weak_candidates(board, depth=depth if hybrid else opponent_depth)
                        telemetry['elapsed_ms'] = round((time.perf_counter() - started_move) * 1000, 2)
                    base = ranked[0]['move']
                    options = shortlist(ranked, margin)
                    choice = base
                    decision = None
                    control = None
                    if hybrid and len(options) >= 2 and selector != 'none':
                        if selector == 'jev':
                            req = make_request(board, options, seed + number * 1000 + ply)
                            decision = ask_jev(client, req, base)
                            choice = decision['selected_move']
                        else:
                            control = random_pick(options, base, seed, number, ply)
                            choice = control['selected_move']
                    if choice not in options: raise ValueError('Chosen move outside shortlist')
                    move = chess.Move.from_uci(choice)
                    if move not in board.legal_moves: raise ValueError('Invalid chosen move')
                    record = {'ply': ply, 'side': 'white' if board.turn else 'black',
                              'engine': row['white'] if board.turn else row['black'],
                              'uci': choice, 'san': board.san(move), 'fen_before': board.fen(),
                              'base_move': base, 'engine_candidates': ranked, 'shortlist': options,
                              'jev': decision, 'random_control': control,
                              'jev_skip': None if decision else 'control' if not hybrid else 'random_control' if control else 'plain' if selector == 'none' else 'no_close_alternative',
                              **telemetry}
                    row['moves'].append(record)
                    board.push(move)
                    node = node.add_variation(move)
                    row.update(plies=ply, final_fen=board.fen())
                    payload['summary'] = summarize(payload)
                    checkpoint(output.with_suffix('.json'), payload)
                    active = decision or control
                    if active or ply % 20 == 0:
                        print(f'game {number} ply {ply}: {record["san"]} {selector}={bool(active)} changed={bool(active and active["intervention"])}', flush=True)
                outcome = board.outcome(claim_draw=True)
                row['result'] = outcome.result() if outcome else '*'
                row['termination'] = outcome.termination.name.lower() if outcome else 'max_plies_unfinished'
                pgn.headers['Result'] = row['result']
                pgn.headers['Termination'] = row['termination']
                pgns.append(str(pgn))
                output.with_suffix('.pgn').write_text('\n\n'.join(pgns) + '\n')
                print(f'GAME {number}: {row["result"]} {row["termination"]} {row["plies"]} plies', flush=True)
        payload['status'] = 'complete'
    except Exception as exc:
        payload['status'] = 'failed'
        payload['error_type'] = type(exc).__name__
        raise
    finally:
        payload['summary'] = summarize(payload)
        payload['points'] = payload['summary']['points']
        payload['elapsed_seconds'] = round(time.perf_counter() - started, 2)
        checkpoint(output.with_suffix('.json'), payload)
    print(json.dumps(payload['summary']), flush=True)
    return payload


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, default=HERE / 'matches' / 'jev-smoke')
    p.add_argument('--engine', default='/opt/homebrew/bin/stockfish')
    p.add_argument('--nodes', type=int, default=5000)
    p.add_argument('--margin', type=int, default=35)
    p.add_argument('--max-plies', type=int, default=400)
    p.add_argument('--opening', nargs='*', default=[])
    p.add_argument('--seed', type=int, default=73419)
    p.add_argument('--selector', choices=sorted(HYBRID_NAMES), default='jev')
    p.add_argument('--base', choices=sorted(BASE_NAMES), default='stockfish')
    p.add_argument('--depth', type=int, default=2, help='weak engine search depth (hybrid side)')
    p.add_argument('--opponent-depth', type=int, default=None, help='weak engine depth for the plain opponent')
    args = p.parse_args()
    run(args.output, args.engine, args.nodes, args.margin, args.max_plies, args.opening, args.seed, args.selector, args.base, args.depth, args.opponent_depth)
