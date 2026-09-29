"""Jeff(firelex/jeff)가 README에서 인용한 벤치 패널을 gamebench/run.py 공통 문항 형식으로 옮긴다.

원천은 Jeff 제작자 코드로 만든 파일 두 개다. 둘 다 데이터셋 리비전과 시드가 코드에 고정돼 있다.
  - data/panel.jsonl:        `python -m jeff.panel` (jeff@2c1bfce, seed 20260926, 5개 스위트 4,599문항)
  - data/jevbench-hard.jsonl: `python -m jeff.jevbench` (fstandhartinger/jevbench@d06ee95 public hard, score 6문항 제외 105문항)
두 파일의 sha256을 고정하고 다르면 멈춘다. 스위트마다 세트 하나씩 만든다.

변환 규칙 (Jeff 자신의 렌더링을 따른다, jeff/src/jeff/model.py:50-57 options()):
  - choice: 선택지 문구 = criteria 값, 값이 None이면 키 (BBH의 "True"/"- option" 줄 등).
  - noul(RAGTruth, JevBench hard 일부): [false 문구, true 문구] 두 선택지로 바꾼다.
    문구는 criteria에 있으면 그 값, 없으면 Jeff 기본값 "No / false" / "Yes / true".
    Jeff 평가기는 noul을 같은 두 선택지(false, true 순)로 채점하므로 문제 자체는 같다.
    다만 공통 계약이 choice뿐이라 모든 시스템(Jeff 포함)이 선택지 문제로 받는다.
  - state는 그대로 (문자열 또는 객체).

  .venv/bin/python claims/build_jeff.py
"""
from collections import Counter
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETS_DIR = HERE / 'sets'
JEFF = Path.home() / 'dev' / 'jev-likes' / 'jeff'
JEFF_COMMIT = '2c1bfce27a394ce48869951332b30aedfba3b7b0'
SOURCES = {
    'panel': ('data/panel.jsonl', '46b6fb82a50d6b8f00f3dc41d3d357e1015c01e2af8faade07e969b3c7bbd99b'),
    'jevbench-hard': ('data/jevbench-hard.jsonl', 'bfec42ef616fb9e0e7d0e8eee81c09a869c14ee9460d0c73cb807664154212da'),
}
SETS = {  # suite -> set name
    'BBH': 'jeff-bbh750',
    'Financial PhraseBank': 'jeff-fpb999',
    'JudgeBench': 'jeff-judgebench350',
    'RAGTruth': 'jeff-ragtruth1500',
    'WinoGrande': 'jeff-winogrande1000',
    'JevBench public hard': 'jeff-jevbenchhard105',
}
NOUL_DEFAULT = {'false': 'No / false', 'true': 'Yes / true'}  # jeff.model.options()


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def convert(row):
    q = row['question']
    if q['type'] == 'choice':
        keys = list(q['criteria'])
        options = [k if v is None else text(v) for k, v in q['criteria'].items()]
        answer = keys.index(row['label']) + 1
    elif q['type'] == 'noul':
        crit = q.get('criteria') or {}
        options = [text(crit.get(k) or NOUL_DEFAULT[k]) for k in ('false', 'true')]
        answer = 2 if row['label'] is True else 1
    else:
        raise ValueError(f"{row['id']}: {q['type']}")
    s = SETS[row['suite']]
    item = {'id': f"{s}:{row['id']}", 'game': s, 'stage': row['family'].split('-')[1] if row['suite'] == 'BBH' else q['type'],
            'state': row['state'], 'question': text(q.get('instructions') or ''), 'options': options}
    if row['suite'] == 'BBH':
        item['stage'] = row['source']['task']
    elif row['suite'] == 'JevBench public hard':
        item['stage'] = row['source']['item_family']
    return item, {'answer': answer, 'n': len(options)}, q['type']


def main():
    rows = []
    src_meta = {}
    for name, (path, pinned) in SOURCES.items():
        data = (JEFF / path).read_bytes()
        got = sha256_bytes(data)
        if got != pinned:
            raise SystemExit(f'{path}: sha256 {got} != pinned {pinned}')
        src_meta[name] = {'path': path, 'sha256': got}
        rows += [json.loads(line) for line in data.decode().splitlines() if line.strip()]
    by_set = {}
    for row in rows:
        item, gold, qtype = convert(row)
        by_set.setdefault(item['game'], []).append((item, gold, qtype))
    for s, entries in sorted(by_set.items()):
        d = SETS_DIR / s
        d.mkdir(parents=True, exist_ok=True)
        items = ''.join(json.dumps(e[0], ensure_ascii=False) + '\n' for e in entries)
        gold = json.dumps({e[0]['id']: e[1] for e in entries}, indent=1, ensure_ascii=False) + '\n'
        (d / 'items.jsonl').write_text(items)
        (d / 'gold.json').write_text(gold)
        manifest = {
            'set': s, 'builder': 'claims/build_jeff.py',
            'source': {'maker': 'firelex/jeff', 'commit': JEFF_COMMIT, 'files': src_meta,
                       'maker_code': ['src/jeff/panel.py', 'src/jeff/jevbench.py', 'src/jeff/model.py:50-57']},
            'items': len(entries),
            'sha256': {'items.jsonl': sha256_bytes(items.encode()), 'gold.json': sha256_bytes(gold.encode())},
            'type_counts': dict(Counter(e[2] for e in entries)),
            'stats': {'options': dict(Counter(e[1]['n'] for e in entries)),
                      'answer_position': dict(Counter(e[1]['answer'] for e in entries))},
            'notes': ['noul questions become two options [false text, true text]; Jeff scores them in the same order.',
                      'Option text is the criteria value, or the key when the value is None (Jeff renders the key alone).'],
        }
        (d / 'manifest.json').write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + '\n')
        print(s, len(entries), manifest['type_counts'])


if __name__ == '__main__':
    main()
