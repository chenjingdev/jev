"""Run the frozen CSAT inputs on Luna, Terra and Sol, all at low effort.

Uses the existing loopback Codex API proxy. Each question is a fresh, tool-free
request. The answer key is opened only after all responses have been collected.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time

import requests

from run_exam import HERE, INSTRUCTIONS, grade, make_job, save

MODELS = ['gpt-5.6-luna', 'gpt-5.6-terra', 'gpt-5.6-sol']
ENDPOINT = 'http://127.0.0.1:11435/v1/chat/completions'
SCHEMA = {'type': 'object', 'properties': {'choice': {'type': 'string', 'enum': list('ABCDE')}},
          'required': ['choice'], 'additionalProperties': False}


def chat_job(question, rotation, model):
    job = make_job(question, rotation)
    choice = job['request']['questions']['answer']
    job['request'] = {
        'model': model, 'reasoning_effort': 'low', 'stream': False,
        'tools': [], 'tool_choice': 'none',
        'messages': [
            {'role': 'system', 'content': INSTRUCTIONS},
            {'role': 'user', 'content': json.dumps({'state': question['state'], 'options': choice['criteria']},
                                                 ensure_ascii=False)},
        ],
        'response_format': {'type': 'json_schema', 'json_schema': {'name': 'exam_answer', 'strict': True, 'schema': SCHEMA}},
    }
    return job


def parse_choice(content):
    content = content.strip()
    if content.startswith('```'):
        match = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', content, re.S)
        if not match:
            raise ValueError('Invalid fenced JSON')
        content = match.group(1)
    value = json.loads(content)
    if not isinstance(value, dict) or set(value) != {'choice'} or value['choice'] not in 'ABCDE' or len(value['choice']) != 1:
        raise ValueError('Expected one A-E choice')
    return value['choice']


def ask(job):
    start = time.perf_counter()
    response = requests.post(ENDPOINT, json=job['request'], timeout=(10, 150))
    elapsed = round((time.perf_counter() - start) * 1000, 2)
    raw = response.json()
    result = {'http_status': response.status_code, 'raw_response': raw, 'elapsed_ms': elapsed}
    if response.status_code != 200:
        result['error_type'] = 'http_error'
        return result
    try:
        completion = raw['choices'][0]
        if completion.get('finish_reason') != 'stop' or completion['message'].get('tool_calls'):
            raise ValueError('Not a complete tool-free answer')
        choice = parse_choice(completion['message']['content'])
    except (KeyError, ValueError, TypeError, IndexError):
        result['error_type'] = 'invalid_answer'
        return result
    usage = raw.get('usage', {})
    result['response'] = {
        'model': raw.get('model'), 'choice': choice, 'original_option': job['choice_to_original'][choice],
        'confidence': None, 'latency_ms': elapsed,
        'usage': {'input_tokens': usage.get('prompt_tokens', 0), 'output_tokens': usage.get('completion_tokens', 0)},
        'provider_usage': usage,
    }
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output-dir', type=Path, required=True)
    ap.add_argument('--control-workers', type=int, default=6)
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    source_path = HERE / 'data/2026-english-reading.json'
    raw = source_path.read_bytes()
    dataset = json.loads(raw)
    paths, payloads = {}, {}
    for model in MODELS:
        payload = {
            'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'running', 'model': model,
            'reasoning_effort': 'low', 'exam': dataset['exam'], 'endpoint': ENDPOINT,
            'dataset_sha256': hashlib.sha256(raw).hexdigest(),
            'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'protocol': 'Same question state, options, common instruction and five cyclic relabelled orders as Jev. Fresh message history per question. No tools. Primary questions sequential per model; three models in parallel. No answer-key-driven retries.',
            'proxy_format_note': 'Local proxy turns response_format into an output-schema instruction, rather than upstream constrained decoding. Parsed schema violations count as failures.',
            'usage_note': 'Proxy prompt_tokens may exclude cached input; preserve raw provider counters and do not treat them as billing totals.',
            'jobs': [chat_job(q, r, model) for r in range(5) for q in dataset['questions']],
        }
        payloads[model] = payload
        paths[model] = args.output_dir / f'{model}-low.json'
        save(paths[model], payload)

    def primary(model):
        payload = payloads[model]
        start = time.perf_counter()
        for i, job in enumerate([j for j in payload['jobs'] if j['rotation'] == 0], 1):
            try:
                job.update(ask(job))
            except requests.RequestException as exc:
                job['error_type'] = type(exc).__name__
            save(paths[model], payload)
            if i % 7 == 0:
                print(f'{model} low: primary {i}/28 answered', flush=True)
        payload['primary_wall_seconds'] = round(time.perf_counter() - start, 3)
        save(paths[model], payload)
        return model

    start = time.perf_counter()
    with ThreadPoolExecutor(3) as pool:
        list(pool.map(primary, MODELS))
    print('All primary answers collected; starting order controls.', flush=True)
    pending_jobs = [(model, j) for model in MODELS for j in payloads[model]['jobs'] if j['rotation'] != 0]
    # Interleave models in the control queue rather than finishing one model first.
    pending_jobs.sort(key=lambda item: (item[1]['rotation'], item[1]['number'], MODELS.index(item[0])))
    with ThreadPoolExecutor(args.control_workers) as pool:
        futures = {pool.submit(ask, j): (model, j) for model, j in pending_jobs}
        for i, future in enumerate(as_completed(futures), 1):
            model, job = futures[future]
            try:
                job.update(future.result())
            except requests.RequestException as exc:
                job['error_type'] = type(exc).__name__
            if i % 21 == 0 or i == len(futures):
                for name in MODELS:
                    save(paths[name], payloads[name])
                print(f'Order controls {i}/{len(futures)} finished', flush=True)
    gold_raw = (HERE / 'data/2026-english-gold.json').read_bytes()
    gold = json.loads(gold_raw)
    for model, payload in payloads.items():
        payload['gold_sha256'] = hashlib.sha256(gold_raw).hexdigest()
        payload['summary'] = grade(payload['jobs'], gold)
        payload['error_count'] = sum('response' not in j for j in payload['jobs'])
        payload['status'] = 'complete' if payload['error_count'] == 0 else 'partial'
        payload['comparison_wall_seconds'] = round(time.perf_counter() - start, 3)
        save(paths[model], payload)
        print(json.dumps({'model': model, **{k: v for k, v in payload['summary'].items() if k != 'details'}}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
