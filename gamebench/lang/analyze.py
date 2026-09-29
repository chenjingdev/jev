"""언어 시험 분석. lang/PROTOCOL.md 4절.

한국어는 v1 호출 기록, 영어는 lang-en, Jev 재실행은 lang-ko-rerun 태그를 읽는다. 문항 id가 같으므로
정답은 v1 gold.json을 그대로 쓴다. 결과는 results.json과 표준 출력의 마크다운 표로 낸다.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import random
import statistics
import sys

HERE = Path(__file__).resolve().parent
GB = HERE.parent
sys.path.insert(0, str(GB))
from report import mcnemar_p  # noqa: E402
from run import make_request, request_hash, shifts  # noqa: E402
from score import load, score_system, summarize  # noqa: E402

SYSTEMS = ['jev-1.13.0', 'kev', 'semif', 'open-jev', 'jevmlx', 'laya', 'clm', 'julia']
REF = 'jev-1.13.0'


def items_of(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def game_scores(rows):
    games = defaultdict(list)
    for r in rows:
        games[r['game']].append(r)
    return {g: summarize(v)['normalized'] for g, v in games.items()}


def mean_over(games, scores):
    return statistics.mean(scores[g] for g in games)


def same_pick_share(items, tag, system):
    """모든 보기 순서에서 같은 원래 보기를 고른 문항의 비율(처리 못 한 문항은 뺀다)."""
    recs = load(tag, system)
    same = total = 0
    for it in items:
        want = {s: request_hash(make_request(it, s)[1]) for s in shifts(len(it['options']))}
        picks = {}
        for r in recs.get(it['id'], []):
            if r['status'] == 'complete' and want.get(r['rotation']) == r['request_sha256']:
                op = r['original_probabilities']
                picks[r['rotation']] = max(op, key=op.get)
        if len(picks) == len(want):
            total += 1
            same += len(set(picks.values())) == 1
    return same / total if total else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--systems', nargs='+', default=SYSTEMS)
    ap.add_argument('--boot', type=int, default=10000)
    a = ap.parse_args()
    ko = items_of(HERE / 'set' / 'ko.jsonl')
    en = items_of(HERE / 'set' / 'en.jsonl')
    assert [x['id'] for x in ko] == [x['id'] for x in en]
    gold = json.loads((GB / 'sets' / 'v1' / 'gold.json').read_text())

    runs = {}
    for s in a.systems:
        runs[(s, 'ko')] = score_system(ko, gold, 'v1', s)
        runs[(s, 'en')] = score_system(en, gold, 'lang-en', s)
    runs[(REF, 'ko-rerun')] = score_system(ko, gold, 'lang-ko-rerun', REF)
    for key, rows in runs.items():
        assert len(rows) == len(ko), (key, len(rows), len(ko))

    gscore = {k: game_scores(v) for k, v in runs.items()}
    games = sorted(gscore[(a.systems[0], 'ko')])
    rng = random.Random(20260928)
    boots = [[rng.choice(games) for _ in games] for _ in range(a.boot)]

    def interval(fn):
        vals = sorted(fn(b) for b in boots)
        return [vals[int(.025 * a.boot)], vals[int(.975 * a.boot) - 1]]

    def delta(s, lang='en', base='ko'):
        return lambda gs: mean_over(gs, gscore[(s, lang)]) - mean_over(gs, gscore[(s, base)])

    out = {}
    for s in a.systems:
        o = {}
        for lang in ('ko', 'en'):
            t = summarize(runs[(s, lang)])
            o[lang] = {'score': mean_over(games, gscore[(s, lang)]), 'accuracy': t['accuracy'],
                       'unsupported': t['unsupported'], 'ece10': t['ece10'], 'brier': t['brier'],
                       'same_pick': same_pick_share(ko if lang == 'ko' else en, 'v1' if lang == 'ko' else 'lang-en', s)}
        o['delta'] = o['en']['score'] - o['ko']['score']
        o['delta_ci95'] = interval(delta(s))
        dref = delta(REF)
        o['delta_minus_jev'] = o['delta'] - (mean_over(games, gscore[(REF, 'en')]) - mean_over(games, gscore[(REF, 'ko')]))
        o['delta_minus_jev_ci95'] = interval(lambda gs, d=delta(s): d(gs) - dref(gs))
        ko_ok = {r['id']: r['correct'] for r in runs[(s, 'ko')]}
        en_ok = {r['id']: r['correct'] for r in runs[(s, 'en')]}
        b = sum(en_ok[i] and not ko_ok[i] for i in ko_ok)
        c = sum(ko_ok[i] and not en_ok[i] for i in ko_ok)
        o['mcnemar'] = {'en_only': b, 'ko_only': c, 'p': mcnemar_p(b, c)}
        o['games'] = {g: {'ko': gscore[(s, 'ko')][g], 'en': gscore[(s, 'en')][g]} for g in games}
        out[s] = o
    rerun = mean_over(games, gscore[(REF, 'ko-rerun')])
    out['jev_ko_rerun'] = {'score': rerun, 'delta_vs_v1': rerun - out[REF]['ko']['score'],
                           'delta_ci95': interval(delta(REF, 'ko-rerun', 'ko'))}
    (HERE / 'results.json').write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n')

    f = lambda x: f'{x:+.3f}'.replace('-', '−')
    print('| 시스템 | 한국어 | 영어 | Δ (영어 − 한국어) | 95% 구간 | Δ − Jev의 Δ | 95% 구간 | 영어만 맞힘 / 한국어만 맞힘 | McNemar p |')
    print('|---|---:|---:|---:|---|---:|---|---:|---:|')
    for s in a.systems:
        o = out[s]
        print(f"| {s} | {o['ko']['score']:.3f} | {o['en']['score']:.3f} | {f(o['delta'])} | "
              f"{f(o['delta_ci95'][0])} ~ {f(o['delta_ci95'][1])} | {f(o['delta_minus_jev'])} | "
              f"{f(o['delta_minus_jev_ci95'][0])} ~ {f(o['delta_minus_jev_ci95'][1])} | "
              f"{o['mcnemar']['en_only']} / {o['mcnemar']['ko_only']} | {o['mcnemar']['p']:.2g} |")
    r = out['jev_ko_rerun']
    print(f"\nJev 한국어 재실행: {r['score']:.3f} (v1 대비 {f(r['delta_vs_v1'])}, 95% {f(r['delta_ci95'][0])} ~ {f(r['delta_ci95'][1])})")
    print('\n| 시스템 | 처리 못 함 (한/영) | ECE (한/영) | 순서 바꿔도 같은 답 (한/영) |')
    print('|---|---:|---:|---:|')
    for s in a.systems:
        o = out[s]
        sp = lambda v: '–' if v is None else f'{v:.1%}'
        print(f"| {s} | {o['ko']['unsupported']} / {o['en']['unsupported']} | {o['ko']['ece10']:.3f} / {o['en']['ece10']:.3f} | "
              f"{sp(o['ko']['same_pick'])} / {sp(o['en']['same_pick'])} |")


if __name__ == '__main__':
    main()
