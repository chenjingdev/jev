"""판단 벤치마크 요약: 시스템별 게임 평균 우연 보정 점수(게임 단위 bootstrap 95%), 판단 능력별,
단계별, 습관률, (판)/(주석) 차이, 보정 지표, Jev 대비 McNemar. PROTOCOL.md 4절."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import random
import statistics
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from score import score_system, summarize  # noqa: E402

STAGE_KEYS = ['1-판정', '2-변형', '3-한수', '4-앞보기']


def mcnemar_p(b, c):
    import math
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--set', type=Path, default=HERE / 'sets' / 'v1')
    ap.add_argument('--tag', default='v1')
    ap.add_argument('--systems', nargs='+', required=True)
    ap.add_argument('--reference', default='jev-1.13.0')
    ap.add_argument('--boot', type=int, default=10000)
    a = ap.parse_args()
    items = [json.loads(l) for l in (a.set / 'items.jsonl').read_text().splitlines() if l.strip()]
    gold = json.loads((a.set / 'gold.json').read_text())
    facet = {x['game']: x['facet'] for x in items}
    rows = {s: score_system(items, gold, a.tag, s) for s in a.systems}
    rng = random.Random(20260928)
    out = {}
    for s, rs in rows.items():
        assert len(rs) == len(items), (s, len(rs), len(items))
        games = defaultdict(list)
        for r in rs:
            games[r['game']].append(r)
        gnorm = {g: summarize(v)['normalized'] for g, v in games.items()}
        names = sorted(gnorm)
        boots = sorted(statistics.mean(gnorm[rng.choice(names)] for _ in names) for _ in range(a.boot))
        by_facet = defaultdict(list)
        for g, v in gnorm.items():
            by_facet[facet[g]].append(v)
        stage = {k: summarize([r for r in rs if r['stage'].startswith(k)]) for k in STAGE_KEYS}
        board = {}
        for rep in ('(판)', '(주석)'):
            sub = [r for r in rs if r['stage'].endswith(rep)]
            board[rep] = summarize(sub)['accuracy'] if sub else None
        total = summarize(rs)
        out[s] = {'score': statistics.mean(gnorm.values()), 'ci95': [boots[int(.025 * a.boot)], boots[int(.975 * a.boot) - 1]],
                  'facets': {f: statistics.mean(v) for f, v in by_facet.items()},
                  'stages': {k: (v['normalized'] if v else None) for k, v in stage.items()},
                  'habit_rate': total['habit_rate'], 'board_raw_acc': board['(판)'], 'board_annotated_acc': board['(주석)'],
                  'unsupported': total['unsupported'], 'brier': total['brier'], 'ece10': total['ece10'],
                  'games': gnorm}
    ref = {r['id']: r['correct'] for r in rows[a.reference]}
    for s in a.systems:
        cur = {r['id']: r['correct'] for r in rows[s]}
        b = sum(cur[i] and not ref[i] for i in ref); c = sum(ref[i] and not cur[i] for i in ref)
        out[s]['vs_reference'] = {'only_this': b, 'only_reference': c, 'mcnemar_p': mcnemar_p(b, c)}
    (HERE / 'results' / a.tag / 'report.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
    facets = sorted({f for o in out.values() for f in o['facets']})
    print('system       score  95%CI          ' + '  '.join(STAGE_KEYS) + '  habit  판→주석')
    for s in sorted(out, key=lambda k: -out[k]['score']):
        o = out[s]
        st = '  '.join(f"{(o['stages'][k] if o['stages'][k] is not None else float('nan')):6.2f}" for k in STAGE_KEYS)
        print(f"{s:12} {o['score']:.3f} [{o['ci95'][0]:.3f},{o['ci95'][1]:.3f}]  {st}  {o['habit_rate']:.2f}  "
              f"{o['board_raw_acc']:.2f}→{o['board_annotated_acc']:.2f}  unsup {o['unsupported']}  ece {o['ece10']:.3f}")
    print('\nfacet ' + ' | '.join(facets))
    for s in sorted(out, key=lambda k: -out[k]['score']):
        print(f"{s:12} " + ' | '.join(f"{out[s]['facets'][f]:.2f}" for f in facets))


if __name__ == '__main__':
    main()
