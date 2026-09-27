"""님.

① 판정: 둘 다 최선을 다할 때 누가 이기는가.
③ 한 수: 반드시 이기는 수가 전체에서 하나뿐인 국면. 보기는 그 수와 다른 합법 수(최대 16개).
② 변형: "마지막 돌을 가져가는 사람이 진다"(미제르). 같은 국면에서 답이 달라지는 경우만.
"""
from functools import lru_cache
from itertools import combinations_with_replacement

from .common import make_item

GAME = 'nim'
NAME = '님'
FACET = '필승 전략'

PLAYERS = ('민수', '지우')


def rules_text(misere):
    return ('돌 무더기 여러 개가 있다. 두 사람이 번갈아 무더기 하나를 골라 그 무더기에서 돌을 1개 이상 원하는 만큼 '
            '가져간다. 여러 무더기에서 한꺼번에 가져갈 수는 없다. 마지막 돌을 가져가는 사람이 '
            + ('진다.' if misere else '이긴다.'))


@lru_cache(maxsize=None)
def mover_wins(piles, misere):
    """piles(정렬된 튜플)에서 가져갈 차례인 사람이 반드시 이길 수 있는가."""
    if sum(piles) == 0:
        return misere  # 앞사람이 마지막 돌을 가져갔다
    return any(not mover_wins(after(piles, i, t), misere) for i, t in moves(piles))


def after(piles, i, t):
    return tuple(sorted(piles[:i] + (piles[i] - t,) + piles[i + 1:]))


def moves(piles):
    return [(i, t) for i, p in enumerate(piles) for t in range(1, p + 1)]


def winning_moves(piles, misere):
    return [(i, t) for i, t in moves(piles) if not mover_wins(after(piles, i, t), misere)]


def label(move):
    return f'{move[0] + 1}번 무더기에서 {move[1]}개'


def describe(piles):
    return ', '.join(f'{i + 1}번 무더기 {p}개' for i, p in enumerate(piles))


def all_positions(kmin, kmax, pmax):
    return [c for k in range(kmin, kmax + 1) for c in combinations_with_replacement(range(1, pmax + 1), k)]


def generate(rng, per_stage):
    items = []
    k = 0
    # ① 판정: 누가 이기는가. 지금 차례인 사람이 이기는 국면과 지는 국면을 번갈아, 짝(미제르)은 결과가 바뀌는 국면
    q1 = '둘 다 최선을 다하면 누가 이기는가?'
    ones = [(1, 1), (1, 1, 1), (1, 1, 1, 1)]  # 미제르에서 결과가 바뀌는 국면은 모두 1개짜리 무더기뿐이다
    rest = {True: [], False: []}
    for p in all_positions(2, 3, 5):
        if max(p) > 1:
            rest[mover_wins(p, False)].append(p)
    for g in rest.values():
        rng.shuffle(g)
    chosen = ones[:per_stage] + [rest[j % 2 == 0][j // 2] for j in range(max(0, per_stage - len(ones)))]
    for i, p in enumerate(chosen):
        p = list(p)
        rng.shuffle(p)
        p = tuple(p)
        me = PLAYERS[i % 2]
        sit = f'{describe(p)}가 남았다. 지금 {me} 차례다.'
        ans = lambda misere: me if mover_wins(tuple(sorted(p)), misere) else PLAYERS[1 - PLAYERS.index(me)]
        base = make_item(rng, GAME, '1-판정', i, {'규칙': rules_text(False), '상황': sit}, q1, list(PLAYERS), ans(False))
        items.append(base)
        if ans(True) != ans(False):
            items.append(make_item(rng, GAME, '2-변형', k, {'규칙': rules_text(True), '상황': sit}, q1, list(PLAYERS),
                                   ans(True), original=ans(False), twin_of=base['id'], order=base['options']))
            k += 1
    # ③ 한 수: 이기는 수가 하나뿐인 국면
    q3 = '내 차례다. 상대가 어떻게 하든 내가 반드시 이기려면 어떻게 가져가야 하는가?'
    twins, plain = [], []
    for p in all_positions(2, 4, 7):
        if sum(p) < 3:
            continue
        w = winning_moves(p, False)
        if len(w) != 1:
            continue
        m = winning_moves(p, True)
        (twins if len(m) == 1 and m[0] != w[0] else plain).append(p)
    rng.shuffle(twins); rng.shuffle(plain)
    chosen = twins[:per_stage // 2] + plain[:per_stage - min(len(twins), per_stage // 2)]
    for i, p in enumerate(chosen):
        perm = list(p)
        rng.shuffle(perm)
        perm = tuple(perm)
        w = winning_moves(perm, False)[0]
        m = winning_moves(perm, True)
        tw = m[0] if len(m) == 1 and m[0] != w else None
        must = [w] + ([tw] if tw else [])
        rest = [mv for mv in moves(perm) if mv not in must]
        opts = must + rng.sample(rest, min(len(rest), 16 - len(must)))
        opts = [label(mv) for mv in opts]
        sit = f'{describe(perm)}가 남았다.'
        base = make_item(rng, GAME, '3-한수', i, {'규칙': rules_text(False), '상황': sit}, q3, opts, label(w))
        items.append(base)
        if tw:
            items.append(make_item(rng, GAME, '2-변형', k, {'규칙': rules_text(True), '상황': sit}, q3, opts,
                                   label(tw), original=label(w), twin_of=base['id'], order=base['options']))
            k += 1
    return items
