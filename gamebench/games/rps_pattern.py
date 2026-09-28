"""가위바위보 상대 패턴.

상대는 둘째 판부터 늘 PATTERNS 중 한 방식으로 손을 정한다(첫 판은 아무 손). 방식 설명의 "이기는/지는"은
규칙의 상성을 따른다. 규칙 문구는 BEATS에서 만들고, 풀이기도 같은 상성을 읽는다.
① 판정: 방식을 알려 주고 첫 판 기록을 줄 때, 다음 판 상대 손 / 내가 이기거나 지려면 낼 손.
③ 한 수: 방식 후보(가)~(사)만 알려 주고 기록에서 맞는 방식을 찾게 한다. 기록과 맞는 후보가 정확히 하나인
   경우만 쓴다(생성기가 후보 전체와 대조한다). 묻는 것은 상대의 방식 / 다음 판 상대 손 / 이기려면 낼 손.
② 변형: 같은 상황·보기에서 상성이 모두 뒤집힌 규칙. 뒤집힌 규칙에서도 맞는 방식이 하나이고 답이 달라지는
   문항만 짝으로 쓴다.
"""
from .common import make_item

GAME = 'rps_pattern'
NAME = '가위바위보 상대 패턴'
FACET = '상대 파악'

HANDS = ['가위', '바위', '보']
STANDARD = {'가위': '보', '바위': '가위', '보': '바위'}  # 키가 값을 이긴다
REVERSED = {v: k for k, v in STANDARD.items()}


def winner_of(beats, h):
    """h를 이기는 손."""
    return next(x for x in HANDS if beats[x] == h)


# (이름, 설명, 다음 손 함수(beats, 내 직전 손, 상대 직전 손))
PATTERNS = [
    ('가', '자기가 직전 판에 낸 손을 다시 낸다.', lambda b, me, op: op),
    ('나', '자기가 직전 판에 낸 손을 이기는 손을 낸다.', lambda b, me, op: winner_of(b, op)),
    ('다', '자기가 직전 판에 낸 손에 지는 손을 낸다.', lambda b, me, op: b[op]),
    ('라', '내가 직전 판에 낸 손을 따라 낸다.', lambda b, me, op: me),
    ('마', '내가 직전 판에 낸 손을 이기는 손을 낸다.', lambda b, me, op: winner_of(b, me)),
    ('바', '내가 직전 판에 낸 손에 지는 손을 낸다.', lambda b, me, op: b[me]),
    ('사', '직전 판에서 자기가 이겼으면 같은 손을 다시 내고, 지거나 비겼으면 자기가 직전 판에 낸 손을 이기는 손을 낸다.',
     lambda b, me, op: op if b[op] == me else winner_of(b, op)),
]
LABELS = [f'({p[0]}) {p[1]}' for p in PATTERNS]


def rules_text(beats):
    return ('나와 상대가 가위바위보를 여러 판 한다. 두 사람이 동시에 가위, 바위, 보 중 하나를 낸다. '
            + ', '.join(f'{a}는 {b}를 이긴다' for a, b in beats.items()) + '. 같은 것을 내면 비긴다.')


def fits(beats, pattern, history):
    f = pattern[2]
    return all(history[t][1] == f(beats, *history[t - 1]) for t in range(1, len(history)))


def matching(beats, history):
    return [p for p in PATTERNS if fits(beats, p, history)]


def predict(beats, pattern, history):
    return pattern[2](beats, *history[-1])


def answer(beats, pattern, history, ask):
    nxt = predict(beats, pattern, history)
    if ask == 'next':
        return nxt
    if ask == 'win':
        return winner_of(beats, nxt)
    if ask == 'lose':
        return beats[nxt]
    return next(l for l, p in zip(LABELS, PATTERNS) if p is pattern)  # ask == 'which'


def render(history):
    return '\n'.join(f'{t + 1}판: 나 {me}, 상대 {op}' for t, (me, op) in enumerate(history))


def make_history(rng, beats, pattern, n):
    h = [(rng.choice(HANDS), rng.choice(HANDS))]
    for _ in range(n - 1):
        h.append((rng.choice(HANDS), pattern[2](beats, *h[-1])))
    return h


QUESTIONS = {'next': '다음 판에 상대가 낼 손은?', 'win': '다음 판에 내가 이기려면 무엇을 내야 하는가?',
             'lose': '다음 판에 내가 지려면 무엇을 내야 하는가?', 'which': '상대가 따르는 방식은?'}


def generate(rng, per_stage):
    items = []
    std, rev = rules_text(STANDARD), rules_text(REVERSED)
    k = 0
    # ① 방식을 알려 준다
    for i in range(per_stage):
        p = PATTERNS[i % len(PATTERNS)]
        ask = ('next', 'win', 'lose')[rng.randrange(3)]
        # 기록은 첫 판 하나만 준다. 여러 판을 주면 상성을 뒤집은 짝 문항에서 기록이 방식과 어긋난다.
        hist = make_history(rng, STANDARD, p, 1)
        sit = (f'상대는 둘째 판부터 늘 이렇게 손을 낸다: {p[1]}\n지금까지 기록:\n' + render(hist))
        ans, twin = answer(STANDARD, p, hist, ask), answer(REVERSED, p, hist, ask)
        base = make_item(rng, GAME, '1-판정', i, {'규칙': std, '상황': sit}, QUESTIONS[ask], HANDS, ans)
        items.append(base)
        if twin != ans:
            items.append(make_item(rng, GAME, '2-변형', k, {'규칙': rev, '상황': sit}, QUESTIONS[ask], HANDS, twin,
                                   original=ans, twin_of=base['id'], order=base['options']))
            k += 1
    # ③ 방식을 기록에서 찾는다
    intro = ('상대는 둘째 판부터 늘 아래 방식 중 하나만 따라 손을 낸다. 어느 방식인지는 알려 주지 않았다.\n'
             + '\n'.join(LABELS))
    for i in range(per_stage):
        p = PATTERNS[i % len(PATTERNS)]
        # 뒤집힌 규칙에서 기록은 대응하는 방식((나)↔(다), (마)↔(바))에 맞고 다음 손은 같다. 그래서 짝은
        # '방식'(상성을 쓰는 방식일 때)이나 '이기려면'을 물을 때만 생긴다. (사)는 뒤집힌 규칙에서 맞는 방식이 없다.
        want_twin = i % 4 != 3 and p[0] != '사'
        if want_twin:
            ask = 'which' if p[0] in '나다마바' and i % 2 == 0 else 'win'
        else:
            ask = ('which', 'next', 'win')[i % 3] if p[0] == '사' else ('which' if p[0] in '가라' else 'next')
        for _ in range(10000):
            hist = make_history(rng, STANDARD, p, rng.choice([5, 6, 7]))
            if len(matching(STANDARD, hist)) != 1:
                continue
            ans = answer(STANDARD, p, hist, ask)
            rm = matching(REVERSED, hist)
            twin = answer(REVERSED, rm[0], hist, ask) if len(rm) == 1 else None
            if (twin is not None and twin != ans) == want_twin:
                break
        else:
            raise AssertionError('no history found')
        assert matching(STANDARD, hist) == [p]
        opts = LABELS if ask == 'which' else HANDS
        sit = intro + '\n지금까지 기록:\n' + render(hist)
        base = make_item(rng, GAME, '3-한수', i, {'규칙': std, '상황': sit}, QUESTIONS[ask], opts, ans)
        items.append(base)
        if want_twin:
            items.append(make_item(rng, GAME, '2-변형', 100 + i, {'규칙': rev, '상황': sit}, QUESTIONS[ask], opts,
                                   twin, original=ans, twin_of=base['id'], order=base['options']))
    return items
