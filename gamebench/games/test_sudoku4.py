"""미니 스도쿠: 규칙 문구에서 손으로 구한 예제."""
from games import sudoku4
from games.sudoku4 import CELLS, SOLUTIONS, determined
from build import game_rng


def board(rows):
    return ''.join(rows)


def test_counts():
    assert len(SOLUTIONS['box']) == 288 and len(SOLUTIONS['alt']) == 288


def test_row_forced():
    b = board(['123.', '....', '....', '....'])
    assert determined(b, 'box')[CELLS.index('A4')] == '4'


def test_box_vs_alt_by_hand():
    # A . 1 . 4 / B . 2 . . / C . . . . / D . 3 . .
    b = board(['.1.4', '.2..', '....', '.3..'])
    db, da = determined(b, 'box'), determined(b, 'alt')
    # 구역 A1·A2·B1·B2에 1,2가 있으니 A1은 3 또는 4, 가로줄 A에 4가 있으니 A1=3, 그러면 A3=2
    assert db[CELLS.index('A1')] == '3' and db[CELLS.index('A3')] == '2'
    assert db[CELLS.index('B1')] == '4'
    # 구역 A1·A2·D1·D2에 1,3이 있으니 A1은 2 또는 4, 가로줄 A에 4가 있으니 A1=2, 그러면 A3=3
    assert da[CELLS.index('A1')] == '2' and da[CELLS.index('A3')] == '3'
    assert CELLS.index('B1') not in da


def test_naked_single_by_hand():
    # A . 3 . . / C . . 4 2 / D 2 . 1 3: A3은 가로줄 A의 3, 세로줄 3의 4·1을 빼면 2
    b = board(['.3..', '....', '..42', '2.13'])
    assert determined(b, 'box')[CELLS.index('A3')] == '2'


def test_twins_differ():
    items = sudoku4.generate(game_rng(20260927, 'sudoku4'), 10)
    by_id = {x['id']: x for x in items}
    twins = [x for x in items if x['stage'] == '2-변형']
    assert twins
    for x in twins:
        t = by_id[x['twin_of']]
        assert x['answer'] != t['answer'] and x['options'] == t['options'] and x['state']['판'] == t['state']['판']
