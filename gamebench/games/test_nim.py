"""님: 규칙 문구에서 손으로 구한 예제."""
from games import nim
from games.nim import mover_wins, winning_moves
from build import game_rng


def test_normal_by_hand():
    # 3,4,5: 1번 무더기에서 2개를 가져가 1,4,5를 남기면 상대가 무엇을 하든 짝을 맞출 수 있다
    assert winning_moves((3, 4, 5), False) == [(0, 2)]
    # 1,2,3: 어떻게 가져가도 상대가 맞대응한다
    assert winning_moves((1, 2, 3), False) == []
    assert not mover_wins((1, 1), False)       # 하나 가져가면 상대가 마지막 돌을 가져간다
    assert mover_wins((1, 1), True)            # 같은 판, 마지막 돌을 가져가면 지는 규칙


def test_misere_by_hand():
    # 1,1,2: 이기는 규칙이면 2개를 다 가져가 1,1을 남긴다
    assert winning_moves((1, 1, 2), False) == [(2, 2)]
    # 지는 규칙이면 3번 무더기에서 1개만 가져가 1,1,1을 남긴다 (상대, 나, 상대 순으로 상대가 마지막 돌)
    assert winning_moves((1, 1, 2), True) == [(2, 1)]
    assert not mover_wins((1, 1, 1), True)
    assert mover_wins((1, 1, 1), False)


def test_twins_differ():
    items = nim.generate(game_rng(20260927, 'nim'), 10)
    by_id = {x['id']: x for x in items}
    twins = [x for x in items if x['stage'] == '2-변형']
    assert twins
    for x in twins:
        t = by_id[x['twin_of']]
        assert x['answer'] != t['answer'] and x['options'] == t['options']
        assert '진다' in x['state']['규칙'] and '이긴다' in t['state']['규칙']
