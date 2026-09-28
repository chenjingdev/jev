"""뺄셈 게임 (돌 한 무더기에서 1~k개씩 가져가기).

① 판정: 둘 다 최선을 다할 때 누가 이기는가.
③ 한 수: 반드시 이기려면 몇 개를 가져가야 하는가(이기는 개수가 하나뿐인 국면만).
② 변형: 한 번에 가져갈 수 있는 최대 개수가 다르거나(k±1), 마지막 돌을 가져가는 사람이 지는 규칙.
   같은 상황·보기에서 답이 달라지는 경우만.
"""
from functools import lru_cache

from .common import make_item

GAME = 'subtraction'
NAME = '뺄셈 게임'
FACET = '필승 전략'

PLAYERS = ('민수', '지우')


def rules_text(rule):
    k, misere = rule
    return (f'돌 한 무더기가 있다. 두 사람이 번갈아 돌을 1개에서 {k}개까지 가져간다. 남은 돌보다 많이 가져갈 수는 없다. '
            f'마지막 돌을 가져가는 사람이 {"진다" if misere else "이긴다"}.')


@lru_cache(maxsize=None)
def mover_wins(n, rule):
    if n == 0:
        return rule[1]  # 앞사람이 마지막 돌을 가져갔다
    return any(not mover_wins(n - c, rule) for c in range(1, min(rule[0], n) + 1))


def winning_counts(n, rule, upto):
    return [c for c in range(1, upto + 1) if c <= rule[0] and c <= n and not mover_wins(n - c, rule)]


def twin_rules(k):
    return [(k + 1, False), (k, True)] + ([(k - 1, False)] if k > 2 else [])


def generate(rng, per_stage):
    items = []
    t = 0
    # ① 판정
    q1 = '둘 다 최선을 다하면 누가 이기는가?'
    pool = {True: [], False: []}
    for k in range(2, 6):
        for n in range(5, 31):
            pool[mover_wins(n, (k, False))].append((k, n))
    for g in pool.values():
        rng.shuffle(g)
    for i in range(per_stage):
        k, n = pool[i % 2 == 0][i // 2]
        me = PLAYERS[(i // 2) % 2]
        other = PLAYERS[1 - PLAYERS.index(me)]
        sit = f'돌이 {n}개 남았다. 지금 {me} 차례다.'
        ans = lambda rule: me if mover_wins(n, rule) else other
        base = make_item(rng, GAME, '1-판정', i, {'규칙': rules_text((k, False)), '상황': sit}, q1, list(PLAYERS),
                         ans((k, False)))
        items.append(base)
        diff = [r for r in twin_rules(k) if ans(r) != ans((k, False))]
        if diff:
            r = diff[i % len(diff)]
            items.append(make_item(rng, GAME, '2-변형', t, {'규칙': rules_text(r), '상황': sit}, q1, list(PLAYERS),
                                   ans(r), original=ans((k, False)), twin_of=base['id'], order=base['options']))
            t += 1
    # ③ 한 수: 보기는 1개~K개 (K = 짝 규칙까지 포함한 최대 개수)
    q3 = '내 차례다. 상대가 어떻게 하든 내가 반드시 이기려면 이번에 돌을 몇 개 가져가야 하는가?'
    cases = []
    for k in range(2, 6):
        for n in range(8, 31):
            base_rule = (k, False)
            w = winning_counts(n, base_rule, k)
            if len(w) != 1:
                continue
            twins = []
            for r in twin_rules(k):
                upto = max(k, r[0])
                tw = winning_counts(n, r, upto)
                if len(tw) == 1 and tw[0] != w[0]:
                    twins.append((r, tw[0]))
            if twins:
                cases.append((k, n, w[0], twins))
    rng.shuffle(cases)
    for i, (k, n, c, twins) in enumerate(cases[:per_stage]):
        r, tc = twins[i % len(twins)]
        upto = max(k, r[0])
        opts = [f'{j}개' for j in range(1, upto + 1)]
        sit = f'돌이 {n}개 남았다.'
        base = make_item(rng, GAME, '3-한수', i, {'규칙': rules_text((k, False)), '상황': sit}, q3, opts, f'{c}개')
        items.append(base)
        items.append(make_item(rng, GAME, '2-변형', 100 + i, {'규칙': rules_text(r), '상황': sit}, q3, opts,
                               f'{tc}개', original=f'{c}개', twin_of=base['id'], order=base['options']))
    return items
