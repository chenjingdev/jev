import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import chess
import pytest
import probe as P
from types import SimpleNamespace

@pytest.mark.parametrize('index',range(1,21))
def test_positions_options_and_independent_fen_decode(index):
    row=P.positions()[index-1];board=P.validate_position(row)
    decoded={}
    for rank,part in zip(range(8,0,-1),row['fen'].split()[0].split('/')):
        file=0
        for symbol in part:
            if symbol.isdigit():file+=int(symbol)
            else:decoded[chr(97+file)+str(rank)]=symbol;file+=1
        assert file==8
    assert decoded=={chess.square_name(sq):piece.symbol() for sq,piece in board.piece_map().items()}
    for stage in P.STAGES:
        c=P.case_for(index,stage)
        assert c['answer'] in c['options'] and len(c['options'])==len(set(c['options']))
        if stage=='occupied':assert [at for at in c['options'] if at in decoded]==[c['answer']]
        elif stage=='colour':assert ('white' if decoded[c['coordinate']].isupper() else 'black')==c['answer']
        elif stage=='piece':assert chess.piece_name(chess.Piece.from_symbol(decoded[c['coordinate']]).piece_type)==c['answer']
        else:
            hits=[];checks=[];origins=[]
            for at in c['options']:
                m=chess.Move.from_uci(at);assert m in board.legal_moves;origins.append(m.from_square)
                if board.gives_check(m):checks.append(at)
                board.push(m)
                if board.is_checkmate():hits.append(at)
                board.pop()
            assert hits==[c['answer']] and len(set(origins))==1
            assert any(at!=c['answer'] for at in checks)
    explicit=P.state_for(P.case_for(index,'mate'),'pieces')['pieces']
    assert len(explicit)==len(decoded)


def test_no_solution_metadata_or_option_descriptions(monkeypatch):
    c=P.case_for(1,'mate')
    def reply(**request):
        assert request['state']=={'fen':c['fen']}
        opts=request['questions']['point'].criteria;assert all(v is None for v in opts.values())
        assert not any('#' in at or '+' in at for at in opts)
        return SimpleNamespace(answers={'point':SimpleNamespace(choice=c['answer'],probabilities={at:float(at==c['answer']) for at in opts},confidence=1.)},usage=SimpleNamespace(input_tokens=1,output_tokens=1))
    monkeypatch.setattr(P,'client',lambda:SimpleNamespace(system_one=reply))
    assert P.ask(1,'mate')['hit']
    assert P.ask(1,'mate',condition='shuffle')['hit']


def test_balanced_sides_and_answer_slots():
    assert sum(chess.Board(p['fen']).turn for p in P.positions())==10
    for stage in ('occupied','piece','mate'):
        assert [sum(P.case_for(i,stage)['options'].index(P.case_for(i,stage)['answer'])==slot for i in range(1,21)) for slot in range(5)]==[4]*5
