import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import pytest
import field_names as F

@pytest.mark.parametrize('index',range(1,21))
def test_only_state_key_changes(index):
    canonical=None
    for field in F.FIELDS:
        request=F.request_for(index,field)
        assert set(request['state'])=={field}
        normalized={**request,'state':{'same_value':request['state'][field]}}
        serialized=json.dumps(normalized)
        if canonical is None:canonical=serialized
        else:assert serialized==canonical
        assert all(v is None for v in request['questions']['point']['criteria'].values())
    assert '`pgn_moves`' not in F.INSTRUCTIONS and '`moves`' not in F.INSTRUCTIONS
