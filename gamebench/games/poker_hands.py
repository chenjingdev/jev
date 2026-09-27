"""포커 족보.

① 판정: 두세 사람의 5장 손패 중 이기는 손패(또는 가장 약한 손패). 족보가 모두 다른 경우만 낸다.
③ 한 수: 손패 5장과 새로 받을 카드 한 장이 주어질 때, 어느 카드를 버려야 가장 높은 족보가 되는가.
   가장 높은 족보가 하나의 선택지에서만 나오는 경우만 쓴다.
② 변형: 족보 순서에서 이웃한 두 족보를 맞바꾼 규칙(예: 플러시가 풀하우스보다 높다). 답이 바뀌는 경우만 쓴다.
"""
from collections import Counter

from .common import make_item

GAME = 'poker_hands'
NAME = '포커 족보'
FACET = '규칙 판정'

SUITS = '♠♥♦♣'
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']  # 인덱스 0~12
CATS = ['스트레이트 플러시', '포카드', '풀하우스', '플러시', '스트레이트', '트리플', '투페어', '원페어', '하이카드']
DEFS = {
    '스트레이트 플러시': '무늬가 같고 숫자가 이어진 5장',
    '포카드': '같은 숫자 4장',
    '풀하우스': '같은 숫자 3장과 다른 같은 숫자 2장',
    '플러시': '무늬가 같은 5장',
    '스트레이트': '숫자가 이어진 5장',
    '트리플': '같은 숫자 3장',
    '투페어': '같은 숫자 2장이 두 쌍',
    '원페어': '같은 숫자 2장',
    '하이카드': '위 어느 것에도 해당하지 않음',
}
STANDARD = tuple(CATS)
# 이웃한 두 족보를 맞바꾼 순서. 두 족보를 동시에 만족하는 손패는 더 높은 족보(스트레이트 플러시)에 먼저 걸리므로 겹치지 않는다.
SWAPS = [('풀하우스', '플러시'), ('플러시', '스트레이트'), ('스트레이트', '트리플')]


def swapped(a, b):
    order = list(STANDARD)
    i, j = order.index(a), order.index(b)
    order[i], order[j] = order[j], order[i]
    return tuple(order)


def rules_text(order):
    ranking = ' > '.join(order)
    defs = ', '.join(f'{c}: {DEFS[c]}' for c in order)
    return (f'카드 5장으로 족보를 정한다. 족보는 높은 것부터 {ranking} 순서다. 각 족보의 뜻은 다음과 같다. {defs}. '
            '숫자는 2<3<4<5<6<7<8<9<10<J<Q<K<A 순서이고, "이어진"은 이 순서로 연달아 있다는 뜻이다(A 다음은 없고 A-2-3-4-5는 이어진 것이 아니다). '
            '손패가 여러 족보에 해당하면 그중 가장 높은 족보로 친다. 족보가 높은 손패가 이긴다.')


NOTATION = '카드는 무늬(♠♥♦♣)와 숫자를 붙여 "♥10", "♠A"처럼 쓴다.'


def card_str(c):
    return c[1] + RANKS[c[0]]


def hand_str(h):
    return ' '.join(card_str(c) for c in sorted(h, key=lambda c: (c[0], c[1])))


def matches(cat, hand):
    ranks = sorted(c[0] for c in hand)
    cnt = sorted(Counter(ranks).values())
    flush = len({c[1] for c in hand}) == 1
    straight = len(set(ranks)) == 5 and ranks[-1] - ranks[0] == 4
    return {
        '스트레이트 플러시': flush and straight,
        '포카드': cnt[-1] >= 4,
        '풀하우스': cnt == [2, 3],
        '플러시': flush,
        '스트레이트': straight,
        '트리플': cnt[-1] >= 3,
        '투페어': sum(1 for v in cnt if v >= 2) >= 2,
        '원페어': cnt[-1] >= 2,
        '하이카드': True,
    }[cat]


def category(hand, order):
    """규칙 문구대로: 해당하는 족보 중 가장 높은 것."""
    return next(c for c in order if matches(c, hand))


def strength(hand, order):
    return len(order) - order.index(category(hand, order))


def winner(hands, order, weakest=False):
    s = [strength(h, order) for h in hands]
    target = min(s) if weakest else max(s)
    assert s.count(target) == 1, (hands, s)
    return s.index(target)


def best_discards(hand, new, order):
    res = {}
    for c in hand:
        h = [x for x in hand if x != c] + [new]
        res[c] = strength(h, order)
    top = max(res.values())
    return [c for c, v in res.items() if v == top]


# --- 족보별 손패 만들기 ---------------------------------------------------------------

def build(rng, cat, used):
    """cat(표준 순서 기준) 족보의 손패를 만든다. used와 겹치지 않는다."""
    for _ in range(1000):
        free = [(r, s) for r in range(13) for s in SUITS if (r, s) not in used]
        h = None
        if cat in ('스트레이트 플러시', '스트레이트'):
            lo = rng.randrange(0, 9)
            s0 = rng.choice(SUITS)
            h = [(lo + k, s0 if cat == '스트레이트 플러시' else rng.choice(SUITS)) for k in range(5)]
        elif cat == '플러시':
            s0 = rng.choice(SUITS)
            h = [(r, s0) for r in rng.sample(range(13), 5)]
        else:
            shape = {'포카드': [4, 1], '풀하우스': [3, 2], '트리플': [3, 1, 1], '투페어': [2, 2, 1],
                     '원페어': [2, 1, 1, 1], '하이카드': [1, 1, 1, 1, 1]}[cat]
            rs = rng.sample(range(13), len(shape))
            h = []
            for r, k in zip(rs, shape):
                h += [(r, s) for s in rng.sample(SUITS, k)]
        if len(set(h)) == 5 and all(c in free for c in h) and category(h, STANDARD) == cat:
            return h
    raise AssertionError(cat)


def deal(rng, cats):
    used, hands = set(), []
    for c in cats:
        h = build(rng, c, used)
        used |= set(h)
        hands.append(h)
    return hands


PLAYERS = ['철수', '영희', '민수']


def situation(hands):
    return '\n'.join(f'{PLAYERS[i]}: {hand_str(h)}' for i, h in enumerate(hands))


def generate(rng, per_stage):
    items = []
    n_twin = 0

    def add_twin(base, orig, order, correct):
        nonlocal n_twin
        items.append(make_item(rng, GAME, '2-변형', n_twin, dict(base['state'], 규칙=rules_text(order)),
                               base['question'], base['options'], correct, original=orig, twin_of=base['id'],
                               order=base['options']))
        n_twin += 1

    # ① 판정: 짝수 번째는 맞바꾼 두 족보가 승부를 가르는 판(② 짝을 만든다), 홀수 번째는 아무 족보나.
    seen = set()
    i = 0
    while i < per_stage:
        n = 2 if i % 3 == 0 else 3
        weakest = n == 3 and i % 4 == 1
        if i % 2 == 0:
            a, b = SWAPS[(i // 2) % len(SWAPS)]
            ia = STANDARD.index(a)
            if n == 2:
                cats = [a, b]
            elif weakest:  # 맞바꾼 두 족보가 가장 낮은 두 자리
                cats = [a, b, rng.choice(STANDARD[:ia])]
            else:  # 맞바꾼 두 족보가 가장 높은 두 자리
                cats = [a, b, rng.choice(STANDARD[ia + 2:])]
            order2 = swapped(a, b)
        else:
            cats = rng.sample(STANDARD, n)
            order2 = None
        rng.shuffle(cats)
        hands = deal(rng, cats)
        key = tuple(hand_str(h) for h in hands)
        if key in seen:
            continue
        seen.add(key)
        opts = PLAYERS[:n]
        q = '가장 약한 손패를 가진 사람은?' if weakest else '이기는 사람은?'
        state = {'규칙': rules_text(STANDARD), '표기': NOTATION, '상황': situation(hands)}
        ans = PLAYERS[winner(hands, STANDARD, weakest)]
        base = make_item(rng, GAME, '1-판정', i, state, q, opts, ans)
        items.append(base)
        if order2 is not None:
            t = PLAYERS[winner(hands, order2, weakest)]
            assert t != ans
            add_twin(base, ans, order2, t)
        i += 1

    # ③ 한 수: 5장 중 한 장을 버리고 새 카드를 받는다. 가장 높은 족보가 되는 버릴 카드가 하나뿐인 경우.
    q3 = '손패 5장 중 한 장을 버리고 새 카드를 받는다. 가장 높은 족보를 만들려면 어느 카드를 버려야 하는가?'
    pool_twin, pool_plain = [], []
    tries = 0
    while (len(pool_twin) < per_stage // 2 or len(pool_plain) < per_stage) and tries < 200000:
        tries += 1
        # 무늬 둘, 숫자 7개 안에서 뽑아 족보가 자주 생기게 한다
        suits = rng.sample(SUITS, 2)
        lo = rng.randrange(0, 7)
        deck = [(r, s) for r in range(lo, lo + 7) for s in suits] + [(r, s) for r in range(lo, lo + 7)
                                                                     for s in SUITS if s not in suits and rng.random() < 0.3]
        cards = rng.sample(deck, 6)
        hand, new = cards[:5], cards[5]
        best = best_discards(hand, new, STANDARD)
        if len(best) != 1:
            continue
        twin = None
        for a, b in SWAPS:
            o2 = swapped(a, b)
            b2 = best_discards(hand, new, o2)
            if len(b2) == 1 and b2[0] != best[0]:
                twin = (o2, b2[0])
                break
        # 최선 족보가 투페어 이상인 것만 (원페어·하이카드 목표는 너무 쉽다)
        top_cat = category([x for x in hand if x != best[0]] + [new], STANDARD)
        if top_cat in ('하이카드', '원페어'):
            continue
        entry = (hand, new, best[0], twin)
        if twin and len(pool_twin) < per_stage // 2:
            pool_twin.append(entry)
        elif not twin and len(pool_plain) < per_stage:
            pool_plain.append(entry)
    assert len(pool_twin) >= 1 and len(pool_twin) + len(pool_plain) >= per_stage, (len(pool_twin), len(pool_plain))
    chosen = (pool_twin + pool_plain)[:per_stage]
    for i, (hand, new, best, twin) in enumerate(chosen):
        state = {'규칙': rules_text(STANDARD), '표기': NOTATION,
                 '상황': f'내 손패: {hand_str(hand)}\n새로 받을 카드: {card_str(new)}'}
        opts = [card_str(c) for c in sorted(hand)]
        base = make_item(rng, GAME, '3-한수', i, state, q3, opts, card_str(best))
        items.append(base)
        if twin:
            add_twin(base, card_str(best), twin[0], card_str(twin[1]))
    return items
