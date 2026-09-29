"""제작자 벤치마크 교차 실행 요약. PROTOCOL.md 3절.

세트를 합친 claims/sets/all/items.jsonl을 gamebench/run.py로 한 번에 돌린다(태그 claims).
여기서 세트(game)별로 나눠 정확도·95% 구간·우연 보정 점수·순환 0 정확도·Jev 대비 McNemar를 낸다.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import random
import statistics
import sys

HERE = Path(__file__).resolve().parent
GB = HERE.parent / 'gamebench'
sys.path.insert(0, str(GB))
from score import load, score_system  # noqa: E402

REF = 'jev-1.13.0'


def mcnemar_p(b, c):  # gamebench/report.py와 같다 (이름이 겹쳐 import하지 않는다)
    import math
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def rotation0(items, gold, tag, system):
    """원래 보기 순서 한 번만 불렀을 때의 정답 여부 (제작자 수치와 맞대는 용도)."""
    recs = load(tag, system)
    out = {}
    for it in items:
        r = next((r for r in recs.get(it['id'], []) if r['rotation'] == 0), None)
        if r is None:
            continue
        if r['status'] != 'complete':
            out[it['id']] = False
            continue
        p = {int(k): v for k, v in r['original_probabilities'].items()}
        out[it['id']] = max(p, key=p.get) == gold[it['id']]['answer']
    return out


def boot(values, rng, n=10000):
    m = sorted(statistics.mean(rng.choice(values) for _ in values) for _ in range(n))
    return [m[int(.025 * n)], m[int(.975 * n) - 1]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', default='claims')
    ap.add_argument('--systems', nargs='+', required=True)
    ap.add_argument('--boot', type=int, default=10000)
    a = ap.parse_args()
    items = [json.loads(l) for l in (HERE / 'sets' / 'all' / 'items.jsonl').read_text().splitlines() if l.strip()]
    gold = json.loads((HERE / 'sets' / 'all' / 'gold.json').read_text())
    sets = sorted({x['game'] for x in items})
    rng = random.Random(20260928)
    out = {}
    rows = {s: score_system(items, gold, a.tag, s) for s in a.systems}
    for s in a.systems:
        r0 = rotation0(items, gold, a.tag, s)
        by = defaultdict(list)
        for r in rows[s]:
            by[r['game']].append(r)
        out[s] = {}
        for st in sets:
            rs = by.get(st, [])
            n_items = sum(x['game'] == st for x in items)
            if len(rs) != n_items:
                out[s][st] = {'incomplete': f'{len(rs)}/{n_items}'}
                continue
            acc = [float(r['correct']) for r in rs]
            norm = [(r['correct'] - 1 / r['n']) / (1 - 1 / r['n']) for r in rs]
            o = {'items': len(rs), 'correct': int(sum(acc)), 'accuracy': statistics.mean(acc),
                 'ci95': boot(acc, rng, a.boot), 'chance': statistics.mean(1 / r['n'] for r in rs),
                 'normalized': statistics.mean(norm), 'unsupported': sum(r['status'] == 'unsupported' for r in rs),
                 'rotation0_accuracy': statistics.mean(r0[r['id']] for r in rs) if all(r['id'] in r0 for r in rs) else None}
            if s != REF and REF in rows:
                ref = {r['id']: r['correct'] for r in rows[REF] if r['game'] == st}
                if len(ref) == len(rs):
                    b = sum(r['correct'] and not ref[r['id']] for r in rs)
                    c = sum(ref[r['id']] and not r['correct'] for r in rs)
                    o['vs_jev'] = {'only_this': b, 'only_jev': c, 'mcnemar_p': mcnemar_p(b, c)}
            stages = defaultdict(list)
            for r in rs:
                stages[r['stage']].append(r['correct'])
            o['stages'] = {k: {'items': len(v), 'accuracy': statistics.mean(v)} for k, v in sorted(stages.items())}
            out[s][st] = o
    (GB / 'results' / a.tag).mkdir(parents=True, exist_ok=True)
    (GB / 'results' / a.tag / 'report.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
    for st in sets:
        print(f'\n## {st}')
        for s in a.systems:
            o = out[s][st]
            if 'incomplete' in o:
                print(f'{s:12} incomplete {o["incomplete"]}')
                continue
            v = o.get('vs_jev')
            print(f"{s:12} acc {o['accuracy']:.3f} [{o['ci95'][0]:.3f},{o['ci95'][1]:.3f}] ({o['correct']}/{o['items']})  "
                  f"r0 {o['rotation0_accuracy'] if o['rotation0_accuracy'] is None else round(o['rotation0_accuracy'], 3)}  "
                  f"norm {o['normalized']:.3f}  unsup {o['unsupported']}"
                  + (f"  vs jev +{v['only_this']}/-{v['only_jev']} p={v['mcnemar_p']:.2g}" if v else ''))


if __name__ == '__main__':
    main()
