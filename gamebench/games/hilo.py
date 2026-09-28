"""하이로우.

남은 카드 더미를 모두 적어 준다. 다음 카드는 남은 카드 중 하나가 같은 확률로 나온다.
① 판정: 하이(또는 로우)가 맞을 확률.
③ 한 수: 하이·로우·확률이 같다 중 무엇이 맞는가 (확률 차이가 뚜렷하거나 정확히 같은 경우만).
② 변형: A를 가장 낮은 카드로 치는 규칙, 또는 같은 숫자를 하이로 치는 규칙. 답이 달라지는 경우만.
"""
from fractions import Fraction

from .common import make_item

GAME = 'hilo'
NAME = '하이로우'
FACET = '확률·기댓값'

RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
MARGIN = Fraction(3, 20)  # ③: 하이·로우 확률 차이가 이보다 작으면(0 제외) 문항을 버린다

RULES = {  # (A 위치, 같은 숫자 처리)
    'base': ('high', 'lose'),
    'alow': ('low', 'lose'),
    'tiehi': ('high', 'hi'),
}


def rules_text(rule):
    ace, tie = RULES[rule]
    order = ('카드 높낮이는 2 < 3 < 4 < 5 < 6 < 7 < 8 < 9 < 10 < J < Q < K < A 순서다(A가 가장 높다).'
             if ace == 'high' else
             '카드 높낮이는 A < 2 < 3 < 4 < 5 < 6 < 7 < 8 < 9 < 10 < J < Q < K 순서다(A가 가장 낮다).')
    tie_t = ('다음 카드가 지금 카드와 같은 숫자면 하이도 로우도 틀린 것으로 한다.' if tie == 'lose' else
             '다음 카드가 지금 카드와 같은 숫자면 하이가 맞은 것으로 하고 로우는 틀린 것으로 한다.')
    return ('지금 펼쳐진 카드 한 장을 보고, 더미에서 뽑을 다음 카드가 더 높을지(하이) 낮을지(로우) 고른다. '
            '무늬는 따지지 않는다. ' + order + ' 다음 카드가 지금 카드보다 높으면 하이가 맞고, 낮으면 로우가 맞는다. '
            + tie_t + ' 다음 카드는 남은 카드 더미에 있는 카드 중 하나가 모두 같은 확률로 나온다.')


def value(card, rule):
    return -1 if (card == 'A' and RULES[rule][0] == 'low') else RANKS.index(card)


def probs(current, deck, rule):
    """(하이가 맞을 확률, 로우가 맞을 확률)."""
    cv = value(current, rule)
    tie_hi = RULES[rule][1] == 'hi'
    hi = sum(1 for c in deck if value(c, rule) > cv or (tie_hi and value(c, rule) == cv))
    lo = sum(1 for c in deck if value(c, rule) < cv)
    return Fraction(hi, len(deck)), Fraction(lo, len(deck))


CHOICES = ['하이', '로우', '하이와 로우가 맞을 확률이 같다']


def choice(current, deck, rule):
    hi, lo = probs(current, deck, rule)
    if hi == lo:
        return CHOICES[2]
    if abs(hi - lo) < MARGIN:
        return None
    return CHOICES[0] if hi > lo else CHOICES[1]


def situation(current, deck):
    return f'지금 펼쳐진 카드: {current}. 남은 카드 더미({len(deck)}장): ' + ', '.join(deck)


def frac(k, n):
    return f'{k}/{n}'


def random_deal(rng, want_ace):
    current = rng.choice(RANKS)
    n = rng.randint(6, 12)
    pool = [r for r in RANKS for _ in range(4)]
    pool.remove(current)
    deck = rng.sample(pool, n)
    if want_ace and 'A' not in deck and current != 'A':
        deck[0] = 'A'
    rng.shuffle(deck)
    return current, deck


def generate(rng, per_stage):
    items = []
    # ① 판정 + ② 변형 짝
    k2 = 0
    for i in range(per_stage):
        side = '하이' if i % 2 == 0 else '로우'
        twin = rng.choice(['alow', 'tiehi']) if i % 3 != 2 else None
        for _ in range(500):
            current, deck = random_deal(rng, twin == 'alow')
            b = probs(current, deck, 'base')[0 if side == '하이' else 1]
            t = probs(current, deck, twin)[0 if side == '하이' else 1] if twin else None
            if twin is None or t != b:
                break
        else:
            twin, t = None, None
        n = len(deck)
        ks = [int(b * n)] + ([int(t * n)] if twin else [])
        cands = sorted(({int(p * n) for r in RULES for p in probs(current, deck, r)} | {n - int(b * n), 1, n // 2})
                       - set(ks) - {0})
        rng.shuffle(cands)
        opts = [frac(k, n) for k in ks + cands[:5 - len(ks)]]
        state = {'규칙': rules_text('base'), '상황': situation(current, deck)}
        q = f'{side}를 고르면 맞을 확률은? (확률은 남은 카드 {n}장 기준 분수로 적었다)'
        base = make_item(rng, GAME, '1-판정', i, state, q, opts, frac(int(b * n), n))
        items.append(base)
        if twin:
            items.append(make_item(rng, GAME, '2-변형', k2, dict(state, 규칙=rules_text(twin)), q, opts,
                                   frac(int(t * n), n), original=frac(int(b * n), n), twin_of=base['id'],
                                   order=base['options']))
            k2 += 1
    # ③ 한 수 + ② 변형 짝
    q3 = '하이와 로우 중 맞을 확률이 더 높은 쪽은?'
    want_twins = per_stage // 2
    twinned, plain = [], []
    for _ in range(20000):
        if len(twinned) >= want_twins and len(plain) >= per_stage - want_twins:
            break
        current, deck = random_deal(rng, rng.random() < 0.5)
        b = choice(current, deck, 'base')
        if b is None or sum(u[2] == b for u in twinned + plain) >= (per_stage + 1) // 2:
            continue
        tws = [(r, choice(current, deck, r)) for r in ('alow', 'tiehi')]
        tws = [(r, c) for r, c in tws if c is not None and c != b]
        if tws and len(twinned) < want_twins:
            twinned.append((current, deck, b, rng.choice(tws)))
        elif not tws and len(plain) < per_stage - want_twins:
            plain.append((current, deck, b, None))
    assert len(twinned) + len(plain) == per_stage, (len(twinned), len(plain))
    for i, (current, deck, b, tw) in enumerate(twinned + plain):
        state = {'규칙': rules_text('base'), '상황': situation(current, deck)}
        base = make_item(rng, GAME, '3-한수', i, state, q3, CHOICES, b)
        items.append(base)
        if tw:
            items.append(make_item(rng, GAME, '2-변형', 100 + i, dict(state, 규칙=rules_text(tw[0])), q3, CHOICES,
                                   tw[1], original=b, twin_of=base['id'], order=base['options']))
    return items
