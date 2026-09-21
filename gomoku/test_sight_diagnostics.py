import json
import re
from types import SimpleNamespace

import pytest
import sight
import sight_diagnostics as D

DATASET = json.loads((sight.HERE / 'results_sight.json').read_text())['dataset']


def independent_wins(grid):
    wins=[]
    for y in range(1,16):
        for x in range(15):
            if (x,y) in grid: continue
            for dx,dy in [(1,0),(0,1),(1,1),(1,-1)]:
                count=1
                for sign in [-1,1]:
                    k=1
                    while grid.get((x+sign*k*dx,y+sign*k*dy))==2:
                        count+=1; k+=1
                if count>=5:
                    wins.append(chr(97+x)+str(y)); break
    return wins


@pytest.mark.parametrize('row', DATASET, ids=range(20))
def test_independent_decode_rotations_and_target(row):
    original = sight.Position(row['board'], sight.E.parse_coord(row['target']), row['moves'])
    for turns in range(4):
        p=sight.rotate_position(original,turns)
        assert sight.rotate_position(p,-turns)==original
        expected={(c,15-r):v for r,line in enumerate(p.board) for c,v in enumerate(line) if v}
        for rep in D.REPS:
            state=sight.state_for(p,rep)
            grid={}
            if rep.startswith('sgf'):
                assert state['sgf'].startswith('(;GM[4]FF[4]SZ[15]')
                for colour,x,y in re.findall(r';([BW])\[([a-o])([a-o])\]',state['sgf']):
                    grid[ord(x)-97,15-(ord(y)-97)]=1 if colour=='B' else 2
            elif rep=='stones':
                for name,colour in [('black_stones',1),('white_stones',2)]:
                    for at in state[name]:grid[ord(at[0])-97,int(at[1:])]=colour
            else:
                for i,at in enumerate(re.findall(r'[a-o](?:1[0-5]|[1-9])',state['moves'])):
                    grid[ord(at[0])-97,int(at[1:])]=1+i%2
            assert grid==expected
            assert independent_wins(grid)==[sight.E.coord(*p.hole)]


def test_request_contains_coordinates_only_and_native_response_maps_back(monkeypatch):
    row=DATASET[0]
    p=sight.Position(row['board'],sight.E.parse_coord(row['target']),row['moves'])
    native_target=sight.sgf_coord(row['target'])
    def reply(**kwargs):
        question=kwargs['questions']['point']
        assert len(question.criteria)==225-len(p.moves)
        assert all(v is None for v in question.criteria.values())
        assert native_target in question.criteria
        return SimpleNamespace(answers={'point':SimpleNamespace(choice=native_target,probabilities={native_target:1.0})},usage=None)
    monkeypatch.setattr(sight.brain,'client',lambda:SimpleNamespace(system_one=reply))
    order=list(sight.options_for(p.board,'all'))[::-1]
    out=sight.ask(p,'all','sgf_native',True,option_order=order,audit=True)
    assert out['hit'] and out['pick']==row['target']
    assert out['probabilities']=={row['target']:1.0}
    assert list(out['request']['questions']['point']['criteria'])==[sight.sgf_coord(at) for at in order]


def test_rotation_preserves_candidate_ordinals_and_shuffle_set():
    jobs=D.jobs_for(DATASET[:1])
    base=next(j for j in jobs if j[1:3]==('sequence','base'))
    for _,rep,condition,turns,p,options in jobs:
        assert set(options)==set(sight.options_for(p.board,'all'))
        if condition.startswith('rotate'):
            assert [sight.rotate_coord(at,-turns) for at in options]==base[-1]
        if condition=='shuffle':assert options!=base[-1]
