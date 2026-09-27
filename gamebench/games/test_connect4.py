"""사목 정답 계산기 손 검사. 기대값은 규칙 문구에서 손으로 따졌다."""
import random

from games import connect4 as g


def cols(*names):
    return [int(n) - 1 for n in names]


def test_drop_and_diag_only_winner():
    b = g.parse(['...X.',
                 '..XO.',
                 '.XOO.',
                 'XOOX.'])
    # X가 D1-C2-B3-A4 대각선으로 4개를 이었다. 가로·세로로 이은 4개는 없다.
    assert g.winner(b, 'standard') == 'X'
    assert g.winner(b, 'nodiag') is None
    assert g.verdict(b, 'standard', 'lose') == 'O'
    assert g.verdict(b, 'nodiag', 'win') == '아직 없음'
    assert g.drop(b, 4) == g.CELLS.index('D5')
    assert g.drop(b, 3) is None            # 4열은 꽉 찼다
    assert g.legal_cols(b) == cols('1', '2', '3', '5')


def test_immediate_win_scores_win():
    b = g.parse(['.....',
                 '.....',
                 'OO...',
                 'XXX.O'])
    # 4열에 넣으면 D4에 놓여 D1~D4 가로 4개
    vals = g.move_values(b, 'standard')
    assert vals[3] == 1
    assert g.completes(b, g.drop(b, 3), 'X', 'standard') == 1


def test_must_block_vertical():
    b = g.parse(['.....',
                 'O....',
                 'O.X..',
                 'OXX..'])
    # O가 1열에 세로 3개. 1열이 아닌 곳에 두면 O가 A1에 넣어 바로 이긴다.
    vals = g.move_values(b, 'standard')
    assert all(vals[c] == -1 for c in cols('2', '3', '4', '5'))


def test_diagonal_threat_only_matters_with_diagonals():
    b = g.parse(['.....',
                 '..OX.',
                 '.OXX.',
                 'OXXOO'])
    # O는 D1-C2-B3에 대각선 3개, A4가 비어 있고 4열은 A4까지 채워져 있어 바로 둘 수 있다.
    assert g.drop(b, 3) == g.CELLS.index('A4')
    assert g.completes(b, g.CELLS.index('A4'), 'O', 'standard') == 1
    assert g.completes(b, g.CELLS.index('A4'), 'O', 'nodiag') == 0
    vals = g.move_values(b, 'standard')
    assert all(vals[c] == -1 for c in cols('1', '2', '3', '5'))   # 막지 않으면 O가 A4로 이긴다


def test_annotation_counts():
    b = g.parse(['.....',
                 '.....',
                 'OO...',
                 'XXX.O'])
    assert g.annotate(b, 3, 'standard') == '4열 — 말이 D4에 놓인다. 여기 두면 X가 완성하는 줄 1개, 그 뒤 O가 바로 4개를 이을 수 있는 열 0개'
    # 1열에 두면(B1) X 줄 없음. 그 뒤 O가 바로 이을 수 있는 열: 없다 (O는 C1·C2·D5뿐)
    assert g.annotate(b, 0, 'standard').endswith('X가 완성하는 줄 0개, 그 뒤 O가 바로 4개를 이을 수 있는 열 0개')


def test_twins_change_answer_and_match_solver():
    items = g.generate(random.Random(7), 10)
    twins = [x for x in items if x['stage'] == '2-변형']
    assert twins
    for x in twins:
        assert x['answer'] != x['original_answer']
        assert '대각선으로 이은 것은 치지 않는다' in x['state']['규칙']
