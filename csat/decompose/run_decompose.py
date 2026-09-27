"""ㄱㄴㄷ 진술을 하나씩 Noul로 묻는다. 정답표는 채점 단계(analyze.py)에서만 연다."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import hashlib
import json
from pathlib import Path
import re
import time

from typesafe_sdk import Noul, TypeSafeClient

HERE = Path(__file__).resolve().parent
DATASET = HERE.parent / 'all_subjects' / 'dataset.json'
MODEL = 'jev-1.13.0'
INSTRUCTIONS = (
    '`statement`는 `question`이 <보기>에서 고르라고 한 항목 하나입니다. '
    '`passage`·`visual_description`의 자료와 필요한 교과 지식에 비추어, 이 항목은 `question`의 조건에 맞아 '
    '정답으로 골라야 하는 항목이다.'
)
COMBO = re.compile(r'[ㄱㄴㄷㄹㅁ ,]+')
BOGI = re.compile(r'<\s*보\s*기\s*>(.*)', re.S)
STMT = re.compile(r'^\s*([ㄱㄴㄷㄹㅁ])\.\s*(.+)$', re.M)


def targets():
    out = []
    for q in json.loads(DATASET.read_text())['questions']:
        if sum(bool(COMBO.fullmatch(o.strip())) for o in q['options']) < 3:
            continue
        m = BOGI.search(q['state'].get('passage') or '')
        stmts = STMT.findall(m.group(1)) if m else []
        if 2 <= len(stmts) <= 4:
            out.append((q, stmts))
    return out


def job(q, label, text):
    state = dict(q['state'], statement=f'{label}. {text}')
    return {'model': MODEL, 'state': state, 'instructions': INSTRUCTIONS}


def ask(req):
    started = time.perf_counter()
    with TypeSafeClient(timeout=45) as client:
        r = client.system_one(model=req['model'], state=req['state'],
                              questions={'s': Noul(instructions=req['instructions'])})
    return {'model': r.model, 'noul': r.answers['s'].noul, 'latency_ms': round((time.perf_counter() - started) * 1000, 2),
            'usage': {'input_tokens': r.usage.input_tokens, 'output_tokens': r.usage.output_tokens}}


def run_one(out_dir, q, label, text):
    req = job(q, label, text)
    digest = hashlib.sha256(json.dumps(req, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    target = out_dir / f"{q['id'].replace(':', '-')}-{label}-{digest[:12]}.json"
    if target.exists() and json.loads(target.read_text()).get('status') == 'complete':
        return 'cached'
    rec = {'id': q['id'], 'label': label, 'request_sha256': digest, 'request': req, 'attempts': [], 'status': 'error'}
    for attempt in range(3):
        try:
            rec['response'] = ask(req); rec['status'] = 'complete'; break
        except Exception as exc:
            rec['attempts'].append({'error_type': type(exc).__name__, 'message': str(exc)[:180]})
            time.sleep(2 ** attempt)
    tmp = target.with_suffix('.tmp'); tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1)); tmp.replace(target)
    return rec['status']


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--limit', type=int); ap.add_argument('--out', default=str(HERE / 'results'))
    a = ap.parse_args(); out_dir = Path(a.out); out_dir.mkdir(parents=True, exist_ok=True)
    items = targets()[:a.limit] if a.limit else targets()
    tasks = [(q, l, t) for q, stmts in items for l, t in stmts]
    print(f'{len(items)} questions, {len(tasks)} statements', flush=True)
    done = 0
    with ThreadPoolExecutor(a.workers) as ex:
        for f in as_completed([ex.submit(run_one, out_dir, *t) for t in tasks]):
            done += 1
            if f.result() != 'complete' and f.result() != 'cached': print('error', flush=True)
            if done % 50 == 0: print(f'{done}/{len(tasks)}', flush=True)


if __name__ == '__main__':
    main()
