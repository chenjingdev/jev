"""하이로우 정답 계산기 검사. 기대값은 규칙 문구를 보고 손으로 셌다."""
from fractions import Fraction as F

from build import game_rng
from games import hilo as h


def test_hand_probs():
    # 지금 8, 남은 2·9·8·A: 하이는 9·A 2장, 로우는 2 1장, 8은 둘 다 틀림
    assert h.probs('8', ['2', '9', '8', 'A'], 'base') == (F(2, 4), F(1, 4))
    # 같은 숫자를 하이로 치면 8도 하이
    assert h.probs('8', ['2', '9', '8', 'A'], 'tiehi') == (F(3, 4), F(1, 4))
    # A가 가장 낮으면 지금 5에 대해 A는 로우
    assert h.probs('5', ['A', 'A', 'K'], 'base') == (F(3, 3), F(0))
    assert h.probs('5', ['A', 'A', 'K'], 'alow') == (F(1, 3), F(2, 3))
    # 지금 A: A가 높으면 모두 로우, 낮으면 모두 하이
    assert h.probs('A', ['3', '10'], 'base') == (F(0), F(1))
    assert h.probs('A', ['3', '10'], 'alow') == (F(1), F(0))


def test_hand_choice():
    assert h.choice('7', ['2', '3', '4', 'K'], 'base') == '로우'                     # 3/4 vs 1/4
    assert h.choice('7', ['2', 'K'], 'base') == h.CHOICES[2]                         # 1/2 = 1/2
    assert h.choice('7', ['2', '3', '4', '5', '8', '9', '10', 'Q', 'K', 'A'], 'base') == '하이'  # 6/10 vs 4/10
    assert h.choice('7', ['2', '3', '4', '8', '9', '10', 'J'], 'base') is None       # 4/7 vs 3/7, 차이 1/7 < 0.15
    assert h.choice('7', ['7', '7', '2'], 'tiehi') == '하이'                          # 2/3 vs 1/3


def test_twins_differ_only_in_rule():
    items = h.generate(game_rng(20260927, h.GAME), 10)
    by_id = {x['id']: x for x in items}
    for x in items:
        assert not any(w in x['state']['규칙'] for w in ('원래', '변형', '바뀐'))
        if x['stage'] == '2-변형':
            t = by_id[x['twin_of']]
            assert x['state']['상황'] == t['state']['상황'] and x['state']['규칙'] != t['state']['규칙']
            assert x['answer'] != x['original_answer'] == t['answer']
