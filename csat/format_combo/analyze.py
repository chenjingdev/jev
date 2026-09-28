"""형식 시험 채점. 기존 단일 Choice 기록과 같은 문항끼리 비교한다."""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALL = HERE.parent / 'all_subjects'
gold = json.loads((ALL / 'gold.json').read_text())
base = {r['id']: int(r['selected']) for r in csv.DictReader(open(ALL / 'answers.csv')) if r['model'] == 'jev-1.13.0'}
rerun = {}
for f in (HERE.parent / 'prompt_study' / 'development' / 'baseline').glob('*.json'):
    x = json.loads(f.read_text()); rerun[x['id']] = x['job']['response']['original_option']

rows, errors, tokens = [], 0, 0
for f in sorted((HERE / 'results' / 'spelled').glob('*.json')):
    r = json.loads(f.read_text())
    if r['status'] != 'complete':
        errors += 1; continue
    resp = r['job']['response']; ans = gold[r['id']]['answer']
    tokens += resp['usage']['input_tokens'] + resp['usage']['output_tokens']
    rows.append({'id': r['id'], 'answer': ans, 'base': base[r['id']], 'rerun': rerun[r['id']],
                 'spelled': resp['original_option'], 'confidence': resp['confidence']})

n = len(rows)
count = lambda k: sum(r[k] == r['answer'] for r in rows)
summary = {'questions': n, 'errors': errors, 'tokens': tokens,
           'base_correct': count('base'), 'rerun_correct': count('rerun'), 'spelled_correct': count('spelled'),
           'wrong_to_right': sum(r['base'] != r['answer'] and r['spelled'] == r['answer'] for r in rows),
           'right_to_wrong': sum(r['base'] == r['answer'] and r['spelled'] != r['answer'] for r in rows),
           'pick_changed': sum(r['base'] != r['spelled'] for r in rows)}
(HERE / 'analysis.json').write_text(json.dumps({'summary': summary, 'rows': rows}, ensure_ascii=False, indent=1))
print(json.dumps(summary, ensure_ascii=False, indent=1))

# 2025 추가 확인(PROTOCOL 7): prompt_study 검증 기준선과 같은 문항끼리 비교한다.
gold25 = json.loads((HERE.parent / 'prompt_study' / 'validation_2025' / 'gold.json').read_text())
rows25 = []
for f in sorted((HERE / 'results' / 'spelled-2025').glob('*.json')):
    r = json.loads(f.read_text())
    if r['status'] != 'complete':
        continue
    b = json.loads((HERE.parent / 'prompt_study' / 'validation_results' / 'baseline' / f"{r['id'].replace(':', '-')}.json").read_text())
    rows25.append({'id': r['id'], 'answer': gold25[r['id']]['answer'],
                   'base': b['job']['response']['original_option'], 'spelled': r['job']['response']['original_option']})
s25 = {'questions': len(rows25),
       'base_correct': sum(r['base'] == r['answer'] for r in rows25),
       'spelled_correct': sum(r['spelled'] == r['answer'] for r in rows25),
       'wrong_to_right': sum(r['base'] != r['answer'] and r['spelled'] == r['answer'] for r in rows25),
       'right_to_wrong': sum(r['base'] == r['answer'] and r['spelled'] != r['answer'] for r in rows25)}
(HERE / 'analysis-2025.json').write_text(json.dumps({'summary': s25, 'rows': rows25}, ensure_ascii=False, indent=1))
print('2025', json.dumps(s25, ensure_ascii=False))
