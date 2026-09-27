"""배스킨라빈스 31.

① 판정: 이번에 말한 숫자들이 규칙에 맞는가 / 기록을 보고 진 사람은 누구인가.
③ 한 수: 지금까지 N까지 말했을 때, 반드시 이기려면 이번에 몇 개를 말해야 하는가(이기는 개수가 하나뿐인 국면만).
② 변형: 판정(말한 개수)의 짝은 "한 번에 1~4개", 진 사람의 짝은 "31을 말하는 사람이 이긴다",
   한 수의 짝은 둘 중 답이 달라지는 규칙.
"""
from functools import lru_cache

from .common import make_item

GAME = 'br31'
NAME = '배스킨라빈스 31'
FACET = '필승 전략'

TARGET = 31
BASE = (3, True)       # (한 번에 최대 개수, 31을 말하면 지는가)
MAX4 = (4, True)
WIN31 = (3, False)
PLAYERS = ('민수', '지우')


def rules_text(rule):
    k, lose = rule
    return (f'두 사람이 번갈아 1부터 차례대로 숫자를 이어서 말한다. 자기 차례에는 앞사람이 말한 다음 숫자부터 '
            f'연속된 숫자를 1개에서 {k}개까지 말해야 한다. {TARGET}보다 큰 수는 말하지 않는다. '
            f'{TARGET}을 말하는 사람이 {"진다" if lose else "이기고"}' + ('' if lose else ' 게임이 끝난다') + '.')


@lru_cache(maxsize=None)
def mover_wins(n, rule):
    """n까지 말한 상태에서 말할 차례인 사람이 반드시 이길 수 있는가."""
    return any(count_wins(n, c, rule) for c in range(1, rule[0] + 1) if n + c <= TARGET)


def count_wins(n, c, rule):
    """n까지 말한 상태에서 c개를 말하면 반드시 이기는가 (규칙상 말할 수 없는 개수면 False)."""
    k, lose = rule
    if not 1 <= c <= k or n + c > TARGET:
        return False
    if n + c == TARGET:
        return not lose
    return not mover_wins(n + c, rule)


def winning_counts(n, rule):
    return [c for c in range(1, 5) if count_wins(n, c, rule)]


def legal(n, said, rule):
    return (1 <= len(said) <= rule[0] and said == list(range(n + 1, n + 1 + len(said))) and said[-1] <= TARGET)


def loser(turns, rule):
    """turns: [(사람, [숫자들])]. 31을 말한 사람이 나오면 진 사람, 아니면 None."""
    for who, nums in turns:
        if TARGET in nums:
            other = PLAYERS[1 - PLAYERS.index(who)]
            return who if rule[1] else other
    return None


def fmt(nums):
    return ', '.join(map(str, nums))


def generate(rng, per_stage):
    items = []
    k = 0  # ② 변형 번호
    # ① 판정 (a) 말한 숫자가 규칙에 맞는가: 짝(1~4개)은 4개를 말한 경우만
    kinds = ['ok', 'four', 'skip', 'four', 'ok', 'five', 'repeat', 'four', 'ok', 'four']
    ns = list(range(3, 25))
    rng.shuffle(ns)
    q_legal = '이번 사람이 말한 것은 규칙에 맞는가?'
    opts_legal = ['규칙에 맞다', '규칙에 어긋난다']
    n_legal = (per_stage + 1) // 2
    for i in range(n_legal):
        n, kind = ns[i], kinds[i % len(kinds)]
        said = {'ok': list(range(n + 1, n + 1 + 1 + i % 3)), 'four': list(range(n + 1, n + 5)),
                'five': list(range(n + 1, n + 6)), 'skip': [n + 1, n + 3], 'repeat': [n, n + 1, n + 2]}[kind]
        sit = f'지금까지 1부터 {n}까지 말했다. 이번 차례인 사람이 "{fmt(said)}"라고 말했다.'
        verdict = lambda r: opts_legal[0] if legal(n, said, r) else opts_legal[1]
        base = make_item(rng, GAME, '1-판정', i, {'규칙': rules_text(BASE), '상황': sit}, q_legal, opts_legal,
                         verdict(BASE))
        items.append(base)
        if verdict(MAX4) != verdict(BASE):
            items.append(make_item(rng, GAME, '2-변형', k, {'규칙': rules_text(MAX4), '상황': sit}, q_legal,
                                   opts_legal, verdict(MAX4), original=verdict(BASE), twin_of=base['id'],
                                   order=base['options']))
            k += 1
    # ① 판정 (b) 기록을 보고 진 사람: 짝(31을 말하면 이긴다)은 31까지 간 기록만
    q_lose = '기록을 보고 판단하면, 진 사람은?'
    opts_lose = [PLAYERS[0], PLAYERS[1], '아직 아무도 지지 않았다']
    for j in range(per_stage - n_legal):
        i = n_legal + j
        finished = j % 3 != 2
        end = TARGET if finished else rng.randint(24, 30)
        turns, cur, who = [], 0, rng.randrange(2)
        while cur < end:
            c = min(rng.randint(1, 3), end - cur)
            turns.append((PLAYERS[who], list(range(cur + 1, cur + c + 1))))
            cur += c
            who = 1 - who
        sit = f'{turns[0][0]}가 먼저 시작했다. 기록: ' + ' / '.join(f'{w}: {fmt(nums)}' for w, nums in turns)
        ans = lambda r: loser(turns, r) or opts_lose[2]
        base = make_item(rng, GAME, '1-판정', i, {'규칙': rules_text(BASE), '상황': sit}, q_lose, opts_lose, ans(BASE))
        items.append(base)
        if ans(WIN31) != ans(BASE):
            items.append(make_item(rng, GAME, '2-변형', k, {'규칙': rules_text(WIN31), '상황': sit}, q_lose,
                                   opts_lose, ans(WIN31), original=ans(BASE), twin_of=base['id'],
                                   order=base['options']))
            k += 1
    # ③ 한 수: 이기는 개수가 하나뿐인 국면. 짝은 다른 규칙에서도 하나뿐이고 답이 다른 국면.
    q3 = '내 차례다. 상대가 어떻게 하든 내가 반드시 이기려면 이번에 숫자를 몇 개 말해야 하는가?'
    opts3 = [f'{c}개' for c in range(1, 5)]
    pool = []
    for n in range(0, TARGET - 1):
        w = winning_counts(n, BASE)
        if len(w) != 1:
            continue
        twins = []
        for rule in (MAX4, WIN31):
            tw = winning_counts(n, rule)
            if len(tw) == 1 and tw[0] != w[0]:
                twins.append((rule, tw[0]))
        pool.append((n, w[0], twins))
    rng.shuffle(pool)
    for i, (n, c, twins) in enumerate(pool[:per_stage]):
        sit = f'지금까지 1부터 {n}까지 말했다.' if n else '아직 아무도 숫자를 말하지 않았다. 내가 먼저 시작한다.'
        base = make_item(rng, GAME, '3-한수', i, {'규칙': rules_text(BASE), '상황': sit}, q3, opts3, f'{c}개')
        items.append(base)
        if twins:
            rule, tc = twins[i % len(twins)]
            items.append(make_item(rng, GAME, '2-변형', k, {'규칙': rules_text(rule), '상황': sit}, q3, opts3,
                                   f'{tc}개', original=f'{c}개', twin_of=base['id'], order=base['options']))
            k += 1
    return items
