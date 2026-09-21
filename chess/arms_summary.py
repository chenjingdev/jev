"""Compare selector arms (Jev vs seeded random) on two base engines using referee files.

Robust statistics: referee cp clipped to ±1000 so forced-mate scores (±10000) do
not dominate means; medians and a two-sided sign test on changed decisions; a
two-proportion z-test for "pick is referee-best" between Jev and random arms.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import random
import statistics

HERE = Path(__file__).resolve().parent
MATCHES = HERE / 'matches'
CLIP = 1000
ARMS = {
    'stockfish': {'jev': 'jev-ten-01', 'random': 'random-ten-01'},
    'weak2': {'jev': 'weak-jev-01', 'random': 'weak-random-01'},
    'weak1': {'jev': 'weak1-jev-01', 'random': 'weak1-random-01'},
    'weak4': {'jev': 'weak4-jev-01', 'random': 'weak4-random-01'},
    'd2_vs_d4_100': {'jev': 'd2jev-vs-d4-100', 'random': 'd2rand-vs-d4-100'},
    'd2_vs_d2_100': {'jev': 'd2jev-vs-d2-100', 'random': 'd2rand-vs-d2-100'},
}


def clip(x):
    return max(-CLIP, min(CLIP, x))


def sign_test(pos, neg):
    n = pos + neg
    if n == 0:
        return 1.0
    k = min(pos, neg)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def two_proportion_z(p1, n1, p2, n2):
    p = (p1 * n1 + p2 * n2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0.0, 1.0
    z = (p1 - p2) / se
    pval = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return round(z, 3), round(pval, 4)


def per_game_means(rows):
    games = {}
    for r in rows:
        games.setdefault(r['game'], []).append(clip(r['grade']['pick_minus_base']))
    return {g: statistics.mean(v) for g, v in sorted(games.items())}


def bootstrap_diff(a, b, n=5000, seed=1):
    """95% percentile CI of mean(a) - mean(b), resampling the given units (decisions or games)."""
    rng = random.Random(seed)
    diffs = sorted(statistics.mean(rng.choices(a, k=len(a))) - statistics.mean(rng.choices(b, k=len(b))) for _ in range(n))
    return [round(diffs[int(n * .025)], 1), round(diffs[int(n * .975) - 1], 1)]


def arm_stats(referee_path, match_path):
    ref = json.loads(referee_path.read_text())
    match = json.loads(match_path.read_text())
    rows = ref['decisions']
    deltas = [clip(r['grade']['pick_minus_base']) for r in rows]
    changed = [r for r in rows if r['pick'] != r['base']]
    cdeltas = [clip(r['grade']['pick_minus_base']) for r in changed]
    pos = sum(d > 0 for d in cdeltas)
    neg = sum(d < 0 for d in cdeltas)
    points = match['summary']['points']
    hybrid = match.get('engine_a', {}).get('name') or next(k for k in points if '+' in k)
    opponent = match.get('engine_b', {}).get('name') or next(k for k in points if '+' not in k)
    return {
        'match': match_path.name, 'hybrid': hybrid,
        'score': f"{points[hybrid]}-{points[opponent]}",
        'wins': match['analysis']['wins'], 'draws': match['analysis']['draws'], 'losses': match['analysis']['losses'],
        'decisions': len(rows), 'changed': len(changed),
        'chance_pick_is_best': ref['summary']['chance_pick_is_best'],
        'pick_is_best_rate': ref['summary']['pick_is_best_rate'],
        'base_is_best_rate': ref['summary']['base_is_best_rate'],
        'mean_pick_minus_base_clipped_cp': round(statistics.mean(deltas), 2),
        'median_pick_minus_base_all_cp': statistics.median(deltas),
        'changed_improved': pos, 'changed_worse': neg, 'changed_equal': len(cdeltas) - pos - neg,
        'changed_mean_clipped_cp': round(statistics.mean(cdeltas), 2) if cdeltas else None,
        'changed_median_cp': statistics.median(cdeltas) if cdeltas else None,
        'changed_sign_test_p': round(sign_test(pos, neg), 4),
        'swings_ge_200_up': sum(d >= 200 for d in deltas), 'swings_le_200_down': sum(d <= -200 for d in deltas),
        'per_game_mean_cp': {str(g): round(v, 1) for g, v in per_game_means(rows).items()},
        '_deltas': deltas, '_game_means': list(per_game_means(rows).values()),
        'tokens': match['summary']['tokens'], 'jev_mean_ms': match['summary']['jev_mean_ms'],
    }


def main():
    out = {'referee_nodes': None, 'clip_cp': CLIP, 'bases': {}}
    for base, arms in ARMS.items():
        if not all((MATCHES / f'{n}.referee-200000.json').exists() for n in arms.values()):
            continue
        stats = {}
        for selector, name in arms.items():
            ref_path = MATCHES / f'{name}.referee-200000.json'
            stats[selector] = arm_stats(ref_path, MATCHES / f'{name}.json')
            out['referee_nodes'] = json.loads(ref_path.read_text())['referee']['nodes']
        j, r = stats['jev'], stats['random']
        z, p = two_proportion_z(j['pick_is_best_rate'], j['decisions'], r['pick_is_best_rate'], r['decisions'])
        stats['jev_vs_random_pick_is_best'] = {'z': z, 'two_sided_p': p,
                                               'note': 'Treats decisions as independent; they cluster within 10 games, so p is optimistic.'}
        stats['jev_minus_random_mean_cp'] = {
            'point': round(statistics.mean(j['_deltas']) - statistics.mean(r['_deltas']), 1),
            'ci95_decision_bootstrap': bootstrap_diff(j['_deltas'], r['_deltas']),
            'ci95_game_bootstrap': bootstrap_diff(j['_game_means'], r['_game_means']),
            'game_means_jev': [round(x, 1) for x in j['_game_means']],
            'game_means_random': [round(x, 1) for x in r['_game_means']],
            'note': 'Game-level bootstrap (10 vs 10 game means) respects clustering and is the honest interval.'}
        for arm in (j, r):
            arm.pop('_deltas'); arm.pop('_game_means')
        out['bases'][base] = stats
    out['interpretation'] = (
        'Ten games per arm cannot rank arms by score. Per-decision referee agreement is the primary measure; '
        'the referee is a deeper Stockfish, i.e. the same evaluator family as the Stockfish base, so on that base '
        'the base #1 is structurally favoured. On the weak base the referee is independent of the players.')
    path = MATCHES / 'arms-summary-01.json'
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
