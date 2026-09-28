"""업다운: 규칙 문구에서 손으로 구한 예제."""
from games import updown
from games.updown import best_among, interval, need, worst
from build import game_rng


def test_interval_by_hand():
    h = [(50, '업'), (75, '다운')]
    assert interval(h, 'base') == (51, 74)
    assert interval(h, 'rev') is None          # 50보다 작고 75보다 큰 수는 없다
    h = [(30, '업'), (60, '업')]
    assert interval(h, 'base') == (61, 100)
    assert interval(h, 'rev') == (1, 29)


def test_best_guess_by_hand():
    assert need(7) == 3 and need(1) == 1 and need(0) == 0
    # 94~100 (7개): 97을 부르면 94~96 또는 98~100이 남아 최대 3번
    assert worst((94, 100), 97) == 3
    assert worst((94, 100), 96) == 4           # 97~100(4개)이 남으면 2번 더
    assert best_among((1, 31), ['15', '16', '17', '1']) == '16'
    assert best_among((94, 100), ['16', '97', '98']) == '97'


def test_twins_differ():
    items = updown.generate(game_rng(20260927, 'updown'), 10)
    by_id = {x['id']: x for x in items}
    twins = [x for x in items if x['stage'] == '2-변형']
    assert twins
    for x in twins:
        t = by_id[x['twin_of']]
        assert x['answer'] != t['answer'] and x['options'] == t['options']
