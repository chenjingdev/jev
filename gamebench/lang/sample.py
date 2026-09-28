"""언어 시험 표본: v1에서 게임마다 6문항을 단계별로 고르게 뽑는다. lang/PROTOCOL.md 1절.

단계 ①②③④를 차례로 돌며 한 문항씩 뽑고, 단계 안에서는 sha256(seed:id) 순서를 쓴다. 결과를 보지 않고
정해지는 순서다. 정답 파일은 읽지 않는다.
"""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
V1 = HERE.parent / 'sets' / 'v1' / 'items.jsonl'


def sample(items, per_game=6, seed=20260928):
    by_game = defaultdict(lambda: defaultdict(list))
    for it in items:
        by_game[it['game']][it['stage'][0]].append(it)
    key = lambda it: hashlib.sha256(f'{seed}:{it["id"]}'.encode()).hexdigest()
    picked = []
    for game in sorted(by_game):
        queues = {s: sorted(v, key=key) for s, v in sorted(by_game[game].items())}
        take = []
        while len(take) < per_game and any(queues.values()):
            for s in sorted(queues):
                if queues[s] and len(take) < per_game:
                    take.append(queues[s].pop(0))
        picked += take
    order = {it['id']: n for n, it in enumerate(items)}
    return sorted(picked, key=lambda it: order[it['id']])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--per-game', type=int, default=6)
    ap.add_argument('--seed', type=int, default=20260928)
    a = ap.parse_args()
    items = [json.loads(l) for l in V1.read_text().splitlines() if l.strip()]
    picked = sample(items, a.per_game, a.seed)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(''.join(json.dumps(it, ensure_ascii=False) + '\n' for it in picked))
    print(len(picked), 'items ->', a.out)


if __name__ == '__main__':
    main()
