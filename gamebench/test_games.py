"""모든 게임 모듈 공통 검사. 게임별 정답 검사는 games/test_<game>.py에 둔다."""
import json
from pathlib import Path
import random
import sys

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build import game_rng, modules, validate  # noqa: E402
from run import make_request, shifts  # noqa: E402

MODS = list(modules())


@pytest.mark.parametrize('mod', MODS, ids=[m.GAME for m in MODS])
def test_contract(mod):
    items = mod.generate(game_rng(20260927, mod.GAME), 10)
    assert validate(mod, items) == []
    assert mod.generate(game_rng(20260927, mod.GAME), 10) == items
    assert isinstance(mod.NAME, str) and isinstance(mod.FACET, str)


@pytest.mark.parametrize('mod', MODS, ids=[m.GAME for m in MODS])
def test_other_seeds_also_valid(mod):
    for seed in (1, 2):
        assert validate(mod, mod.generate(random.Random(seed), 10)) == []


def test_rotation_maps_back():
    item = {'id': 'x', 'state': {}, 'question': 'q', 'options': [f'o{i}' for i in range(1, 17)]}
    for n in (2, 3, 7, 16):
        it = dict(item, options=item['options'][:n])
        for s in shifts(n):
            mapping, req = make_request(it, s)
            assert all(req['criteria'][k] == f'o{v}' for k, v in mapping.items())


def test_runner_never_reads_gold():
    for f in (HERE / 'run.py', HERE / 'build.py'):
        text = f.read_text()
        assert 'gold.json' not in text or f.name == 'build.py'
    assert "json.loads" in (HERE / 'run.py').read_text() and 'gold' not in (HERE / 'run.py').read_text()
