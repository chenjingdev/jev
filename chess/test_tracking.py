import sys,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import chess,chess.pgn
import pytest
import tracking as T
from types import SimpleNamespace

CHECKPOINTS=[(i,p) for i,g in enumerate(T.games(),1) for p in T.PLIES if len(g['moves'])>=p]

@pytest.mark.parametrize('index,plies',CHECKPOINTS)
def test_checkpoint_and_choice_coverage(index,plies):
    pos=T.position(index,plies)
    game=chess.pgn.read_game(io.StringIO(pos['pgn_moves']))
    assert not game.errors and game.end().board().fen()==pos['fen']
    alive=[]
    for row in pos['pieces']:
        assert len(row['options'])==len(set(row['options']))==5
        assert row['target'] in row['options'] and T.NONE in row['options']
        if row['target']!=T.NONE:
            assert chess.Board(pos['fen']).piece_at(chess.parse_square(row['target'])).symbol()==row['symbol']
            alive.append(row['target'])
    assert len(set(alive))==len(alive)


def fixture(monkeypatch,san):
    board=chess.Board();moves=[]
    for token in san.split():
        move=board.parse_san(token);moves.append(move.uci());board.push(move)
    assert len(moves)==12
    monkeypatch.setattr(T,'games',lambda:[{'game_id':'fixture','moves':moves}])
    return {r['origin']:r for r in T.position.__wrapped__(1,12)['pieces']}


def test_castling_moves_both_original_pieces(monkeypatch):
    rows=fixture(monkeypatch,'e4 e5 Nf3 Nc6 Bc4 Bc5 O-O Nf6 d3 O-O Nc3 d6')
    for origin,target in [('e1','g1'),('h1','f1'),('e8','g8'),('h8','f8')]:
        assert rows[origin]['target']==target and rows[origin]['castled']


def test_capture_does_not_reassign_identity(monkeypatch):
    rows=fixture(monkeypatch,'e4 e5 Qh5 Nc6 Qxe5+ Nxe5 d4 Nf6 Nf3 d6 Nc3 Be7')
    assert rows['d1']['target']==T.NONE and rows['d1']['status']=='captured'
    assert rows['b8']['target']=='e5'


def test_official_multiquestion_request_has_only_history(monkeypatch):
    pos=T.position(1,12)
    def reply(**request):
        assert request['state']=={'pgn_moves':pos['pgn_moves']}
        assert set(request['questions'])==set(T.IDENTITIES)
        answers={}
        for row in pos['pieces']:
            q=request['questions'][row['id']]
            assert len(q.criteria)==5 and all(v is None for v in q.criteria.values())
            assert row['origin'] in q.instructions and row['colour'] in q.instructions and row['kind'] in q.instructions
            answers[row['id']]=SimpleNamespace(choice=row['target'],probabilities={v:float(v==row['target']) for v in q.criteria},confidence=1.)
        return SimpleNamespace(answers=answers,usage=SimpleNamespace(input_tokens=1,output_tokens=1))
    monkeypatch.setattr(T.P,'client',lambda:SimpleNamespace(system_one=reply))
    assert all(a['hit'] for a in T.ask(1,12)['answers'])
