"""Test reading GNU Go's supplied facts, separately from choosing a good move.

Gold answers are explicit input facts, NOT Go truth or rollout winners. Each case
is repeated across full/focused state and two criterion orders. Repeats never
increase the number of cases. No result/outcome fields are sent to Jev.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import time

HERE = Path(__file__).resolve().parent
MODEL = 'jev-1.13.0'
PURPOSES = {
    'defense': ('defending a group now', r'^(?:owl-|strategically )?defends\b'),
    'attack': ('attacking a group now', r'^(?:owl-|strategically )?attacks\b'),
    'connection': ('connecting groups', r'^connects\b'),
    'territory': ('expanding territory or moyo', r'^expands (?:territory|moyo)\b'),
}
GATE = {'minimum_balanced_accuracy_per_task': .90,
        'minimum_recall_per_observed_label': .80,
        'minimum_same_answer_both_orders_per_task': .90}


def purpose(notes, category):
    return any(re.search(PURPOSES[category][1], line) for line in notes)


def groups(features):
    stones = features['state']['stones']
    return {g: {'colour': stones[g], 'status': status}
            for g, status in features['group_status'].items() if g in stones}


def state_for(position, mode):
    f = position['features']
    if mode == 'full':
        return dict(f['state'], candidate_notes=f['candidate_notes'],
                    group_status=f['group_status'], reading=f['reading'])
    if mode == 'focused':
        return {'side_to_move': f['state']['side_to_move'],
                'groups': groups(f), 'candidate_notes': f['candidate_notes']}
    raise ValueError(mode)


def all_cases(positions):
    cases = []
    for p in positions:
        f = p['features']
        for g, info in groups(f).items():
            for task, answer in (
                ('group_status', info['status']),
                ('friendly_critical', 'yes' if info['colour'] == f['state']['side_to_move']
                 and info['status'] == 'critical' else 'no'),
            ):
                cases.append({'id': f'{p["id"]}/{task}/{g}', 'position_id': p['id'],
                              'task': task, 'target': g, 'expected': answer})
        for move, notes in f['candidate_notes'].items():
            for category in PURPOSES:
                cases.append({'id': f'{p["id"]}/{category}/{move}', 'position_id': p['id'],
                              'task': category, 'target': move,
                              'expected': 'yes' if purpose(notes, category) else 'no'})
    return cases


def sample_cases(positions, per_label, seed):
    # Remove identical visible questions from repeated board positions first.
    by_id = {p['id']: p for p in positions}
    buckets, seen = defaultdict(list), set()
    for c in all_cases(positions):
        key = json.dumps([state_for(by_id[c['position_id']], 'full'), c['task'], c['target']], sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        buckets[c['task'], c['expected']].append(c)
    selected = []
    for bucket, available in sorted(buckets.items()):
        rng = random.Random(f'{seed}-{bucket}')
        rng.shuffle(available)
        # Spread each label over positions before taking more from one position.
        available.sort(key=lambda c: sum(x['position_id'] == c['position_id'] for x in selected))
        selected.extend(available[:per_label])
    return sorted(selected, key=lambda c: c['id'])


def question(case, mode, order, seed):
    task, target = case['task'], case['target']
    preamble = 'Read only the supplied engine report. Do not calculate Go moves or infer unreported facts. '
    status_path = f'`group_status.{target}`' if mode == 'full' else f'`groups.{target}.status`'
    colour_path = f'`stones.{target}`' if mode == 'full' else f'`groups.{target}.colour`'
    if task == 'group_status':
        instructions = preamble + f'What life status is explicitly recorded for group {target} in {status_path}?'
        criteria = {k: f'The reported status is {k}.' for k in ('alive', 'critical', 'dead', 'unknown')}
    elif task == 'friendly_critical':
        instructions = preamble + (
            f'Is group {target} BOTH on the side to move AND explicitly marked critical? '
            f'Compare {colour_path} with `side_to_move` and read {status_path}. '
            'Answer yes only if the colours match and the status is critical. Alive and dead do not count as critical.')
        criteria = {'yes': 'Both conditions hold.', 'no': 'At least one condition does not hold.'}
    else:
        meaning = PURPOSES[task][0]
        instructions = preamble + (
            f'Does `candidate_notes.{target}` explicitly describe move {target} as {meaning}? '
            'Use only the notes of this candidate. A move may have several purposes. '
            'For defense/attack, owl-defends/attacks and strategically defends/attacks count; '
            'threatens to defend/attack does not count as defending/attacking now. '
            'Connecting and cutting are separate purposes from defense/attack. '
            'Do not infer extra purposes from another listed purpose.')
        criteria = {'yes': 'The specified purpose is explicitly listed.',
                    'no': 'The specified purpose is not explicitly listed.'}
    keys = list(criteria)
    random.Random(f'{seed}-{case["id"]}').shuffle(keys)
    if order == 'reverse':
        keys.reverse()
    return {'type': 'choice', 'instructions': instructions, 'criteria': {k: criteria[k] for k in keys}}


def build_jobs(positions, cases, modes, seed):
    by_id = {p['id']: p for p in positions}
    grouped = defaultdict(list)
    for c in cases:
        grouped[c['position_id']].append(c)
    jobs = []
    for pid, group in sorted(grouped.items()):
        for mode in modes:
            for order in ('forward', 'reverse'):
                qs = {f'q{i}': question(c, mode, order, seed) for i, c in enumerate(group)}
                jobs.append({'id': f'{pid}/{mode}/{order}', 'position_id': pid, 'mode': mode, 'order': order,
                             'case_ids': {f'q{i}': c['id'] for i, c in enumerate(group)},
                             'request': {'model': MODEL, 'state': state_for(by_id[pid], mode), 'questions': qs}})
    return jobs


def summarize(payload):
    cases = {c['id']: c for c in payload['cases']}
    predictions = defaultdict(dict)
    for job in payload['jobs']:
        for qid, answer in job.get('response', {}).get('answers', {}).items():
            predictions[job['mode'], job['case_ids'][qid]][job['order']] = answer['choice']
    out = {}
    for mode in payload['modes']:
        tasks = {}
        for task in sorted({c['task'] for c in cases.values()}):
            group = [c for c in cases.values() if c['task'] == task]
            complete = [c for c in group if len(predictions[mode, c['id']]) == 2]
            if not complete:
                continue
            labels = defaultdict(list)
            errors, same = [], 0
            for c in complete:
                a = predictions[mode, c['id']]
                labels[c['expected']].append(sum(v == c['expected'] for v in a.values()) / 2)
                same += len(set(a.values())) == 1
                if any(v != c['expected'] for v in a.values()):
                    errors.append({'case_id': c['id'], 'expected': c['expected'], 'predictions': a})
            recall = {label: sum(v) / len(v) for label, v in labels.items()}
            ba = sum(recall.values()) / len(recall)
            agreement = same / len(complete)
            tasks[task] = {'cases': len(group), 'complete_cases': len(complete),
                           'label_counts': {k: len(v) for k, v in labels.items()},
                           'label_recall_order_averaged': recall, 'balanced_accuracy': ba,
                           'same_answer_both_orders': agreement, 'errors': errors,
                           'passes_gate': len(complete) == len(group) and ba >= GATE['minimum_balanced_accuracy_per_task']
                           and min(recall.values()) >= GATE['minimum_recall_per_observed_label']
                           and agreement >= GATE['minimum_same_answer_both_orders_per_task']}
        out[mode] = {'tasks': tasks, 'passes_gate': bool(tasks) and len(tasks) == 6
                     and all(t['passes_gate'] for t in tasks.values())}
    out['usage'] = {k: sum(j.get('response', {}).get('usage', {}).get(k, 0) for j in payload['jobs'])
                    for k in ('input_tokens', 'output_tokens')}
    out['completed_requests'] = sum('response' in j for j in payload['jobs'])
    return out


def ask(job):
    from typesafe_sdk import Choice, TypeSafeClient
    req = job['request']
    start = time.perf_counter()
    with TypeSafeClient(timeout=45) as client:
        result = client.system_one(model=req['model'], state=req['state'],
            questions={k: Choice(instructions=q['instructions'], criteria=q['criteria'])
                       for k, q in req['questions'].items()})
    answers = {}
    for k, q in req['questions'].items():
        a = result.answers[k]
        if a.choice not in q['criteria'] or set(a.probabilities) != set(q['criteria']):
            raise ValueError('Response criteria mismatch')
        answers[k] = {'choice': a.choice, 'confidence': a.confidence, 'probabilities': dict(a.probabilities)}
    return {'model': result.model, 'answers': answers,
            'usage': {'input_tokens': result.usage.input_tokens, 'output_tokens': result.usage.output_tokens},
            'latency_ms': round((time.perf_counter() - start) * 1000, 2)}


def save(path, payload):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    tmp.replace(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path, default=HERE / 'matches/discrim-103.json')
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--per-label', type=int, default=12)
    ap.add_argument('--seed', type=int, default=20260923)
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--modes', nargs='+', choices=['full', 'focused'], default=['full', 'focused'])
    ap.add_argument('--run', action='store_true')
    args = ap.parse_args()
    if args.per_label < 1 or args.workers < 1:
        ap.error('Counts must be positive')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x'):
        pass
    raw = args.source.read_bytes()
    positions = json.loads(raw)['positions']
    cases = sample_cases(positions, args.per_label, args.seed)
    jobs = build_jobs(positions, cases, args.modes, args.seed)
    payload = {'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'prepared',
               'purpose': 'Input comprehension only; gold is supplied engine reports, not optimal Go play.',
               'source': str(args.source.resolve()), 'source_sha256': hashlib.sha256(raw).hexdigest(),
               'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'seed': args.seed, 'modes': args.modes, 'gate_fixed_before_calls': GATE,
               'cases': cases, 'jobs': jobs}
    save(args.output, payload)
    print(f'{len(cases)} cases, {len(jobs)} requests; labels: {Counter((c["task"], c["expected"]) for c in cases)}', flush=True)
    if args.run:
        payload['status'] = 'running'
        save(args.output, payload)
        with ThreadPoolExecutor(args.workers) as pool:
            pending = {pool.submit(ask, j): j for j in jobs}
            for i, future in enumerate(as_completed(pending), 1):
                job = pending[future]
                try:
                    job['response'] = future.result()
                except Exception as exc:
                    job['error_type'] = type(exc).__name__
                if i % 20 == 0 or i == len(jobs):
                    save(args.output, payload)
                    print(f'{i}/{len(jobs)} requests finished', flush=True)
        payload['status'] = 'complete' if all('response' in j for j in jobs) else 'partial'
    payload['summary'] = summarize(payload)
    save(args.output, payload)
    print(json.dumps(payload['summary'], ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
