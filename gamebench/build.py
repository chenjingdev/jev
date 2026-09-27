"""게임 모듈에서 문항을 만들고 검증해 items.jsonl(정답 없음)과 gold.json으로 나눈다. PROTOCOL.md.

python gamebench/build.py --seed 20260927 --per-stage 10 --out gamebench/sets/v1
개발용 dev 세트(게임마다 3문항)는 어댑터 점검에만 쓰고 채점 결과에 넣지 않는다.
"""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import pkgutil
import random
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from games.common import MAX_OPTIONS, STAGES  # noqa: E402

LEAK_WORDS = ('정답', '답:', '(답)', '올바른 보기', 'correct')
MIN_ITEMS, MAX_ITEMS = 15, 80  # 상황 수가 적은 게임(가위바위보 등)은 중복 없이 15개 안팎이다


def modules():
    import games
    for m in sorted(pkgutil.iter_modules(games.__path__), key=lambda m: m.name):
        if m.name == 'common' or m.name.startswith('test_'):
            continue
        yield importlib.import_module(f'games.{m.name}')


def game_rng(seed, game):
    return random.Random(int(hashlib.sha256(f'{seed}:{game}'.encode()).hexdigest(), 16))


def validate(mod, items):
    errs = []
    ids = [x['id'] for x in items]
    by_id = {x['id']: x for x in items}
    if len(set(ids)) != len(ids):
        errs.append('duplicate ids')
    if not MIN_ITEMS <= len(items) <= MAX_ITEMS:
        errs.append(f'{len(items)} items (want {MIN_ITEMS}~{MAX_ITEMS})')
    for x in items:
        n = len(x['options'])
        if x['game'] != mod.GAME or not x['id'].startswith(mod.GAME + ':'):
            errs.append(f"{x['id']}: game id")
        if not any(x['stage'].startswith(s) for s in STAGES):
            errs.append(f"{x['id']}: stage {x['stage']}")
        if not 2 <= n <= MAX_OPTIONS or len(set(x['options'])) != n:
            errs.append(f"{x['id']}: options")
        if not 1 <= x['answer'] <= n:
            errs.append(f"{x['id']}: answer range")
        visible = json.dumps(x['state'], ensure_ascii=False) + x['question'] + ''.join(x['options'])
        if any(w in visible for w in LEAK_WORDS):
            errs.append(f"{x['id']}: leak word")
        if x['stage'].startswith('2-'):
            t = by_id.get(x.get('twin_of'))
            if t is None:
                errs.append(f"{x['id']}: twin missing")
            else:
                if t['options'] != x['options']:
                    errs.append(f"{x['id']}: twin options differ")
                if t['question'] != x['question']:
                    errs.append(f"{x['id']}: twin question differs")
                if x.get('original_answer') != t['answer']:
                    errs.append(f"{x['id']}: original_answer != twin answer")
                if x.get('original_answer') == x['answer']:
                    errs.append(f"{x['id']}: twin answer unchanged")
    if not any(x['stage'].startswith('2-') for x in items):
        errs.append('no 2-변형 items')
    multi = [x for x in items if len(x['options']) >= 3]
    if len(multi) >= 10:
        share = max(sum(x['answer'] == k for x in multi) for k in range(1, MAX_OPTIONS + 1)) / len(multi)
        if share > 0.6:
            errs.append(f'answer position skew {share:.2f}')
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=20260927)
    ap.add_argument('--per-stage', type=int, default=10)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--dev', type=int, default=3, help='게임마다 dev로 뺄 문항 수')
    a = ap.parse_args()
    all_items, gold, dev, failed = [], {}, [], {}
    for mod in modules():
        items = mod.generate(game_rng(a.seed, mod.GAME), a.per_stage)
        again = mod.generate(game_rng(a.seed, mod.GAME), a.per_stage)
        errs = validate(mod, items) + ([] if again == items else ['not deterministic'])
        if errs:
            failed[mod.GAME] = errs[:10]; continue
        # dev: ①/③ 단계에서 짝이 없는 문항 몇 개 (변형 짝을 깨지 않도록)
        twinned = {x.get('twin_of') for x in items}
        cand = [x for x in items if not x['stage'].startswith('2-') and x['id'] not in twinned]
        dev_ids = {x['id'] for x in game_rng(a.seed + 1, mod.GAME).sample(cand, min(a.dev, len(cand)))}
        for x in items:
            meta = {'game_name': mod.NAME, 'facet': mod.FACET}
            pub = {k: x[k] for k in ('id', 'game', 'stage', 'state', 'question', 'options')} | meta
            (dev if x['id'] in dev_ids else all_items).append(pub)
            gold[x['id']] = {k: x[k] for k in ('answer', 'original_answer', 'twin_of') if k in x} | {'n': len(x['options'])}
    if failed:
        print(json.dumps(failed, ensure_ascii=False, indent=1))
        sys.exit(1)
    a.out.mkdir(parents=True, exist_ok=True)
    write = lambda name, rows: (a.out / name).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    write('items.jsonl', all_items); write('dev.jsonl', dev)
    (a.out / 'gold.json').write_text(json.dumps(gold, ensure_ascii=False, indent=1))
    manifest = {'seed': a.seed, 'per_stage': a.per_stage, 'games': sorted({x['game'] for x in all_items}),
                'items': len(all_items), 'dev': len(dev),
                'sha256': {n: hashlib.sha256((a.out / n).read_bytes()).hexdigest() for n in ('items.jsonl', 'dev.jsonl', 'gold.json')}}
    (a.out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in manifest.items() if k != 'sha256'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
