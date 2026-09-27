"""몬티홀 정답 계산기 검사. 기대값은 규칙 문구대로 손으로 베이즈 계산했다."""
from fractions import Fraction as F

from build import game_rng
from games import montyhall as m


def test_classic():
    # 문 3개, 1번 고름, 알고 여는 사회자가 3번을 엶: 그대로 1/3, 2번 2/3
    assert m.posterior(3, 1, 1, (3,), 'know') == {1: F(1, 3), 2: F(2, 3)}
    assert m.best_choice(3, 1, 1, (3,), 'know') == '2번 문으로 바꾼다'
    # 모르고 연 문이 우연히 비었으면 반반
    assert m.posterior(3, 1, 1, (3,), 'blind') == {1: F(1, 2), 2: F(1, 2)}
    assert m.best_choice(3, 1, 1, (3,), 'blind') == m.SAME
    # 자동차 문을 골랐을 때만 문을 여는 사회자: 문이 열렸으면 처음 고른 문이 자동차
    assert m.best_choice(3, 1, 1, (3,), 'carpick') == '처음 고른 1번 문을 그대로 둔다'


def test_lowest_host():
    # 번호가 작은 빈 문부터 여는 사회자, 1번 고름.
    # 3번을 열었다 → 2번이 비었으면 2번을 열었을 것이므로 자동차는 2번
    assert m.posterior(3, 1, 1, (3,), 'low') == {1: F(0), 2: F(1)}
    # 2번을 열었다 → 자동차가 1번이어도(2번 엶), 3번이어도(2번 엶) 같은 일 → 반반
    assert m.posterior(3, 1, 1, (2,), 'low') == {1: F(1, 2), 3: F(1, 2)}


def test_more_doors():
    # 문 4개, 2개 엶: 그대로 1/4, 남은 한 문 3/4
    assert m.posterior(4, 2, 1, (2, 3), 'know') == {1: F(1, 4), 4: F(3, 4)}
    # 문 5개, 1개 엶: 그대로 1/5, 다른 세 문이 각각 4/15 → 가장 좋은 선택이 여럿이라 문항으로 못 쓴다
    assert m.posterior(5, 1, 1, (5,), 'know') == {1: F(1, 5), 2: F(4, 15), 3: F(4, 15), 4: F(4, 15)}
    assert m.best_choice(5, 1, 1, (5,), 'know') is None


def test_twins_differ_only_in_rule():
    items = m.generate(game_rng(20260927, m.GAME), 10)
    by_id = {x['id']: x for x in items}
    for x in items:
        assert not any(w in x['state']['규칙'] for w in ('원래', '변형', '바뀐'))
        if x['stage'] == '2-변형':
            t = by_id[x['twin_of']]
            assert x['state']['상황'] == t['state']['상황'] and x['state']['규칙'] != t['state']['규칙']
            assert x['answer'] != x['original_answer'] == t['answer']
