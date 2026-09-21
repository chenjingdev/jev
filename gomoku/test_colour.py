import re
from types import SimpleNamespace
import pytest
import colour as C

@pytest.mark.parametrize('seed',range(1,21))
def test_known_occupied_colour_and_density_pair(seed):
    cases=C.cases_for_seed(seed)
    assert len(cases)==4
    for answer in ('black','white'):
        a,b=[c for c in cases if c['answer']==answer]
        assert a['coordinate']==b['coordinate']
        for c in (a,b):
            tokens=re.findall(r'[a-o](?:1[0-5]|[1-9])',''.join(c['moves']))
            assert tokens==c['moves']
            assert ('black' if tokens.index(c['coordinate'])%2==0 else 'white')==answer


def test_same_state_across_prompts_no_index_colour_leak(monkeypatch):
    case=C.cases_for_seed(1)[0];requests=[]
    def reply(**request):
        requests.append(request)
        assert request['state']=={'moves':''.join(case['moves']),'coordinate':case['coordinate']}
        assert request['questions']['point'].criteria=={'black':None,'white':None}
        return SimpleNamespace(answers={'point':SimpleNamespace(choice=case['answer'],probabilities={'black':1.,'white':0.},confidence=1.)},usage=None)
    monkeypatch.setattr(C.B.brain,'client',lambda:SimpleNamespace(system_one=reply))
    for prompt in C.PROMPTS:C.ask(case,prompt=prompt)
    assert all(r['state']==requests[0]['state'] for r in requests)

@pytest.mark.parametrize('encoding',['compact','spaced','array','paired'])
def test_encoding_changes_only_coordinate_boundaries(monkeypatch,encoding):
    case=C.cases_for_seed(1)[0]
    def reply(**request):
        state=request['state'];assert set(state)=={'moves','coordinate'}
        parsed=state['moves'] if encoding in ('array','paired') else re.findall(r'[a-o](?:1[0-5]|[1-9])',state['moves'])
        if encoding=='paired':parsed=[at for pair in state['moves'] for at in pair]
        assert parsed==case['moves'] and state['coordinate']==case['coordinate']
        assert request['questions']['point'].criteria=={'black':None,'white':None}
        return SimpleNamespace(answers={'point':SimpleNamespace(choice=case['answer'],probabilities={'black':1.,'white':0.},confidence=1.)},usage=None)
    monkeypatch.setattr(C.B.brain,'client',lambda:SimpleNamespace(system_one=reply))
    assert C.ask(case,prompt='pairs',encoding=encoding)['hit']


def test_colour_http_dispatch(monkeypatch):
    import io,json,server
    case=C.cases_for_seed(1)[0]
    monkeypatch.setattr(server.colour,'cases_for_seed',lambda seed:[case])
    monkeypatch.setattr(server.colour,'ask',lambda *args:{'stage':'colour','hit':True})
    handler=object.__new__(server.Handler)
    body=json.dumps({'stage':'colour','seed':1,'density':'sparse','probe':0,'colour_encoding':'paired'}).encode()
    handler.path='/api/basics';handler.headers={'Content-Length':str(len(body))};handler.rfile=io.BytesIO(body)
    outputs=[];handler._json=lambda status,payload:outputs.append((status,payload))
    handler.do_POST()
    assert outputs==[(200,{'stage':'colour','hit':True})]
