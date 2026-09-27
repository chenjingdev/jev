"""몬티홀.

문 3~5개, 사회자가 참가자가 고르지 않은 문 k개를 연다. 사회자의 행동 방식은 규칙에 정확히 적는다.
확률은 사회자 행동에 대한 베이즈 계산으로 정확히(Fraction) 구한다.
① 판정: 지금 문 X 뒤에 자동차가 있을 확률.
③ 한 수: 그대로 둘까, 어느 문으로 바꿀까, 아니면 모두 같은가. 가장 높은 선택이 다음 선택보다
   MARGIN 이상 높거나, 닫힌 문의 확률이 모두 같은 경우만 쓴다.
② 변형: 같은 상황에서 사회자 행동 방식만 다르다(알고 여는 사회자 ↔ 모르고 여는 사회자 등). 답이 달라지는 경우만.
"""
from fractions import Fraction
from itertools import combinations
from math import comb

from .common import make_item

GAME = 'montyhall'
NAME = '몬티홀'
FACET = '확률·기댓값'

MARGIN = Fraction(1, 10)
HOSTS = ('know', 'blind', 'low', 'high', 'carpick')
SAME = '어느 문을 골라도 자동차가 있을 확률이 같다'


def rules_text(n, k, host):
    kk = f'{k}개'
    head = (f'문이 {n}개(1~{n}번) 있고, 그중 한 문 뒤에만 자동차가 있다. 자동차는 처음에 모든 문 뒤에 같은 확률로 놓인다. '
            f'참가자가 문 하나를 고르면 사회자가 참가자가 고르지 않은 문 {kk}를 연다. ')
    body = {
        'know': f'사회자는 자동차가 어느 문 뒤에 있는지 안다. 참가자가 고르지 않은 빈 문 가운데 {kk}를 무작위로'
                '(가능한 조합이 모두 같은 확률로) 골라 연다. ',
        'blind': f'사회자는 자동차가 어느 문 뒤에 있는지 모른다. 참가자가 고르지 않은 문 가운데 {kk}를 무작위로'
                 '(가능한 조합이 모두 같은 확률로) 골라 연다. 연 문 뒤에서 자동차가 나오면 그 판은 없던 것으로 하고 처음부터 다시 한다. ',
        'low': f'사회자는 자동차가 어느 문 뒤에 있는지 안다. 참가자가 고르지 않은 빈 문 가운데 번호가 가장 작은 문부터 차례로 {kk}를 연다. ',
        'high': f'사회자는 자동차가 어느 문 뒤에 있는지 안다. 참가자가 고르지 않은 빈 문 가운데 번호가 가장 큰 문부터 차례로 {kk}를 연다. ',
        'carpick': f'사회자는 자동차가 어느 문 뒤에 있는지 안다. 참가자가 처음에 자동차가 있는 문을 골랐을 때만, 고르지 않은 문 가운데 '
                   f'{kk}를 무작위로(가능한 조합이 모두 같은 확률로) 골라 열어 준다. 참가자가 빈 문을 골랐으면 사회자는 문을 하나도 열지 않고 '
                   '곧바로 참가자가 고른 문을 열어 게임을 끝낸다. ',
    }[host]
    tail = '문이 열린 뒤 참가자는 처음 고른 문을 그대로 두거나 아직 닫힌 다른 문 하나로 바꿀 수 있고, 마지막에 고른 문 뒤의 것을 받는다.'
    return head + body + tail


def likelihood(n, k, p, opened, car, host):
    """자동차가 car 뒤에 있을 때 사회자가 opened를 열 확률."""
    unchosen = [d for d in range(1, n + 1) if d != p]
    empty = [d for d in unchosen if d != car]
    if host == 'know':
        return Fraction(1, comb(len(empty), k)) if set(opened) <= set(empty) else Fraction(0)
    if host == 'blind':
        return Fraction(1, comb(n - 1, k)) if car not in opened else Fraction(0)
    if host == 'low':
        return Fraction(1) if tuple(sorted(empty)[:k]) == tuple(opened) else Fraction(0)
    if host == 'high':
        return Fraction(1) if tuple(sorted(empty)[-k:]) == tuple(opened) else Fraction(0)
    if host == 'carpick':
        return Fraction(1, comb(n - 1, k)) if car == p else Fraction(0)
    raise ValueError(host)


def posterior(n, k, p, opened, host):
    """닫힌 문별 자동차 확률. 이 사회자 방식으로 opened가 나올 수 없으면 None."""
    w = {d: Fraction(1, n) * likelihood(n, k, p, opened, d, host) for d in range(1, n + 1)}
    tot = sum(w.values())
    if tot == 0:
        return None
    return {d: v / tot for d, v in w.items() if d not in opened}


def options3(n, p, opened):
    closed = [d for d in range(1, n + 1) if d not in opened]
    return ([f'처음 고른 {p}번 문을 그대로 둔다'] + [f'{d}번 문으로 바꾼다' for d in closed if d != p] + [SAME])


def best_choice(n, k, p, opened, host):
    post = posterior(n, k, p, opened, host)
    if post is None:
        return None
    opts = options3(n, p, opened)
    if len(set(post.values())) == 1:
        return SAME
    ranked = sorted(post.items(), key=lambda kv: -kv[1])
    if ranked[0][1] - ranked[1][1] < MARGIN:
        return None
    d = ranked[0][0]
    return opts[0] if d == p else f'{d}번 문으로 바꾼다'


def fmt(fr):
    return f'{fr.numerator}/{fr.denominator}' if fr.denominator != 1 else str(fr.numerator)


def situation(n, p, opened):
    closed = [d for d in range(1, n + 1) if d not in opened]
    return (f'참가자가 {p}번 문을 골랐다. 사회자가 {", ".join(map(str, opened))}번 문을 열었고, 연 문 뒤는 모두 비어 있었다. '
            f'아직 닫힌 문은 {", ".join(map(str, closed))}번이다.')


def scenarios():
    for n in (3, 4, 5):
        for k in range(1, n - 1):
            for p in range(1, n + 1):
                for opened in combinations([d for d in range(1, n + 1) if d != p], k):
                    yield n, k, p, opened


def generate(rng, per_stage):
    items = []
    scen = list(scenarios())
    # ① 판정 + ② 변형 짝: 닫힌 문 하나의 확률
    q_pool = []
    for n, k, p, opened in scen:
        for host in HOSTS:
            post = posterior(n, k, p, opened, host)
            if post is None:
                continue
            for d in sorted(post):
                twins = [h for h in HOSTS if h != host and (pt := posterior(n, k, p, opened, h)) and pt[d] != post[d]]
                q_pool.append((n, k, p, opened, host, d, twins))
    rng.shuffle(q_pool)
    chosen, used = [], set()
    for u in q_pool:  # 사회자 방식이 골고루 나오게, 같은 상황은 한 번만
        key = u[:4]
        if key in used or sum(c[4] == u[4] for c in chosen) >= (per_stage + len(HOSTS) - 1) // len(HOSTS) + 1:
            continue
        if len(chosen) < per_stage * 2 // 3 and not u[6]:
            continue
        used.add(key)
        chosen.append(u)
        if len(chosen) == per_stage:
            break
    assert len(chosen) == per_stage
    k2 = 0
    for i, (n, k, p, opened, host, d, twins) in enumerate(chosen):
        post = posterior(n, k, p, opened, host)
        twin = rng.choice(twins) if twins else None
        tv = posterior(n, k, p, opened, twin)[d] if twin else None
        vals = [post[d]] + ([tv] if twin else [])
        cands = {Fraction(1, n), Fraction(1, n - k), Fraction(n - 1, n), Fraction(1, 2), Fraction(0), Fraction(1)}
        for h in HOSTS:
            ph = posterior(n, k, p, opened, h)
            if ph:
                cands |= set(ph.values())
        cands = sorted(cands - set(vals))
        rng.shuffle(cands)
        opts = [fmt(v) for v in vals + cands[:5 - len(vals)]]
        state = {'규칙': rules_text(n, k, host), '상황': situation(n, p, opened)}
        q = f'지금 {d}번 문 뒤에 자동차가 있을 확률은?'
        base = make_item(rng, GAME, '1-판정', i, state, q, opts, fmt(post[d]))
        items.append(base)
        if twin:
            items.append(make_item(rng, GAME, '2-변형', k2, dict(state, 규칙=rules_text(n, k, twin)), q, opts,
                                   fmt(tv), original=fmt(post[d]), twin_of=base['id'], order=base['options']))
            k2 += 1
    # ③ 한 수 + ② 변형 짝
    q3 = '자동차를 받을 확률을 가장 높이려면 어떻게 해야 하는가?'
    pool = []
    for n, k, p, opened in scen:
        for host in HOSTS:
            b = best_choice(n, k, p, opened, host)
            if b is None:
                continue
            twins = [(h, t) for h in HOSTS if h != host and (t := best_choice(n, k, p, opened, h)) not in (None, b)]
            pool.append((n, k, p, opened, host, b, twins))
    rng.shuffle(pool)
    kind = lambda b: 'same' if b == SAME else ('stay' if b.startswith('처음') else 'switch')
    picked, used = [], set()
    for u in pool:  # 답의 종류(그대로/바꾸기/같다)와 사회자 방식이 한쪽으로 몰리지 않게
        if len(picked) >= per_stage:
            break
        if u[:4] in used or sum(kind(c[5]) == kind(u[5]) for c in picked) >= (per_stage + 2) // 3 + 1:
            continue
        if sum(c[4] == u[4] for c in picked) >= (per_stage + 2) // 3:
            continue
        used.add(u[:4])
        picked.append(u)
    assert len(picked) == per_stage, len(picked)
    for i, (n, k, p, opened, host, b, twins) in enumerate(picked):
        opts = options3(n, p, opened)
        state = {'규칙': rules_text(n, k, host), '상황': situation(n, p, opened)}
        base = make_item(rng, GAME, '3-한수', i, state, q3, opts, b)
        items.append(base)
        if twins:
            h, t = rng.choice(twins)
            items.append(make_item(rng, GAME, '2-변형', 100 + i, dict(state, 규칙=rules_text(n, k, h)), q3, opts, t,
                                   original=b, twin_of=base['id'], order=base['options']))
    return items
