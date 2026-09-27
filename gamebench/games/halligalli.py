"""할리갈리.

① 판정: 펼쳐진 카드들을 보고 종을 쳐야 하는지(예/아니오), 또는 개수가 조건에 맞는 과일은 무엇인지.
③ 한 수: 내가 새 카드를 펼치면 내 이전 카드는 가려진다. 후보 카드 중 펼쳤을 때 종을 쳐야 하는 카드는?
② 변형: 같은 상황에서 "정확히 네 개일 때 종을 친다"는 규칙. 답이 바뀌는 경우만 쓴다.
"""
from .common import make_item

GAME = 'halligalli'
NAME = '할리갈리'
FACET = '규칙 판정'

FRUITS = ['바나나', '딸기', '라임', '자두']
PLAYERS = ['철수', '영희', '민수', '지은']
NONE = '없음'


def rules_text(target):
    word = {5: '다섯', 4: '네'}[target]
    return ('카드마다 과일 한 종류가 1~5개 그려져 있다. 사람마다 자기 카드를 한 장씩 펼쳐 쌓고, 각자 맨 위에 펼친 카드 한 장만 보인다'
            '(새 카드를 펼치면 그 사람의 이전 카드는 가려진다). '
            f'보이는 카드들에서 같은 과일의 개수를 모두 더했을 때, 어떤 과일이든 합이 정확히 {word} 개이면 종을 친다. '
            '그런 과일이 없으면 종을 치지 않는다.')


def totals(cards):
    t = {f: 0 for f in FRUITS}
    for f, n in cards:
        t[f] += n
    return t


def hit_fruits(cards, target):
    return [f for f, v in totals(cards).items() if v == target]


def should_ring(cards, target):
    return '예' if hit_fruits(cards, target) else '아니오'


def which_fruit(cards, target):
    h = hit_fruits(cards, target)
    assert len(h) <= 1, (cards, h)
    return h[0] if h else NONE


def card_str(c):
    return f'{c[0]} {c[1]}개'


def show(cards, names):
    return '\n'.join(f'{p}: {card_str(c)}' for p, c in zip(names, cards))


def after_play(cards, me, new):
    return [new if i == me else c for i, c in enumerate(cards)]


def generate(rng, per_stage):
    items = []
    n_twin = 0

    def twin(base, orig, correct):
        nonlocal n_twin
        items.append(make_item(rng, GAME, '2-변형', n_twin, dict(base['state'], 규칙=rules_text(4)),
                               base['question'], base['options'], correct, original=orig, twin_of=base['id'],
                               order=base['options']))
        n_twin += 1

    # ① 판정. 짝수 번째는 "종을 쳐야 하는가?", 홀수 번째는 "합이 조건에 맞는 과일은?"
    seen = set()
    i = tries = 0
    while i < per_stage:
        tries += 1
        assert tries < 100000
        n = rng.choice([2, 3, 3, 4, 4])
        cards = [(rng.choice(FRUITS), rng.randint(1, 5)) for _ in range(n)]
        key = tuple(sorted(cards))
        if key in seen or len(hit_fruits(cards, 5)) > 1 or len(hit_fruits(cards, 4)) > 1:
            continue
        want_twin = i % 3 != 2  # 셋 중 둘은 짝이 생기는 판
        if i % 2 == 0:
            q, opts = '지금 종을 쳐야 하는가?', ['예', '아니오']
            a5, a4 = should_ring(cards, 5), should_ring(cards, 4)
        else:
            q, opts = '보이는 카드에서 종을 치게 만드는 과일은? 그런 과일이 없으면 "없음".', FRUITS + [NONE]
            a5, a4 = which_fruit(cards, 5), which_fruit(cards, 4)
        if want_twin != (a5 != a4):
            continue
        # 예/아니오 판정은 예와 아니오를 번갈아 낸다
        if i % 2 == 0 and a5 != ('예' if i % 4 == 0 else '아니오'):
            continue
        seen.add(key)
        state = {'규칙': rules_text(5), '상황': '보이는 카드\n' + show(cards, PLAYERS)}
        base = make_item(rng, GAME, '1-판정', i, state, q, opts, a5)
        items.append(base)
        if a5 != a4:
            twin(base, a5, a4)
        i += 1

    # ③ 한 수: 나(지은)의 새 카드 후보 4장 중 펼쳤을 때 종을 쳐야 하는 카드가 하나뿐인 경우.
    q3 = '내 차례다. 다음 네 장 중 어느 카드를 펼치면 종을 쳐야 하는 상황이 되는가?'
    i = tries = 0
    while i < per_stage:
        tries += 1
        assert tries < 200000
        n = rng.choice([3, 4])
        names = PLAYERS[:n - 1] + ['나']
        cards = [(rng.choice(FRUITS), rng.randint(1, 5)) for _ in range(n)]
        if hit_fruits(cards, 5):
            continue  # 펼치기 전부터 종을 칠 상황이면 뺀다
        cand = []
        while len(cand) < 4:
            c = (rng.choice(FRUITS), rng.randint(1, 5))
            if c not in cand and c != cards[-1]:
                cand.append(c)
        good5 = [c for c in cand if hit_fruits(after_play(cards, n - 1, c), 5)]
        good4 = [c for c in cand if hit_fruits(after_play(cards, n - 1, c), 4)]
        if len(good5) != 1:
            continue
        # 내 이전 카드가 가려진다는 점이 판단에 쓰이도록: 이전 카드를 그대로 두면 답이 달라지는 경우만
        if [c for c in cand if hit_fruits(cards + [c], 5)] == good5:
            continue
        want_twin = i % 2 == 0
        has_twin = len(good4) == 1 and good4 != good5
        if want_twin != has_twin:
            continue
        if has_twin and hit_fruits(cards, 4):
            continue  # 네 개 규칙에서는 펼치기 전부터 종을 칠 상황이면 뺀다
        state = {'규칙': rules_text(5), '상황': '보이는 카드\n' + show(cards, names)}
        opts = [card_str(c) for c in cand]
        base = make_item(rng, GAME, '3-한수', i, state, q3, opts, card_str(good5[0]))
        items.append(base)
        if has_twin:
            twin(base, card_str(good5[0]), card_str(good4[0]))
        i += 1
    return items
