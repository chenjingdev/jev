import sys,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import chess,chess.pgn
import pytest
import tracking_length as L
from types import SimpleNamespace

IDS=[i for i,g in enumerate(L.T.games(),1) if len(g['moves'])>=60]

@pytest.mark.parametrize('index',IDS)
@pytest.mark.parametrize('plies',[12,36,60])
def test_extension_preserves_every_original_piece_identity(index,plies):
    data=L.extended(index,plies);board=chess.Board();ids={sq:sq for sq in board.piece_map()}
    for uci in data['uci_history']:
        move=chess.Move.from_uci(uci);moving=ids.pop(move.from_square)
        if board.is_en_passant(move):ids.pop(move.to_square-8 if board.turn else move.to_square+8)
        else:ids.pop(move.to_square,None)
        if board.is_castling(move):
            rank=0 if board.turn else 7
            kingside=chess.square_file(move.to_square)>chess.square_file(move.from_square)
            ids[chess.square(5 if kingside else 3,rank)]=ids.pop(chess.square(7 if kingside else 0,rank))
        ids[move.to_square]=moving;board.push(move)
    targets={chess.square_name(identity):chess.square_name(square) for square,identity in ids.items()}
    original=L.T.position(index,plies)
    assert all(targets.get(row['origin'],L.T.NONE)==row['target'] for row in original['pieces'])
    parsed=chess.pgn.read_game(io.StringIO(data['pgn_moves']))
    assert not parsed.errors and parsed.end().board().fen()==data['final_fen']
    assert board.fen().split()[:5]==original['fen'].split()[:5]
    assert len(data['uci_history'])==plies+24
