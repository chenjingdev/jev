"""야추 정답 계산기 검사. 기대값은 규칙 문구를 보고 손으로 계산했다."""
from build import game_rng
from games import yacht as y

TW = lambda name: y.cfg_of(name)


def test_hand_scores():
    assert y.score([2, 2, 2, 3, 3], '풀하우스') == 12
    assert y.score([2, 2, 2, 3, 3], '풀하우스', TW('fh25')) == 25
    assert y.score([6, 6, 6, 6, 6], '풀하우스') == 0          # 다섯 개 모두 같으면 풀하우스 아님
    assert y.score([6, 6, 6, 6, 6], '야추') == 50
    assert y.score([6, 6, 6, 6, 2], '포카드') == 26
    assert y.score([6, 6, 6, 6, 2], '포카드', TW('fk4')) == 24
    assert y.score([1, 2, 3, 4, 6], '스몰 스트레이트') == 15
    assert y.score([1, 2, 3, 5, 6], '스몰 스트레이트') == 0
    assert y.score([2, 3, 4, 5, 6], '라지 스트레이트') == 30
    assert y.score([2, 3, 4, 5, 6], '라지 스트레이트', TW('ls40')) == 40
    assert y.score([5, 5, 1, 2, 5], '파이브(5)') == 15
    assert y.score([5, 5, 1, 2, 5], '파이브(5)', TW('dbl5')) == 30
    assert y.score([5, 5, 1, 2, 5], '초이스') == 18


def test_hand_best():
    # 1,2,3,4,6: 초이스 16 > 스몰 15. 스몰이 30점이면 스몰.
    assert y.best_cat([1, 2, 3, 4, 6], ['초이스', '스몰 스트레이트']) == '초이스'
    assert y.best_cat([1, 2, 3, 4, 6], ['초이스', '스몰 스트레이트'], TW('ss30')) == '스몰 스트레이트'
    # 풀하우스(합)와 초이스는 같은 점수 → 최댓값이 둘이라 문항으로 못 쓴다
    assert y.best_cat([2, 2, 2, 3, 3], ['초이스', '풀하우스']) is None
    # 6,6,6,1,2: 식스 18 < 초이스 21, 식스 두 배면 36
    assert y.best_cat([6, 6, 6, 1, 2], ['식스(6)', '초이스']) == '초이스'
    assert y.best_cat([6, 6, 6, 1, 2], ['식스(6)', '초이스'], TW('dbl6')) == '식스(6)'


def test_twins_differ_only_in_rule():
    items = y.generate(game_rng(20260927, y.GAME), 10)
    by_id = {x['id']: x for x in items}
    for x in items:
        assert not any(w in x['state']['규칙'] for w in ('원래', '변형', '바뀐'))
        if x['stage'] == '2-변형':
            t = by_id[x['twin_of']]
            assert x['state']['상황'] == t['state']['상황'] and x['state']['규칙'] != t['state']['규칙']
            assert x['answer'] != x['original_answer'] == t['answer']
