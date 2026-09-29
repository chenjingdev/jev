"""세트를 합쳐 claims/sets/all/{items.jsonl,gold.json}을 만든다. 실행기는 이 파일 하나로 시스템마다 한 번 돈다."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SETS = sorted(p.name for p in (HERE / 'sets').iterdir() if p.is_dir() and p.name != 'all')

items, gold = [], {}
for s in SETS:
    items += [l for l in (HERE / 'sets' / s / 'items.jsonl').read_text().splitlines() if l.strip()]
    gold.update(json.loads((HERE / 'sets' / s / 'gold.json').read_text()))
assert len(items) == len(gold) == len({json.loads(l)['id'] for l in items})
out = HERE / 'sets' / 'all'
out.mkdir(exist_ok=True)
(out / 'items.jsonl').write_text('\n'.join(items) + '\n')
(out / 'gold.json').write_text(json.dumps(gold, ensure_ascii=False, indent=1) + '\n')
print(len(SETS), 'sets', len(items), 'items')
