"""Frozen single-question Jev exam, with separate answer key and order controls."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import time

from typesafe_sdk import Choice, TypeSafeClient

HERE = Path(__file__).resolve().parent
MODEL = 'jev-1.13.0'
INSTRUCTIONS = (
    '`question`의 요구에 따라 주어진 지문과 자료를 읽고 정답 하나를 선택하세요. '
    '내용이 일치하지 않는 것, 어법상 틀린 것 등 문항의 긍정·부정 조건에 주의하세요. '
    '지문에 ①~⑤ 또는 (a)~(e)가 있으면 원문의 위치·밑줄을 가리키는 표시입니다. '
    '반환할 답은 현재 제시된 선택지 A~E 중 해당하는 키입니다. '
    '추가 해설이나 힌트 없이 주어진 내용으로 문항을 풀어야 합니다.'
)
TYPES = {18: '목적', 19: '심경', 20: '주장', 21: '함축의미', 22: '요지', 23: '주제', 24: '제목',
         25: '도표', 26: '내용불일치', 27: '안내문', 28: '안내문', 29: '어법', 30: '어휘',
         31: '빈칸', 32: '빈칸', 33: '빈칸', 34: '빈칸', 35: '무관한문장',
         36: '순서', 37: '순서', 38: '삽입', 39: '삽입', 40: '요약',
         41: '장문제목', 42: '장문어휘', 43: '장문순서', 44: '지칭', 45: '장문내용불일치'}


def make_job(question, rotation):
    original = list(range(1, 6))
    order = original[rotation:] + original[:rotation]
    mapping = dict(zip('ABCDE', order))
    return {'number': question['number'], 'rotation': rotation, 'choice_to_original': mapping,
            'request': {'model': MODEL, 'state': question['state'],
                        'questions': {'answer': {'instructions': INSTRUCTIONS,
                                               'criteria': {k: question['options'][n-1] for k, n in mapping.items()}}}}}


def ask(job):
    req = job['request']
    q = req['questions']['answer']
    started = time.perf_counter()
    with TypeSafeClient(timeout=45) as client:
        response = client.system_one(model=req['model'], state=req['state'],
                                    questions={'answer': Choice(instructions=q['instructions'], criteria=q['criteria'])})
    elapsed = time.perf_counter() - started
    a = response.answers['answer']
    if set(a.probabilities) != set(q['criteria']) or a.choice not in q['criteria']:
        raise ValueError('Response options do not match request')
    return {'model': response.model, 'choice': a.choice, 'original_option': job['choice_to_original'][a.choice],
            'probabilities': dict(a.probabilities), 'confidence': a.confidence,
            'latency_ms': round(elapsed * 1000, 2),
            'usage': {'input_tokens': response.usage.input_tokens, 'output_tokens': response.usage.output_tokens}}


def grade(jobs, gold):
    numbers = sorted({j['number'] for j in jobs})
    details = []
    for n in numbers:
        items = sorted([j for j in jobs if j['number'] == n], key=lambda j: j['rotation'])
        g = gold[str(n)]
        base = next(j for j in items if j['rotation'] == 0)
        picks = [j['response']['original_option'] for j in items if 'response' in j]
        primary_pick = base.get('response', {}).get('original_option')
        details.append({'number': n, 'type': TYPES.get(n, 'unspecified'), 'gold': g['answer'], 'points': g['points'],
                        'primary_pick': primary_pick, 'primary_correct': primary_pick == g['answer'],
                        'primary_confidence': base.get('response', {}).get('confidence'),
                        'picks_across_orders': picks, 'order_correct': sum(p == g['answer'] for p in picks),
                        'order_trials': len(picks), 'stable': len(picks) == 5 and len(set(picks)) == 1})
    base_jobs = [j for j in jobs if j['rotation'] == 0 and 'response' in j]
    completed = [j for j in jobs if 'response' in j]
    result = {
        'questions': len(numbers), 'primary_completed': len(base_jobs),
        'primary_correct': sum(d['primary_correct'] for d in details),
        'primary_points': sum(d['points'] for d in details if d['primary_correct']),
        'maximum_points': sum(d['points'] for d in details),
        'primary_wrong_numbers': [d['number'] for d in details if not d['primary_correct']],
        'stable_across_five_orders': sum(d['stable'] for d in details),
        'order_correct': sum(d['order_correct'] for d in details),
        'order_trials': sum(d['order_trials'] for d in details),
        'all_orders_correct_questions': [d['number'] for d in details if d['order_correct'] == 5],
        'all_orders_wrong_questions': [d['number'] for d in details if d['order_trials'] == 5 and d['order_correct'] == 0],
        'primary_median_latency_ms': statistics.median(j['response']['latency_ms'] for j in base_jobs) if base_jobs else None,
        'primary_sum_latency_ms': sum(j['response']['latency_ms'] for j in base_jobs),
        'usage': {k: sum(j['response']['usage'][k] for j in completed) for k in ['input_tokens', 'output_tokens']},
        'details': details,
    }
    return result


def save(path, payload):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    tmp.replace(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--questions', type=Path, default=HERE / 'data/2026-english-reading.json')
    ap.add_argument('--gold', type=Path, default=HERE / 'data/2026-english-gold.json')
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--workers', type=int, default=4)
    args = ap.parse_args()
    raw = args.questions.read_bytes()
    dataset = json.loads(raw)
    jobs = [make_job(q, r) for r in range(5) for q in dataset['questions']]
    payload = {'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'prepared',
               'model': MODEL, 'exam': dataset['exam'], 'dataset_sha256': hashlib.sha256(raw).hexdigest(),
               'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'protocol': 'One fixed prompt; original order is primary; four cyclic relabelled orders are controls. No answer key or explanations sent. Repeat trials are not independent questions.',
               'jobs': jobs}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x'):
        pass
    save(args.output, payload)
    start = time.perf_counter()
    # Primary exam runs once in question order, before any accuracy is computed.
    for job in [j for j in jobs if j['rotation'] == 0]:
        job['response'] = ask(job)
        save(args.output, payload)
        print(f'Primary question {job["number"]} answered', flush=True)
    payload['primary_wall_seconds'] = round(time.perf_counter() - start, 3)
    with ThreadPoolExecutor(args.workers) as pool:
        pending = {pool.submit(ask, j): j for j in jobs if j['rotation'] != 0}
        for i, future in enumerate(as_completed(pending), 1):
            pending[future]['response'] = future.result()
            if i % 20 == 0:
                save(args.output, payload)
                print(f'{i}/{len(pending)} order-control requests answered', flush=True)
    # Gold is loaded only after all model answers have been collected.
    gold_raw = args.gold.read_bytes()
    payload['gold_sha256'] = hashlib.sha256(gold_raw).hexdigest()
    payload['summary'] = grade(jobs, json.loads(gold_raw))
    payload['wall_seconds'] = round(time.perf_counter() - start, 3)
    payload['status'] = 'complete'
    save(args.output, payload)
    print(json.dumps({k: v for k, v in payload['summary'].items() if k != 'details'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
