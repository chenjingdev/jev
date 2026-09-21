import re
from types import SimpleNamespace
import pytest
import basics as B


def independent_board(moves):
    grid={}
    for i,at in enumerate(moves):
        x,y=ord(at[0])-97,int(at[1:])
        assert 0<=x<15 and 1<=y<=15 and (x,y) not in grid
        grid[x,y]=1+i%2
    return grid


def independent_wins(grid):
    result=[]
    for x in range(15):
        for y in range(1,16):
            if (x,y) in grid:continue
            for dx,dy in [(1,0),(0,1),(1,1),(1,-1)]:
                length=1
                for sign in [-1,1]:
                    k=1
                    while grid.get((x+sign*k*dx,y+sign*k*dy))==2:length+=1;k+=1
                if length>=5:result.append(chr(97+x)+str(y));break
    return result


@pytest.mark.parametrize('seed',range(1,21))
def test_paired_cases_independently(seed):
    cases=B.cases_for_seed(seed)
    for stage in B.STAGES:
        sparse,dense=[c for c in cases if c.stage==stage]
        assert (len(sparse.moves),len(dense.moves))==(9,29)
        assert sparse.target==dense.target and sparse.options==dense.options
        assert dense.moves[:5]+dense.moves[25:]==sparse.moves
    for case in cases:
        B.validate(case)
        for condition in B.CONDITIONS:
            c,turns=B.transform(case,condition)
            grid=independent_board(c.moves)
            parsed=re.findall(r'[a-o](?:1[0-5]|[1-9])',''.join(c.moves))
            assert parsed==c.moves
            assert len(c.options)==len(set(c.options))==5
            if c.stage=='identify':
                colours=[grid.get((ord(at[0])-97,int(at[1:])),0) for at in c.options]
                assert sorted(colours)==[0,0,1,1,2]
                assert colours[c.options.index(c.target)]==2
            else:
                assert all((ord(at[0])-97,int(at[1:])) not in grid for at in c.options)
                assert independent_wins(grid)==[c.target]
            if condition=='shuffle':assert c.options!=case.options
            else:assert [B.sight.rotate_coord(at,-turns) for at in c.options]==case.options


@pytest.mark.parametrize('stage',B.STAGES)
def test_request_contains_no_answer_or_metadata(monkeypatch,stage):
    case=next(c for c in B.cases_for_seed(1) if c.stage==stage and c.density=='sparse')
    def respond(**request):
        assert set(request['state'])=={'game','to_move','moves'}
        assert request['state']['moves']==''.join(case.moves)
        criteria=request['questions']['point'].criteria
        assert list(criteria)==case.options and all(v is None for v in criteria.values())
        return SimpleNamespace(answers={'point':SimpleNamespace(choice=case.target,probabilities={at:float(at==case.target) for at in case.options})},usage=None)
    monkeypatch.setattr(B.brain,'client',lambda:SimpleNamespace(system_one=respond))
    result=B.ask(case)
    assert result['hit'] and result['target']==case.target
