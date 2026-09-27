"""미로 탈출 정답 계산기 검사. 기대값은 판을 보고 손으로 찾았다."""
from build import game_rng
from games import maze as mz

# A: S D E
# B: . # #
# C: K . .
KEYMAZE = ['SDE', '.##', 'K..']


def test_key_maze():
    # 잠긴 문: 아래로 K(C1)까지 가서 열쇠를 얻고 돌아와 D를 지나 E. 6번 이동, 경로 하나
    assert mz.shortest(KEYMAZE, 'locked') == (6, 1, {'아래'})
    assert mz.unique_first(KEYMAZE, 'locked') == '아래'
    # 열린 문: 오른쪽으로 두 번
    assert mz.shortest(KEYMAZE, 'open') == (2, 1, {'오른쪽'})


def test_simple_and_ties():
    assert mz.unique_first(['S.E'], 'locked') == '오른쪽'
    assert mz.shortest(['S#E'], 'locked') is None
    # S(A1)에서 E(B2)까지 오른쪽-아래, 아래-오른쪽 두 길 → 경로가 하나가 아님
    assert mz.shortest(['S.', '.E'], 'locked') == (2, 2, {'오른쪽', '아래'})
    assert mz.unique_first(['S.', '.E'], 'locked') is None


def test_step():
    s = (0, 0, False)
    assert mz.step(KEYMAZE, s, '오른쪽', 'locked') is None       # 열쇠 없이 D
    assert mz.step(KEYMAZE, s, '오른쪽', 'open') == (0, 1, False)
    assert mz.step(KEYMAZE, s, '위', 'locked') is None           # 판 밖
    assert mz.step(KEYMAZE, (1, 0, False), '아래', 'locked') == (2, 0, True)  # K에 들어가면 열쇠


def test_twins_differ_only_in_rule():
    items = mz.generate(game_rng(20260927, mz.GAME), 10)
    by_id = {x['id']: x for x in items}
    for x in items:
        assert not any(w in x['state']['규칙'] for w in ('원래', '변형', '바뀐'))
        if x['stage'] == '2-변형':
            t = by_id[x['twin_of']]
            assert x['state']['판'] == t['state']['판'] and x['state']['규칙'] != t['state']['규칙']
            assert x['answer'] != x['original_answer'] == t['answer']
