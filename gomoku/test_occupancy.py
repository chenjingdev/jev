import pytest
import occupancy as O
from types import SimpleNamespace

@pytest.mark.parametrize('seed',range(1,21))
def test_one_occupied_four_empty_same_across_densities(seed):
    sparse,dense=O.cases_for_seed(seed)
    assert sparse.options==dense.options and sparse.target==dense.target
    for c in (sparse,dense):
        O.B.validate(c)
        occupied=set(c.moves)
        assert [at for at in c.options if at in occupied]==[c.target]
        assert len(set(c.options))==5


def test_prompts_keep_inputs_identical_and_do_not_expose_answer(monkeypatch):
    c=O.cases_for_seed(1)[0]
    requests=[]
    def reply(**request):
        requests.append(request)
        opts=request['questions']['point'].criteria
        assert list(opts)==c.options and all(v is None for v in opts.values())
        return SimpleNamespace(answers={'point':SimpleNamespace(choice=c.target,probabilities={at:float(at==c.target) for at in opts})},usage=None)
    monkeypatch.setattr(O.B.brain,'client',lambda:SimpleNamespace(system_one=reply))
    for prompt in O.PROMPTS:assert O.ask(c,prompt=prompt)['hit']
    assert all(r['state']==requests[0]['state'] for r in requests)
    assert set(requests[0]['state'])=={'game','to_move','moves'}
