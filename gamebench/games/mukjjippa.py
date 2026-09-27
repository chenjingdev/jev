"""묵찌빠.

규칙 문구는 NEXT(다른 손을 냈을 때 누가 공격자가 되는지)에서 만들고, 풀이기도 같은 값을 읽는다.
① 판정: 공격자와 두 손이 주어졌을 때 이번 판의 결과, 또는 상대 손을 알 때 원하는 결과(이기기·지기·공격자 되기)를 내는 손.
③ 한 수: 상대가 두 손 중 하나를 낸다는 것만 알 때, 지지 않는 손(수비) / 공격권을 잃지 않는 손(공격).
② 변형: 같은 상황·보기에서 "다른 손을 내면 그 판에서 진 손을 낸 사람이 공격자가 된다". 답이 달라지는 문항만 짝으로 쓴다.
"""
from .common import make_item

GAME = 'mukjjippa'
NAME = '묵찌빠'
FACET = '규칙 판정'

HANDS = ['묵', '찌', '빠']
BEATS = {'찌': '빠', '빠': '묵', '묵': '찌'}  # 키가 값을 이긴다
OUTCOMES = ['내가 이긴다', '상대가 이긴다', '내가 공격자가 되어 다시 낸다', '상대가 공격자가 되어 다시 낸다']


def obj(w):
    return w + ('을' if (ord(w[-1]) - 0xAC00) % 28 else '를')


def topic(w):
    return w + ('은' if (ord(w[-1]) - 0xAC00) % 28 else '는')


def rules_text(next_attacker):
    who = '이긴' if next_attacker == 'winner' else '진'
    return ('두 사람이 묵, 찌, 빠 중 하나를 동시에 낸다. '
            + ', '.join(f'{topic(a)} {obj(b)} 이긴다' for a, b in BEATS.items())
            + '. 공격권을 가진 사람을 공격자라 한다. 두 사람이 같은 손을 내면 공격자가 게임에서 이긴다. '
            f'서로 다른 손을 내면 그 판에서 {who} 손을 낸 사람이 공격자가 되어 다시 낸다.')


def outcome(next_attacker, attacker, mine, opp):
    """attacker: '나' 또는 '상대'."""
    if mine == opp:
        return '내가 이긴다' if attacker == '나' else '상대가 이긴다'
    i_won = BEATS[mine] == opp
    me_next = i_won if next_attacker == 'winner' else not i_won
    return OUTCOMES[2] if me_next else OUTCOMES[3]


def hand_for(next_attacker, attacker, opp, target):
    hs = [h for h in HANDS if outcome(next_attacker, attacker, h, opp) == target]
    assert len(hs) == 1, (next_attacker, attacker, opp, target, hs)
    return hs[0]


def safe_hand(next_attacker, attacker, pair, bad):
    hs = [h for h in HANDS if all(outcome(next_attacker, attacker, h, o) not in bad for o in pair)]
    assert len(hs) == 1, (next_attacker, attacker, pair, hs)
    return hs[0]


GOAL_Q = {
    OUTCOMES[0]: '이번 판에서 내가 게임을 이기려면 나는 무엇을 내야 하는가?',
    OUTCOMES[1]: '이번 판에서 내가 게임을 지려면 나는 무엇을 내야 하는가?',
    OUTCOMES[2]: '이번 판 뒤 내가 공격자가 되려면 나는 무엇을 내야 하는가?',
    OUTCOMES[3]: '이번 판 뒤 상대가 공격자가 되려면 나는 무엇을 내야 하는가?',
}


def attacker_line(attacker):
    return '지금 공격자는 나다.' if attacker == '나' else '지금 공격자는 상대다.'


def generate(rng, per_stage):
    items = []
    std, alt = rules_text('winner'), rules_text('loser')
    outcome_cases = [(a, m, o) for a in ('나', '상대') for m in HANDS for o in HANDS]
    goal_cases = [(a, o, t) for a in ('나', '상대') for o in HANDS
                  for t in (OUTCOMES[0] if a == '나' else OUTCOMES[1], OUTCOMES[2], OUTCOMES[3])]
    rng.shuffle(outcome_cases); rng.shuffle(goal_cases)
    n_out = per_stage // 2
    k = 0
    for i in range(per_stage):
        if i < n_out:
            a, m, o = outcome_cases[i % len(outcome_cases)]
            sit = f'{attacker_line(a)} 이번 판에 나는 {obj(m)}, 상대는 {obj(o)} 냈다.'
            q, opts = '이번 판의 결과는?', OUTCOMES
            ans, twin = outcome('winner', a, m, o), outcome('loser', a, m, o)
        else:
            a, o, t = goal_cases[(i - n_out) % len(goal_cases)]
            sit = f'{attacker_line(a)} 상대가 이번 판에 {obj(o)} 낸다는 것을 알고 있다.'
            q, opts = GOAL_Q[t], HANDS
            ans, twin = hand_for('winner', a, o, t), hand_for('loser', a, o, t)
        base = make_item(rng, GAME, '1-판정', i, {'규칙': std, '상황': sit}, q, opts, ans)
        items.append(base)
        if twin != ans:
            items.append(make_item(rng, GAME, '2-변형', k, {'규칙': alt, '상황': sit}, q, opts, twin,
                                   original=ans, twin_of=base['id'], order=base['options']))
            k += 1
    # ③ 상대가 두 손 중 하나를 낸다. 수비면 지지 않는 손, 공격이면 공격권을 잃지 않는 손.
    roles = {
        '상대': ({OUTCOMES[1]}, '상대가 둘 중 무엇을 내든 이번 판에서 지지 않으려면 나는 무엇을 내야 하는가?'),
        '나': ({OUTCOMES[1], OUTCOMES[3]}, '상대가 둘 중 무엇을 내든 이번 판 뒤 상대가 공격자가 되지 않게 하려면 나는 무엇을 내야 하는가?'),
    }
    cases3 = [(a, p) for a in ('나', '상대') for p in (('묵', '찌'), ('찌', '빠'), ('빠', '묵'))]
    rng.shuffle(cases3)
    for i, (a, pair) in enumerate(cases3[:per_stage]):
        pair = tuple(rng.sample(pair, 2))
        bad, q = roles[a]
        sit = f'{attacker_line(a)} 상대는 이번 판에 {pair[0]} 아니면 {obj(pair[1])} 낸다. 둘 중 무엇을 낼지는 모른다.'
        ans, twin = safe_hand('winner', a, pair, bad), safe_hand('loser', a, pair, bad)
        base = make_item(rng, GAME, '3-한수', i, {'규칙': std, '상황': sit}, q, HANDS, ans)
        items.append(base)
        if twin != ans:
            items.append(make_item(rng, GAME, '2-변형', 100 + i, {'규칙': alt, '상황': sit}, q, HANDS, twin,
                                   original=ans, twin_of=base['id'], order=base['options']))
    return items
