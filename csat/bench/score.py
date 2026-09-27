"""채점. 정답 파일은 여기서만 읽는다. PROTOCOL.md 5절.

문항마다 보기 순환 5회의 확률을 원래 보기 번호로 되돌려 평균하고, 최댓값 번호를 답으로 한다.
unsupported 문항은 오답, 확률 지표에서는 균등분포(각 0.2)로 계산한다.
"""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import statistics
import hashlib
import sys

HERE = Path(__file__).resolve().parent
UNIFORM = {n: 0.2 for n in range(1, 6)}
sys.path.insert(0, str(HERE))
from run import make_request  # noqa: E402


def current_hashes(q):
    """정본이 바뀐 뒤 남은 옛 기록을 섞지 않도록, 지금 입력의 요청 해시만 받는다."""
    return {hashlib.sha256(json.dumps(make_request(q, r)[1], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            for r in range(5)}


def load(tag, system):
    by_id = defaultdict(list)
    for f in (HERE / 'results' / tag / system).glob('*.json'):
        r = json.loads(f.read_text())
        by_id[r['id']].append(r)
    return by_id


def item_distribution(records, rotations):
    """(평균 분포, rotation0 분포, 상태). 상태: complete / unsupported / incomplete."""
    done = {r['rotation']: r for r in records if r['status'] in ('complete', 'unsupported')}
    if any(r['status'] == 'unsupported' for r in done.values()):
        return UNIFORM, UNIFORM, 'unsupported'
    if set(rotations) - set(done):
        return None, None, 'incomplete'
    dists = [{int(k): v for k, v in done[k]['original_probabilities'].items()} for k in rotations]
    avg = {n: sum(d.get(n, 0.0) for d in dists) / len(dists) for n in range(1, 6)}
    total = sum(avg.values()) or 1.0
    avg = {n: p / total for n, p in avg.items()}
    return avg, dists[0] if 0 in rotations else None, 'complete'


def pick(dist):
    return max(dist, key=dist.get) if dist is not UNIFORM else None


def ece(rows, bins=10):
    buckets = defaultdict(list)
    for conf, ok in rows:
        buckets[min(int(conf * bins), bins - 1)].append((conf, ok))
    n = len(rows)
    return sum(len(b) / n * abs(statistics.mean(c for c, _ in b) - statistics.mean(o for _, o in b))
               for b in buckets.values()) if n else None


def mcnemar_p(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def score(dataset, gold, tag, system, rotations):
    recs = load(tag, system)
    rows, per_item = [], {}
    for q in dataset:
        ans = gold[q['id']]['answer']
        ok = current_hashes(q)
        dist, d0, status = item_distribution([r for r in recs.get(q['id'], []) if r['request_sha256'] in ok], rotations)
        if status == 'incomplete':
            continue
        p = pick(dist)
        per_item[q['id']] = p == ans
        rows.append({'id': q['id'], 'section': q['section'], 'status': status, 'answer': ans, 'pick': p,
                     'pick_r0': pick(d0) if d0 else None, 'dist': dist})
    n = len(rows)
    if not n:
        return None, per_item
    correct = sum(r['pick'] == r['answer'] for r in rows)
    by_sec = defaultdict(list)
    for r in rows:
        by_sec[r['section']].append(r['pick'] == r['answer'])
    brier = statistics.mean(sum((r['dist'][k] - (k == r['answer'])) ** 2 for k in range(1, 6)) for r in rows)
    logloss = statistics.mean(-math.log(max(r['dist'][r['answer']], 1e-6)) for r in rows)
    lat = [x['latency_ms'] for rs in recs.values() for x in rs if x.get('latency_ms') is not None]
    summary = {
        'system': system, 'items_scored': n, 'items_expected': len(dataset),
        'accuracy': correct / n, 'correct': correct,
        # unsupported 문항은 주 정확도와 같게 오답으로 센다 (분모를 맞춘다)
        'accuracy_rotation0': (statistics.mean(r['status'] == 'complete' and r['pick_r0'] == r['answer'] for r in rows)
                               if 0 in rotations else None),
        'macro_section_accuracy': statistics.mean(statistics.mean(v) for v in by_sec.values()),
        'unsupported': sum(r['status'] == 'unsupported' for r in rows),
        'coverage': sum(r['status'] == 'complete' for r in rows) / n,
        'brier': brier, 'log_loss': logloss,
        'ece10': ece([(r['dist'][r['pick']], r['pick'] == r['answer']) for r in rows if r['pick']]),
        'median_latency_ms': statistics.median(lat) if lat else None,
    }
    return summary, per_item


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', default='2026-dev')
    ap.add_argument('--dataset', type=Path, default=HERE.parent / 'all_subjects' / 'dataset.json')
    ap.add_argument('--gold', type=Path, default=HERE.parent / 'all_subjects' / 'gold.json')
    ap.add_argument('--systems', nargs='*')
    ap.add_argument('--rotations', type=int, nargs='*', default=[0, 1, 2, 3, 4])
    a = ap.parse_args()
    dataset = json.loads(a.dataset.read_text())['questions']
    gold = json.loads(a.gold.read_text())
    systems = a.systems or sorted(p.name for p in (HERE / 'results' / a.tag).iterdir() if p.is_dir())
    summaries, items = [], {}
    for s in systems:
        summary, per_item = score(dataset, gold, a.tag, s, a.rotations)
        if summary:
            summaries.append(summary); items[s] = per_item
    pairs = []
    for i, x in enumerate(summaries):
        for y in summaries[i + 1:]:
            common = set(items[x['system']]) & set(items[y['system']])
            b = sum(items[x['system']][k] and not items[y['system']][k] for k in common)
            c = sum(items[y['system']][k] and not items[x['system']][k] for k in common)
            pairs.append({'a': x['system'], 'b': y['system'], 'common': len(common),
                          'a_only': b, 'b_only': c, 'mcnemar_p': mcnemar_p(b, c)})
    out = {'tag': a.tag, 'rotations': a.rotations, 'chance': 0.2, 'systems': summaries, 'pairs': pairs}
    (HERE / 'results' / a.tag / 'scores.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
    for s in summaries:
        print(f"{s['system']:14} acc {s['accuracy']:.3f} ({s['correct']}/{s['items_scored']})  r0 "
              f"{(s['accuracy_rotation0'] or 0):.3f}  unsupported {s['unsupported']}  brier {s['brier']:.3f}  "
              f"ece {(s['ece10'] or 0):.3f}  median {s['median_latency_ms']}ms")


if __name__ == '__main__':
    main()
