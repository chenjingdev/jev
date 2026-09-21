import sys,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import chess,chess.pgn
import pytest
import knight as K
from types import SimpleNamespace

@pytest.mark.parametrize('index',range(1,21))
def test_history_and_unique_current_knight(index):
    c=K.cases()[index-1];board=K.validate(c)
    # Decode FEN independently; uppercase N is the exact requested piece.
    knights=set()
    for rank,row in zip(range(8,0,-1),c['fen'].split()[0].split('/')):
        file=0
        for token in row:
            if token.isdigit():file+=int(token)
            else:
                if token=='N':knights.add(chr(97+file)+str(rank))
                file+=1
        assert file==8
    assert set(c['options'])&knights=={c['answer']}
    assert len(set(c['options']))==5 and c['answer'] not in ('b1','g1')
    for at in c['stale_options']:assert not board.piece_at(chess.parse_square(at))


def test_request_only_history_and_no_fen_answer_leak(monkeypatch):
    c=K.cases()[0]
    def reply(**request):
        assert request['state']=={'pgn_moves':c['pgn_moves']}
        opts=request['questions']['point'].criteria
        assert set(opts)==set(c['options']) and all(v is None for v in opts.values())
        return SimpleNamespace(answers={'point':SimpleNamespace(choice=c['answer'],probabilities={at:float(at==c['answer']) for at in opts},confidence=1.)},usage=SimpleNamespace(input_tokens=1,output_tokens=1))
    monkeypatch.setattr(K.P,'client',lambda:SimpleNamespace(system_one=reply))
    assert K.ask(1,'pgn')['hit']
    assert K.ask(1,'pgn','shuffle')['hit']
