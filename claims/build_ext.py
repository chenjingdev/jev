"""Jev-like 제작자가 인용한 벤치마크를 gamebench/run.py 공통 문항 형식으로 옮긴다 (build.py와 별개 세트).

세트마다 claims/sets/<set>/ 에 items.jsonl(정답 없음), gold.json, manifest.json을 쓴다.
제작자 코드를 그대로 옮겨(import하지 않고) 다시 구현하고, 제작자가 남긴 해시로 재현을 확인한다.
  - jevbench-*: AbdelStark/jev-benchmarks@0d610cc 의 BTZSC 파일럿 (Julia-1이 인용). 매니페스트 해시 ec064c52… 재현.
  - laya-*: Laya research/scripts/bench_apps.py 의 Jev 비교 스위트 (400건).
  - jevmlx-typesafe45: jevmlx benchmarks/typesafe/fetch.py. cases.jsonl 해시 50401fe5… 재현.
원천 파일은 sha256을 고정하고 다르면 멈춘다. 시각·절대경로를 쓰지 않아 다시 돌리면 바이트가 같다.

  .venv/bin/python claims/build_ext.py {all|check|<set> ...}
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
import re
import sys
import urllib.request

HERE = Path(__file__).resolve().parent
SETS_DIR = HERE / 'sets'
LIKES = Path.home() / 'dev' / 'jev-likes'
CACHE = Path.home() / '.cache' / 'jev-claims'
RUNNER_MAX_OPTIONS = 26  # gamebench/run.py KEYS = A-Z
ITEM_KEYS = ('id', 'game', 'stage', 'state', 'question', 'options')

# 옵션 토큰 수(48 초과 집계용). Julia-1 스냅숏의 mmBERT 토크나이저, Laya처럼 앞에 공백 하나(common.py:119-125).
TOKENIZER = LIKES / 'julia' / 'repo' / 'tokenizer' / 'tokenizer.json'
TOKENIZER_SHA256 = '609d8f4c067cd3950f88594c5a802616cea245823836ef5848ee4fc40aab5b6f'
OPTION_TOKEN_LIMIT = 48


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    return sha256_bytes(Path(p).read_bytes())


def hf_file(repo, path, revision, sha256):
    from huggingface_hub import hf_hub_download
    p = Path(hf_hub_download(repo, path, repo_type='dataset', revision=revision))
    got = sha256_file(p)
    if got != sha256:
        raise RuntimeError(f'{repo}@{revision}/{path}: sha256 {got} != pinned {sha256}')
    return p, {'repo': repo, 'revision': revision, 'path': path,
               'url': f'https://huggingface.co/datasets/{repo}/blob/{revision}/{path}', 'sha256': got}


def read_parquet(p):
    import pyarrow.parquet as pq
    return pq.read_table(p).to_pydict()


_tok = None


def option_tokens(text):
    global _tok
    if _tok is None:
        if sha256_file(TOKENIZER) != TOKENIZER_SHA256:
            raise RuntimeError(f'{TOKENIZER}: sha256 mismatch')
        from tokenizers import Tokenizer
        _tok = Tokenizer.from_file(str(TOKENIZER))
    return len(_tok.encode(' ' + text, add_special_tokens=False).ids)


# ---------------------------------------------------------------- 1. jev-benchmarks BTZSC pilot
JEVBENCH_CLONE = LIKES / 'jev-benchmarks'
JEVBENCH_COMMIT = '0d610cc53e79bcbec691312b0c4adb4a0e371642'
BTZSC_REPO = 'btzsc/btzsc'
BTZSC_REVISION = 'fef2a2ac62b69c58670047dddf045c53d7c3cb5e'   # configs/pilot-v1.yaml:6
BTZSC_SEED = 20260917                                         # configs/pilot-v1.yaml:3
BTZSC_SAMPLES = 100                                           # configs/pilot-v1.yaml:7
BTZSC_QUESTION = 'Which single label best describes the input text?'  # configs/pilot-v1.yaml:23
# configs/pilot-v1.yaml:8-14, 순서가 시드 오프셋이다 (data.py:52, 77)
BTZSC_DATASETS = [
    ('agnews', 'topic', 'b51a89341546018960b5724596ad3192f12d0649c5e45e91a06c0cee4253510f'),
    ('emotiondair', 'emotion', '779970bb63817275a9d4004e4114ed00f2d86dc7670c36e13b4d018f85dc18ae'),
    ('banking77', 'intent', 'f42b14bddca9455891438e5e03ad2626e9de908eac0b65dbee4d5fa9eff8a776'),
]
# results/reports/btzsc-pilot-v1.json artifacts.manifest_sha256 — 제작자가 실제로 Jev에 보낸 100×3 선택
BTZSC_MANIFEST_SHA256 = 'ec064c52b149de458344cd4b4a44c158460f30b3bbb7fe8b2e7ec72d0abf3ba5'
JEV_BTZSC = {  # results/reports/btzsc-pilot-v1.md:17,19,21 (jev-1.13.0, n=100)
    'agnews': {'accuracy': 0.91, 'macro_f1': 0.905, 'line': 17},
    'banking77': {'accuracy': 0.87, 'macro_f1': 0.857, 'line': 19},
    'emotiondair': {'accuracy': 0.48, 'macro_f1': 0.479, 'line': 21},
}
JULIA_BTZSC = {  # Julia-1 README.md:28-30, metrics/accuracy-20260924.json benchmarks.*
    'agnews': {'correct': 94, 'total': 100, 'readme_line': 28},
    'emotiondair': {'correct': 86, 'total': 100, 'readme_line': 29},
    'banking77': {'correct': 64, 'total': 100, 'answered': 99, 'abstained': 1, 'readme_line': 30,
                  'protocol': 'ranking/top-16 shortlist, not a native 72-option call (README.md:42)'},
}
JEVBENCH_SETS = {'agnews': 'jevbench-agnews100', 'emotiondair': 'jevbench-emotion100',
                 'banking77': 'jevbench-banking77-100'}


def _class_count(texts):  # data.py:13-18
    first = texts[0]
    for index in range(1, len(texts)):
        if texts[index] != first:
            return index
    raise ValueError('could not infer class count from repeated BTZSC texts')


def _balanced_indices(targets, limit, seed):  # data.py:21-38
    by_class = defaultdict(list)
    for index, target in enumerate(targets):
        by_class[target].append(index)
    rng = random.Random(seed)
    for indices in by_class.values():
        rng.shuffle(indices)
    chosen = []
    classes = sorted(by_class)
    while len(chosen) < min(limit, len(targets)):
        made_progress = False
        for class_id in classes:
            if by_class[class_id] and len(chosen) < limit:
                chosen.append(by_class[class_id].pop())
                made_progress = True
        if not made_progress:
            break
    return sorted(chosen)


_btzsc = None


def btzsc_examples():
    """data.py:41-94 load_examples. 세 데이터셋을 함께 만들고 제작자 매니페스트 해시와 대조한다."""
    global _btzsc
    if _btzsc is not None:
        return _btzsc
    examples, sources, stats = [], {}, {}
    for offset, (name, task, sha) in enumerate(BTZSC_DATASETS):
        path, src = hf_file(BTZSC_REPO, f'{name}/test-00000-of-00001.parquet', BTZSC_REVISION, sha)
        rows = read_parquet(path)
        binary = [int(v) for v in rows['labels']]
        texts = [str(v) for v in rows['text']]
        n_classes = _class_count(texts)
        total = len(texts) // n_classes
        labels = tuple(str(rows['hypothesis'][i]) for i in range(n_classes))
        valid, targets = [], []
        for sample_index in range(total):
            values = binary[sample_index * n_classes:(sample_index + 1) * n_classes]
            if sum(values) == 1:
                valid.append(sample_index)
                targets.append(values.index(1))
        selected = _balanced_indices(targets, BTZSC_SAMPLES, BTZSC_SEED + offset)
        for position in selected:
            sample_index = valid[position]
            text = texts[sample_index * n_classes]
            examples.append({'dataset': name, 'task': task, 'example_id': f'{name}:{sample_index}', 'text': text,
                             'text_sha256': sha256_bytes(text.encode()), 'labels': list(labels),
                             'target_index': targets[position]})
        sources[name] = src
        stats[name] = {'rows': len(texts), 'n_classes': n_classes, 'samples': total,
                       'samples_without_single_positive_excluded': total - len(valid),
                       'seed': BTZSC_SEED + offset}
    # io.py:21-27 write_jsonl 형식 그대로 직렬화해 제작자 매니페스트와 대조
    blob = ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n' for r in examples).encode()
    got = sha256_bytes(blob)
    if got != BTZSC_MANIFEST_SHA256:
        raise RuntimeError(f'BTZSC selection does not reproduce the maker manifest: {got}')
    _btzsc = examples, sources, stats, got
    return _btzsc


def build_jevbench(name):
    set_name = JEVBENCH_SETS[name]
    examples, sources, stats, manifest_sha = btzsc_examples()
    items, gold = [], {}
    for ex in (e for e in examples if e['dataset'] == name):
        iid = f"{set_name}:{ex['example_id']}"
        # adapters/jev.py:19-20, 30-33: state {"text": ...}, Choice(question, {label_NNN: hypothesis})
        items.append({'id': iid, 'game': set_name, 'stage': name, 'state': {'text': ex['text']},
                      'question': BTZSC_QUESTION, 'options': list(ex['labels'])})
        gold[iid] = {'answer': ex['target_index'] + 1, 'n': len(ex['labels'])}
    notes = [
        'Selection mirrors jev_benchmarks/data.py:41-94 (load_examples): BTZSC rows come in blocks of n_classes '
        '(one row per hypothesis, same text), class count inferred from the first text change (data.py:13-18), '
        'samples without exactly one positive are dropped (data.py:66-73), then _balanced_indices(targets, 100, '
        'seed=20260917+dataset_offset) (data.py:21-38, 74-78). Offsets follow configs/pilot-v1.yaml:8-14 order '
        '(agnews 0, emotiondair 1, banking77 2).',
        f'Reproduction proof: the 300-example selection serialised as jev_benchmarks/io.py:21-27 write_jsonl hashes to '
        f'{manifest_sha}, equal to artifacts.manifest_sha256 in results/reports/btzsc-pilot-v1.json. The build fails '
        f'if this ever differs.',
        'Request mirrors jev_benchmarks/adapters/jev.py:19-20 and :30-33: state={"text": text} (a dict, kept as is), '
        'one Choice with instructions = configs/pilot-v1.yaml:23 and criteria {"label_000": hypothesis_0, ...}. '
        'options = the hypothesis strings in BTZSC column order (data.py:65); the label_NNN keys are replaced by the '
        "runner's A-Z keys (gamebench/run.py:28-34). No wording added.",
        'Julia-1 README.md:42 says its classification pilots follow this pinned protocol; the Julia repo ships no '
        'rendering code of its own, so the jev-benchmarks request is the one mirrored.',
        'ids: "<set>:<example_id>" with example_id = "<dataset>:<sample_index>" from data.py:87.',
    ]
    if name == 'banking77':
        notes += [
            'Banking77 in BTZSC exposes 72 hypotheses; 200 of 3,080 samples have no positive and are excluded '
            '(docs/PROTOCOL.md:40-43). Jev received all 72 options in one native Choice call; its 0.870 is for that.',
            'Julia-1 did NOT use this request: README.md:42 "Banking uses a 72-label pilot through a ranking/top-16 '
            'shortlist, not a native 72-option call". The shortlist is model-produced: provenance.json:20-24 has a '
            '"banking-rank" validation entry and provenance.json:518-523 reports banking77 recall_at_16 0.99; '
            'julia/router/router.py:25-30 and julia/router/README.md:131-148 describe the only public >20-option '
            'path as model-scored groups with reranked survivors. No deterministic, model-free shortlist exists in '
            'the Julia repo, so no shortlist set is built; this set is the all-72-label variant (what Jev saw). '
            "Julia's 64/100 is therefore not directly comparable to a run on this set.",
            'RUNNER LIMIT: every item has 72 options > 26. gamebench/run.py:32 dict(zip(KEYS, order)) silently '
            'drops options 27-72 (and with them the gold for many items) instead of failing. Do not run this set '
            'through gamebench/run.py until the runner supports >26 options or refuses them.',
        ]
    refs = {'jev': dict(JEV_BTZSC[name], model='jev-1.13.0 (resolved from jev-latest)', n=100,
                        source=f'jev-benchmarks results/reports/btzsc-pilot-v1.md:{JEV_BTZSC[name]["line"]}; '
                               f'results/reports/btzsc-pilot-v1.json results.jev.{name}'),
            'julia-1': dict(JULIA_BTZSC[name], source='Julia-1 README.md:26-30, metrics/accuracy-20260924.json '
                                                     f'benchmarks.{name}; Jev column there = the numbers above')}
    return set_name, items, gold, {
        'maker': 'AbdelStark/jev-benchmarks BTZSC pilot v1 (cited by SupersonicLabs/Julia-1 README.md:42)',
        'maker_code': {'repo': 'https://github.com/AbdelStark/jev-benchmarks', 'commit': JEVBENCH_COMMIT,
                       'clone': '~/dev/jev-likes/jev-benchmarks',
                       'files': ['configs/pilot-v1.yaml', 'src/jev_benchmarks/data.py',
                                 'src/jev_benchmarks/adapters/jev.py', 'src/jev_benchmarks/io.py']},
        'citing_maker': {'repo': 'https://huggingface.co/SupersonicLabs/Julia-1',
                         'snapshot': 'a85b127321d580d65176c89ced8273f305745d85',
                         'readme_sha256': 'bc46a6785ddbae32b769591841954393510b073f148aa9f7e4fced5a1bba9a81'},
        'source': {'dataset': BTZSC_REPO, 'config': name, 'split': 'test', 'files': [sources[name]]},
        'selection': dict(stats[name], method='data.py _balanced_indices', maker_manifest_sha256=manifest_sha),
        'references': refs, 'notes': notes}


# ---------------------------------------------------------------- 2. Laya bench_apps.py
LAYA_COMMIT = '4066d5d5fbf08b66c6757ddeedbd797bd7655bc0'
LAYA_N = 400  # bench_apps.py:41 (BENCH_N default); app_benchmark_results.json meta.n_per_task = 400
LAYA_SOURCES = {  # Laya does not pin revisions; these are the HF heads, unchanged since before its 2026-09-19 run
    'ag_news': ('fancyzhx/ag_news', 'eb185aade064a813bc0b7f42de02595523103ca4', 'data/test-00000-of-00001.parquet',
                '71de87ec66bc5737752a2502204dfa6d7fe9856ade3ea444dc6317789a4f13fb', '2024-03-07'),
    'emotion': ('dair-ai/emotion', 'cab853a1dbdf4c42c2b3ef2173804746df8825fe', 'split/test-00000-of-00001.parquet',
                '6f8407fa1ca9c310f55781f082ed73812f6551e8dda2c61973123a121869245b', '2024-08-08'),
    'banking77': ('mteb/banking77', '18072d2685ea682290f7b8924d94c62acc19c0b2', 'data/test-00000-of-00001.parquet',
                  '9575f636fdeae0c94a0f3f2d926ca8f9a2833b998cf94108936dfd5d72322bf9', '2025-07-06'),
}
LAYA_SETS = {'ag_news': 'laya-agnews400', 'emotion': 'laya-emotion400', 'banking77': 'laya-banking77-400'}
# research/results/app_benchmark_results.json suites.jev.* (laya 0.2.1, CPU, 2026-09-19); BENCHMARKS.md:145-147
LAYA_RESULTS = {
    'ag_news': {'laya': 0.95, 'laya-multilingual': 0.93, 'laya-typed-decisions': 0.9525, 'benchmarks_md_line': 145},
    'emotion': {'laya': 0.595, 'laya-multilingual': 0.53, 'laya-typed-decisions': 0.6, 'benchmarks_md_line': 146},
    'banking77': {'laya': 0.425, 'laya-multilingual': 0.425, 'laya-typed-decisions': 0.4925,
                  'benchmarks_md_line': 147},
}
LAYA_JEV = {'ag_news': ('agnews', 0.91), 'emotion': ('emotiondair', 0.48), 'banking77': ('banking77', 0.87)}


def laya_option(key, value):
    """criteria 값이 설명. None/"" 이면 Laya는 키 자체를 옵션 텍스트로 쓴다 (laya/common.py:79-80)."""
    return str(key) if value is None or value == '' else value


def build_laya(name):
    set_name = LAYA_SETS[name]
    repo, rev, path, sha, _ = LAYA_SOURCES[name]
    p, src = hf_file(repo, path, rev, sha)
    rows = read_parquet(p)
    n_rows = len(rows['text'])
    items, gold = [], {}
    extra = {}
    if name == 'ag_news':  # bench_apps.py:78-88
        crit = {'world': 'world news and international politics', 'sports': 'sports',
                'business': 'business and economy', 'sci_tech': 'science and technology'}
        keys = list(crit)
        state_key, question = 'article', 'What is the topic of `article`?'
        options = [laya_option(k, v) for k, v in crit.items()]
        answer = lambda i: keys.index(keys[int(rows['label'][i])])
    elif name == 'emotion':  # bench_apps.py:94-104
        names = ['sadness', 'joy', 'love', 'anger', 'fear', 'surprise']
        state_key, question = 'text', 'Which emotion is most strongly expressed in `text`?'
        options = [laya_option(n, None) for n in names]
        answer = lambda i: int(rows['label'][i])
    else:  # bench_apps.py:110-120 + choice_q :67-69
        labels = sorted(set(rows['label_text']))
        keys = [x.replace('_', ' ') for x in labels]
        state_key, question = 'message', 'Which banking intent does `message` express?'
        options = [laya_option(k, None) for k in keys]
        answer = lambda i: keys.index(rows['label_text'][i].replace('_', ' '))
        extra['n_labels'] = len(labels)
    for i in range(min(LAYA_N, n_rows)):  # `for r in list(d)[:N]`
        iid = f'{set_name}:test-{i}'
        items.append({'id': iid, 'game': set_name, 'stage': name, 'state': {state_key: rows['text'][i]},
                      'question': question, 'options': list(options)})
        gold[iid] = {'answer': answer(i) + 1, 'n': len(options)}
    jev_key, jev_acc = LAYA_JEV[name]
    lines = {'ag_news': '76-90', 'emotion': '92-106', 'banking77': '108-122'}[name]
    notes = [
        f'Mirrors laya research/scripts/bench_apps.py:{lines} (commit {LAYA_COMMIT[:7]}). Selection is the first '
        f'{LAYA_N} rows of the HF test split in file order (`list(d)[:N]`, N from bench_apps.py:41). SEED=13 '
        '(bench_apps.py:40, BENCHMARKS.md:9 "seed 13") is never used by this suite: rng only touches the '
        'phishing/toxic-chat/MS MARCO/routing suites.',
        f'Laya calls load_dataset("{repo}"{", \"split\"" if name == "emotion" else ""}, split="test") with no '
        f'revision. Pinned here to {repo}@{rev} (last modified {LAYA_SOURCES[name][4]}, before Laya\'s 2026-09-19 run), '
        f'file {path}; the build fails if its sha256 changes. The datasets library reads this single parquet file '
        'in file order, so pyarrow reproduces its row order.',
        f'state = {{"{state_key}": text}} (a dict, as Laya sends it); question = the Laya instructions string verbatim.',
        'Not the same benchmark as the jevbench-* sets of item 1: different source (raw HF dataset vs BTZSC '
        'fef2a2a), different selection (first 400 rows vs class-balanced seeded 100), different state key, '
        'instructions and option texts. Hence a separate set.',
        f'Laya compares these runs with Jev {jev_acc} (bench_apps.py:44-50, "AbdelStark/jev-benchmarks v0.1.0", '
        f'n=100). That number was measured on jevbench-{"banking77-100" if name == "banking77" else jev_key.replace("dair", "")+"100"} '
        '(item 1), not on these 400 items; BENCHMARKS.md:3 says Jev was never run by Laya.',
    ]
    if name == 'ag_news':
        notes.append('options = the criteria descriptions (bench_apps.py:79-80) in dict order world, sports, '
                     'business, sci_tech; the keys are replaced by the runner\'s A-Z keys. Laya\'s own model '
                     'renders each option as "key: description" (laya/common.py:79); the runner sends only the '
                     'description, like the jev-benchmarks request does.')
    elif name == 'emotion':
        notes.append('criteria are {name: None} (bench_apps.py:101). With no description Laya renders the key '
                     'itself as the option text (laya/common.py:79-80), and CLM embeds the key when the description '
                     'is empty (CLM README API table), so options = the six emotion names in dair-ai label order '
                     '(label ints 0-5, bench_apps.py:95, 102).')
    else:
        covered = len({g['answer'] for g in gold.values()})
        notes += [f'mteb/banking77 test is ordered by label, so the first {LAYA_N} rows cover only {covered} of the '
                  f'{len(labels)} intents ({LAYA_N // covered if covered else 0} rows each). That is what Laya ran '
                  '(bench_apps.py:113 `list(d)[:N]`); not a class-balanced sample.',
                  'labels = sorted(set(test label_text)) with "_" -> " " (bench_apps.py:111, 115-116); criteria '
                  'are {key: None}, so options = those keys (laya/common.py:79-80). 77 labels, unlike BTZSC\'s 72.',
                  'Laya\'s BENCHMARKS.md:147-149 compares its 77-label 400-item accuracy with Jev\'s 72-label '
                  '100-item BTZSC 0.870.',
                  'RUNNER LIMIT: every item has 77 options > 26. gamebench/run.py:32 dict(zip(KEYS, order)) silently '
                  'drops options 27-77 instead of failing. Do not run this set through gamebench/run.py as is.']
    return set_name, items, gold, {
        'maker': 'NandhaKishorM/laya research/scripts/bench_apps.py (BENCHMARKS.md "On the public datasets where '
                 'Jev numbers exist")',
        'maker_code': {'repo': 'https://github.com/NandhaKishorM/laya', 'commit': LAYA_COMMIT,
                       'files': ['research/scripts/bench_apps.py', 'laya/common.py']},
        'source': {'dataset': repo, 'config': 'split' if name == 'emotion' else 'default', 'split': 'test',
                   'rows_in_split': n_rows, 'files': [src]},
        'selection': dict({'method': f'first {LAYA_N} rows', 'seed_used': None}, **extra),
        'references': {
            'laya': dict(LAYA_RESULTS[name], n=LAYA_N, source='laya research/results/app_benchmark_results.json '
                                                              f'suites.jev.{"banking77_full" if name == "banking77" else name}'),
            'jev': {'accuracy': jev_acc, 'n': 100, 'measured_on': JEVBENCH_SETS[jev_key],
                    'source': 'laya bench_apps.py:44-50 citing jev-benchmarks v0.1.0; NOT measured on this set'}},
        'notes': notes}


# ---------------------------------------------------------------- 3. jevmlx TypeSafe public cases
JEVMLX_COMMIT = '7e0d746081b88412ccd7d84a5ffdcf9d61b36904'
TS_BASE_URL = 'https://evals.typesafe.ai'                          # fetch.py:45
TS_USER_AGENT = 'Mozilla/5.0 (compatible; jevmlx-eval-fetcher)'   # fetch.py:52
TS_WORKFLOWS = ('security_incidents', 'agent_trace_observability', 'invoice_processing',
                'customer_service')                                # questions.py:15-20
TS_SCORE_CHOICES = ('0', '1', '2', '3')                            # questions.py:24
TS_AMBIGUOUS_MARGIN = 0.1                                          # questions.py:28
# benchmarks/results/*/typesafe.dataset.lock.json sources[] (fetched 2026-09-17 by jevmlx); same bytes today
TS_PAGES = {
    'security_incidents': ('6c96b19f192d07004613afc281a31712aa7d04bd75e31a3afe2322174ade0645',
                           '"8aa770ab7aff994e7d075483c66d03ab"', '2026-09-17T18:34:16+00:00'),
    'agent_trace_observability': ('4a3821a24366dc9830e12b481a23c96d0ab70e3c473b59551b88e8d0c4b615b3',
                                  '"27977ed69ce977e87e49751e4691a8d6"', '2026-09-17T18:34:17+00:00'),
    'invoice_processing': ('8c2f886978a30e637d577cd0713b3cf12bb622ef7210fcc9a4be47540a6df27f',
                           '"69aac93baa3562a90227ccbde1f3364e"', '2026-09-17T18:34:17+00:00'),
    'customer_service': ('066f789bcc17ae906a17fc37ad4fd2f2bb1e881245aeb76b524715bc962a2493',
                         '"1e5a58af6a69c79c1cdb9f4c7388e81a"', '2026-09-17T18:34:17+00:00'),
}
TS_CASES_SHA256 = '50401fe5facb25dce1c72713def4582512c52763c423af8f567fb2176156eeea'  # same lock, cases_sha256
TS_SET = 'jevmlx-typesafe45'
TS_JEV_CITED = {'accuracy': 0.678, 'by_workflow': {'customer_service': 0.76, 'agent_trace_observability': 0.716,
                                                   'security_incidents': 0.617, 'invoice_processing': 0.618}}
_VIEWER_DATA_RE = re.compile(r'__VIEWER_DATA__\((\{.*\})\)', re.S)


def ts_page(workflow):
    sha, etag, fetched = TS_PAGES[workflow]
    cached = CACHE / 'typesafe' / f'{workflow}-{sha[:12]}.js'
    url = f'{TS_BASE_URL}/{workflow}-cases.js'
    if cached.exists() and sha256_file(cached) == sha:
        raw = cached.read_bytes()
    else:
        req = urllib.request.Request(url, headers={'User-Agent': TS_USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
            raw = r.read()
        if sha256_bytes(raw) != sha:
            raise RuntimeError(f'{url}: sha256 {sha256_bytes(raw)} != jevmlx lock {sha}')
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(raw)
    text = raw.decode('utf-8', errors='replace')
    m = _VIEWER_DATA_RE.search(text) or re.search(r'__VIEWER_DATA__\((.*)\)', text, re.S)  # fetch.py:70-75
    return json.loads(m.group(1))['eval'], {'url': url, 'sha256': sha, 'etag': etag, 'jevmlx_fetched_at': fetched}


def ts_field_schema(q):  # questions.py:38-66
    instructions, criteria, qtype = q['instructions'], q.get('criteria'), q['type']
    if qtype == 'noul':
        return {'type': 'boolean', 'description': instructions}
    if qtype == 'choice':
        return {'type': 'enum', 'description': instructions, 'choices': list(criteria)}
    if qtype == 'score':
        levels = '; '.join(f'{i} = {text}' for i, text in enumerate(criteria))
        return {'type': 'enum', 'description': f'{instructions} Scale: {levels}.',
                'choices': list(TS_SCORE_CHOICES), 'ordered': True}
    return None


def ts_margin(distribution):  # questions.py:83-88
    probs = sorted((float(p) for p in distribution.values()), reverse=True)
    if not probs:
        return 0.0
    return probs[0] - (probs[1] if len(probs) > 1 else 0.0)


def ts_canonical(value, qtype):  # fetch.py:126-139
    if qtype == 'noul':
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return float(value) >= 0.5
        return str(value).lower() == 'true'
    if qtype == 'score':
        try:
            return str(max(0, min(3, int(round(float(value))))))
        except (TypeError, ValueError):
            return None
    return str(value)


def ts_dist_key(label, qtype):  # fetch.py:217-223
    if label is None:
        return None
    if qtype == 'noul':
        return 'true' if label else 'false'
    return str(label)


def ts_consensus(entry, where, choices=None):  # fetch.py:142-198
    sets = entry.get('sets') or []
    prob_sets = [s for s in sets if s.get('probabilities')]
    value_sets = [s for s in sets if not s.get('probabilities') and s.get('value') is not None]
    if prob_sets and value_sets:
        raise ValueError(f'{where}: mixed consensus forms (probability and bare-value sets)')
    qtype = entry['type']
    distribution = {}
    if prob_sets:
        totals = {}
        for s in prob_sets:
            for key, prob in s['probabilities'].items():
                totals[key] = totals.get(key, 0.0) + float(prob)
        total = sum(totals.values())
        distribution = {k: v / total for k, v in totals.items()} if total else {}
    elif value_sets:
        votes = {}
        for s in value_sets:
            key = ts_dist_key(ts_canonical(s['value'], qtype), qtype)
            if key is not None:
                votes[key] = votes.get(key, 0) + 1
        total = sum(votes.values())
        distribution = {k: c / total for k, c in votes.items()} if total else {}
    if not distribution:
        return None, {}, 0.0, True
    if qtype == 'noul':  # fetch.py:201-214 _choice_order
        ordered = [k for k in ('true', 'false') if k in distribution]
    else:
        ordered = [k for k in (choices or ()) if k in distribution]
        ordered += sorted(k for k in distribution if k not in ordered)
    top = max(ordered, key=lambda k: distribution[k])
    margin = ts_margin({k: distribution[k] for k in ordered})
    label = (top == 'true') if qtype == 'noul' else top  # fetch.py:226-230
    return label, distribution, margin, margin < TS_AMBIGUOUS_MARGIN


def ts_split(case_id):  # fetch.py:57-67
    return 'holdout' if int(hashlib.sha1(case_id.encode()).hexdigest()[:8], 16) % 5 == 0 else 'train'


def ts_records(workflow, ev, forms):
    """fetch.py:284-392 iter_case_records/_case_records, 같은 dict 순서로.

    forms[(record_id, field)] = (합의 형식, 검토자 수)는 기록 밖의 부가 정보 (해시에 들어가지 않는다)."""
    catalog, documents = ev['questions'], ev['documents']
    for example in ev['examples']:
        case_id = example['case_id']
        case = ev['cases'][case_id]
        qmap = {}
        for md in case.get('models', {}).values():
            for node in md.get('nodes', []):
                for qid, idx in (node.get('questions') or {}).items():
                    qmap.setdefault(qid, int(idx))
        qid_counts = {}
        for node_answers in case.get('reference_answers', {}).values():
            for qid in node_answers:
                qid_counts[qid] = qid_counts.get(qid, 0) + 1
        occurrences = {}
        read_sets = {}  # fetch.py:237-255
        for md in case.get('models', {}).values():
            for node in md.get('nodes', []):
                nm = node.get('node')
                if nm is None:
                    continue
                read_sets.setdefault(nm, set())
                if node.get('doc') is not None:
                    read_sets[nm].add(int(node['doc']))
        for nm in case.get('reference_answers', {}):
            read_sets.setdefault(nm, set())
        read_sets = {k: frozenset(v) for k, v in read_sets.items()}
        groups = []
        for nm in case.get('reference_answers', {}):
            for docs, names in groups:
                if docs == read_sets[nm]:
                    names.append(nm)
                    break
            else:
                groups.append((read_sets[nm], [nm]))
        for gi, (docs, node_names) in enumerate(groups):
            schema, labels, cons, margins, ambiguous, models_meta, skipped = {}, {}, {}, {}, [], {}, 0
            gforms = {}
            for nm in node_names:
                for qid, entry in case['reference_answers'][nm].items():
                    field = None
                    idx = qmap.get(qid)
                    if idx is not None and 0 <= idx < len(catalog):
                        field = ts_field_schema(catalog[idx])
                    occurrences[qid] = occurrences.get(qid, 0) + 1
                    if field is None:
                        skipped += 1
                        continue
                    value, dist, margin, amb = ts_consensus(entry, f'{workflow}/{case_id}/{nm}/{qid}',
                                                            choices=field.get('choices'))
                    if value is None:
                        skipped += 1
                        continue
                    fname = f'{nm}__{qid}__{occurrences[qid]}' if qid_counts[qid] > 1 else qid
                    schema[fname], labels[fname], cons[fname], margins[fname] = field, value, dist, margin
                    if amb:
                        ambiguous.append(fname)
                    sets = entry.get('sets') or []
                    gforms[fname] = ('probability-average' if any(x.get('probabilities') for x in sets)
                                     else 'vote', len(sets))
                    answers = {}  # fetch.py:268-281
                    for model, md in case.get('models', {}).items():
                        for node in md.get('nodes', []):
                            if node.get('node') != nm:
                                continue
                            ans = (node.get('answers') or {}).get(qid)
                            if ans is None:
                                continue
                            raw = ans.get(ans.get('type'))
                            if raw is not None:
                                answers.setdefault(model, raw)
                    if answers:
                        models_meta[fname] = answers
            rid = f'typesafe/{workflow}/{case_id}' + (f'/n{gi}' if len(groups) > 1 else '')
            forms.update({(rid, f): v for f, v in gforms.items()})
            context = '\n\n'.join(  # fetch.py:233-265
                f'## Document {i}\n' + (documents[i] if isinstance(documents[i], str)
                                        else json.dumps(documents[i], indent=1, ensure_ascii=False))
                for i in sorted(docs) if 0 <= i < len(documents))
            yield {'id': rid, 'group_id': f'typesafe/{workflow}/{case_id}', 'source': 'typesafe',
                   'workflow': workflow, 'benchmark_only': True, 'schema': schema, 'context': context,
                   'labels': labels, 'split': ts_split(rid),
                   'meta': {'consensus': cons, 'margin': margins, 'ambiguous': ambiguous, 'models': models_meta},
                   'skipped_questions': skipped}


def ts_pick(raw, ftype, is_score):  # published.py:52-60
    if raw is None:
        return None
    if is_score and isinstance(raw, (int, float)):
        return str(int(round(raw)))
    if ftype == 'boolean' and isinstance(raw, (int, float)):
        return bool(raw >= 0.5)
    return raw


def build_typesafe():
    records, sources, skipped, fields, forms = [], [], 0, Counter(), {}
    for wf in TS_WORKFLOWS:
        ev, src = ts_page(wf)
        sources.append(src)
        for rec in ts_records(wf, ev, forms):
            skipped += rec.pop('skipped_questions')  # fetch.py:409
            fields.update(f['type'] for f in rec['schema'].values())
            records.append(rec)
    blob = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records).encode()  # fetch.py:436-438
    cases_sha = sha256_bytes(blob)
    if cases_sha != TS_CASES_SHA256:
        raise RuntimeError(f'TypeSafe records do not reproduce jevmlx cases.jsonl: {cases_sha}')
    items, gold, ambiguous_ids, empty_state = [], {}, [], []
    unreachable, five_level, gold_forms, vote_ties = [], [], Counter(), []
    model_names = sorted({m for r in records for a in r['meta']['models'].values() for m in a})
    jev = {'all': [0, 0], 'strict_common_subset': [0, 0], 'by_workflow_all': defaultdict(lambda: [0, 0])}
    for rec in records:
        for fname, field in rec['schema'].items():
            iid = f"{TS_SET}:{rec['id']}::{fname}"  # published.py:63-69 <record_id>::<field>
            # boolean -> ("true", "false") jevmlx/schema.py:444; enum -> choices (questions.py:55, :57-61)
            options = ['true', 'false'] if field['type'] == 'boolean' else list(field['choices'])
            label = rec['labels'][fname]
            key = ('true' if label else 'false') if field['type'] == 'boolean' else str(label)
            if field.get('ordered') and set(rec['meta']['consensus'][fname]) - set(options):
                five_level.append(iid)  # TypeSafe rubric has more levels than jevmlx's fixed 0-3 scale
            if key not in options:
                # jevmlx's own model cannot pick this gold; the runner needs 1 <= answer <= n, so leave it out
                unreachable.append({'id': iid, 'consensus_label': key, 'jevmlx_options': options,
                                    'consensus': rec['meta']['consensus'][fname]})
                continue
            items.append({'id': iid, 'game': TS_SET, 'stage': rec['workflow'], 'state': rec['context'],
                          'question': field['description'], 'options': options})
            gold[iid] = {'answer': options.index(key) + 1, 'n': len(options)}
            form, n_sets = forms[(rec['id'], fname)]
            gold_forms[f'{form}, {n_sets} reviewer set(s)'] += 1
            if form == 'vote' and rec['meta']['margin'][fname] == 0.0:
                vote_ties.append(iid)
            if not rec['context']:
                empty_state.append(iid)
            amb = fname in rec['meta']['ambiguous']
            if amb:
                ambiguous_ids.append(iid)
            answers = rec['meta']['models'].get(fname, {})
            raw = answers.get('typesafe')
            if raw is not None:
                ok = ts_pick(raw, field['type'], tuple(field.get('choices') or ()) == TS_SCORE_CHOICES) == label
                for bucket in (jev['all'], jev['by_workflow_all'][rec['workflow']]):
                    bucket[0] += ok
                    bucket[1] += 1
                if not amb and all(answers.get(m) is not None for m in model_names):
                    jev['strict_common_subset'][0] += ok
                    jev['strict_common_subset'][1] += 1
    rate = lambda p: {'agreed': p[0], 'total': p[1], 'agreement': round(p[0] / p[1], 4) if p[1] else None}
    notes = [
        f'Fetch mirrors jevmlx benchmarks/typesafe/fetch.py (commit {JEVMLX_COMMIT[:7]}): GET {TS_BASE_URL}/'
        '<workflow>-cases.js with the jevmlx User-Agent (fetch.py:45, 52, 82-86, 106), payload = the '
        '__VIEWER_DATA__(...) JSON "eval" object (fetch.py:54, 70-75). Page sha256s are pinned to jevmlx\'s own '
        'typesafe.dataset.lock.json (benchmarks/results/*/typesafe.dataset.lock.json); today\'s bytes are identical.',
        f'Reproduction proof: records rebuilt with the ported fetch.py:126-392 and serialised as fetch.py:436-438 '
        f'hash to {cases_sha}, equal to cases_sha256 in jevmlx\'s lock (45 records, 230 boolean + 135 enum fields, '
        '11 free-text questions skipped). The build fails if this ever differs.',
        'One item per (record, field): jevmlx scores all fields of a record in one prompt (PROMPT_PROTOCOL.md '
        '"Schema block"); the runner asks one question at a time. ids are "<set>:<record_id>::<field>", the same '
        'pair id jevmlx uses for the common subset (published.py:63-69). 45 records = 20 published cases, split '
        'per distinct document read-set (fetch.py:237-255, 320-330, 372-374).',
        'state = the jevmlx context string, kept as a string: "## Document <i>\\n" + json.dumps(doc, indent=1, '
        'ensure_ascii=False), documents of the read-set joined by blank lines (fetch.py:233-265). The "## Document '
        'i" header is jevmlx\'s wording, not added here.',
        (f'{len(empty_state)} item(s) have an empty-string state (a reference node no model ran has an empty '
         'read-set, fetch.py:250-255, 258-265); kept as jevmlx sends it, some systems may reject it.'
         if empty_state else
         'No item has an empty state. Records with no decidable field yield no items: '
         + ', '.join(r['id'] for r in records if not r['schema'])
         + ' (empty read-set, empty context, no fields; still counted in jevmlx\'s 45 records).'),
        'question = jevmlx field description: the TypeSafe instructions verbatim for noul/choice; for score, '
        'instructions + " Scale: 0 = <level0>; 1 = <level1>; ...." (questions.py:57-61).',
        'options follow jevmlx\'s schema, not TypeSafe\'s criteria: boolean -> ["true", "false"] (jevmlx/schema.py:'
        '444, same order as the TypeSafe criteria dicts); choice -> the criteria KEYS in published order '
        '(questions.py:55) - jevmlx drops the per-option descriptions TypeSafe publishes and Jev receives; '
        'score -> ["0","1","2","3"] with the level texts only inside the question. noul and score questions are '
        'posed as choices because the runner only has choose().',
        'Gold = jevmlx consensus pseudo-label, NOT independent ground truth. Each TypeSafe reference answer has one '
        '"set" per reference reviewer (README.md:165: GPT-6 Astra + Claude Fable 5.1; 1 or 2 sets per answer). If '
        'any set carries a probability distribution, the distributions are summed and normalised and gold = argmax; '
        'otherwise each set\'s bare value is one vote and gold = plurality (modal agreement). Ties are broken by the '
        'field\'s choice order, booleans true before false, and flagged ambiguous (fetch.py:142-214); score votes '
        'are rounded/clamped to 0-3 (fetch.py:134-138). Per item in this set: '
        + '; '.join(f'{k}: {v}' for k, v in sorted(gold_forms.items()))
        + f'. {len(vote_ties)} vote items are 1-1 reviewer splits whose gold is decided only by option order '
        '(vote_tie_ids).',
        f'jevmlx bug mirrored, not fixed: questions.py:24 fixes every score question to choices "0".."3", but '
        f'{len(five_level)} fields (agent_trace expressed_satisfaction, customer_service frustration) have a 5-level '
        'TypeSafe rubric 0-4; their question text still lists all five levels (questions.py:57) while the options '
        f'stop at "3" (five_level_ids). {len(unreachable)} of them have consensus label "4", which jevmlx\'s model can '
        'never choose; the runner needs 1 <= answer <= n, so those are left out of items/gold and listed in '
        f'excluded_unreachable_gold. The set therefore has {len(items)} items, not 365.',
        f'{len(ambiguous_ids)} items are ambiguous (consensus top1-top2 margin < 0.1 or tie, questions.py:28, '
        'fetch.py:195-196); they stay in the set as jevmlx keeps them (its "overall" agreement) and are listed in '
        'ambiguous_ids so the strict common subset (published.py:72-109) can be re-derived.',
        'Jev reference: jevmlx cites TypeSafe\'s official Jev 67.8% (README.md:150, benchmarks/typesafe/official.json) '
        'but that is on TypeSafe\'s full private eval with full criteria, not these 45 public cases (README.md:164). '
        'jev_published_answers below is NOT cited by jevmlx: it is Jev\'s own published per-question answers '
        '(payload model "typesafe") scored against this gold with jevmlx\'s pick rule (published.py:52-60) - '
        'boolean p>=0.5, score round(score), choice exact - and was produced from TypeSafe\'s native request '
        '(document object + full criteria), not from this rendering.',
        'Other jevmlx fetchers (benchmarks/public: ag_news/boolq/sst5; benchmarks/openjev; benchmarks/public/jabr.py; '
        'benchmarks/typed_decisions) exist, but no committed result or README claim uses them; only TypeSafe and '
        'jevmlx\'s own bundled presets appear in benchmarks/results/ and the leaderboard.',
    ]
    return TS_SET, items, gold, {
        'maker': 'bnsd55/jevmlx benchmarks/typesafe (README.md:142-165 leaderboard)',
        'maker_code': {'repo': 'https://github.com/bnsd55/jevmlx', 'commit': JEVMLX_COMMIT,
                       'files': ['benchmarks/typesafe/fetch.py', 'benchmarks/typesafe/questions.py',
                                 'benchmarks/typesafe/published.py', 'jevmlx/schema.py']},
        'source': {'site': TS_BASE_URL, 'files': sources, 'jevmlx_cases_sha256': cases_sha,
                   'records': len(records), 'fields': dict(sorted(fields.items())), 'skipped_free_text': skipped},
        'ambiguous_ids': ambiguous_ids, 'empty_state_ids': empty_state, 'five_level_ids': five_level,
        'excluded_unreachable_gold': unreachable, 'vote_tie_ids': vote_ties,
        'gold_consensus_forms': dict(sorted(gold_forms.items())),
        'references': {
            'jev_cited': dict(TS_JEV_CITED, source='jevmlx README.md:150, benchmarks/typesafe/official.json '
                                                   '(TypeSafe leaderboard retrieved 2026-09-17)',
                              scope='TypeSafe full private eval, NOT this set'),
            'jev_published_answers': {'all_fields': rate(jev['all']),
                                      'strict_common_subset': rate(jev['strict_common_subset']),
                                      'by_workflow_all_fields': {k: rate(v) for k, v in sorted(jev['by_workflow_all'].items())},
                                      'note': 'derived here from the payload, not cited by the maker'},
            'jevmlx_local': 'README.md:161: e.g. Qwen3-8B-4bit labels scorer 84.6% on the 45 cases (agreement over '
                            'all labelled fields, with order rotations)'},
        'notes': notes}


# ---------------------------------------------------------------- 쓰기·검사
BUILDERS = {
    'jevbench-agnews100': lambda: build_jevbench('agnews'),
    'jevbench-emotion100': lambda: build_jevbench('emotiondair'),
    'jevbench-banking77-100': lambda: build_jevbench('banking77'),
    'laya-agnews400': lambda: build_laya('ag_news'),
    'laya-emotion400': lambda: build_laya('emotion'),
    'laya-banking77-400': lambda: build_laya('banking77'),
    'jevmlx-typesafe45': build_typesafe,
}


def option_stats(items):
    counts = [len(x['options']) for x in items]
    long_opts = [(x['id'], i + 1, option_tokens(o)) for x in items for i, o in enumerate(x['options'])]
    long_opts = [t for t in long_opts if t[2] > OPTION_TOKEN_LIMIT]
    return {'min': min(counts), 'max': max(counts), 'histogram': {str(k): v for k, v in sorted(Counter(counts).items())},
            'items_over_20': sum(c > 20 for c in counts),
            f'items_over_{RUNNER_MAX_OPTIONS}_runner_limit': sum(c > RUNNER_MAX_OPTIONS for c in counts),
            f'options_over_{OPTION_TOKEN_LIMIT}_tokens': len(long_opts),
            'items_with_option_over_48_tokens': len({t[0] for t in long_opts}),
            'longest_option_tokens': max(option_tokens(o) for x in items for o in x['options']),
            'token_counter': f'tokenizers {TOKENIZER.name} from SupersonicLabs/Julia-1 snapshot (mmBERT), '
                             f'sha256 {TOKENIZER_SHA256}, " " + option, no special tokens. Nothing truncated.'}


def write_set(name):
    set_name, items, gold, meta = BUILDERS[name]()
    assert set_name == name
    out = SETS_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    (out / 'items.jsonl').write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in items))
    (out / 'gold.json').write_text(json.dumps(gold, ensure_ascii=False, indent=1) + '\n')
    manifest = {'set': name, 'count': len(items),
                'stages': dict(sorted(Counter(x['stage'] for x in items).items())),
                'options': option_stats(items),
                'sha256': {n: sha256_file(out / n) for n in ('items.jsonl', 'gold.json')},
                'builder': 'claims/build_ext.py ' + name, **meta}
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n')
    return manifest


def check_set(name):
    out = SETS_DIR / name
    items = [json.loads(l) for l in (out / 'items.jsonl').read_text().splitlines() if l.strip()]
    gold = json.loads((out / 'gold.json').read_text())
    manifest = json.loads((out / 'manifest.json').read_text())
    errors = []
    ids = [x['id'] for x in items]
    if len(ids) != len(set(ids)):
        errors.append('duplicate ids')
    if set(ids) != set(gold):
        errors.append('items and gold ids differ')
    for x in items:
        if tuple(x) != ITEM_KEYS:
            errors.append(f"{x['id']}: keys {list(x)}")
        if x['game'] != name or not x['id'].startswith(name + ':'):
            errors.append(f"{x['id']}: game/id prefix")
        if not isinstance(x['state'], (str, dict)) or not isinstance(x['question'], str) or not x['question']:
            errors.append(f"{x['id']}: state/question type")
        if not all(isinstance(o, str) and o for o in x['options']) or len(x['options']) < 2:
            errors.append(f"{x['id']}: options")
        g = gold.get(x['id'], {})
        if g.get('n') != len(x['options']) or not 1 <= g.get('answer', 0) <= len(x['options']):
            errors.append(f"{x['id']}: gold out of range {g}")
            continue
        truth = x['options'][g['answer'] - 1]
        # 정답 누출: 정답 필드가 없고, id·stage가 정답 텍스트를 담지 않는다 (bool 옵션 "true"/"false"는 필드명에 흔해 제외)
        blob = json.dumps(x, ensure_ascii=False)
        if any(f'"{k}"' in blob for k in ('answer', 'gold', 'target_index', 'label_text', 'consensus')):
            errors.append(f"{x['id']}: label-like key in item")
        if truth not in ('true', 'false') and (truth == x['stage'] or x['id'].endswith(':' + truth)):
            errors.append(f"{x['id']}: gold text in id/stage")
    for n in ('items.jsonl', 'gold.json'):
        if manifest['sha256'][n] != sha256_file(out / n):
            errors.append(f'manifest sha256 stale for {n}')
    if manifest['count'] != len(items):
        errors.append('manifest count')
    return items, gold, manifest, errors


def report(name):
    items, gold, manifest, errors = check_set(name)
    o = manifest['options']
    sample = dict(items[0])
    if isinstance(sample['state'], str) and len(sample['state']) > 160:
        sample['state'] = sample['state'][:160] + f'...(+{len(sample["state"]) - 160} chars)'
    print(f"== {name}: {'OK' if not errors else 'FAIL'}  count {len(items)}  stages {manifest['stages']}  "
          f"options {o['min']}-{o['max']}  >20: {o['items_over_20']}  >26: {o['items_over_26_runner_limit']}  "
          f">48tok options: {o['options_over_48_tokens']}  answer hist "
          f"{dict(sorted(Counter(g['answer'] for g in gold.values()).items()))}")
    print('   sample', json.dumps(sample, ensure_ascii=False)[:600])
    for e in errors[:10]:
        print('   ERROR', e)
    return not errors


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('what', nargs='+', choices=['all', 'check', *BUILDERS])
    a = ap.parse_args()
    names = list(BUILDERS) if 'all' in a.what else [n for n in a.what if n in BUILDERS]
    for n in names:
        write_set(n)
    targets = names or [n for n in BUILDERS if (SETS_DIR / n / 'manifest.json').exists()]
    ok = all([report(n) for n in targets])
    all_ids = [json.loads(l)['id'] for n in targets for l in (SETS_DIR / n / 'items.jsonl').read_text().splitlines()]
    if len(all_ids) != len(set(all_ids)):
        print('ERROR ids collide across sets'); ok = False
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
