"""claims/build.py checks: written sets are valid and local sets rebuild byte-identically.

    .venv/bin/python -m pytest -q claims/test_build.py
"""
import argparse
import json
from pathlib import Path

import pytest

import build

BUILT = [n for n in build.BUILDERS if (build.SETS_DIR / n / 'items.jsonl').exists()]
LOCAL = ['kev-transfer-v4', 'semif-authored144', 'openjev-synthetic400']  # no download needed


def read(name):
    d = build.SETS_DIR / name
    items = [json.loads(l) for l in (d / 'items.jsonl').read_text().splitlines() if l.strip()]
    return items, json.loads((d / 'gold.json').read_text()), json.loads((d / 'manifest.json').read_text())


@pytest.mark.parametrize('name', BUILT)
def test_written_set_valid(name):
    items, gold, manifest = read(name)
    assert build.validate(name, items, gold) == []
    assert len({x['id'] for x in items}) == len(items) == manifest['items'] == build.EXPECTED[name]
    assert all(1 <= gold[x['id']]['answer'] <= len(x['options']) for x in items)
    for f in ('items.jsonl', 'gold.json'):
        assert build.sha256_file(build.SETS_DIR / name / f) == manifest['sha256'][f]
    assert manifest['notes'] and manifest['source']


@pytest.mark.parametrize('name', BUILT)
def test_no_label_text_in_items(name):
    raw = (build.SETS_DIR / name / 'items.jsonl').read_text()
    for key in ('"gold":', '"_meta":', '"provenance":', '"target_distribution":', '"published_models":'):
        assert key not in raw
    items, _, _ = read(name)
    allowed = build.STATE_KEY_ALLOW.get(name, set())
    labels = [q for x in items for q in build.leak_paths(x)]
    assert all(build.generic(q) in allowed for q in labels)   # only maker document fields named "label"
    assert raw.count('"label":') == len(labels)


def test_leak_scan_catches_nested_label():
    x = build.item('t', '1', 's', {'a': [{'label': 1}]}, 'q', ['x', 'y'])
    assert list(build.leak_paths(x)) == ['.state.a[0].label']


@pytest.mark.parametrize('name', [n for n in LOCAL if n in BUILT])
def test_local_rebuild_identical(name, tmp_path, monkeypatch):
    monkeypatch.setattr(build, 'SETS_DIR', tmp_path)
    tok, tok_sha = build.tokenizer()
    build.build(name, argparse.Namespace(typesafe_dir=None), tok, tok_sha)
    for f in ('items.jsonl', 'gold.json', 'manifest.json'):
        assert (tmp_path / name / f).read_bytes() == (Path(build.HERE) / 'sets' / name / f).read_bytes()


def test_kev_label_mapping():
    """noul bool -> [false, true] index, score int -> level index, choice key -> key position (kev benchmark.py:30-33)."""
    items, gold, _ = read('kev-transfer-v4')
    src = {json.loads(l)['_meta']['id']: json.loads(l) for l in (build.LIKES / build.KEV_TEST[0]).read_text().splitlines()}
    for x in items:
        (_, q), = src[x['id'].split(':', 1)[1]]['questions'].items()
        k = gold[x['id']]['answer'] - 1
        if q['type'] == 'noul':
            assert k == (1 if q['label'] else 0)
        elif q['type'] == 'score':
            assert k == q['label'] and x['options'] == q['criteria']
        else:
            assert list(q['criteria'])[k] == q['label']
