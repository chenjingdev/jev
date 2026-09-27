"""블랙잭.

① 판정: (가) 플레이어 카드의 합(A 처리, 버스트), (나) 두 사람의 최종 카드로 본 승부, (다) 정해진 카드 순서에서 딜러의 최종 결과.
③ 한 수: 카드를 한 장 받을지(받으면 한 장만 받고 멈춤) 멈출지. 무한 덱 가정으로 기댓값을 정확히 계산하고,
   두 선택의 기댓값 차이가 0.05보다 큰 경우만 쓴다.
② 변형: 버스트 기준을 23으로 올린 규칙, 딜러가 16 이상에서 멈추는 규칙. 답이 바뀌는 경우만 쓴다(③ 짝도 차이 0.05 초과).
"""
from functools import lru_cache
import itertools

from .common import make_item

GAME = 'blackjack'
NAME = '블랙잭'
FACET = '확률·기댓값'

STANDARD = (21, 17)   # (버스트 기준, 딜러가 멈추는 합)
BUST23 = (23, 17)
STAND16 = (21, 16)
PTS = {'A': 1, 'J': 10, 'Q': 10, 'K': 10, **{str(n): n for n in range(2, 11)}}
RANKS = ['A'] + [str(n) for n in range(2, 11)] + ['J', 'Q', 'K']
BUST = '버스트'
DECK_NOTE = ('카드는 매우 많은 벌을 섞은 덱에서 나온다고 본다. 한 장을 뽑을 때마다 A, 2, 3, 4, 5, 6, 7, 8, 9는 각각 1/13, '
             '10점 카드(10, J, Q, K)는 4/13 확률로 나오고, 앞에 나온 카드는 확률에 영향을 주지 않는다.')
GAP = 0.05


def rules_text(rule):
    lim, d = rule
    return (f'카드 점수는 2~10은 적힌 숫자, J·Q·K는 10점이다. A는 1점 또는 11점이다. A 한 장을 11점으로 세어도 합이 {lim} 이하이면 '
            f'그 A를 11점으로, 아니면 1점으로 센다(11점으로 세는 A는 많아야 한 장). 합이 {lim}을 넘으면 버스트다. '
            '플레이어가 먼저 카드를 더 받을지 정하고, 플레이어가 버스트하면 딜러와 상관없이 플레이어가 진다. '
            f'딜러는 합이 {d} 이상이 될 때까지 카드를 받고, {d} 이상이 되면 멈춘다(A를 11점으로 센 합도 같다). '
            '딜러가 버스트하면 플레이어가 이긴다. 둘 다 버스트가 아니면 합이 큰 쪽이 이기고, 같으면 비긴다. '
            '처음 두 장으로 만든 합에 따로 보너스는 없다. 이기면 1을 얻고, 지면 1을 잃고, 비기면 0이다.')


def total(cards, rule):
    """합. 버스트면 None."""
    lim = rule[0]
    hard = sum(PTS[c] for c in cards)
    if 'A' in cards and hard + 10 <= lim:
        hard += 10
    return None if hard > lim else hard


def total_str(cards, rule):
    t = total(cards, rule)
    return BUST if t is None else str(t)


def outcome(player, dealer, rule):
    p, d = total(player, rule), total(dealer, rule)
    if p is None:
        return '딜러 승'
    if d is None or p > d:
        return '플레이어 승'
    return '딜러 승' if d > p else '무승부'


def dealer_play(cards, draws, rule):
    """딜러가 처음 카드 cards에서 draws를 차례로 받는다. 최종 카드."""
    cards = list(cards)
    it = iter(draws)
    while True:
        t = total(cards, rule)
        if t is None or t >= rule[1]:
            return cards
        cards.append(next(it))


# --- 기댓값 (무한 덱) -----------------------------------------------------------------
PROB = {**{p: 1 / 13 for p in range(1, 10)}, 10: 4 / 13}  # 점수 1은 A


def _val(hard, ace, lim):
    return hard + 10 if ace and hard + 10 <= lim else hard


@lru_cache(maxsize=None)
def dealer_dist(hard, ace, rule):
    """딜러의 최종 합 분포. 키 0은 버스트."""
    lim, d = rule
    if hard > lim:
        return ((0, 1.0),)
    v = _val(hard, ace, lim)
    if v >= d:
        return ((v, 1.0),)
    out = {}
    for p, pr in PROB.items():
        for k, q in dealer_dist(hard + p, ace or p == 1, rule):
            out[k] = out.get(k, 0) + pr * q
    return tuple(sorted(out.items()))


def ev_stand(hard, ace, up, rule):
    lim = rule[0]
    if hard > lim:
        return -1.0
    p = _val(hard, ace, lim)
    ev = 0.0
    for k, q in dealer_dist(up, up == 1, rule):
        ev += q * (1 if k == 0 or p > k else (-1 if k > p else 0))
    return ev


def ev_hit(hard, ace, up, rule):
    return sum(pr * ev_stand(hard + p, ace or p == 1, up, rule) for p, pr in PROB.items())


def decision(cards, up, rule):
    hard = sum(PTS[c] for c in cards)
    ace = 'A' in cards
    s, h = ev_stand(hard, ace, PTS[up], rule), ev_hit(hard, ace, PTS[up], rule)
    return ('카드를 받는다' if h > s else '멈춘다'), abs(h - s)


HIT_OPTS = ['카드를 받는다', '멈춘다']


def cards_str(cards):
    return ', '.join(cards)


def generate(rng, per_stage):
    items = []
    n_twin = 0

    def twin(base, rule, orig, correct):
        nonlocal n_twin
        items.append(make_item(rng, GAME, '2-변형', n_twin, dict(base['state'], 규칙=rules_text(rule)),
                               base['question'], base['options'], correct, original=orig, twin_of=base['id'],
                               order=base['options']))
        n_twin += 1

    def rand_cards(k):
        return [rng.choice(RANKS) for _ in range(k)]

    idx = 0
    n_each = (per_stage + 2) // 3 + 1
    # ① (가) 플레이어 카드의 합
    q_a = '플레이어 카드의 합은? 버스트면 "버스트".'
    made = tries = 0
    while made < n_each:
        tries += 1
        assert tries < 100000
        cards = rand_cards(rng.choice([3, 3, 4]))
        if 'A' not in cards:
            continue
        a, t = total_str(cards, STANDARD), total_str(cards, BUST23)
        want_twin = made % 3 != 2
        if want_twin != (a != t):
            continue
        hard = sum(PTS[c] for c in cards)
        cand = [a, t, str(hard), str(hard + 10), BUST, str(hard + 1)]
        opts = []
        for v in cand:
            if v not in opts:
                opts.append(v)
        opts = opts[:5]
        state = {'규칙': rules_text(STANDARD), '상황': f'플레이어 카드: {cards_str(cards)}'}
        base = make_item(rng, GAME, '1-판정', idx, state, q_a, opts, a)
        items.append(base); idx += 1
        if a != t:
            twin(base, BUST23, a, t)
        made += 1

    # ① (나) 승부
    q_b = '두 사람 모두 카드 받기를 마쳤다. 결과는?'
    opts_b = ['플레이어 승', '딜러 승', '무승부']
    made = tries = 0
    while made < n_each:
        tries += 1
        assert tries < 100000
        pl = rand_cards(rng.choice([2, 3, 3]))
        dl = dealer_play(rand_cards(2), [rng.choice(RANKS) for _ in range(8)], STANDARD)
        a, t = outcome(pl, dl, STANDARD), outcome(pl, dl, BUST23)
        # 버스트 기준 23에서는 딜러가 더 일찍 멈췄을 수 있다. 두 규칙 모두에서 딜러가 규칙대로 받은 카드인 판만 쓴다.
        if dealer_play(dl[:2], dl[2:], BUST23) != dl:
            continue
        want_twin = made % 3 != 2
        if want_twin != (a != t):
            continue
        if made % 3 == 2 and a == '무승부' and made % 2:
            continue
        state = {'규칙': rules_text(STANDARD), '상황': f'플레이어 카드: {cards_str(pl)}\n딜러 카드: {cards_str(dl)}'}
        base = make_item(rng, GAME, '1-판정', idx, state, q_b, opts_b, a)
        items.append(base); idx += 1
        if a != t:
            twin(base, BUST23, a, t)
        made += 1

    # ① (다) 딜러의 최종 결과
    q_c = '딜러가 규칙대로 카드를 받는다. 딜러의 최종 합은? 버스트면 "버스트".'
    made = tries = 0
    while made < n_each:
        tries += 1
        assert tries < 100000
        first = rand_cards(2)
        draws = rand_cards(4)
        try:
            fa = dealer_play(first, draws, STANDARD)
            ft = dealer_play(first, draws, STAND16)
        except StopIteration:
            continue
        if len(fa) == 2 and len(ft) == 2:
            continue  # 한 장도 더 받지 않는 판은 뺀다
        a, t = total_str(fa, STANDARD), total_str(ft, STAND16)
        want_twin = made % 3 != 2
        if want_twin != (a != t):
            continue
        cand = [a, t, total_str(fa[:-1], STANDARD), BUST, total_str(first + draws[:len(fa) - 1], STANDARD)]
        opts = []
        for v in cand:
            if v not in opts:
                opts.append(v)
        if len(opts) < 3:
            continue
        state = {'규칙': rules_text(STANDARD),
                 '상황': f'딜러의 처음 두 장: {cards_str(first)}\n딜러가 더 받는다면 나올 카드(순서대로): {cards_str(draws)}'}
        base = make_item(rng, GAME, '1-판정', idx, state, q_c, opts, a)
        items.append(base); idx += 1
        if a != t:
            twin(base, STAND16, a, t)
        made += 1

    # ③ 한 수: 카드를 한 장 받을지 멈출지 (기댓값)
    q3 = ('플레이어 차례다. 카드를 받는다면 딱 한 장만 받고 멈춘다. 기댓값(이긴 경우 +1, 진 경우 -1, 비긴 경우 0의 평균)이 '
          '더 큰 쪽은?')
    pool = {'twin': [], 'plain': []}
    reps = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10']
    for c1, c2 in itertools.combinations_with_replacement(reps, 2):
        for up in reps:
            cards = [c1, c2]
            if total(cards, STANDARD) < 12:
                continue
            a, gap = decision(cards, up, STANDARD)
            if gap <= GAP:
                continue
            tw = None
            for rule in (BUST23, STAND16):
                t, g2 = decision(cards, up, rule)
                if t != a and g2 > GAP:
                    tw = (rule, t)
                    break
            pool['twin' if tw else 'plain'].append((cards, up, a, tw))
    for k in pool:
        rng.shuffle(pool[k])
    # 받는다/멈춘다 답이 한쪽으로 쏠리지 않게 섞는다
    twins = pool['twin'][:per_stage // 2]
    need = per_stage - len(twins)
    hits = [u for u in pool['plain'] if u[2] == '카드를 받는다']
    stands = [u for u in pool['plain'] if u[2] == '멈춘다']
    plain = [x for pair in zip(hits, stands) for x in pair][:need]
    for i, (cards, up, a, tw) in enumerate(twins + plain):
        shown = [rng.choice(['10', 'J', 'Q', 'K']) if c == '10' else c for c in cards]
        up_s = rng.choice(['10', 'J', 'Q', 'K']) if up == '10' else up
        state = {'규칙': rules_text(STANDARD), '덱': DECK_NOTE,
                 '상황': f'플레이어 카드: {cards_str(shown)}\n딜러의 보이는 카드: {up_s} (다른 한 장은 뒤집혀 있다)'}
        base = make_item(rng, GAME, '3-한수', i, state, q3, HIT_OPTS, a)
        items.append(base)
        if tw:
            twin(base, tw[0], a, tw[1])
    return items
