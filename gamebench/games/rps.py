"""가위바위보 (참조 구현).

① 판정: 상대 손이 주어졌을 때 이기기·비기기·지기 위한 손.
③ 한 수: 상대가 두 손 중 하나를 낸다는 것만 알 때, 지지 않는 손.
② 변형: 같은 상황·보기에서 상성이 모두 뒤집힌 규칙("바위가 보를 이긴다" 등).
"""
from .common import make_item

GAME = 'rps'
NAME = '가위바위보'
FACET = '규칙 판정'

HANDS = ['가위', '바위', '보']
STANDARD = {'가위': '보', '바위': '가위', '보': '바위'}      # 키가 값을 이긴다
REVERSED = {v: k for k, v in STANDARD.items()}                # 모든 상성을 뒤집은 규칙

GOALS = {'이기려면': 'win', '비기려면': 'draw', '지려면': 'lose'}


def rules_text(beats):
    return ('두 사람이 동시에 가위, 바위, 보 중 하나를 낸다. '
            + ', '.join(f'{a}는 {b}를 이긴다' for a, b in beats.items())
            + '. 같은 것을 내면 비긴다.')


def solve(beats, opponent, goal):
    if goal == 'draw':
        return opponent
    if goal == 'win':
        return next(h for h in HANDS if beats[h] == opponent)
    return beats[opponent]


def never_loses(beats, pair):
    safe = [h for h in HANDS if all(o == h or beats[h] == o for o in pair)]
    assert len(safe) == 1, (beats, pair, safe)
    return safe[0]


def generate(rng, per_stage):
    items = []
    cases = [(opp, g) for opp in HANDS for g in GOALS]  # 9가지
    for i in range(per_stage):
        opp, goal_ko = cases[i % len(cases)]
        state = {'규칙': rules_text(STANDARD), '상황': f'상대가 {opp}를 냈다.'}
        q = f'내가 {goal_ko} 무엇을 내야 하는가?'
        base = make_item(rng, GAME, '1-판정', i, state, q, HANDS, solve(STANDARD, opp, GOALS[goal_ko]))
        items.append(base)
        if GOALS[goal_ko] == 'draw':
            continue  # 비기기는 상성을 뒤집어도 답이 같아 짝이 되지 않는다
        tstate = {'규칙': rules_text(REVERSED), '상황': state['상황']}
        items.append(make_item(rng, GAME, '2-변형', i, tstate, q, HANDS, solve(REVERSED, opp, GOALS[goal_ko]),
                               original=solve(STANDARD, opp, GOALS[goal_ko]), twin_of=base['id'],
                               order=base['options']))
    # ③ 상대가 두 손 중 하나를 낼 때 어떤 경우에도 지지 않는 손 (정확히 하나)
    q3 = '상대가 무엇을 내든 지지 않으려면 나는 무엇을 내야 하는가?'
    for i, pair in enumerate([('가위', '보'), ('바위', '가위'), ('보', '바위')]):
        sit = f'상대는 {pair[0]} 아니면 {pair[1]}를 낸다. 둘 중 무엇을 낼지는 모른다.'
        base = make_item(rng, GAME, '3-한수', i, {'규칙': rules_text(STANDARD), '상황': sit}, q3, HANDS, never_loses(STANDARD, pair))
        items.append(base)
        items.append(make_item(rng, GAME, '2-변형', 100 + i, {'규칙': rules_text(REVERSED), '상황': sit}, q3, HANDS,
                               never_loses(REVERSED, pair), original=never_loses(STANDARD, pair), twin_of=base['id'], order=base['options']))
    return items
