import json
from types import SimpleNamespace
import pytest
import sight

DATA=json.loads((sight.HERE/'results_sight.json').read_text())['dataset']

@pytest.mark.parametrize('row',DATA,ids=range(20))
def test_five_varied_unlabelled_points(row):
    roles=sight.varied_candidates(row['board'])
    options=sight.options_for(row['board'],'five')
    assert set(roles)=={'target','attack','defend','develop','other'}
    assert set(roles.values())==set(options)
    assert len(options)==5 and row['target'] in options and all(v is None for v in options.values())
    for at in options:
        r,c=sight.E.parse_coord(at)
        assert row['board'][r][c]==0
        assert sight.E.neighbours(row['board'],r,c,2)


@pytest.mark.parametrize('seed',[1,2,3])
def test_black_real_game_with_forbidden_candidate(seed):
    p=sight.position_for_seed(seed,sight.E.BLACK)
    sight.validate(p)
    assert len(p.moves)%2==0
    roles=sight.varied_candidates(p.board,p.player)
    assert len(set(roles.values()))==5
    assert roles['target']==sight.E.coord(*p.hole)
    assert 'forbidden' in roles
    for role,at in roles.items():
        why=sight.E.forbidden(p.board,*sight.E.parse_coord(at),p.player)
        assert bool(why)==(role=='forbidden')
    for rotation in range(4):sight.validate(sight.rotate_position(p,rotation))


def test_black_rules_but_no_candidate_labels_in_request(monkeypatch):
    p=sight.position_for_seed(1,sight.E.BLACK)
    def respond(**request):
        opts=request['questions']['point'].criteria
        assert len(opts)==5 and all(v is None for v in opts.values())
        assert request['state']['to_move']=='black'
        assert set(request['state'])=={'game','to_move','moves'}
        assert 'black to move' in request['questions']['point'].instructions
        assert 'double-three' in request['questions']['point'].instructions
        choice=next(iter(opts))
        return SimpleNamespace(answers={'point':SimpleNamespace(choice=choice,probabilities={k:float(k==choice) for k in opts})},usage=None)
    monkeypatch.setattr(sight.brain,'client',lambda:SimpleNamespace(system_one=respond))
    assert sight.ask(p,'five','compact')['target_offered']
