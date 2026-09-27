"""jevmlx shim for the Jev-like knowledge benchmark (PROTOCOL.md section 1).

Runs inside jevmlx's own venv (~/dev/jev-likes/jevmlx/repo/.venv), NOT the repo venv.

Mapping onto jevmlx's native Python API (`jevmlx.choose(context, {name: description}, instructions)`):
  - criteria {"A": option text, ...}  -> options dict name -> description (names "A".."E", option
    text as the description, which the labels renderer prints as `"A" — "<option text>"`).
  - instructions                      -> choose()'s `instructions` parameter (the field description).
  - state (object)                    -> context = json.dumps(state, indent=2, ensure_ascii=False)
    (jevmlx serve's own state->context convention is json.dumps(state, indent=2); ensure_ascii=False
    is the only change, so Korean text reaches the model as text rather than \\uXXXX escapes).

choose() returns a FieldResult whose `alternatives` holds only the top 3. To report the full
distribution over all 5 keys, this shim runs the exact body of choose()/_one_field_decision
(same schema dict, same StructuredSchema, same run_parallel_generation call with choose()'s
defaults: temperature=1.0, scoring=DEFAULT_SCORING="labels", no calibration, no prior correction,
no constraints) and reads field_telemetry["choice"]["top_choices"], the same list FieldResult's
alternatives and probability_margin come from.

Admission: same limit as `jevmlx serve` (--max-prompt-tokens default 8192, counted over the
context with engine.tokenizer.encode(context, add_special_tokens=False)). Over the limit -> 413.
Nothing is truncated.

Start:
  HF_TOKEN=$(cat ~/.cache/huggingface/token) \
  ~/dev/jev-likes/jevmlx/repo/.venv/bin/python csat/bench/shims/jevmlx/serve.py --port 8802
"""
import argparse
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import jevmlx
from jevmlx.api import _normalize_options
from jevmlx.engine import load_engine, run_parallel_generation
from jevmlx.models import DEFAULT_MODEL, DEFAULT_SCORING, resolve_model
from jevmlx.schema import StructuredSchema
from jevmlx.trie import softmax

REPO = Path(jevmlx.__file__).resolve().parent.parent
MAX_PROMPT_TOKENS = 8192  # jevmlx serve DEFAULT_MAX_PROMPT_TOKENS
FIELD = 'choice'  # the field name choose() uses


def repo_commit():
    try:
        return subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    except Exception:
        return None


class JevmlxChooser:
    def __init__(self, model_alias):
        self.alias = model_alias
        self.model_id = resolve_model(model_alias)
        self.engine = load_engine(model_alias)
        self.lock = threading.Lock()  # one Metal GPU, serial like jevmlx serve's single worker

    def context_of(self, state):
        if isinstance(state, str):
            return state
        return json.dumps(state, indent=2, ensure_ascii=False)

    def count_tokens(self, context):
        return len(self.engine.tokenizer.encode(context, add_special_tokens=False))

    def choose(self, context, instructions, criteria):
        # Body of jevmlx.api.choose + _one_field_decision with choose()'s defaults.
        names, descriptions = _normalize_options(dict(criteria), min_count=2, what='options')
        schema_dict = {
            'type': 'enum',
            'description': instructions.strip() or 'Choose the best option.',
            'choices': names,
            'choice_descriptions': descriptions,
        }
        schema = StructuredSchema({FIELD: schema_dict})
        with self.lock:
            result = run_parallel_generation(self.engine, context, schema, temperature=1.0,
                                             scoring=DEFAULT_SCORING, calibration=None,
                                             prior_correction=False, constraints=None)
        tel = result['field_telemetry'][FIELD]
        # top_choices는 엔진이 상위 5개로 자른다(engine.py `top_choices[:5]`). 전체 분포는 엔진과 같은 식
        # softmax(log_scores, T=1.0)로 복원하고, 잘리지 않은 상위 항목과 일치하는지 매번 확인한다.
        scores = tel['log_scores']
        if set(scores) != set(criteria):
            raise RuntimeError(f'log_scores does not cover all options: {sorted(scores)}')
        keys = list(scores)
        probs = dict(zip(keys, softmax([scores[k] for k in keys], temperature=1.0)))
        for e in tel['top_choices']:
            if abs(probs[e['choice']] - float(e['probability'])) > 1e-6:
                raise RuntimeError(f'reconstructed probability mismatch for {e["choice"]}')
        return probs, result


def make_handler(chooser, health):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, payload):
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            pass

        def do_GET(self):
            if self.path == '/health':
                self._send(200, health)
            else:
                self._send(404, {'error': 'not found'})

        def do_POST(self):
            if self.path != '/choose':
                self._send(404, {'error': 'not found'})
                return
            try:
                req = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                state, instructions, criteria = req['state'], req['instructions'], req['criteria']
                if not isinstance(criteria, dict) or not all(isinstance(v, str) for v in criteria.values()):
                    raise ValueError('criteria must be an object of strings')
            except Exception as exc:
                self._send(400, {'error': f'bad request: {exc}'})
                return
            context = chooser.context_of(state)
            n = chooser.count_tokens(context)
            if n > MAX_PROMPT_TOKENS:
                self._send(413, {'error': 'unsupported',
                                 'reason': f'prompt too long: {n} tokens > limit {MAX_PROMPT_TOKENS}',
                                 'input_tokens': n})
                return
            try:
                probs, result = chooser.choose(context, instructions, criteria)
            except Exception as exc:
                self._send(500, {'error': f'{type(exc).__name__}: {exc}'})
                return
            self._send(200, {'probabilities': probs, 'input_tokens': n,
                             'prompt_sha256': result.get('prompt_sha256')})

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8802)
    ap.add_argument('--model', default=DEFAULT_MODEL, help='jevmlx alias or HF id (default: quality)')
    a = ap.parse_args()
    chooser = JevmlxChooser(a.model)
    health = {
        'name': 'jevmlx',
        'returns_probabilities': True,
        'max_input_tokens': MAX_PROMPT_TOKENS,
        'detail': {
            'repo': 'https://github.com/bnsd55/jevmlx',
            'repo_commit': repo_commit(),
            'model_alias': a.model,
            'model_id': chooser.model_id,
            'model_revision': chooser.engine.revision,
            'quant': '4bit (MLX, mlx-community)',
            'scoring': DEFAULT_SCORING,
            'temperature': 1.0,
            'api': 'jevmlx.choose() body (run_parallel_generation, one enum field "choice")',
            'instructions': "passed as choose()'s native `instructions` param (enum field description)",
            'criteria': 'options dict {A..E: option text}; labels renderer shows `"A" — "<text>"`, scorer scores "A".."E"',
            'state': 'json.dumps(state, indent=2, ensure_ascii=False) as context (serve uses indent=2, ASCII-escaped)',
            'max_input_tokens_counts': 'context tokens only (same as jevmlx serve admission)',
        },
    }
    server = ThreadingHTTPServer(('127.0.0.1', a.port), make_handler(chooser, health))
    print(json.dumps(health, ensure_ascii=False), flush=True)
    print(f'jevmlx shim on http://127.0.0.1:{a.port}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
