import ast
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run import make_request  # noqa: E402
from score import UNIFORM, item_distribution, pick  # noqa: E402


def q():
    return {'id': 'x:1', 'state': {'question': 'q'}, 'options': ['o1', 'o2', 'o3', 'o4', 'o5']}


def test_rotation_maps_back_to_original_numbers():
    for r in range(5):
        mapping, req = make_request(q(), r)
        for key, original in mapping.items():
            assert req['criteria'][key] == f'o{original}'


def test_rotation_average_and_unsupported():
    recs = []
    for r in range(5):
        mapping, _ = make_request(q(), r)
        recs.append({'rotation': r, 'status': 'complete',
                     'original_probabilities': {str(n): (0.6 if n == 3 else 0.1) for n in mapping.values()}})
    dist, d0, status = item_distribution(recs, range(5))
    assert status == 'complete' and pick(dist) == 3 and abs(sum(dist.values()) - 1) < 1e-9
    recs[2] = {'rotation': 2, 'status': 'unsupported'}
    dist, _, status = item_distribution(recs, range(5))
    assert status == 'unsupported' and dist is UNIFORM and pick(dist) is None
    assert item_distribution(recs[:3], range(5))[2] in ('unsupported', 'incomplete')


def test_runner_and_adapters_never_touch_gold():
    for f in [HERE / 'run.py', *sorted((HERE / 'adapters').glob('*.py')), *sorted((HERE / 'shims').glob('*/*.py'))]:
        assert 'gold' not in f.read_text(), f
        ast.parse(f.read_text())
