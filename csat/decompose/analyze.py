"""분해 결과 채점. 정답표는 여기서만 연다."""
import csv
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_decompose import targets  # noqa: E402

ALL = HERE.parent / 'all_subjects'
gold = json.loads((ALL / 'gold.json').read_text())
single = {r['id']: r['correct'] == 'True' for r in csv.DictReader(open(ALL / 'answers.csv')) if r['model'] == 'jev-1.13.0'}
single_sel = {r['id']: int(r['selected']) for r in csv.DictReader(open(ALL / 'answers.csv')) if r['model'] == 'jev-1.13.0'}
res = {}
for f in (HERE / 'results').glob('*.json'):
    r = json.loads(f.read_text())
    if r['status'] == 'complete':
        res[(r['id'], r['label'])] = r['response']['noul']

rows, missing = [], 0
for q, stmts in targets():
    labels = [l for l, _ in stmts]
    if any((q['id'], l) not in res for l in labels):
        missing += 1; continue
    p = {l: min(max(res[(q['id'], l)], 0.001), 0.999) for l in labels}
    sets = [set(c for c in o if c in 'ㄱㄴㄷㄹㅁ') for o in q['options']]
    ans = gold[q['id']]['answer']; truth = sets[ans - 1]
    score = [sum(math.log(p[l]) if l in s else math.log(1 - p[l]) for l in labels) for s in sets]
    pick = max(range(5), key=lambda i: score[i]) + 1
    stmt_ok = {l: (p[l] >= 0.5) == (l in truth) for l in labels}
    rows.append({'id': q['id'], 'n': len(labels), 'single': single[q['id']], 'single_pick': single_sel[q['id']],
                 'composed': pick == ans, 'composed_pick': pick, 'answer': ans,
                 'stmt_ok': stmt_ok, 'p': p, 'truth': sorted(truth)})

n = len(rows)
def pct(k): return f'{k}/{n} ({k / n:.1%})'
S = sum(r['single'] for r in rows); C = sum(r['composed'] for r in rows)
st = [v for r in rows for v in r['stmt_ok'].values()]
all_ok = [r for r in rows if all(r['stmt_ok'].values())]
wrong = [r for r in rows if not r['single']]
summary = {
    'questions': n, 'missing_questions': missing,
    'single_choice_correct': S, 'decomposed_correct': C,
    'both': sum(r['single'] and r['composed'] for r in rows),
    'single_only': sum(r['single'] and not r['composed'] for r in rows),
    'decomposed_only': sum(r['composed'] and not r['single'] for r in rows),
    'statements': len(st), 'statement_correct': sum(st),
    'questions_all_statements_correct': len(all_ok),
    'single_wrong': len(wrong),
    'single_wrong_but_all_statements_correct': sum(all(r['stmt_ok'].values()) for r in wrong),
    'single_wrong_and_some_statement_wrong': sum(not all(r['stmt_ok'].values()) for r in wrong),
}
(HERE / 'analysis.json').write_text(json.dumps({'summary': summary, 'rows': rows}, ensure_ascii=False, indent=1))
print(f'문항 {n} (누락 {missing})')
print('단일 Choice 정답', pct(S)); print('분해·조합 정답', pct(C))
print('둘 다', summary['both'], '단일만', summary['single_only'], '분해만', summary['decomposed_only'])
print(f"진술 단위 정답 {sum(st)}/{len(st)} ({sum(st) / len(st):.1%})")
print('모든 진술 판정이 맞은 문항', pct(len(all_ok)))
print(f"기존 오답 {len(wrong)}: 진술 모두 맞음 {summary['single_wrong_but_all_statements_correct']}, 진술 하나 이상 틀림 {summary['single_wrong_and_some_statement_wrong']}")
