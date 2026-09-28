"""9x9 Go: GNU Go picks candidate moves, a selector (Jev, seeded random, or none) picks one.

Mirror of chess/jev_engine_match.py. One color-swapped pair per run. Komi 7.5 under
Chinese rules, so no game can end in a draw. Both sides are the same deterministic GNU Go
level; the hybrid side lets the selector choose among the engine's top moves within a value
margin. Jev receives only the position (stone lists), never engine values, ranks or the
engine's own choice (first principle).
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import time
from typesafe_sdk import Choice, TypeSafeClient
from gnugo import GnuGo, shortlist

HERE = Path(__file__).resolve().parent
MODEL = 'jev-1.13.0'
INSTRUCTIONS = (
    'You are playing Go on a 9x9 board as `side_to_move`, Chinese (area) scoring, komi 7.5 for white. '
    'Choose the move that gives your side the best practical position: secure territory, keep your '
    'groups connected and alive, and punish weak enemy stones. `stones` lists every occupied point with '
    'its colour. Points are named column letter then row number; columns run A B C D E F G H J from '
    'left to right (there is no column I), rows 1 to 9 from bottom to top. Choose one option.'
)


def make_request(engine, color, candidates, seed, move_number, last_move):
    moves = sorted(candidates)
    if len(moves) < 2 or len(set(moves)) != len(moves):
        raise ValueError('Need at least two distinct candidates')
    random.Random(seed).shuffle(moves)
    stones = {v: 'black' for v in engine.stones('black')}
    stones.update({v: 'white' for v in engine.stones('white')})
    return {
        'model': MODEL,
        'state': {
            'side_to_move': color,
            'board_size': engine.boardsize,
            'komi': engine.komi,
            'move_number': move_number,
            'last_move': last_move,
            'stones': dict(sorted(stones.items())),
            'captured_by_black': engine.captures('black'),
            'captured_by_white': engine.captures('white'),
        },
        'questions': {'move': {'type': 'choice', 'instructions': INSTRUCTIONS,
                               'criteria': {m: None for m in moves}}},
    }


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


def random_pick(options, base, seed, number, ply):
    choice = random.Random(f'pick-{seed}-{number}-{ply}').choice(sorted(options))
    return {'base_move': base, 'selected_move': choice, 'intervention': choice != base,
            'options': sorted(options), 'selector': 'random'}


def hybrid_name_for(level, selector, min_confidence=None):
    if selector == 'none':
        return f'GnuGo L{level} (plain)'
    if selector == 'jev' and min_confidence:
        return f'GnuGo L{level} + Jev(conf>={min_confidence:g})'
    return f"GnuGo L{level} + {'Jev' if selector == 'jev' else 'Random'}"


def checkpoint(path, payload):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    tmp.replace(path)


def result_for(score):
    """GTP final_score like 'W+7.5' -> ('white', 7.5)."""
    if score in ('0', ''):
        raise ValueError('Draw is impossible with komi 7.5; scoring failed')
    winner = {'B': 'black', 'W': 'white'}[score[0]]
    return winner, float(score[2:])


def summarize(payload):
    hybrid = payload['engine_a']['name']
    opponent = payload['engine_b']['name']
    points = {hybrid: 0.0, opponent: 0.0}
    wins = losses = unfinished = 0
    decisions = interventions = gated = jev_disagreed = 0
    tokens = {'input': 0, 'output': 0}
    latencies = []
    for g in payload['games']:
        if g['winner'] is None:
            unfinished += 1
        else:
            hybrid_won = g[g['winner']] == hybrid
            points[hybrid if hybrid_won else opponent] += 1
            wins += hybrid_won
            losses += not hybrid_won
        for m in g['moves']:
            d = m.get('jev')
            if d:
                decisions += 1
                interventions += d['intervention']
                gated += bool(d.get('gated'))
                jev_disagreed += d.get('jev_move', d['selected_move']) != d['base_move']
                tokens['input'] += d['response']['usage']['input_tokens']
                tokens['output'] += d['response']['usage']['output_tokens']
                latencies.append(d['latency_ms'])
            elif m.get('random_control'):
                decisions += 1
                interventions += m['random_control']['intervention']
    return {'points': points, 'hybrid_wins': wins, 'hybrid_losses': losses, 'unfinished': unfinished,
            'decisions': decisions, 'interventions': interventions, 'gated': gated, 'jev_disagreed': jev_disagreed,
            'tokens': tokens, 'jev_mean_ms': round(sum(latencies) / len(latencies), 1) if latencies else None}


def sgf(game, komi, size=9):
    def vertex(v):
        if v == 'PASS':
            return ''
        col = 'ABCDEFGHJKLMNOPQRST'.index(v[0])
        row = size - int(v[1:])
        return 'abcdefghijklmnopqrs'[col] + 'abcdefghijklmnopqrs'[row]
    moves = ''.join(f";{'B' if m['side'] == 'black' else 'W'}[{vertex(m['move'])}]" for m in game['moves'])
    result = f"{game['score']}" if game['winner'] else '?'
    return (f"(;GM[1]FF[4]SZ[{size}]KM[{komi}]RU[Chinese]PB[{game['black']}]PW[{game['white']}]"
            f"RE[{result}]{moves})")


def run(output, level=1, margin=2.0, max_plies=200, seed=73419, selector='jev', min_confidence=None, opening=()):
    if selector not in ('jev', 'random', 'none') or level < 1 or margin < 0 or max_plies < 1:
        raise ValueError('Invalid match configuration')
    if min_confidence is not None and not (0 < min_confidence <= 1 and selector == 'jev'):
        raise ValueError('min_confidence must be in (0, 1] and requires selector=jev')
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.with_suffix('.json').exists():
        raise FileExistsError('Use a new output name to preserve previous evidence')
    komi = 7.5
    hybrid_name = hybrid_name_for(level, selector, min_confidence)
    base_name = f'GnuGo L{level}'
    payload = {'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'running', 'model': MODEL,
               'design': (f'Two colour-swapped 9x9 games, Chinese rules, komi {komi} (no draws possible). Both sides are GNU Go 3.8 '
                          f'level {level} started with the pair seed, so the engine is a deterministic function of (position, seed). '
                          'The hybrid side lets the selector (Jev, or seeded uniform random) pick among the engine\'s move '
                          'and its top alternatives within a value margin, at most three options. No values, ranks or '
                          'engine choice are sent to Jev. Two consecutive passes end the game; final_score decides.'),
               'selector': selector, 'min_confidence': min_confidence,
               'config': {'engine': 'gnugo 3.8', 'level': level, 'boardsize': 9, 'komi': komi, 'margin_points': margin,
                          'max_options': 3, 'max_plies': max_plies, 'seed': seed, 'opening': list(opening), 'selector': selector},
               'engine_a': {'name': hybrid_name}, 'engine_b': {'name': base_name}, 'games': []}
    sgfs = []
    started = time.perf_counter()
    client = TypeSafeClient(timeout=20) if selector == 'jev' else None
    try:
        for number in (1, 2):
            hybrid_color = 'black' if number == 1 else 'white'
            with GnuGo(level=level, komi=komi, seed=seed) as engine:
                row = {'game': number, 'black': hybrid_name if hybrid_color == 'black' else base_name,
                       'white': base_name if hybrid_color == 'black' else hybrid_name,
                       'opening': list(opening), 'winner': None, 'margin': None, 'score': None,
                       'termination': 'in_progress', 'moves': [], 'plies': 0}
                payload['games'].append(row)
                color = 'black'
                ply = 0
                last_move = None
                for v in opening:
                    ply += 1
                    engine.play(color, v)
                    row['moves'].append({'ply': ply, 'side': color, 'move': v.upper(), 'opening': True})
                    last_move = v.upper()
                    color = 'white' if color == 'black' else 'black'
                passes = 0
                while ply < max_plies:
                    ply += 1
                    hybrid = color == hybrid_color
                    t0 = time.perf_counter()
                    base, ranked = engine.ranked_moves(color)
                    engine_ms = round((time.perf_counter() - t0) * 1000, 1)
                    options = shortlist(ranked, margin)
                    choice = base
                    decision = control = None
                    if hybrid and len(options) >= 2 and selector != 'none':
                        if selector == 'jev':
                            req = make_request(engine, color, options, seed + number * 1000 + ply, ply, last_move)
                            decision = ask_jev(client, req, base)
                            choice = decision['selected_move']
                            if min_confidence is not None and decision['confidence'] < min_confidence:
                                decision.update(jev_move=decision['selected_move'], selected_move=base,
                                                intervention=False, gated=True)
                                choice = base
                            elif min_confidence is not None:
                                decision.update(jev_move=decision['selected_move'], gated=False)
                        else:
                            control = random_pick(options, base, seed, number, ply)
                            choice = control['selected_move']
                    if choice != 'PASS' and choice not in options:
                        raise ValueError('Chosen move outside shortlist')
                    if choice != 'PASS' and not engine.is_legal(color, choice):
                        raise ValueError(f'Illegal chosen move {choice}')
                    engine.play(color, choice)
                    row['moves'].append({'ply': ply, 'side': color, 'engine': row[color], 'move': choice,
                                         'base_move': base, 'engine_candidates': ranked, 'shortlist': options,
                                         'jev': decision, 'random_control': control,
                                         'jev_skip': None if decision else 'control' if not hybrid else 'random_control' if control
                                         else 'plain' if selector == 'none' else 'no_close_alternative',
                                         'engine_ms': engine_ms})
                    row['plies'] = ply
                    last_move = choice
                    passes = passes + 1 if choice == 'PASS' else 0
                    active = decision or control
                    if active or ply % 20 == 0:
                        print(f'game {number} ply {ply}: {color} {choice} {selector}={bool(active)} changed={bool(active and active["intervention"])}', flush=True)
                    color = 'white' if color == 'black' else 'black'
                    if passes >= 2:
                        break
                if passes >= 2:
                    score = engine.final_score()
                    winner, margin_pts = result_for(score)
                    row.update(winner=winner, margin=margin_pts, score=score, termination='two_passes')
                else:
                    row['termination'] = 'max_plies_unfinished'
                row['final_board'] = engine.showboard()
                row['captured_by_black'] = engine.captures('black')
                row['captured_by_white'] = engine.captures('white')
            sgfs.append(sgf(row, komi))
            output.with_suffix('.sgf').write_text('\n\n'.join(sgfs) + '\n')
            payload['summary'] = summarize(payload)
            checkpoint(output.with_suffix('.json'), payload)
            print(f'GAME {number}: {row["score"]} {row["termination"]} {row["plies"]} plies', flush=True)
        payload['status'] = 'complete'
    except Exception as exc:
        payload['status'] = 'failed'
        payload['error_type'] = type(exc).__name__
        payload['error'] = str(exc)[:500]
        raise
    finally:
        if client:
            client.close()
        payload['summary'] = summarize(payload)
        payload['points'] = payload['summary']['points']
        payload['elapsed_seconds'] = round(time.perf_counter() - started, 2)
        checkpoint(output.with_suffix('.json'), payload)
    print(json.dumps(payload['summary']), flush=True)
    return payload


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, default=HERE / 'matches' / 'go-smoke')
    p.add_argument('--level', type=int, default=1)
    p.add_argument('--margin', type=float, default=2.0)
    p.add_argument('--max-plies', type=int, default=200)
    p.add_argument('--seed', type=int, default=73419)
    p.add_argument('--selector', choices=['jev', 'random', 'none'], default='jev')
    p.add_argument('--min-confidence', type=float, default=None)
    p.add_argument('--opening', nargs='*', default=[])
    a = p.parse_args()
    run(a.output, level=a.level, margin=a.margin, max_plies=a.max_plies, seed=a.seed, selector=a.selector,
        min_confidence=a.min_confidence, opening=a.opening)
