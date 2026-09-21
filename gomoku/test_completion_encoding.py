import re
from types import SimpleNamespace
import pytest
import completion_encoding as C

@pytest.mark.parametrize('condition',C.B.CONDITIONS)
@pytest.mark.parametrize('encoding',['compact','paired'])
def test_request_matches_rotated_board_and_options_without_answer(monkeypatch,condition,encoding):
    original=next(c for c in C.B.cases_for_seed(2) if c.stage=='complete' and c.density=='dense')
    expected,_=C.B.transform(original,condition)
    def reply(**request):
        assert set(request['state'])=={'moves'}
        value=request['state']['moves']
        moves=[at for pair in value for at in pair] if encoding=='paired' else re.findall(r'[a-o](?:1[0-5]|[1-9])',value)
        assert moves==expected.moves
        opts=request['questions']['point'].criteria
        assert list(opts)==expected.options and all(v is None for v in opts.values())
        assert expected.target not in moves
        return SimpleNamespace(answers={'point':SimpleNamespace(choice=expected.target,probabilities={at:float(at==expected.target) for at in opts})},usage=None)
    monkeypatch.setattr(C.B.brain,'client',lambda:SimpleNamespace(system_one=reply))
    assert C.ask(original,condition,encoding)['hit']

@pytest.mark.parametrize('seed',range(1,21))
def test_distance_shortcuts_fail_and_density_choices_match(seed):
    sparse,dense=C.cases_for_seed(seed)
    assert sparse.options==dense.options and sparse.target==dense.target
    for case in (sparse,dense):
        C.B.validate(case)
        d=C.distance(case.target)
        assert sum(C.distance(at)==d for at in case.options)==2
        assert sum(C.distance(at)>d for at in case.options)==1
        assert sum(C.distance(at)<d for at in case.options)==2
        assert case.target!=max(case.options,key=C.distance)
