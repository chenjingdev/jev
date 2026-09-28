"""스네이크 정답 계산기 검사. 기대값은 규칙 문구대로 손으로 따라가 봤다."""
from build import game_rng
from games import snake as sn

B3 = sn.Board(3, 3, [])
BODY = ((1, 1), (1, 0), (0, 0))   # 머리 B2, 몸 B1, 꼬리 A1


def test_moves():
    assert B3.move(BODY, None, '왼쪽', 'wall') is None                        # 몸 B1
    assert B3.move(BODY, None, '위', 'wall') == (((0, 1), (1, 1), (1, 0)), None)  # 꼬리 A1이 비워진다
    # 꼬리 칸으로 들어가도 죽는다 (움직이기 직전 몸이 있던 칸)
    assert B3.move(((0, 1), (1, 1), (1, 0), (0, 0)), None, '왼쪽', 'wall') is None
    # 먹으면 꼬리가 남아 길이 3
    assert B3.move(((1, 1), (1, 0)), (0, 1), '위', 'wall') == (((0, 1), (1, 1), (1, 0)), None)
    # 가장자리: 벽 규칙이면 죽고, 넘어가는 규칙이면 반대편 C2로
    assert B3.move(((0, 1), (1, 1)), None, '위', 'wall') is None
    assert B3.move(((0, 1), (1, 1)), None, '위', 'wrap') == (((2, 1), (0, 1)), None)


def test_survival():
    # 1×4 판, 머리 A2 꼬리 A1: 오른쪽(A3)→오른쪽(A4) 뒤에는 막힌다
    b = sn.Board(1, 4, [])
    body = ((0, 1), (0, 0))
    assert sn.survivable_dirs(b, body, None, 'wall', horizon=2) == ['오른쪽']
    assert sn.survivable_dirs(b, body, None, 'wall', horizon=3) == []
    # 넘어가는 규칙이면 A4에서 오른쪽으로 A1(이미 비워짐)에 나와 계속 돈다
    assert sn.survivable_dirs(b, body, None, 'wrap', horizon=6) == ['오른쪽']


def test_food():
    assert sn.food_first(B3, BODY, (1, 2), 'wall') == (1, {'오른쪽'})
    # 1×5 판, 머리 A2 꼬리 A3, 먹이 A5: 벽 규칙이면 왼쪽(A1)뿐이고 그다음 막힌다
    b = sn.Board(1, 5, [])
    body = ((0, 1), (0, 2))
    assert sn.food_first(b, body, (0, 4), 'wall') == (None, set())
    # 넘어가는 규칙: 왼쪽 A1, 다시 왼쪽이면 A5 먹이 → 2턴
    assert sn.food_first(b, body, (0, 4), 'wrap') == (2, {'왼쪽'})


def test_twins_differ_only_in_rule():
    items = sn.generate(game_rng(20260927, sn.GAME), 10)
    by_id = {x['id']: x for x in items}
    assert any(x['stage'] == '2-변형' for x in items)
    for x in items:
        assert not any(w in x['state']['규칙'] for w in ('원래', '변형', '바뀐'))
        if x['stage'] == '2-변형':
            t = by_id[x['twin_of']]
            assert x['state']['판'] == t['state']['판'] and x['state']['규칙'] != t['state']['규칙']
            assert x['answer'] != x['original_answer'] == t['answer']
