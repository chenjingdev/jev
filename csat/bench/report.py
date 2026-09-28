"""영역별 정확도, 원문 페이지 단위 bootstrap 95% 구간, Jev 대비 McNemar. PROTOCOL.md 5절."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import random
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from score import current_hashes, item_distribution, load, mcnemar_p, pick  # noqa: E402

AREAS = {'korean': '국어', 'math': '수학', 'english': '영어', 'korean-history': '한국사'}
SOCIAL = {'east-asia-history', 'economics', 'ethics-thought', 'korean-geography', 'life-ethics', 'politics-law',
          'social-culture', 'world-geography', 'world-history'}
SCIENCE = {'biology-1', 'biology-2', 'chemistry-1', 'chemistry-2', 'earth-science-1', 'earth-science-2',
           'physics-1', 'physics-2'}
VOCATIONAL = {'agriculture', 'commerce-economics', 'fishery-maritime', 'human-development', 'industrial-general',
              'successful-career'}


def area(subject):
    return AREAS.get(subject) or ('사회탐구' if subject in SOCIAL else '과학탐구' if subject in SCIENCE
                                  else '직업탐구' if subject in VOCATIONAL else '제2외국어·한문')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', default='2027-09')
    ap.add_argument('--dataset', type=Path, default=HERE / 'canonical-2027-09.json')
    ap.add_argument('--gold', type=Path, default=HERE.parent / 'exams' / '2027-09' / 'gold.json')
    ap.add_argument('--systems', nargs='+', required=True)
    ap.add_argument('--reference', default='jev-1.13.0')
    ap.add_argument('--boot', type=int, default=10000)
    a = ap.parse_args()
    qs = json.loads(a.dataset.read_text())['questions']
    gold = json.loads(a.gold.read_text())
    correct = {}
    for s in a.systems:
        recs = load(a.tag, s)
        correct[s] = {}
        for q in qs:
            ok = current_hashes(q)
            dist, _, status = item_distribution([r for r in recs.get(q['id'], []) if r['request_sha256'] in ok], range(5))
            assert status != 'incomplete', (s, q['id'])
            correct[s][q['id']] = pick(dist) == gold[q['id']]['answer']
    # 원문 페이지 단위 묶음 (같은 지문을 공유하는 문항은 함께 재표집)
    clusters = defaultdict(list)
    for q in qs:
        clusters[(q['subject'], q.get('source_page'))].append(q['id'])
    keys = list(clusters)
    rng = random.Random(20260927)
    boots = {s: [] for s in a.systems}
    for _ in range(a.boot):
        sample = [i for k in (rng.choice(keys) for _ in keys) for i in clusters[k]]
        for s in a.systems:
            boots[s].append(sum(correct[s][i] for i in sample) / len(sample))
    by_area = defaultdict(list)
    for q in qs:
        by_area[area(q['subject'])].append(q['id'])
    rows = []
    for s in a.systems:
        b = sorted(boots[s])
        acc = sum(correct[s].values()) / len(qs)
        ref = correct[a.reference]
        x = sum(correct[s][i] and not ref[i] for i in ref)
        y = sum(ref[i] and not correct[s][i] for i in ref)
        rows.append({'system': s, 'accuracy': acc, 'ci95': [b[int(.025 * len(b))], b[int(.975 * len(b)) - 1]],
                     'areas': {k: sum(correct[s][i] for i in ids) / len(ids) for k, ids in by_area.items()},
                     'vs_reference': {'only_this': x, 'only_reference': y, 'mcnemar_p': mcnemar_p(x, y)}})
    out = {'tag': a.tag, 'area_sizes': {k: len(v) for k, v in by_area.items()}, 'rows': rows,
           'bootstrap': {'unit': 'subject x source page', 'clusters': len(keys), 'resamples': a.boot, 'seed': 20260927}}
    (HERE / 'results' / a.tag / 'report.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
    order = list(by_area)
    print('system'.ljust(12), 'acc   95%CI        ', ' '.join(f'{k}({len(by_area[k])})' for k in order))
    for r in rows:
        print(r['system'].ljust(12), f"{r['accuracy']:.3f} [{r['ci95'][0]:.3f},{r['ci95'][1]:.3f}]",
              ' '.join(f"{r['areas'][k]:.2f}".rjust(len(k) + 4) for k in order),
              f"| vs ref +{r['vs_reference']['only_this']}/-{r['vs_reference']['only_reference']} p={r['vs_reference']['mcnemar_p']:.2g}")


if __name__ == '__main__':
    main()
