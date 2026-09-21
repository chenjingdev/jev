import chess
from weak_engine import candidates, evaluate, rank_moves


def test_evaluate_is_from_side_to_move_and_antisymmetric():
    board = chess.Board('rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1')
    black_view = evaluate(board)
    board.turn = chess.WHITE
    assert evaluate(board) == -black_view


def test_depth_two_takes_free_material_and_finds_mate_in_one():
    board = chess.Board('4k3/8/8/q7/8/8/8/R3K3 w Q - 0 1')  # queen hangs on a5
    rows, info = candidates(board)
    assert rows[0]['move'] == 'a1a5' and info['depth'] == 2
    board = chess.Board('6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1')
    rows, _ = candidates(board)
    assert rows[0]['move'] == 'a1a8' and rows[0]['mate'] == 1 and rows[0]['cp'] is None


def test_ranking_is_deterministic_with_uci_tie_break():
    board = chess.Board()
    a = rank_moves(board)
    b = rank_moves(chess.Board())
    assert [r['move'] for r in a] == [r['move'] for r in b]
    assert [r['rank'] for r in a] == list(range(1, len(a) + 1))
    for x, y in zip(a, a[1:]):
        assert (x['raw'], y['move']) >= (y['raw'], x['move']) or x['raw'] > y['raw']
    assert len(candidates(board)[0]) == 3
