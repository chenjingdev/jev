"""판단 벤치마크 채점. 정답 파일(gold.json)은 여기서만 읽는다. PROTOCOL.md 지표 절.

- 문항마다 보기 순환 확률을 원래 보기 번호로 되돌려 평균하고, 최댓값을 답으로 한다.
- 보기 개수가 문항마다 달라 우연 수준이 다르다. 게임·단계별 정확도와 우연 보정 점수
  (acc - 1/n) / (1 - 1/n)의 평균을 보고한다. 게임을 합친 원시 정확도는 보고하지 않는다.
- ② 변형 문항은 gold에 original_answer(원래 규칙의 답)가 있다. 습관률 = 변형 문항에서
  원래 규칙의 답을 고른 비율.
- unsupported는 오답, 확률 지표에서는 균등분포.
"""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run import make_request, request_hash, shifts  # noqa: E402


def load(tag, system):
    by_id = defaultdict(list)
    for f in (HERE / 'results' / tag / system).glob('*.json'):
        r = json.loads(f.read_text())
        by_id[r['id']].append(r)
    return by_id


def distribution(item, records):
    n = len(item['options'])
    want = {s: request_hash(make_request(item, s)[1]) for s in shifts(n)}
    done = {r['rotation']: r for r in records
            if r['status'] in ('complete', 'unsupported') and want.get(r['rotation']) == r['request_sha256']}
    if any(r['status'] == 'unsupported' for r in done.values()):
        return {k: 1 / n for k in range(1, n + 1)}, 'unsupported'
    if set(want) - set(done):
        return None, 'incomplete'
    dists = [{int(k): v for k, v in done[s]['original_probabilities'].items()} for s in want]
    avg = {k: sum(d.get(k, 0.0) for d in dists) / len(dists) for k in range(1, n + 1)}
    total = sum(avg.values()) or 1.0
    return {k: p / total for k, p in avg.items()}, 'complete'


def ece(rows, bins=10):
    buckets = defaultdict(list)
    for conf, ok in rows:
        buckets[min(int(conf * bins), bins - 1)].append((conf, ok))
    n = len(rows)
    return sum(len(b) / n * abs(statistics.mean(c for c, _ in b) - statistics.mean(o for _, o in b))
               for b in buckets.values()) if n else None


def score_system(items, gold, tag, system):
    recs = load(tag, system)
    rows = []
    for it in items:
        dist, status = distribution(it, recs.get(it['id'], []))
        if status == 'incomplete':
            continue
        g = gold[it['id']]
        n = len(it['options'])
        pick = None if status == 'unsupported' else max(dist, key=dist.get)
        rows.append({'id': it['id'], 'game': it['game'], 'stage': it['stage'], 'n': n, 'status': status,
                     'correct': pick == g['answer'], 'habit': (pick == g['original_answer']) if 'original_answer' in g else None,
                     'conf': dist[pick] if pick else None,
                     'brier': sum((dist[k] - (k == g['answer'])) ** 2 for k in dist),
                     'logloss': -math.log(max(dist[g['answer']], 1e-6))})
    return rows


def summarize(rows):
    if not rows:
        return None
    norm = lambda r: (r['correct'] - 1 / r['n']) / (1 - 1 / r['n'])
    habit = [r['habit'] for r in rows if r['habit'] is not None]
    return {'items': len(rows), 'accuracy': statistics.mean(r['correct'] for r in rows),
            'chance': statistics.mean(1 / r['n'] for r in rows),
            'normalized': statistics.mean(norm(r) for r in rows),
            'habit_rate': statistics.mean(habit) if habit else None,
            'unsupported': sum(r['status'] == 'unsupported' for r in rows),
            'brier': statistics.mean(r['brier'] for r in rows), 'log_loss': statistics.mean(r['logloss'] for r in rows),
            'ece10': ece([(r['conf'], r['correct']) for r in rows if r['conf'] is not None])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--items', type=Path, required=True)
    ap.add_argument('--gold', type=Path, required=True)
    ap.add_argument('--tag', required=True)
    ap.add_argument('--systems', nargs='+', required=True)
    a = ap.parse_args()
    items = [json.loads(l) for l in a.items.read_text().splitlines() if l.strip()]
    gold = json.loads(a.gold.read_text())
    out = {'tag': a.tag, 'systems': {}}
    for s in a.systems:
        rows = score_system(items, gold, a.tag, s)
        by = defaultdict(list)
        for r in rows:
            by[(r['game'], r['stage'])].append(r)
        games = defaultdict(list)
        for r in rows:
            games[r['game']].append(r)
        out['systems'][s] = {'overall_mean_of_games_normalized':
                             statistics.mean(summarize(v)['normalized'] for v in games.values()) if games else None,
                             'by_game': {g: summarize(v) for g, v in games.items()},
                             'by_game_stage': {f'{g}|{st}': summarize(v) for (g, st), v in by.items()},
                             'rows': rows}
        o = out['systems'][s]
        print(f"{s:12} games {len(games)}  mean normalized {o['overall_mean_of_games_normalized']}")
    (HERE / 'results' / a.tag / 'scores.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
