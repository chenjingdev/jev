import re
from types import SimpleNamespace
import pytest
import occupancy_boundaries as O

@pytest.mark.parametrize('seed',range(1,21))
def test_prefix_pairs_are_matched_and_really_ambiguous(seed):
    cases=O.cases_for_seed(seed)
    for density in ('sparse','dense'):
        control=next(c for v,c in cases if v=='control' and c.density==density)
        boundary=next(c for v,c in cases if v=='boundary' and c.density==density)
        assert control.moves==boundary.moves and control.target==boundary.target
        assert sum(a!=b for a,b in zip(control.options,boundary.options))==1
        for variant,case in [('control',control),('boundary',boundary)]:
            tokens=re.findall(r'[a-o](?:1[0-5]|[1-9])',''.join(case.moves))
            assert tokens==case.moves
            assert set(tokens)&set(case.options)=={case.target}
            negatives=[at for at in case.options if at!=case.target and at in ''.join(case.moves)]
            assert len(negatives)==(variant=='boundary')
            if negatives:assert any(at.startswith(negatives[0]) and at!=negatives[0] for at in tokens)


def test_minimal_request_and_no_answer_leak(monkeypatch):
    case=next(c for v,c in O.cases_for_seed(1) if v=='boundary' and c.density=='sparse')
    def respond(**request):
        assert request['state']=={'moves':''.join(case.moves)}
        opts=request['questions']['point'].criteria
        assert list(opts)==case.options and all(v is None for v in opts.values())
        return SimpleNamespace(answers={'point':SimpleNamespace(choice=case.target,probabilities={at:float(at==case.target) for at in opts})},usage=None)
    monkeypatch.setattr(O.B.brain,'client',lambda:SimpleNamespace(system_one=respond))
    assert O.ask(case,prompt='exact_en')['hit']


def test_row1_balance_and_old_shortcut_fails_in_each_split():
    for seeds in (range(1,11),range(11,21)):
        cases=[c for seed in seeds for v,c in O.cases_for_seed(seed) if v=='boundary']
        assert sum(int(c.target[1:])==1 for c in cases)==len(cases)//2
        for c in cases:
            assert len(c.moves)==(17 if c.density=='sparse' else 37)
            O.B.validate(c)
            assert 'i10' in c.moves and 'j10' in c.moves
            assert ('i1' in c.moves)!=('j1' in c.moves)
            candidates=[at for at in c.options if at in ''.join(c.moves) and int(at[1:])!=1]
            assert (candidates==[c.target])==(int(c.target[1:])!=1)


def test_additions_are_local_and_preserve_density_pair():
    for seed in range(1,21):
        sparse,dense=[c for v,c in O.cases_for_seed(seed) if v=='boundary']
        assert sparse.options==dense.options and sparse.target==dense.target
        assert dense.moves[:16]+dense.moves[36:]==sparse.moves
        for case in (sparse,dense):
            board=O.B.E.new_board()
            for i,at in enumerate(case.moves):
                r,c=O.B.E.parse_coord(at)
                if i:assert O.B.E.neighbours(board,r,c,2)
                board[r][c]=1+i%2
