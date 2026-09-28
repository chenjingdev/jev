"""A frozen offline test of Jev choosing a Go objective, with engine execution.

Inputs: prospective plain-engine positions. Jev chooses defense/attack/connection/
territory or abstains; code selects the engine's first candidate with that purpose.
Comparison: engine, a fixed priority rule with the SAME facts/execution, and uniform
candidate selection. Every move is evaluated by the same GNU Go L1 continuation.
This is policy-specific offline value, not a full-match win rate or optimal Go truth.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import random
import re

import numpy as np

from counterfactual_replay import branch
from gnugo import GnuGo, shortlist
from understanding_probe import MODEL, PURPOSES, ask, purpose, save

OBJECTIVES = {
    'defense': 'Protect our groups: an explicitly listed defense purpose.',
    'attack': 'Attack enemy groups: an explicitly listed attack purpose.',
    'connection': 'Connect our groups.',
    'territory': 'Expand territory or moyo.',
    'undecided': 'The report gives no clear reason to prioritize one available objective.',
}
INSTRUCTIONS = (
    'Choose the single Go objective that most deserves attention NOW for `side_to_move`, '
    'using only `groups` and `candidate_reports`. Consider vulnerable friendly groups, '
    'vulnerable enemies, group sizes, connections and territorial opportunities. '
    'You are choosing an objective, not a coordinate. Code will execute an engine-ranked '
    'candidate with that explicit purpose. Candidate order is alphabetical and is not a ranking. '
    'alive means the engine reports the group alive, critical means unsettled life/death, '
    'dead means the engine reports it dead. These are engine reports, not guaranteed truth. '
    '`targets` links the original note to canonical group IDs in `groups`. '
    'No move scores or engine preference are supplied. Several objectives can describe one move. '
    'Do not invent future moves. Choose undecided if the report does not justify a priority.'
)


def life_status(reply):
    # Critical replies append suggested attack/defense coordinates. Those must
    # neither corrupt the rule's status comparison nor leak into model state.
    status = reply.split()[0]
    if status not in ('alive', 'critical', 'dead', 'unknown'):
        raise ValueError('Unexpected GNU Go life status')
    return status


def enrich(position):
    p = json.loads(json.dumps(position))
    f = p['features']
    mentioned = set(f['group_status'])
    for notes in f['candidate_notes'].values():
        mentioned.update(re.findall(r'\b[A-HJ][1-9]\b', ' '.join(notes)))
    group_map, aliases = {}, {}
    with GnuGo(level=p['level'], seed=p['seed']) as e:
        for colour, move, queried in p['prefix']:
            if queried:
                e.ranked_moves(colour)
                if move != 'PASS':
                    e.is_legal(colour, move)
            e.play(colour, move)
        base, ranked = e.ranked_moves(p['color'])
        assert base == p['engine_move']
        ranked_options = shortlist(ranked, 2.0)
        assert set(ranked_options) == set(p['moves'])
        for g in sorted(mentioned):
            if g not in f['state']['stones']:
                continue
            stones = sorted(e.cmd(f'dragon_stones {g}').split())
            anchor = stones[0]
            aliases[g] = anchor
            group_map[anchor] = {'colour': f['state']['stones'][g],
                                 'status': life_status(e.cmd(f'dragon_status {g}')),
                                 'stone_count': len(stones)}
    reports = {}
    for move in sorted(p['moves']):
        notes = f['candidate_notes'][move]
        targets = {}
        for category in PURPOSES:
            related = [line for line in notes if re.search(PURPOSES[category][1], line)]
            targets[category] = sorted({aliases[g] for line in related
                                       for g in re.findall(r'\b[A-HJ][1-9]\b', line) if g in aliases})
        reports[move] = {'notes': notes, 'purposes': [c for c in PURPOSES if purpose(notes, c)], 'targets': targets}
    p['priority_state'] = {'side_to_move': p['color'], 'groups': group_map, 'candidate_reports': reports}
    p['ranked_options'] = ranked_options  # internal only; never sent to Jev
    return p


def route(position, objective):
    for move in position['ranked_options']:
        if objective in position['priority_state']['candidate_reports'][move]['purposes']:
            return move
    return position['engine_move']


def fixed_rule(position):
    s = position['priority_state']
    for category, friendly in [('defense', True), ('attack', False)]:
        for report in s['candidate_reports'].values():
            for g in report['targets'][category]:
                group = s['groups'][g]
                if (group['colour'] == s['side_to_move']) == friendly and group['status'] == 'critical':
                    return category
    for category in ('connection', 'territory'):
        if any(category in r['purposes'] for r in s['candidate_reports'].values()):
            return category
    return 'undecided'


def jobs_for(positions, seed):
    jobs = []
    for p in positions:
        categories = [c for c in PURPOSES if any(c in r['purposes'] for r in p['priority_state']['candidate_reports'].values())]
        choices = categories + ['undecided']
        # If every possible objective executes the same move, no API call is needed.
        if len({route(p, c) for c in choices}) == 1:
            continue
        random.Random(f'{seed}-{p["id"]}').shuffle(choices)
        for order, ordered in [('forward', choices), ('reverse', list(reversed(choices)))]:
            jobs.append({'id': f'{p["id"]}/{order}', 'position_id': p['id'], 'order': order,
                         'request': {'model': MODEL, 'state': p['priority_state'],
                                     'questions': {'priority': {'instructions': INSTRUCTIONS,
                                                               'criteria': {c: OBJECTIVES[c] for c in ordered}}}}})
    return jobs


def rollout(job):
    p, move = job
    value = branch(p['level'], p['seed'], p['prefix'], p['color'], move, p['color'])
    if value is None:
        raise ValueError('Unfinished continuation; cannot score as a loss')
    return p['id'], move, value


def cluster_ci(values, keys, seed):
    grouped = {}
    for v, key in zip(values, keys):
        grouped.setdefault(tuple(key), []).append(v)
    totals = np.array([[sum(v), len(v)] for v in grouped.values()])
    indices = np.random.default_rng(seed).integers(0, len(totals), (50000, len(totals)))
    sampled = totals[indices].sum(axis=1)
    return {'mean': float(np.mean(values)), 'ci95': np.quantile(sampled[:, 0] / sampled[:, 1], [.025, .975]).tolist(),
            'positions': len(values), 'opening_families': len(grouped)}


def summarize(payload):
    answers = {}
    for job in payload['jobs']:
        answers.setdefault(job['position_id'], {})[job['order']] = job['response']['answers']['priority']['choice']
    scores = {k: [] for k in ['jev', 'engine', 'rule', 'random']}
    interventions = objective_agreement = routed_agreement = 0
    details = []
    for p in payload['positions']:
        outcomes = p['rollouts']
        choices = answers.get(p['id'], {'forward': 'undecided', 'reverse': 'undecided'})
        moves = [route(p, choices[o]) for o in ('forward', 'reverse')]
        rule_goal = fixed_rule(p)
        scores['jev'].append(sum(outcomes[m] for m in moves) / 2)
        scores['engine'].append(outcomes[p['engine_move']])
        scores['rule'].append(outcomes[route(p, rule_goal)])
        scores['random'].append(sum(outcomes.values()) / len(outcomes))
        interventions += sum(m != p['engine_move'] for m in moves)
        if p['id'] in answers:
            objective_agreement += choices['forward'] == choices['reverse']
            routed_agreement += moves[0] == moves[1]
        details.append({'id': p['id'], 'objectives': choices, 'moves': moves, 'rule_objective': rule_goal,
                        'rule_move': route(p, rule_goal), 'engine_move': p['engine_move'], 'outcomes': outcomes})
    keys = [p['opening_canonical'] for p in payload['positions']]
    diffs = {name: cluster_ci(np.array(scores['jev']) - np.array(scores[name]), keys, payload['seed'])
             for name in ['engine', 'rule', 'random']}
    return {'continuation_value': {k: float(np.mean(v)) for k, v in scores.items()},
            'jev_minus_baseline': diffs, 'api_positions': len(answers),
            'objective_agreement_count': objective_agreement, 'routed_move_agreement_count': routed_agreement,
            'interventions_out_of_two_orders': interventions,
            'advance_to_matches': all(diffs[k]['ci95'][0] > 0 for k in ['engine', 'rule']),
            'usage': {k: sum(j['response']['usage'][k] for j in payload['jobs']) for k in ['input_tokens', 'output_tokens']},
            'details': details}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--seed', type=int, default=662309)
    ap.add_argument('--workers', type=int, default=8)
    args = ap.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x'):
        pass
    raw = args.source.read_bytes()
    source = json.loads(raw)
    assert source['status'] == 'complete'
    with ProcessPoolExecutor(args.workers) as pool:
        positions = list(pool.map(enrich, source['positions']))
    payload = {'status': 'prepared', 'seed': args.seed, 'source_sha256': hashlib.sha256(raw).hexdigest(),
               'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'gate_before_evaluation': 'Advance to full matches only if paired opening-cluster 95% lower bounds vs both engine and fixed rule are positive.',
               'estimand': 'Mean one-step intervention outcome under deterministic GNU Go L1 continuation, not a match win rate.',
               'positions': positions, 'jobs': jobs_for(positions, args.seed)}
    save(args.output, payload)
    print(f'{len(positions)} positions, {len(payload["jobs"])} API requests', flush=True)
    with ThreadPoolExecutor(6) as api_pool, ProcessPoolExecutor(args.workers) as engine_pool:
        api_pending = {api_pool.submit(ask, j): j for j in payload['jobs']}
        engine_jobs = [(p, move) for p in positions for move in p['moves']]
        engine_pending = [engine_pool.submit(rollout, job) for job in engine_jobs]
        by_id = {p['id']: p for p in positions}
        for i, future in enumerate(as_completed(engine_pending), 1):
            pid, move, result = future.result()
            by_id[pid].setdefault('rollouts', {})[move] = result
            if i % 50 == 0:
                save(args.output, payload)
                print(f'{i}/{len(engine_pending)} continuations', flush=True)
        for future in as_completed(api_pending):
            api_pending[future]['response'] = future.result()
    payload['summary'] = summarize(payload)
    payload['status'] = 'complete'
    save(args.output, payload)
    print(json.dumps({k: v for k, v in payload['summary'].items() if k != 'details'}, indent=1))


if __name__ == '__main__':
    main()
