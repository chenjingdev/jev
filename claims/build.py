"""Convert the benchmarks Jev-like makers cite into gamebench items, one directory per set.

    .venv/bin/python claims/build.py all                       # every set
    .venv/bin/python claims/build.py kev-transfer-v4 semif-wanli256
    .venv/bin/python claims/build.py check                     # re-validate the written sets

Each set writes claims/sets/<set>/items.jsonl (no labels; read by gamebench/run.py), gold.json
({id: {"answer": 1-based, "n": len(options)}}; read only by gamebench/score.py) and manifest.json.
The rendering mirrors the maker's own conversion (file:line in each manifest's notes). Sources are
pinned by sha256 and verified; nothing is random and nothing is timestamped, so reruns are byte-identical.
semif-typesafe102 downloads four evals.typesafe.ai snapshots on every run (or reads --typesafe-dir).
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

HERE = Path(__file__).resolve().parent
SETS_DIR = HERE / 'sets'
LIKES = Path(os.environ.get('JEV_LIKES', Path.home() / 'dev' / 'jev-likes'))

ITEM_KEYS = ('id', 'game', 'stage', 'state', 'question', 'options')
LEAK_KEYS = {'label', 'gold', 'labels', 'target', 'target_distribution', '_meta', 'provenance',
             'published_models', 'original_label', 'answer_index', 'correct'}
MAX_RUNNER_OPTIONS = 20
OPTION_TOKEN_CAP = 48  # julia/repo/julia/data.py:84 (strict refusal) and laya.common.build_sequence (truncation)

TYPED = {'repo': 'LocalLLaMA/typed-decisions', 'revision': 'c76749ec58bd8c3d2ea706b31c333a9059c38f90',
         'filename': 'all/test-00000-of-00001.parquet',
         'sha256': '4f294f218ea1da27f3efef936359389c62ea4d3973a41457732990f1d31b647c'}
WANLI = {'repo': 'alisawuffles/WANLI', 'revision': '61c95318fd71c55b6ba355d76253254615f387ec',
         'filename': 'test.jsonl', 'sha256': '4276e0af7fcdf657d1ab7beb54eaf025fda592a76c9ee86b63b7871953fc74fd'}
KEV_TEST = ('kev/src/evals/v4/transfer-v4/test.jsonl', 'c30a91274f9b483aac9e4f02ada5dea953b3f1a2829456e0bc07806c4e73b517')
AUTHORED = ('semif/src/benchmarks/data/authored144.jsonl', '8162d1c73f925af64453f1ec05ef36d583b3815bf698e60f0d454bd11537e079')
SELECTION = ('semif/src/benchmarks/manifests/source-selection.jsonl', '81d98a4195971e1fe046673928730b7112a6a7677baf046505761f2504b424c7')
OPENJEV = ('open-jev/data/synthetic/test.jsonl', '98f6022c052b4c7d423215b22971517a753d16ea409426f7e9c43017fbf721ab')
TOKENIZER = 'julia/repo/tokenizer/tokenizer.json'
# sha256 of SemIf's build_*.py output files, as recorded by Kev when it froze the same rows for its live Jev run
# (kev/src/evals/external/{wanli-v1,typesafe-v1}/manifest.json -> external.files). Matching them proves the rebuild.
WANLI_ROWS_SHA256 = '40b795d82c8e53c0dbae132f5fc87c33bf0517340c69169474049e784f311c0f'
TYPESAFE_ROWS_SHA256 = '3eabe11c02e90308d03e857bc614874e7369b390d15f0e456a6049bbc932ba17'
TYPESAFE_URL = 'https://evals.typesafe.ai/{workflow}-cases.js'

# Decisions the maker code leaves open (see manifest notes). Defaults; the main session may change them.
KEV_NOUL_NO_CRITERIA = ('no', 'yes')  # kev/src/kev/api.py:110 option_text("no"/"yes", None) -> "no"/"yes"
OPENJEV_QUESTION = ''                 # open-jev/openjev/cli.py:78 scores row["context"] alone; no question text


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def git_head(path):
    try:
        return subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def pinned_local(rel, expected):
    path = LIKES / rel
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f'{path}: sha256 {actual} != pinned {expected}')
    return path


def hf_file(spec):
    from huggingface_hub import hf_hub_download
    path = hf_hub_download(spec['repo'], spec['filename'], repo_type='dataset', revision=spec['revision'])
    actual = sha256_file(path)
    if actual != spec['sha256']:
        raise ValueError(f"{spec['repo']}/{spec['filename']}: sha256 {actual} != pinned {spec['sha256']}")
    return Path(path)


def hf_source(spec):
    return {'url': f"https://huggingface.co/datasets/{spec['repo']}/resolve/{spec['revision']}/{spec['filename']}",
            'repo': spec['repo'], 'revision': spec['revision'], 'file': spec['filename'], 'sha256': spec['sha256']}


def item(name, source_id, stage, state, question, options):
    return {'id': f'{name}:{source_id}', 'game': name, 'stage': stage, 'state': state, 'question': question,
            'options': list(options)}


def jsonl(rows):
    return ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows)


# ---------------------------------------------------------------------------------------------- sets

def typed_decisions(a):
    import pyarrow.parquet as pq
    name = 'typed-decisions'
    path = hf_file(TYPED)
    cases = pq.read_table(path).to_pylist()
    rows = []
    for case in cases:                                           # reproduce_typed.py:52-68, verbatim logic
        state = json.loads(case['state'])
        gold = json.loads(case['gold'])
        for qid, q in json.loads(case['questions']).items():
            kind = q['type']
            criteria = q.get('criteria')
            if criteria is None and kind == 'noul':
                criteria = {'false': 'false', 'true': 'true'}
            if isinstance(criteria, list):
                criteria = {str(i): value for i, value in enumerate(criteria)}
            if not isinstance(criteria, dict):
                raise ValueError('Missing option descriptions')
            keys = ['false', 'true'] if kind == 'noul' else list(criteria)
            answer = keys.index(str(gold[qid]['label'])) + 1
            rows.append((item(name, f"{case['id']}:{qid}", kind, state, q['instructions'],
                              [criteria[k] for k in keys]), answer))
    types = Counter(x['stage'] for x, _ in rows)
    if len(cases) != 400 or types != {'choice': 600, 'score': 800, 'noul': 600}:   # reproduce_typed.py:70
        raise ValueError(f'typed-decisions shape changed: {len(cases)} cases, {dict(types)}')
    return {
        'source': hf_source(TYPED) | {'cases': len(cases)},
        'maker': {'repo': str(LIKES / 'julia/repo'), 'script': 'scripts/reproduce_typed.py'},
        'type_counts': dict(types),
        'rendering': {
            'state': "json.loads(case['state']) (dict), shared by the case's questions",
            'question': "question['instructions']",
            'options': "noul: [criteria['false'], criteria['true']]; choice: criteria values in key order; "
                       "score: rubric list in order (keys '0'..'n-1')",
            'answer': "keys.index(str(gold[qid]['label'])) + 1",
            'id': "typed-decisions:<case id>:<question id> (Julia's metadata id, reproduce_typed.py:67)",
            'stage': 'question type (choice / score / noul)',
        },
        'notes': [
            'Mirrors julia/repo/scripts/reproduce_typed.py:52-68: state = json.loads(case["state"]) (:53); '
            'noul with no criteria -> {"false": "false", "true": "true"} (:58-59); score rubric list -> '
            'keys "0".."n-1" (:60-61); keys = ["false", "true"] for noul else list(criteria) (:64); '
            'options = [criteria[key] for key in keys] and question = instructions (:65-66); '
            'gold = str(gold[qid]["label"]) (:68), mapped to keys.index(...) + 1.',
            'Option keys (choice names such as "continue") are dropped, as in the maker conversion: Julia\'s '
            'engine sees only the descriptions (:66).',
            'Case/type count assertion copied from reproduce_typed.py:70 (400 cases; 600 choice, 800 score, 600 noul).',
        ],
    }, rows


def kev_transfer_v4(a):
    name = 'kev-transfer-v4'
    path = pinned_local(*KEV_TEST)
    rows, types, variants, criteria_less = [], Counter(), Counter(), 0
    suffix = {'clean': '', 'permuted': '/permuted', 'none_present': '/none', 'none_absent': '/none'}
    for line in path.read_text().splitlines():
        rec = json.loads(line)
        (qid, q), = rec['questions'].items()
        meta, kind, crit, label = rec['_meta'], q['type'], q.get('criteria'), q['label']
        if kind == 'choice':                                     # api.py:94-97 keys; benchmark.py:33 label index
            keys = list(crit)
            options = [k if d is None or d == '' else d for k, d in crit.items()]
            if not isinstance(label, str):
                raise ValueError(f"{meta['id']}: choice label {label!r}")
            index = keys.index(label)
        elif kind == 'noul':                                     # keys ["false", "true"]; bool label -> int
            if not isinstance(label, bool) or (crit is not None and not set(crit) <= {'false', 'true'}):
                raise ValueError(f"{meta['id']}: noul label/criteria")
            c = crit or {}
            criteria_less += crit is None
            options = [c.get('false') or KEV_NOUL_NO_CRITERIA[0], c.get('true') or KEV_NOUL_NO_CRITERIA[1]]
            index = int(label)
        elif kind == 'score':                                    # keys "0".."n-1"; int label is the level index
            if not isinstance(crit, list) or isinstance(label, bool) or not isinstance(label, int):
                raise ValueError(f"{meta['id']}: score label/criteria")
            options = list(crit)
            index = int(label)
        else:
            raise ValueError(f"{meta['id']}: type {kind}")
        types[kind] += 1
        variants[meta['variant']] += 1
        stage = f"{kind}/{q['src']}{suffix[meta['variant']]}"
        rows.append((item(name, meta['id'], stage, rec['state'], q['instructions'], options), index + 1))
    if len(rows) != 764:
        raise ValueError(f'kev-transfer-v4: {len(rows)} rows')
    return {
        'source': {'path': str(path), 'sha256': KEV_TEST[1], 'repo_commit': git_head(LIKES / 'kev/src'),
                   'split': 'test', 'suite_manifest': 'kev/src/evals/v4/transfer-v4/manifest.json (files.test.jsonl.sha256)'},
        'maker': {'repo': str(LIKES / 'kev/src'), 'code': ['kev/api.py', 'kev/benchmark.py', 'kev/data.py']},
        'type_counts': dict(types),
        'variant_counts': dict(sorted(variants.items())),
        'noul_without_criteria': criteria_less,
        'rendering': {
            'state': "record['state'] as stored (dict, string or list): what kev.data.api_request sends to Jev",
            'question': "question['instructions']",
            'options': 'choice: criteria in key order, the description, or the key name when the description is '
                       'null/empty; noul: [false, true] descriptions, "no"/"yes" when absent; score: criteria list',
            'answer': 'choice keys.index(label) + 1; noul int(bool label) + 1; score int(label) + 1',
            'id': "kev-transfer-v4:<_meta.id>",
            'stage': "<type>/<task src>, plus /permuted or /none for Kev's variant rows ('none' merges "
                     'none_present and none_absent so the stage does not reveal the answer)',
        },
        'notes': [
            'Label -> option index mirrors kev/src/kev/benchmark.py:30-33 (labels): keys = question_keys(type, '
            'criteria) and label index = keys.index(label) for choice, int(label) otherwise; question_keys at '
            'kev/src/kev/api.py:94-99 gives list(criteria) for choice, ["false", "true"] for noul and "0".."n-1" '
            'for score. kev/src/kev/data.py:402 states the same: noul labels are bools, score labels level indices.',
            'What Jev receives: kev/src/kev/data.py:389-394 api_request -> {state, questions: {type, instructions, '
            'criteria}} (JevPredictor, kev/src/kev/predictors.py:210). State and instructions are copied unchanged.',
            'Option text: the description; when it is null or "" the key name, as kev/src/kev/api.py:58-59 '
            'option_text falls back to the name (emotion rows have criteria {"sadness": null, ...}). Kev\'s own '
            'model sees "name: description" (api.py:59,112); the name prefix is not added here because the runner '
            're-keys options to A, B, ... and Julia\'s typed conversion also sends descriptions only.',
            'Noul without criteria (%d rows): options "no"/"yes", the text Kev\'s own model scores '
            '(kev/src/kev/api.py:110, option_text("no", None) / option_text("yes", None)). Jev itself receives a '
            'criteria-less noul.' % criteria_less,
            'Test split only (the brief). kev.jev runs Jev on the development split (kev/src/kev/jev.py:43); '
            "Kev's headline metrics use variant == clean rows only (kev/src/kev/benchmark.py:76): filter stages "
            'without a /permuted or /none suffix to match them.',
            'The 11 list states are kept as lists (maker data); csat/bench/adapters.as_state currently passes only '
            'str or dict.',
        ],
    }, rows


def semif_authored144(a):
    name = 'semif-authored144'
    path = pinned_local(*AUTHORED)
    rows, families = [], Counter()
    for line in path.read_text().splitlines():
        row = json.loads(line)
        families[row['family']] += 1
        rows.append((item(name, row['id'], row['family'], row['state'], row['question'],
                          [o['description'] for o in row['options']]), row['label'] + 1))
    return {
        'source': {'path': str(path), 'sha256': AUTHORED[1], 'repo_commit': git_head(LIKES / 'semif/src')},
        'maker': {'repo': str(LIKES / 'semif/src'), 'code': ['src/semif_phase1/core.py']},
        'type_counts': {'choice': len(rows)},
        'rendering': {
            'state': "row['state'] (string, unchanged)",
            'question': "row['question']",
            'options': "[option['description'] for option in row['options']] in source order",
            'answer': "row['label'] + 1",
            'id': "semif-authored144:<row id>",
            'stage': "row['family']",
        },
        'notes': [
            'SemIf\'s own request: semif/src/src/semif_phase1/core.py:43-56 direct_messages -> {"evidence": '
            'row["state"], "criterion": row["question"], "options": [{"letter", "description"}]}; option ids are '
            'not shown to the model, only letters and descriptions. Mirrored as state / question / options.',
            'SemIf never ran live Jev (semif/src/README.md:154). The published Jev number on these 144 is Kev\'s run '
            '(kev/src/scripts/freeze_semif_external.py:34-51 -> evals/external/semif-v1): string state, '
            'instructions = row["question"], criteria {option id: description}. Same content as here.',
            'Dropped from items: label, target_distribution, group_id, split and provenance (provenance carries '
            'rationale and evidence_span, which give the answer away).',
            'Source sha256 equals kev/src/evals/external/semif-v1/manifest.json external.files["authored144.jsonl"].',
        ],
    }, rows


def semif_wanli256(a):
    name = 'semif-wanli256'
    sel_path = pinned_local(*SELECTION)
    manifest = [json.loads(line) for line in sel_path.read_text().splitlines() if line.strip()]
    selected = [row for row in manifest if row['source'] == 'wanli']
    src_path = hf_file(WANLI)
    # --- semif/src/benchmarks/build_wanli.py:10-59, reproduced line for line ---
    descriptions = {'supported': 'The evidence establishes the claim',
                    'insufficient': 'The evidence does not establish either',
                    'contradicted': 'The evidence establishes the opposite'}
    labels = {'entailment': 'supported', 'neutral': 'insufficient', 'contradiction': 'contradicted'}
    source = {str(row['id']): row for row in map(json.loads, src_path.read_text().splitlines())}
    semif_rows = []
    for sel in selected:
        upstream = source[str(sel['upstream']['source_id'])]
        option_ids = sel['option_ids']
        gold_id = labels[upstream['gold']]
        semif_rows.append({
            'id': sel['id'], 'group_id': sel['group_id'], 'family': sel['family'], 'split': 'external_test',
            'state': upstream['premise'],
            'question': 'Assess the claim using only the supplied evidence: ' + upstream['hypothesis'],
            'options': [{'id': key, 'description': descriptions[key]} for key in option_ids],
            'label': option_ids.index(gold_id), 'target_distribution': None,
            'provenance': {'source': 'WANLI', 'source_id': upstream['id'], 'source_seed_id': upstream['pairID'],
                           'source_revision': sel['upstream']['revision'], 'source_official_split': 'test',
                           'original_label': upstream['gold'], 'rights': 'CC-BY-4.0'}})
    if len(semif_rows) != 256 or len({r['id'] for r in semif_rows}) != 256:
        raise ValueError('Selection must rebuild exactly 256 unique WANLI rows')
    rows_sha = sha256_bytes(jsonl(semif_rows).encode())
    if rows_sha != WANLI_ROWS_SHA256:
        raise ValueError(f'wanli256.jsonl rebuild sha256 {rows_sha} != {WANLI_ROWS_SHA256}')
    rows = [(item(name, r['id'], r['family'], r['state'], r['question'], [o['description'] for o in r['options']]),
             r['label'] + 1) for r in semif_rows]
    return {
        'source': hf_source(WANLI) | {'selection': str(sel_path), 'selection_sha256': SELECTION[1],
                                      'semif_commit': git_head(LIKES / 'semif/src'),
                                      'semif_rows_sha256': rows_sha},
        'maker': {'repo': str(LIKES / 'semif/src'), 'code': ['benchmarks/build_wanli.py', 'src/semif_phase1/core.py']},
        'type_counts': {'choice': len(rows)},
        'rendering': {
            'state': "WANLI premise (string)",
            'question': "'Assess the claim using only the supplied evidence: ' + hypothesis",
            'options': "SemIf's three descriptions in the per-row option_ids order of source-selection.jsonl",
            'answer': 'option_ids.index(LABELS[gold]) + 1',
            'id': 'semif-wanli256:<selection id>',
            'stage': "selection family",
        },
        'notes': [
            'Rows rebuilt with semif/src/benchmarks/build_wanli.py:10-59 logic (DESCRIPTIONS :10-14, LABELS :15, '
            'state = premise :40, question = "Assess the claim using only the supplied evidence: " + hypothesis '
            ':41, options in selection option_ids order :42, label :43) from the selection manifest '
            '(benchmarks/manifests/source-selection.jsonl, source == "wanli") and WANLI test.jsonl at the pinned '
            'revision (semif/src/benchmarks/fetch_sources.py:12-16). No randomness: the selection is fixed by id.',
            'The rebuilt SemIf-format file hashes to %s, the wanli256.jsonl sha256 that Kev recorded for the rows it '
            'sent to live Jev (kev/src/evals/external/wanli-v1/manifest.json).' % rows_sha,
            'Item rendering as SemIf sends rows to its model: semif/src/src/semif_phase1/core.py:43-56 (evidence = '
            'state, criterion = question, options = descriptions). Kev\'s Jev run used the same state, instructions '
            'and descriptions (kev/src/scripts/freeze_semif_external.py:34-38).',
            'gold-wanli256.jsonl named in semif/src/results/raw/calibration/wanli256.json:3 is not in the repo; '
            'it is the output of build_wanli.py, reproduced here.',
        ],
    }, rows


def _typesafe_payload(text):
    """semif/src/benchmarks/build_typesafe.py:12-20."""
    text = text.strip()
    prefix = '__VIEWER_DATA__('
    if not text.startswith(prefix):
        raise ValueError('Unexpected wrapper in TypeSafe snapshot')
    payload, end = json.JSONDecoder().raw_decode(text[len(prefix):])
    if text[len(prefix) + end:].strip() not in {')', ');'}:
        raise ValueError('Unexpected trailing content in TypeSafe snapshot')
    return payload


def _lsum(values):
    """Left-to-right float sum: builtin sum() before Python 3.12. From 3.12 sum() compensates rounding, which moves
    the last digit of SemIf's target/published distributions and so the rebuilt file's sha256 (items are unaffected)."""
    total = 0
    for value in values:
        total = total + value
    return total


def _ts_vector(raw, keys):
    values = [float(raw.get(key, 0)) for key in keys]
    if any(not math.isfinite(value) or value < 0 for value in values) or _lsum(values) <= 0:
        raise ValueError('Invalid probability vector')
    total = _lsum(values)
    return [value / total for value in values]


def _ts_reference(answer, keys):
    if answer.get('probabilities'):
        return _ts_vector(answer['probabilities'], keys)
    value = answer.get('value')
    key = str(value).lower() if isinstance(value, bool) else str(value)
    if key not in keys:
        raise ValueError('Reference value is outside the declared options')
    return [float(candidate == key) for candidate in keys]


def _ts_published(answer, primitive, keys):
    if primitive == 'noul':
        probability = float(answer['noul'])
        return [probability if key == 'true' else 1 - probability for key in keys]
    return _ts_vector(answer['probabilities'], keys)


def semif_typesafe102(a):
    name = 'semif-typesafe102'
    sel_path = pinned_local(*SELECTION)
    manifest = [json.loads(line) for line in sel_path.read_text().splitlines() if line.strip()]
    selected = [row for row in manifest if row['source'] == 'typesafe']
    payloads, snapshots = {}, {}
    for workflow in sorted({row['upstream']['workflow'] for row in selected}):
        url = TYPESAFE_URL.format(workflow=workflow)
        if a.typesafe_dir:
            data = (Path(a.typesafe_dir) / f'typesafe-{workflow}-cases.js').read_bytes()
        else:
            req = urllib.request.Request(url, headers={'User-Agent': 'semif-research-fetch/1.0'})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read(64 * 1024 * 1024 + 1)
            if len(data) > 64 * 1024 * 1024:
                raise ValueError(f'{url} exceeded 64 MiB')
        payloads[workflow] = _typesafe_payload(data.decode('utf-8'))
        snapshots[workflow] = {'url': url, 'raw_sha256': sha256_bytes(data),
                               'parsed_sha256': hashlib.sha256(json.dumps(payloads[workflow], indent=2).encode()).hexdigest()}
    # --- semif/src/benchmarks/build_typesafe.py:62-130, reproduced line for line ---
    semif_rows, filled = [], 0
    for sel in selected:
        upstream = sel['upstream']
        workflow = upstream['workflow']
        payload = payloads[workflow]
        if snapshots[workflow]['parsed_sha256'] != upstream['snapshot_sha256']:
            raise ValueError(f'Parsed {workflow} snapshot hash changed')
        evaluation = payload['eval']
        case = evaluation['cases'][upstream['case_id']]
        question = evaluation['questions'][upstream['question_index']]
        document = evaluation['documents'][upstream['document_index']]
        primitive = upstream['primitive']
        criteria = question.get('criteria')
        if primitive == 'noul':
            filled += any(key not in (criteria or {}) for key in ('true', 'false'))
            options = [{'id': key, 'description': (criteria or {}).get(key, f'The proposition is {key}.')}
                       for key in ('true', 'false')]
        elif primitive == 'choice':
            options = [{'id': key, 'description': value} for key, value in criteria.items()]
        else:
            raise ValueError('The frozen comparison excludes Score primitives')
        for option in options:
            option['description'] = option['id'] + ': ' + option['description']
        keys = [option['id'] for option in options]
        if keys != sel['option_ids']:
            raise ValueError(f"Option order changed for {sel['id']}")
        references = case['reference_answers'][upstream['node']][upstream['question_id']]['sets']
        distributions = [_ts_reference(answer, keys) for answer in references]
        target = [_lsum(row[index] for row in distributions) / len(distributions) for index in range(len(keys))]
        maxima = [index for index, value in enumerate(target) if abs(value - max(target)) < 1e-12]
        if len(maxima) != 1:
            raise ValueError('Frozen TypeSafe rows require a unique reference argmax')
        published = {}
        for model_key, model_record in case['models'].items():
            for node in model_record['nodes']:
                if (node['node'] == upstream['node'] and node.get('doc') == upstream['document_index']
                        and node.get('questions', {}).get(upstream['question_id']) == upstream['question_index']
                        and upstream['question_id'] in node.get('answers', {})):
                    answer = node['answers'][upstream['question_id']]
                    published[model_key] = {'model': model_record['model'],
                                            'distribution': _ts_published(answer, primitive, keys)}
        if 'typesafe' not in published:
            raise ValueError('Selected row lacks a published TypeSafe answer')
        semif_rows.append({'id': sel['id'], 'group_id': sel['group_id'], 'family': sel['family'],
                           'split': 'external_typesafe_selected',
                           'state': json.dumps(document, ensure_ascii=False, indent=2),
                           'question': question['instructions'], 'options': options, 'label': maxima[0],
                           'target_distribution': target, 'primitive': primitive, 'published_models': published,
                           'provenance': upstream})
    if len(semif_rows) != 102 or len({r['id'] for r in semif_rows}) != 102:
        raise ValueError('Selection must rebuild exactly 102 unique TypeSafe rows')
    rows_sha = sha256_bytes(jsonl(semif_rows).encode())
    if rows_sha != TYPESAFE_ROWS_SHA256:
        raise ValueError(f'typesafe102.jsonl rebuild sha256 {rows_sha} != {TYPESAFE_ROWS_SHA256}')
    # Jev-shaped request, as kev/src/scripts/freeze_semif_external.py:36,47 sent these rows to live Jev:
    # state = the parsed document object, option description = SemIf's description without the "<id>: " prefix.
    rows = [(item(name, r['id'], r['family'], json.loads(r['state']), r['question'],
                  [o['description'].removeprefix(o['id'] + ': ') for o in r['options']]), r['label'] + 1)
            for r in semif_rows]
    return {
        'source': {'url': 'https://evals.typesafe.ai/', 'snapshots': snapshots, 'selection': str(sel_path),
                   'selection_sha256': SELECTION[1], 'semif_commit': git_head(LIKES / 'semif/src'),
                   'semif_rows_sha256': rows_sha},
        'maker': {'repo': str(LIKES / 'semif/src'), 'code': ['benchmarks/build_typesafe.py'],
                  'jev_request': str(LIKES / 'kev/src/scripts/freeze_semif_external.py')},
        'type_counts': dict(Counter(r['primitive'] for r in semif_rows)),
        'case_count': len({r['group_id'] for r in semif_rows}),
        'noul_with_filled_criteria': filled,
        'rendering': {
            'state': 'the TypeSafe document object (json.loads of SemIf\'s state string), as Jev received it',
            'question': "TypeSafe question['instructions']",
            'options': 'option descriptions without SemIf\'s "<id>: " prefix, in selection option_ids order; noul = '
                       '[true description, false description], "The proposition is <key>." where SemIf filled a '
                       'missing criterion',
            'answer': 'argmax of the mean reference distribution (unique by construction) + 1',
            'id': 'semif-typesafe102:<selection id>',
            'stage': "selection family (typesafe_<workflow>)",
        },
        'notes': [
            'Rows rebuilt with semif/src/benchmarks/build_typesafe.py:12-130 logic from the four public '
            'evals.typesafe.ai <workflow>-cases.js payloads; each parsed payload matches the snapshot_sha256 in '
            'source-selection.jsonl (:67-70). Noul options ["true", "false"] with "The proposition is <key>." '
            'fill (:77-81); choice options in criteria order (:82-83); every description prefixed "<id>: " '
            '(:86-87); state = json.dumps(document, indent=2) (:119); question = instructions (:120); label = '
            'unique reference argmax (:91-96, :122).',
            'The rebuilt SemIf-format file hashes to %s, the typesafe102.jsonl sha256 Kev recorded '
            '(kev/src/evals/external/typesafe-v1/manifest.json). Matching it needs left-to-right float sums '
            '(builtin sum() before Python 3.12); with 3.12+ compensated sum() only the last digits of '
            'target_distribution / published_models change, never state, question, options or label.' % rows_sha,
            'Item rendering = the Jev-shaped request Kev sent to live Jev (kev/src/scripts/freeze_semif_external.py'
            ':36 description.removeprefix(id + ": "), :47 state = json.loads(row["state"])): state is the parsed '
            'document object and option text has no "<id>: " prefix. Principle: every system gets the same '
            'Jev-shaped request and each shim does its own native rendering. Kev sent noul rows as noul; the runner '
            'sends them as a two-option choice in SemIf\'s ["true", "false"] order.',
            'Not SemIf\'s own rendering: SemIf fed its model a string state json.dumps(document, indent=2) '
            '(build_typesafe.py:119) and "<id>: <description>" options (:86-87) through core.py:43-56. SemIf\'s '
            'published 0.845 modal agreement (direct Qwen3.5-4B, semif/src/README.md:146) was measured on that '
            'rendering, not on these items. TypeSafe\'s published Jev 0.883 comes from Jev\'s native requests.',
            'The documents of %d items have invoice.fields.adjustments[].label (e.g. "Freight and handling"): '
            'document content, not the gold; STATE_KEY_ALLOW exempts that path from the leak scan.'
            % sum(any(generic(q) in STATE_KEY_ALLOW[name] for q in leak_paths(x)) for x, _ in rows),
            '%d noul rows had no (or partial) criteria in the TypeSafe question; their "The proposition is true./'
            'false." text is SemIf\'s fill (build_typesafe.py:79), which Kev also sent to Jev as criteria.' % filled,
            'Scoring differs from the makers: SemIf reports equal-case modal agreement and total-variation distance '
            'to the reference distribution (semif/src/benchmarks/evaluate_external.py:44-79); gold.json here has '
            'only the reference argmax, so gamebench accuracy is comparable to agreement, not to distance.',
            'Build needs network (or --typesafe-dir with the four typesafe-<workflow>-cases.js files).',
        ],
    }, rows


def openjev_synthetic400(a):
    name = 'openjev-synthetic400'
    path = pinned_local(*OPENJEV)
    rows = []
    for i, line in enumerate(path.read_text().splitlines()):
        row = json.loads(line)
        rows.append((item(name, f'{i:03d}', 'synthetic', row['context'], OPENJEV_QUESTION, row['options']),
                     row['label'] + 1))
    return {
        'source': {'path': str(path), 'sha256': OPENJEV[1], 'repo_commit': git_head(LIKES / 'open-jev'),
                   'origin': 'jevlike-data synthetic (open-jev/README.md:243)'},
        'maker': {'repo': str(LIKES / 'open-jev'), 'code': ['openjev/cli.py']},
        'type_counts': {'choice': len(rows)},
        'rendering': {
            'state': "row['context'] (string)",
            'question': repr(OPENJEV_QUESTION) + ' (open-jev eval sends no question text)',
            'options': "row['options'] in order",
            'answer': "row['label'] + 1",
            'id': 'openjev-synthetic400:<0-based line number>',
            'stage': 'synthetic',
        },
        'notes': [
            'open-jev eval (open-jev/openjev/cli.py:66-80, cmd_eval) scores row["options"] as continuations of '
            'row["context"] (:78); the task instruction ("Choose the exact badge ...") is inside the context. It has '
            'no question field, so question is the empty string. The only other string is the --sep separator '
            '(cli.py:24, default ""; README.md:244 uses "\\nChoice: " for the published run), which sits between '
            'context and option rather than acting as a question.',
            'Rows have no id; the 0-based line number is used.',
        ],
    }, rows


BUILDERS = {'typed-decisions': typed_decisions, 'kev-transfer-v4': kev_transfer_v4,
            'semif-authored144': semif_authored144, 'semif-wanli256': semif_wanli256,
            'semif-typesafe102': semif_typesafe102, 'openjev-synthetic400': openjev_synthetic400}
EXPECTED = {'typed-decisions': 2000, 'kev-transfer-v4': 764, 'semif-authored144': 144, 'semif-wanli256': 256,
            'semif-typesafe102': 102, 'openjev-synthetic400': 400}


# ------------------------------------------------------------------------------------ checks, stats

# Maker document fields that happen to share a name with a label key (index-free paths). They are content of the
# state Jev receives, not the gold: semif-typesafe102 invoice adjustments are {"label": "Freight and handling", ...}.
STATE_KEY_ALLOW = {'semif-typesafe102': {'.state.invoice.fields.adjustments[].label'}}


def generic(path):
    return re.sub(r'\[\d+\]', '[]', path)


def leak_paths(obj, path='', allow=frozenset()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in LEAK_KEYS and generic(f'{path}.{k}') not in allow:
                yield f'{path}.{k}'
            yield from leak_paths(v, f'{path}.{k}', allow)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from leak_paths(v, f'{path}[{i}]', allow)


def validate(name, items, gold):
    errs = []
    ids = [x['id'] for x in items]
    if len(set(ids)) != len(ids):
        errs.append(f'{len(ids) - len(set(ids))} duplicate ids')
    if set(gold) != set(ids):
        errs.append('gold ids differ from item ids')
    if len(items) != EXPECTED[name]:
        errs.append(f'{len(items)} items, expected {EXPECTED[name]}')
    for x in items:
        if tuple(x) != ITEM_KEYS:
            errs.append(f"{x['id']}: keys {list(x)}")
        if x['game'] != name or not x['id'].startswith(name + ':'):
            errs.append(f"{x['id']}: game/id prefix")
        if not isinstance(x['stage'], str) or not x['stage'] or '|' in x['stage']:
            errs.append(f"{x['id']}: stage {x['stage']!r}")
        if not isinstance(x['question'], str):
            errs.append(f"{x['id']}: question is not a string")
        if not isinstance(x['state'], (str, dict, list)):
            errs.append(f"{x['id']}: state type {type(x['state']).__name__}")
        opts = x['options']
        if not isinstance(opts, list) or len(opts) < 2 or not all(isinstance(o, str) and o for o in opts):
            errs.append(f"{x['id']}: options must be >= 2 non-empty strings")
        errs += [f"{x['id']}: leak key {p}" for p in leak_paths(x, allow=STATE_KEY_ALLOW.get(name, frozenset()))]
        g = gold.get(x['id'])
        if g is None or set(g) != {'answer', 'n'} or g['n'] != len(opts) or not 1 <= g['answer'] <= g['n']:
            errs.append(f"{x['id']}: gold {g}")
    return errs


def tokenizer():
    path = LIKES / TOKENIZER
    if not path.exists():
        return None, None
    from tokenizers import Tokenizer
    return Tokenizer.from_file(str(path)), sha256_file(path)


def stats(items, gold, tok):
    n_opts = [len(x['options']) for x in items]
    out = {'items': len(items),
           'stage_counts': dict(sorted(Counter(x['stage'] for x in items).items())),
           'state_types': dict(sorted(Counter(type(x['state']).__name__ for x in items).items())),
           'option_count_histogram': {str(k): v for k, v in sorted(Counter(n_opts).items())},
           'max_options': max(n_opts),
           f'items_over_{MAX_RUNNER_OPTIONS}_options': sum(n > MAX_RUNNER_OPTIONS for n in n_opts),
           'items_with_duplicate_option_text': sum(len(set(x['options'])) != len(x['options']) for x in items),
           'items_with_empty_question': sum(not x['question'] for x in items),
           'label_named_state_fields': dict(sorted(Counter(generic(q) for x in items for q in leak_paths(x)).items())),
           'answer_position_histogram': {str(k): v for k, v in sorted(Counter(g['answer'] for g in gold.values()).items())}}
    if tok is not None:
        # julia/repo/julia/data.py:80,83: encode(' ' + option, add_special_tokens=False), refused when > 48 tokens
        lens = [[len(tok.encode(' ' + o, add_special_tokens=False).ids) for o in x['options']] for x in items]
        out[f'options_over_{OPTION_TOKEN_CAP}_tokens'] = sum(n > OPTION_TOKEN_CAP for ls in lens for n in ls)
        out[f'items_with_option_over_{OPTION_TOKEN_CAP}_tokens'] = sum(any(n > OPTION_TOKEN_CAP for n in ls) for ls in lens)
        out['max_option_tokens'] = max(n for ls in lens for n in ls)
    return out


def build(name, a, tok, tok_sha):
    meta, rows = BUILDERS[name](a)
    items = [x for x, _ in rows]
    gold = {x['id']: {'answer': ans, 'n': len(x['options'])} for x, ans in rows}
    errs = validate(name, items, gold)
    if errs:
        raise ValueError(f'{name}: ' + '; '.join(errs[:10]))
    out = SETS_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    items_text = jsonl(items)
    gold_text = json.dumps(gold, ensure_ascii=False, indent=1) + '\n'
    (out / 'items.jsonl').write_text(items_text)
    (out / 'gold.json').write_text(gold_text)
    st = stats(items, gold, tok)
    if tok is not None:
        st['option_tokenizer'] = {'path': str(LIKES / TOKENIZER), 'sha256': tok_sha,
                                  'rule': f"len(encode(' ' + option, add_special_tokens=False)) > {OPTION_TOKEN_CAP} "
                                          '(julia/repo/julia/data.py:83-85)'}
    else:
        st['option_tokenizer'] = None
    manifest = {'set': name, 'builder': 'claims/build.py', 'source': meta.pop('source'), 'maker': meta.pop('maker'),
                'items': len(items),
                'sha256': {'items.jsonl': sha256_bytes(items_text.encode()), 'gold.json': sha256_bytes(gold_text.encode())},
                **{k: v for k, v in meta.items() if k not in ('rendering', 'notes')},
                'stats': st, 'rendering': meta['rendering'], 'notes': meta['notes']}
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n')
    return manifest


def check_written(names):
    """Re-read written sets: gold in range, no label leak, unique ids, manifest hashes match the files."""
    failed = False
    for name in names:
        d = SETS_DIR / name
        if not (d / 'items.jsonl').exists():
            print(f'{name}: not built')
            continue
        items = [json.loads(l) for l in (d / 'items.jsonl').read_text().splitlines() if l.strip()]
        gold = json.loads((d / 'gold.json').read_text())
        manifest = json.loads((d / 'manifest.json').read_text())
        errs = validate(name, items, gold)
        for f in ('items.jsonl', 'gold.json'):
            if sha256_file(d / f) != manifest['sha256'][f]:
                errs.append(f'{f} sha256 differs from manifest')
        raw = (d / 'items.jsonl').read_text()
        errs += [f'{k} key appears in items.jsonl' for k in ('"gold"', '"_meta"', '"provenance"',
                                                            '"target_distribution"', '"published_models"')
                 if f'{k}:' in raw]
        # "label" is checked structurally by validate(): allowed only at STATE_KEY_ALLOW paths (maker document fields)
        n_label = raw.count('"label":')
        n_allowed = sum(generic(q) in STATE_KEY_ALLOW.get(name, ()) for x in items for q in leak_paths(x))
        if n_label != n_allowed:
            errs.append(f'"label" appears {n_label} times in items.jsonl, {n_allowed} at allowed state paths')
        print(f"{name}: {len(items)} items, {len(set(x['id'] for x in items))} unique ids, "
              f"answers in range {all(1 <= g['answer'] <= g['n'] for g in gold.values())}, "
              f"{'OK' if not errs else 'FAIL ' + '; '.join(errs[:5])}")
        failed |= bool(errs)
    return not failed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('sets', nargs='+', help=f"'all', 'check', or any of: {', '.join(BUILDERS)}")
    ap.add_argument('--typesafe-dir', help='read typesafe-<workflow>-cases.js from here instead of downloading')
    a = ap.parse_args()
    if a.sets == ['check']:
        sys.exit(0 if check_written(list(BUILDERS)) else 1)
    names = list(BUILDERS) if a.sets == ['all'] else a.sets
    unknown = [n for n in names if n not in BUILDERS]
    if unknown:
        ap.error(f'unknown set(s): {unknown}')
    tok, tok_sha = tokenizer()
    for name in names:
        m = build(name, a, tok, tok_sha)
        s = m['stats']
        print(f"{name}: {m['items']} items, max options {s['max_options']}, "
              f"over {MAX_RUNNER_OPTIONS} options {s[f'items_over_{MAX_RUNNER_OPTIONS}_options']}, "
              f"options over {OPTION_TOKEN_CAP} tokens {s.get(f'options_over_{OPTION_TOKEN_CAP}_tokens')}, "
              f"items.jsonl {m['sha256']['items.jsonl'][:12]} gold.json {m['sha256']['gold.json'][:12]}", flush=True)
    sys.exit(0 if check_written(names) else 1)


if __name__ == '__main__':
    main()
