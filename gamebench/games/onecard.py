"""원카드.

① 판정: (가) 공격이 없을 때 낼 수 있는 카드, (나) 공격을 막을 수 있는 카드, (다) 쌓인 공격으로 받을 장수.
   (가)(나)는 가능한 카드가 하나이거나 하나도 없는 경우만 쓴다(보기에 "없음"이 있다).
③ 한 수: 다음 사람의 마지막 카드가 공개돼 있을 때, 그 사람이 그 카드를 내지 못하게 하려면 무엇을 내야 하는가.
② 변형: 무늬 대신 색이 같으면 낼 수 있는 규칙, 숫자가 같을 때만 낼 수 있는 규칙, 공격 카드면 무엇이든 막을 수 있는
   규칙((나)만), 2와 A의 공격 장수를 맞바꾼 규칙((다)). 답이 바뀌는 경우만 쓴다.
"""
from .common import make_item

GAME = 'onecard'
NAME = '원카드'
FACET = '규칙 판정'

SUITS = '♠♥♦♣'
RED = '♥♦'
RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
JOKER = ('조커', '')
DECK = [(r, s) for s in SUITS for r in RANKS] + [JOKER]
STRENGTH = {'2': 1, 'A': 2, '조커': 3}

STANDARD = {'match': 'suit', 'block': 'strict', 'amount': {'2': 2, 'A': 3, '조커': 5}}
COLOR = dict(STANDARD, match='color')
RANK = dict(STANDARD, match='rank')
ANY = dict(STANDARD, block='any')
SWAP_AMT = dict(STANDARD, amount={'2': 3, 'A': 2, '조커': 5})

NOTATION = '카드는 무늬(♠♥♦♣)와 숫자를 붙여 "♥7", "♠A"처럼 쓴다. 조커는 "조커"로 쓴다. ♥♦는 빨강, ♠♣는 검정이다.'


def rules_text(rule):
    m = {'suit': '무늬가 같거나 ', 'color': '색이 같거나(♥♦는 빨강, ♠♣는 검정) ', 'rank': ''}[rule['match']]
    a = rule['amount']
    text = (f'차례마다 맨 위 카드와 {m}숫자가 같은 카드 한 장을 낼 수 있다. ')
    if rule['match'] == 'rank':
        text += '무늬나 색은 상관없다. '
    text += (f'조커는 공격을 받지 않은 차례라면 언제나 낼 수 있다. '
            f'2, A, 조커는 공격 카드다. 공격 카드를 내면 다음 사람이 공격을 받는다. 받을 장수는 2가 {a["2"]}장, A가 {a["A"]}장, 조커가 {a["조커"]}장이다. '
            '공격을 받은 사람은 공격 카드를 내서 막을 수 있고, 그러면 장수가 더해져 공격이 다음 사람에게 넘어간다. '
            '막지 못하면 더해진 장수만큼 카드를 받고 공격이 끝난다. 공격을 받은 차례에는 공격 카드만 낼 수 있다. ')
    if rule['block'] == 'strict':
        m2 = {'suit': '무늬나 ', 'color': '색이나 ', 'rank': ''}[rule['match']]
        text += f'막는 카드는 맨 위 카드보다 약하면 안 되고(세기는 2 < A < 조커), 조커가 아니면 맨 위 카드와 {m2}숫자가 같아야 한다.'
    else:
        text += '막는 카드는 공격 카드이기만 하면 세기, 무늬, 색, 숫자와 상관없이 낼 수 있다.'
    return text


def cs(c):
    return '조커' if c == JOKER else c[1] + c[0]


def is_attack(c):
    return c[0] in STRENGTH


def match(rule, c, top):
    if c[0] == top[0]:
        return True
    if rule['match'] == 'rank':
        return False
    if rule['match'] == 'suit':
        return c[1] == top[1]
    return (c[1] in RED) == (top[1] in RED)


def playable(rule, c, top, attacked):
    if not attacked:
        return c == JOKER or match(rule, c, top)
    if not is_attack(c):
        return False
    if rule['block'] == 'any':
        return True
    return STRENGTH[c[0]] >= STRENGTH[top[0]] and (c == JOKER or (top != JOKER and match(rule, c, top)))


def only_playable(rule, hand, top, attacked, none_label):
    p = [c for c in hand if playable(rule, c, top, attacked)]
    if len(p) > 1:
        return None
    return cs(p[0]) if p else none_label


def stack_total(rule, seq):
    return sum(rule['amount'][c[0]] for c in seq)


def blockers(rule, hand, top, x):
    """내가 낼 수 있는 카드 중, 그 카드를 낸 뒤 다음 사람이 x를 낼 수 없게 되는 카드들.
    공격 카드를 내면 다음 사람은 공격을 받은 차례가 된다."""
    return [c for c in hand if playable(rule, c, top, False) and not playable(rule, x, c, is_attack(c))]


def spoil_answer(rule, hand, top, x):
    b = blockers(rule, hand, top, x)
    return cs(b[0]) if len(b) == 1 else None


def generate(rng, per_stage):
    items = []
    n_twin = 0

    def twin(base, rule, orig, correct):
        nonlocal n_twin
        items.append(make_item(rng, GAME, '2-변형', n_twin, dict(base['state'], 규칙=rules_text(rule)),
                               base['question'], base['options'], correct, original=orig, twin_of=base['id'],
                               order=base['options']))
        n_twin += 1

    def draw(k, exclude=()):
        return rng.sample([c for c in DECK if c not in exclude], k)

    NO_PLAY, NO_BLOCK = '낼 수 있는 카드 없음', '막을 수 있는 카드 없음'
    idx = 0
    # ① (가) 공격 없는 차례에 낼 수 있는 카드
    q_a = '지금 내 차례이고 공격은 받지 않았다. 내가 낼 수 있는 카드는?'
    made = tries = 0
    while made < (per_stage + 2) // 3 + 1:
        tries += 1
        assert tries < 100000
        top = draw(1, [JOKER])[0]
        hand = draw(rng.choice([4, 5]), [top])
        # 색 규칙은 더 느슨하고 숫자 규칙은 더 엄격하다. 느슨한 쪽 짝은 "없음"에서 카드로, 엄격한 쪽 짝은 카드에서 "없음"으로 바뀐다.
        rule2 = [COLOR, RANK, None][made % 3]
        a = only_playable(STANDARD, hand, top, False, NO_PLAY)
        t = only_playable(rule2, hand, top, False, NO_PLAY) if rule2 else None
        want_twin = rule2 is not None
        if a is None or (want_twin and (t is None or t == a)) or (not want_twin and a == NO_PLAY):
            continue
        state = {'규칙': rules_text(STANDARD), '표기': NOTATION,
                 '상황': f'맨 위 카드: {cs(top)}\n내 손패: {" ".join(cs(c) for c in hand)}'}
        base = make_item(rng, GAME, '1-판정', idx, state, q_a, [cs(c) for c in hand] + [NO_PLAY], a)
        items.append(base); idx += 1
        if want_twin:
            twin(base, rule2, a, t)
        made += 1

    # ① (나) 공격을 막을 수 있는 카드
    q_b = '앞 사람이 공격 카드를 내서 지금 내가 공격을 받고 있다. 막을 수 있는 카드는?'
    made = tries = 0
    while made < (per_stage + 2) // 3 + 1:
        tries += 1
        assert tries < 200000
        top = rng.choice([c for c in DECK if c[0] in ('2', 'A')])
        # 손패에 공격 카드가 섞이도록 공격 카드 1~2장 + 일반 카드
        atk = rng.sample([c for c in DECK if is_attack(c) and c != top], rng.choice([1, 2]))
        rest = draw(rng.choice([2, 3]), [top] + atk)
        hand = atk + rest
        rng.shuffle(hand)
        rule2 = [ANY, RANK, COLOR, None][made % 4]
        a = only_playable(STANDARD, hand, top, True, NO_BLOCK)
        t = only_playable(rule2, hand, top, True, NO_BLOCK) if rule2 else None
        want_twin = rule2 is not None
        if a is None or (want_twin and (t is None or t == a)) or (not want_twin and a == NO_BLOCK):
            continue
        state = {'규칙': rules_text(STANDARD), '표기': NOTATION,
                 '상황': f'맨 위 카드: {cs(top)} (공격 중)\n내 손패: {" ".join(cs(c) for c in hand)}'}
        base = make_item(rng, GAME, '1-판정', idx, state, q_b, [cs(c) for c in hand] + [NO_BLOCK], a)
        items.append(base); idx += 1
        if want_twin:
            twin(base, rule2, a, t)
        made += 1

    # ① (다) 쌓인 공격 장수
    q_c = '지금 내 차례이고 공격을 받고 있다. 내가 막지 못하면 카드를 몇 장 받는가?'
    made = tries = 0
    while made < (per_stage + 2) // 3:
        tries += 1
        assert tries < 100000
        start = draw(1, [JOKER])[0]
        seq, top, attacked = [], start, False
        for _ in range(rng.choice([2, 3, 3, 4])):
            cand = [c for c in DECK if is_attack(c) and c not in seq and playable(STANDARD, c, top, attacked)]
            if not cand:
                break
            c = rng.choice(cand)
            seq.append(c); top = c; attacked = True
        if len(seq) < 2:
            continue
        a = stack_total(STANDARD, seq)
        t = stack_total(SWAP_AMT, seq)
        cands = [a, t, STANDARD['amount'][seq[-1][0]], len(seq), a + 2, a - 1]
        opts = []
        for v in cands:
            if v > 0 and str(v) not in opts:
                opts.append(str(v))
        opts = opts[:5]
        state = {'규칙': rules_text(STANDARD), '표기': NOTATION,
                 '상황': f'공격 전 맨 위 카드: {cs(start)}\n그 뒤 나온 카드(순서대로): {", ".join(cs(c) for c in seq)}'}
        base = make_item(rng, GAME, '1-판정', idx, state, q_c, opts, str(a))
        items.append(base); idx += 1
        if t != a:
            twin(base, SWAP_AMT, str(a), str(t))
        made += 1

    # ③ 한 수: 다음 사람의 마지막 카드 x를 내지 못하게 막는 카드
    q3 = '다음 사람은 카드가 한 장 남았고, 그 카드가 무엇인지 모두 알고 있다. 다음 사람이 그 카드를 내지 못하게 하려면, 내가 지금 낼 수 있는 카드 중 무엇을 내야 하는가?'
    made = tries = 0
    while made < per_stage:
        tries += 1
        assert tries < 400000
        # 막기 규칙을 느슨하게 하면 막는 카드가 줄기만 해서(부분집합) 다른 카드가 답이 될 수 없다. 짝은 색·숫자 규칙만 쓴다.
        rule2 = [RANK, COLOR, None][made % 3]
        top = draw(1, [JOKER])[0]
        x = draw(1, [JOKER, top])[0]
        hand = draw(rng.choice([4, 5]), [top, x])
        if sum(playable(STANDARD, c, top, False) for c in hand) < 2:
            continue  # 낼 수 있는 카드가 여럿이어야 고르는 문제가 된다
        a = spoil_answer(STANDARD, hand, top, x)
        if a is None:
            continue
        t = spoil_answer(rule2, hand, top, x) if rule2 else None
        has_twin = t is not None and t != a
        if has_twin != (rule2 is not None):
            continue
        state = {'규칙': rules_text(STANDARD), '표기': NOTATION,
                 '상황': f'맨 위 카드: {cs(top)} (공격 없음)\n내 손패: {" ".join(cs(c) for c in hand)}\n다음 사람의 마지막 카드: {cs(x)}'}
        base = make_item(rng, GAME, '3-한수', made, state, q3, [cs(c) for c in hand], a)
        items.append(base)
        if has_twin:
            twin(base, rule2, a, t)
        made += 1
    return items
