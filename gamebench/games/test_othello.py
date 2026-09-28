"""오셀로 정답 계산기 손 검사."""
import random

from games import othello as g


def B(rows):
    assert len(rows) == 6 and all(len(r) == 6 for r in rows)
    return ''.join(rows)


def cell(name):
    return g.CELLS.index(name)


def test_start_legal_moves():
    # 시작 판: C3=O, C4=X, D3=X, D4=O. X는 B3, C2, D5, E4에 둘 수 있고 각각 1개를 뒤집는다.
    assert sorted(g.CELLS[i] for i in g.legal(g.START, 'X', 'standard')) == ['B3', 'C2', 'D5', 'E4']
    assert all(len(g.flips(g.START, i, 'X', 'standard')) == 1 for i in g.legal(g.START, 'X', 'standard'))


def test_diagonal_flip_and_nodiag():
    b = B(['X.....',
           '.O....',
           '..O...',
           '......',
           '......',
           '......'])
    # D4에서 왼쪽 위로 C3(O), B2(O), A1(X) → 2개. 대각선을 안 치면 0개(둘 수 없다).
    assert sorted(g.CELLS[i] for i in g.flips(b, cell('D4'), 'X', 'standard')) == ['B2', 'C3']
    assert g.flips(b, cell('D4'), 'X', 'nodiag') == []


def test_two_directions():
    b = B(['......',
           '...X..',
           '...O..',
           'XOO...',
           '......',
           '......'])
    # D4에서 왼쪽 D3·D2(O) 끝에 D1(X) → 2개, 위로 C4(O) 끝에 B4(X) → 1개. 합 3개, 대각선 없음.
    assert len(g.flips(b, cell('D4'), 'X', 'standard')) == 3
    assert len(g.flips(b, cell('D4'), 'X', 'nodiag')) == 3


def test_gap_blocks_flip():
    b = B(['......',
           '......',
           '......',
           'X.OX..',
           '......',
           '......'])
    # D2가 비어 있어 D3의 O는 X 사이에 끼지 않는다. D2에 두면 오른쪽 D3(O) 끝에 D4(X) → 1개.
    assert g.flips(b, cell('D2'), 'X', 'standard') == [cell('D3')]
    assert g.flips(b, cell('E3'), 'X', 'standard') == []


def test_most_flips_and_lookahead():
    b = B(['X....X',
           '.O..O.',
           '..OO..',
           '......',
           '......',
           '......'])
    # D4: 왼쪽 위로 C3(O), B2(O), A1(X) → 2개. D3: 오른쪽 위로 C4(O), B5(O), A6(X) → 2개. 최댓값이 둘이다.
    assert len(g.flips(b, cell('D4'), 'X', 'standard')) == 2
    assert len(g.flips(b, cell('D3'), 'X', 'standard')) == 2
    assert g.most_flips(b, 'standard', [cell('D3'), cell('D4')]) is None
    # 시작 판에서 X가 C2에 두면 C3을 뒤집어 X는 C2·C3·C4·D3 4개. O의 응수(B2·B4·D2 등)는 모두 1개씩
    # 뒤집으므로 X는 3개가 남는다. 네 첫 수가 대칭이라 모두 3 → 하나로 정해지지 않는다.
    assert g.after_reply(g.START, cell('C2'), 'standard') == 3
    best, sc = g.lookahead_best(g.START, 'standard')
    assert best is None and set(sc.values()) == {3}


def test_twins_change_answer():
    items = g.generate(random.Random(7), 10)
    twins = [x for x in items if x['stage'] == '2-변형']
    assert twins
    assert all(x['answer'] != x['original_answer'] and '대각선 방향으로는 뒤집지 않는다' in x['state']['규칙']
               for x in twins)
