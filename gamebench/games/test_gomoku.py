"""오목 퍼즐 정답 계산기 손 검사."""
import random

from games import gomoku as g

E = '.' * 9


def cell(name):
    return g.CELLS.index(name)


def test_overline_winner():
    b = g.parse(['XXXXXX...', E, 'OO.OO.O..', E, 'O..O.....', E, E, E, E])
    # X가 가로 6개: 자유룰은 X 승, 정확히 다섯 규칙에서는 아직 없음
    assert g.winner(b, 'free') == 'X'
    assert g.winner(b, 'exact') is None
    assert g.verdict(b, 'free', 'lose') == 'O'


def test_wins_at_gap_and_end():
    b = g.parse(['XXX.XX...', 'OOOO.....', E, E, E, E, E, E, E])
    # A4를 채우면 A1~A6 6개: 자유룰에서만 이긴다. O는 B5에 두면 B1~B5 5개.
    assert g.wins_at(b, cell('A4'), 'X', 'free')
    assert not g.wins_at(b, cell('A4'), 'X', 'exact')
    assert g.win_points(b, 'O', 'free') == {cell('B5')} == g.win_points(b, 'O', 'exact')


def test_open_four_is_the_only_forced_win():
    b = g.parse([E, E, E, E, 'O.XXX....', E, E, E, 'O.O......'])
    # E6에 두면 E3~E6 넷, 이길 빈칸 E2·E7 두 곳 → 반드시 이긴다. E2는 E1이 O라 이길 빈칸이 E6 하나뿐.
    assert g.forced_wins(b, 'free') == [cell('E6')]


def test_must_win_now_when_opponent_has_four():
    b = g.parse(['XXXX.....', E, E, E, 'OOOO.....', E, E, E, E])
    # X가 A5로 바로 이긴다. 다른 수는 O가 E5로 이긴다.
    assert g.forced_wins(b, 'free') == [cell('A5')]


def test_block_only_is_not_a_forced_win():
    b = g.parse(['OOOO.....', E, E, 'X.......X', E, E, 'X.......X', E, E])
    # O가 A5로 이길 수 있다. X가 막아도 X는 이길 빈칸을 두 곳 만들지 못한다.
    assert g.win_points(b, 'O', 'free') == {cell('A5')}
    assert g.forced_wins(b, 'free') == []


def test_exact_five_twin():
    b = g.parse(['XXX.XX...', E, 'OOO.OO...', E, 'O.XXX....', E, E, E, 'O.O......'])
    # 자유룰: X는 A4로 바로 이기고, O가 C4로 이길 수 있어 다른 수는 안 된다.
    assert g.forced_wins(b, 'free') == [cell('A4')]
    # 정확히 다섯: A4·C4는 6개라 이기지 못한다. E6에 두면 E2(E2~E6)·E7(E3~E7) 두 곳이 정확히 다섯 → E6만.
    assert g.forced_wins(b, 'exact') == [cell('E6')]


def test_twins_change_answer():
    items = g.generate(random.Random(7), 10)
    twins = [x for x in items if x['stage'] == '2-변형']
    assert twins and all(x['answer'] != x['original_answer'] for x in twins)
