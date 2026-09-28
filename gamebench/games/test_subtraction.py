"""뺄셈 게임: 규칙 문구에서 손으로 구한 예제."""
from games import subtraction
from games.subtraction import mover_wins, winning_counts
from build import game_rng


def test_by_hand():
    # 1~3개, 마지막 돌을 가져가면 이긴다: 4의 배수를 남기면 이긴다
    assert winning_counts(10, (3, False), 3) == [2]
    assert winning_counts(8, (3, False), 3) == []
    assert not mover_wins(4, (3, False))
    # 1~5개: 6의 배수를 남긴다 / 1~6개: 7의 배수를 남긴다
    assert winning_counts(11, (5, False), 6) == [5]
    assert winning_counts(11, (6, False), 6) == [4]
    # 마지막 돌을 가져가면 진다, 1~3개: 4로 나눈 나머지가 1인 수를 남긴다
    assert winning_counts(10, (3, True), 3) == [1]
    assert not mover_wins(1, (3, True))
    assert mover_wins(2, (3, True))


def test_twins_differ():
    items = subtraction.generate(game_rng(20260927, 'subtraction'), 10)
    by_id = {x['id']: x for x in items}
    twins = [x for x in items if x['stage'] == '2-변형']
    assert twins
    for x in twins:
        t = by_id[x['twin_of']]
        assert x['answer'] != t['answer'] and x['options'] == t['options']
        assert x['state']['규칙'] != t['state']['규칙']
