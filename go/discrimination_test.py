"""Can Jev tell a winning move from a losing one when GNU Go's analysis is spelled out?

Offline test, no new games. The problem set is every decision in the v2 counterfactual files
where the two candidate moves led to different results (one wins, one loses under plain
GNU Go L1 continuation). Each position is shown to Jev in several representations:

  bare     - exactly the match representation (stones dict + two coordinates)
  reasons  - bare + what each candidate move does, from GNU Go `move_reasons`
             (defends / attacks / connects / cuts / expands territory), judgement words removed
  status   - reasons + life status of every group (`dragon_status`) + reading results
             (`attack` / `defend`) for the groups the reasons mention

No values, ranks, scores or the engine's own choice are sent in any condition. Whether the
labelled conditions are still inside the first principle is the user's call; this test is
the evidence for making it.

Baselines computed without any API call: engine preference (the move `reg_genmove` chose),
label count (the candidate with more move_reasons lines), and chance (50%).
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import re
import statistics
from gnugo import GnuGo

HERE = Path(__file__).resolve().parent
MATCHES = HERE / 'matches'
RUNS = ['l1rand-100', 'l1jev-100', 'l1jev-100b']
CONDITIONS = ['bare', 'reasons', 'status']

INSTRUCTIONS = (
    'You are playing Go on a 9x9 board as `side_to_move`, Chinese (area) scoring, komi 7.5 for white. '
    'Choose the move that gives your side the best practical position: secure territory, keep your '
    'groups connected and alive, and punish weak enemy stones. `stones` lists every occupied point with '
    'its colour. Points are named column letter then row number; columns run A B C D E F G H J from '
    'left to right (there is no column I), rows 1 to 9 from bottom to top. Choose one option.'
)
NOTES_HELP = (
    ' `candidate_notes` describes, for each option, what the move does on the board (which groups it '
    'defends, attacks, connects or cuts, whether it expands territory). Groups are named by one of their stones.'
)
STATUS_HELP = (
    ' `group_status` gives the current life status of every group (alive, dead, critical, unknown). '
    '`reading` states, for groups mentioned in the notes, whether they can currently be captured or saved.'
)

JUDGEMENT = re.compile(r'\s*\((defenseless|with good ko|with bad ko)\)|strategically or tactically unsafe')


# ---------------------------------------------------------------- problem set

def collect_positions(runs=RUNS):
    """Decisive counterfactual rows -> positions, deduplicated by move sequence + candidates."""
    seen = {}
    for run in runs:
        cf = json.loads((MATCHES / f'{run}.counterfactual-v2.json').read_text())
        pairs = {}
        for row in cf['rows']:
            if row['delta'] == 0:
                continue
            pair = pairs.setdefault(row['file'], json.loads((MATCHES / run / row['file']).read_text()))
            game = next(g for g in pair['games'] if g['game'] == row['game'])
            hybrid = pair['engine_a']['name']
            hybrid_color = 'black' if game['black'] == hybrid else 'white'
            prefix = [(m['side'], m['move'], not m.get('opening')) for m in game['moves'] if m['ply'] < row['ply']]
            target = next(m for m in game['moves'] if m['ply'] == row['ply'])
            winner = row['selector_move'] if row['delta'] > 0 else row['engine_move']
            moves = sorted([row['selector_move'], row['engine_move']])
            key = (tuple(v for _, v, _ in prefix), target['side'], tuple(moves))
            if key in seen:
                seen[key]['sources'].append(run)
                continue
            seen[key] = {
                'id': f"{run}/{row['file'].removesuffix('.json')}/g{row['game']}/p{row['ply']}",
                'run': run, 'sources': [run], 'file': row['file'], 'game': row['game'], 'ply': row['ply'],
                'level': pair['config']['level'], 'seed': pair['config']['seed'],
                'color': target['side'], 'hybrid_color': hybrid_color,
                'prefix': prefix, 'moves': moves, 'winning_move': winner,
                'engine_move': row['engine_move'],
                'historical_pick': row['selector_move'] if 'jev' in run else None,
                'shortlist': target.get('shortlist'),
            }
    return list(seen.values())


# ---------------------------------------------------------------- engine facts

def split_reasons(text, move):
    """GTP reply 'Move reasons:\nMove at E5 defends D8\nMove at E5 ...' -> ['defends D8', ...].
    GnuGo.cmd joins reply lines with spaces, so split on the 'Move at <move>' marker."""
    parts = re.split(rf'Move at {move}\s+', text)
    out = []
    for part in parts:
        part = JUDGEMENT.sub('', part.replace('Move reasons:', '')).strip()
        if part and part not in out:
            out.append(part)
    return out


def status_map(text):
    out = {}
    for stone, status in re.findall(r'([A-J]\d+):\s*(\w+)', text):
        out[stone] = status
    return out


def features(position):
    """Replay the game with the match's query sequence, then ask GNU Go about the two moves."""
    color, moves = position['color'], position['moves']
    with GnuGo(level=position['level'], seed=position['seed']) as e:
        for c, v, queried in position['prefix']:
            if queried:
                e.ranked_moves(c)
                if v != 'PASS':
                    e.is_legal(c, v)
            e.play(c, v)
        base, _rows = e.ranked_moves(color)
        stones = {v: 'black' for v in e.stones('black')}
        stones.update({v: 'white' for v in e.stones('white')})
        notes = {}
        for m in moves:
            notes[m] = split_reasons(e.cmd(f'move_reasons {m}'), m)
        groups = status_map(e.cmd('dragon_status'))
        mentioned = sorted({g for lines in notes.values() for l in lines for g in re.findall(r'\b[A-J]\d\b', l)})
        reading = {}
        for g in mentioned:
            if g not in stones:
                continue
            can_attack = e.cmd(f'attack {g}').split()[0] != '0'
            can_defend = e.cmd(f'defend {g}').split()[0] != '0'
            reading[g] = {'colour': stones[g],
                          'can_be_captured': can_attack,
                          'can_be_saved': can_defend if can_attack else None}
        last = position['prefix'][-1][1] if position['prefix'] else None
        return {
            'engine_move_now': base,
            'state': {
                'side_to_move': color, 'board_size': e.boardsize, 'komi': e.komi,
                'move_number': len(position['prefix']) + 1, 'last_move': last,
                'stones': dict(sorted(stones.items())),
                'captured_by_black': e.captures('black'), 'captured_by_white': e.captures('white'),
            },
            'candidate_notes': notes,
            'group_status': groups,
            'reading': reading,
        }


def build_request(position, feats, condition, seed):
    moves = list(position['moves'])
    random.Random(f'{seed}-{position["id"]}-{condition}').shuffle(moves)
    state = dict(feats['state'])
    instructions = INSTRUCTIONS
    if condition in ('reasons', 'status'):
        state['candidate_notes'] = {m: feats['candidate_notes'][m] or ['no specific purpose recorded'] for m in moves}
        instructions += NOTES_HELP
    if condition == 'status':
        state['group_status'] = feats['group_status']
        state['reading'] = feats['reading']
        instructions += STATUS_HELP
    return {'model': None, 'state': state,
            'questions': {'move': {'type': 'choice', 'instructions': instructions,
                                   'criteria': {m: None for m in moves}}}}


# ---------------------------------------------------------------- baselines & scoring

def label_count_pick(position, feats):
    counts = {m: len(feats['candidate_notes'][m]) for m in position['moves']}
    a, b = position['moves']
    if counts[a] == counts[b]:
        return None
    return max(counts, key=lambda m: counts[m])


def accuracy(rows, key):
    hits = [r[key] == r['winning_move'] for r in rows if r.get(key) is not None]
    return {'n': len(hits), 'correct': sum(hits), 'rate': round(sum(hits) / len(hits), 3) if hits else None}


def summarize(payload):
    rows = payload['positions']
    out = {'positions': len(rows), 'baselines': {}, 'conditions': {}}
    out['baselines']['engine_preference'] = accuracy(rows, 'engine_move')
    out['baselines']['label_count'] = accuracy(rows, 'label_count_pick')
    out['baselines']['historical_jev_pick'] = accuracy([r for r in rows if r.get('historical_pick')], 'historical_pick')
    for cond in payload['conditions']:
        done = [r for r in rows if r.get('answers', {}).get(cond)]
        picks = [{'winning_move': r['winning_move'], 'pick': r['answers'][cond]['choice'], 'run': r['run'],
                  'hist': r.get('historical_pick'), 'conf': r['answers'][cond]['confidence'],
                  'engine': r['engine_move']} for r in done]
        by_run = {run: accuracy([p for p in picks if p['run'] == run], 'pick') for run in RUNS}
        agree_hist = [p['pick'] == p['hist'] for p in picks if p['hist']]
        agree_engine = [p['pick'] == p['engine'] for p in picks]
        tokens = {'input': sum(r['answers'][cond]['usage']['input_tokens'] for r in done),
                  'output': sum(r['answers'][cond]['usage']['output_tokens'] for r in done)}
        out['conditions'][cond] = {
            'overall': accuracy(picks, 'pick'), 'by_run': by_run,
            'agrees_with_engine_move': round(sum(agree_engine) / len(agree_engine), 3) if agree_engine else None,
            'agrees_with_historical_pick': {'n': len(agree_hist),
                                            'rate': round(sum(agree_hist) / len(agree_hist), 3) if agree_hist else None},
            'mean_confidence': round(statistics.mean(p['conf'] for p in picks), 3) if picks else None,
            'tokens': tokens,
        }
    return out


# ---------------------------------------------------------------- run

def ask(client, model, request):
    from typesafe_sdk import Choice
    q = request['questions']['move']
    result = client.system_one(model=model, state=request['state'],
                              questions={'move': Choice(instructions=q['instructions'], criteria=q['criteria'])})
    answer = result.answers['move']
    if answer.choice not in q['criteria'] or set(answer.probabilities) != set(q['criteria']):
        raise ValueError('Jev response does not match candidates')
    return {'choice': answer.choice, 'confidence': answer.confidence,
            'probabilities': dict(answer.probabilities), 'order_shown': list(q['criteria']),
            'usage': {'input_tokens': result.usage.input_tokens, 'output_tokens': result.usage.output_tokens}}


def swap_control(source, output, api_workers):
    """Label-swap control: resend the `status` request for every position whose two candidates
    carry different notes, with the notes swapped between the moves (order shown unchanged).
    If Jev reads the notes, accuracy on these positions should fall below 50%."""
    from typesafe_sdk import TypeSafeClient
    src = json.loads((MATCHES / f'{source}.json').read_text())
    out_path = MATCHES / f'{output}.json'
    if out_path.exists():
        raise SystemExit(f'{out_path} exists; pick a new name')
    rows = []
    for p in src['positions']:
        a, b = p['moves']
        notes = p['features']['candidate_notes']
        if notes[a] == notes[b] or 'status' not in p['answers']:
            continue
        order = p['answers']['status']['order_shown']
        state = dict(p['features']['state'])
        state['candidate_notes'] = {m: (notes[b if m == a else a] or ['no specific purpose recorded']) for m in order}
        state['group_status'] = p['features']['group_status']
        state['reading'] = p['features']['reading']
        req = {'state': state, 'questions': {'move': {'instructions': INSTRUCTIONS + NOTES_HELP + STATUS_HELP,
                                                       'criteria': {m: None for m in order}}}}
        rows.append({'id': p['id'], 'moves': p['moves'], 'winning_move': p['winning_move'], 'engine_move': p['engine_move'],
                     'status_choice': p['answers']['status']['choice'], 'swapped_notes': state['candidate_notes'], 'request': req})
    client = TypeSafeClient(timeout=30)
    with ThreadPoolExecutor(api_workers) as pool:
        for row, ans in zip(rows, pool.map(lambda r: ask(client, src['model'], r['request']), rows)):
            row['answer'] = ans
            del row['request']
    correct = sum(r['answer']['choice'] == r['winning_move'] for r in rows)
    followed_label = sum(r['answer']['choice'] != r['status_choice'] for r in rows)
    summary = {'n': len(rows), 'correct': correct, 'rate': round(correct / len(rows), 3),
               'status_correct_same_positions': sum(r['status_choice'] == r['winning_move'] for r in rows),
               'pick_changed_vs_status': followed_label,
               'tokens': {'input': sum(r['answer']['usage']['input_tokens'] for r in rows),
                          'output': sum(r['answer']['usage']['output_tokens'] for r in rows)}}
    out_path.write_text(json.dumps({'created_at': datetime.now(timezone.utc).isoformat(), 'source': source,
                                    'model': src['model'], 'rows': rows, 'summary': summary}, ensure_ascii=False, indent=1))
    print(json.dumps(summary, indent=1))


def reorder_control(source, output, conditions, api_workers):
    """Order control: resend every request of an existing run with the two options in reverse
    order, everything else identical. Averaging with the original run cancels first-option bias."""
    from typesafe_sdk import TypeSafeClient
    src = json.loads((MATCHES / f'{source}.json').read_text())
    out_path = MATCHES / f'{output}.json'
    if out_path.exists():
        raise SystemExit(f'{out_path} exists; pick a new name')
    jobs = []
    for p in src['positions']:
        for cond in conditions:
            order = list(reversed(p['answers'][cond]['order_shown']))
            req = build_request(p, p['features'], cond, 0)
            for key in ('candidate_notes',):
                if key in req['state']:
                    req['state'][key] = {m: req['state'][key][m] for m in order}
            req['questions']['move']['criteria'] = {m: None for m in order}
            jobs.append((p, cond, req))
    client = TypeSafeClient(timeout=30)
    with ThreadPoolExecutor(api_workers) as pool:
        answers = list(pool.map(lambda j: ask(client, src['model'], j[2]), jobs))
    for (p, cond, _req), ans in zip(jobs, answers):
        p.setdefault('reversed_answers', {})[cond] = ans
    rows = []
    for p in src['positions']:
        rows.append({k: p[k] for k in ('id', 'run', 'sources', 'moves', 'winning_move', 'engine_move', 'ply')}
                    | {'answers': p['answers'], 'reversed_answers': p['reversed_answers'],
                       'notes_identical': p['features']['candidate_notes'][p['moves'][0]] == p['features']['candidate_notes'][p['moves'][1]]})
    summary = {}
    for cond in conditions:
        orig = sum(r['answers'][cond]['choice'] == r['winning_move'] for r in rows)
        rev = sum(r['reversed_answers'][cond]['choice'] == r['winning_move'] for r in rows)
        same_pick = sum(r['answers'][cond]['choice'] == r['reversed_answers'][cond]['choice'] for r in rows)
        summary[cond] = {'n': len(rows), 'original_correct': orig, 'reversed_correct': rev,
                         'order_balanced_rate': round((orig + rev) / (2 * len(rows)), 3),
                         'same_pick_both_orders': same_pick,
                         'tokens': {'input': sum(r['reversed_answers'][cond]['usage']['input_tokens'] for r in rows),
                                    'output': sum(r['reversed_answers'][cond]['usage']['output_tokens'] for r in rows)}}
    out_path.write_text(json.dumps({'created_at': datetime.now(timezone.utc).isoformat(), 'source': source,
                                    'model': src['model'], 'conditions': conditions, 'rows': rows, 'summary': summary},
                                   ensure_ascii=False, indent=1))
    print(json.dumps(summary, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reorder-from', default=None, help='order control on an existing run (name under go/matches/)')
    ap.add_argument('--output', required=True, help='name under go/matches/, e.g. discrim-pilot')
    ap.add_argument('--swap-from', default=None, help='label-swap control on an existing run (name under go/matches/)')
    ap.add_argument('--limit', type=int, default=None, help='first N positions (pilot)')
    ap.add_argument('--conditions', nargs='+', default=CONDITIONS, choices=CONDITIONS)
    ap.add_argument('--seed', type=int, default=20260922)
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--api-workers', type=int, default=6)
    ap.add_argument('--no-api', action='store_true', help='features and baselines only')
    args = ap.parse_args()
    if args.swap_from:
        return swap_control(args.swap_from, args.output, args.api_workers)
    if args.reorder_from:
        return reorder_control(args.reorder_from, args.output, args.conditions, args.api_workers)

    out_path = MATCHES / f'{args.output}.json'
    if out_path.exists():
        raise SystemExit(f'{out_path} exists; pick a new name')

    positions = collect_positions()
    positions.sort(key=lambda p: (RUNS.index(p['run']), p['file'], p['game'], p['ply']))
    if args.limit:
        rng = random.Random(args.seed)
        positions = rng.sample(positions, args.limit)
    print(f'{len(positions)} positions', flush=True)

    with ProcessPoolExecutor(args.workers) as pool:
        feats = list(pool.map(features, positions))
    for p, f in zip(positions, feats):
        p['features'] = f
        p['label_count_pick'] = label_count_pick(p, f)
        p['engine_move_now_matches'] = f['engine_move_now'] == p['engine_move']
        p['answers'] = {}
    mismatch = sum(not p['engine_move_now_matches'] for p in positions)
    print(f'replay check: engine move reproduced in {len(positions) - mismatch}/{len(positions)}', flush=True)

    payload = {'created_at': datetime.now(timezone.utc).isoformat(), 'model': None,
               'conditions': args.conditions, 'seed': args.seed, 'positions': positions}

    if not args.no_api:
        from typesafe_sdk import TypeSafeClient
        from jev_go_match import MODEL
        payload['model'] = MODEL
        client = TypeSafeClient(timeout=30)
        jobs = [(p, cond) for p in positions for cond in args.conditions]

        def work(job):
            p, cond = job
            req = build_request(p, p['features'], cond, args.seed)
            ans = ask(client, MODEL, req)
            ans['request_state_keys'] = sorted(req['state'])
            return p['id'], cond, ans, req

        with ThreadPoolExecutor(args.api_workers) as pool:
            for i, (pid, cond, ans, req) in enumerate(pool.map(work, jobs), 1):
                p = next(p for p in positions if p['id'] == pid)
                p['answers'][cond] = ans
                p.setdefault('requests', {})[cond] = req['state'] if cond == 'status' else None
                if i % 25 == 0:
                    print(f'{i}/{len(jobs)}', flush=True)
    payload['summary'] = summarize(payload)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(json.dumps(payload['summary'], ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
