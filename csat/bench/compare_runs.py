"""같은 시스템의 두 회차 비교 (PROTOCOL 18). 호출 단위 확률 차이와 문항 단위 답 일치를 본다."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from score import current_hashes, item_distribution, load, pick  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--system', required=True)
    ap.add_argument('--a', default='2027-09'); ap.add_argument('--b', default='2027-09-rerun')
    ap.add_argument('--dataset', type=Path, default=HERE / 'canonical-2027-09.json')
    ap.add_argument('--gold', type=Path, default=HERE.parent / 'exams' / '2027-09' / 'gold.json')
    a = ap.parse_args()
    qs = {q['id']: q for q in json.loads(a.dataset.read_text())['questions']}
    gold = json.loads(a.gold.read_text())
    ra, rb = load(a.a, a.system), load(a.b, a.system)
    key = lambda r: (r['id'], r['rotation'], r['request_sha256'])
    ia = {key(r): r for rs in ra.values() for r in rs if r['status'] == 'complete'}
    ib = {key(r): r for rs in rb.values() for r in rs if r['status'] == 'complete'}
    common = sorted(set(ia) & set(ib))
    diffs, same_pick = [], 0
    for k in common:
        pa, pb = ia[k]['probabilities'], ib[k]['probabilities']
        diffs.append(max(abs(pa[x] - pb[x]) for x in pa))
        same_pick += max(pa, key=pa.get) == max(pb, key=pb.get)
    diffs.sort()
    out = {'system': a.system, 'calls_compared': len(common), 'call_pick_agreement': same_pick,
           'max_abs_prob_diff': {'median': diffs[len(diffs) // 2], 'p95': diffs[int(len(diffs) * .95)], 'max': diffs[-1]},
           'identical_calls': sum(d == 0 for d in diffs)}
    # 5순환이 모두 있는 문항만 문항 단위로 비교
    items = [i for i in qs if all((i, r) in {(k[0], k[1]) for k in common} for r in range(5))]
    if items:
        acc, agree = {a.a: 0, a.b: 0}, 0
        for i in items:
            ok = current_hashes(qs[i])
            picks = {}
            for tag, recs in ((a.a, ra), (a.b, rb)):
                d, _, _ = item_distribution([r for r in recs[i] if r['request_sha256'] in ok], range(5))
                picks[tag] = pick(d); acc[tag] += picks[tag] == gold[i]['answer']
            agree += picks[a.a] == picks[a.b]
        out.update(items_compared=len(items), item_pick_agreement=agree, correct=acc)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
