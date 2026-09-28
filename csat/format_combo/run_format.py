"""ㄱㄴㄷ 선택지를 진술 본문으로 풀어 쓴 Choice 1회. 정답표는 analyze.py에서만 연다."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / 'decompose'))
from run_exam import make_job, ask  # noqa: E402
import run_decompose  # noqa: E402
from run_decompose import targets  # noqa: E402

VARIANT = 'spelled'


def spell(option, stmts):
    chosen = {c for c in option if c in 'ㄱㄴㄷㄹㅁ'}
    text = dict(stmts)
    yes = ' / '.join(f'{l}. {text[l]}' for l, _ in stmts if l in chosen)
    no = ' / '.join(f'{l}. {text[l]}' for l, _ in stmts if l not in chosen) or '없음'
    return f'옳은 것: {yes} || 옳지 않은 것: {no}'


def build(q, stmts):
    job = make_job(q, 0)
    crit = job['request']['questions']['answer']['criteria']
    for k in crit:
        crit[k] = spell(crit[k], stmts)
    return job


def run_one(out_dir, q, stmts):
    job = build(q, stmts)
    digest = hashlib.sha256(json.dumps(job['request'], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    target = out_dir / f"{q['id'].replace(':', '-')}-{digest[:12]}.json"
    if target.exists() and json.loads(target.read_text()).get('status') == 'complete':
        return 'cached'
    rec = {'id': q['id'], 'variant': VARIANT, 'request_sha256': digest, 'job': job, 'attempts': [], 'status': 'error'}
    for attempt in range(3):
        try:
            job['response'] = ask(job); rec['status'] = 'complete'; break
        except Exception as exc:
            rec['attempts'].append({'error_type': type(exc).__name__, 'message': str(exc)[:180]})
            time.sleep(2 ** attempt)
    tmp = target.with_suffix('.tmp'); tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1)); tmp.replace(target)
    return rec['status']


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--limit', type=int); ap.add_argument('--out')
    ap.add_argument('--dataset', type=Path, help='같은 필터를 다른 연도 dataset.json에 적용')
    a = ap.parse_args()
    if a.dataset and not a.out: ap.error('--dataset에는 --out이 필요하다 (연도가 달라도 문항 id가 겹친다)')
    a.out = a.out or str(HERE / 'results' / VARIANT)
    if a.dataset: run_decompose.DATASET = a.dataset
    out_dir = Path(a.out); out_dir.mkdir(parents=True, exist_ok=True)
    items = targets()[:a.limit] if a.limit else targets()
    print(f'{len(items)} questions', flush=True)
    with ThreadPoolExecutor(a.workers) as ex:
        for f in as_completed([ex.submit(run_one, out_dir, q, s) for q, s in items]):
            if f.result() not in ('complete', 'cached'): print('error', flush=True)


if __name__ == '__main__':
    main()
