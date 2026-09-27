"""숫자야구: 규칙 문구에서 손으로 구한 예제."""
from games import bulls_cows
from games.bulls_cows import consistent, fmt, score
from build import game_rng


def test_score_by_hand():
    # 비밀 769, 추측 791: 7은 자리까지 같다, 9는 있지만 자리가 다르다, 1은 없다
    assert fmt(score('769', '791', 'base')) == '1S 1B'
    assert fmt(score('769', '791', 'total')) == '1S 2B'
    assert fmt(score('123', '321', 'base')) == '1S 2B'
    assert fmt(score('123', '321', 'total')) == '1S 3B'
    assert fmt(score('123', '456', 'base')) == '0S 0B'
    assert fmt(score('123', '123', 'base')) == '3S 0B'


def test_history_by_hand():
    h = [('593', '2S 0B'), ('578', '1S 0B'), ('127', '0S 0B')]
    assert consistent('543', h, 'base')
    assert not consistent('583', h, 'base')   # 578과 비교하면 8이 볼이라 1S 1B
    # 볼에 스트라이크도 세는 규칙: 1S 1B는 겹치는 숫자가 하나이고 그게 자리까지 같다는 뜻
    h2 = [('251', '0S 0B'), ('482', '1S 1B'), ('589', '1S 1B')]
    assert consistent('984', h2, 'base') and not consistent('984', h2, 'total')
    assert consistent('786', h2, 'total') and not consistent('786', h2, 'base')


def test_twins_differ():
    items = bulls_cows.generate(game_rng(20260927, 'bulls_cows'), 10)
    by_id = {x['id']: x for x in items}
    twins = [x for x in items if x['stage'] == '2-변형']
    assert twins
    for x in twins:
        t = by_id[x['twin_of']]
        assert x['answer'] != t['answer'] and x['options'] == t['options']
