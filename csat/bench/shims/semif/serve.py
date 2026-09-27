"""SemIf (MLX, Qwen3.5-4B) shim for the knowledge benchmark. Contract: adapters/__init__.py.

Run with SemIf's own venv (~/dev/jev-likes/semif/.venv). The model is loaded once and every
/choose request goes through SemIf's direct scorer (`semif_phase1.mlx_backend.score`), the same
function `semif-score --backend mlx --mode direct` calls per JSONL row. The request is mapped
onto SemIf's native row format without adding any wording:

  row = {"id": ..., "state": <state object as-is>, "question": <instructions>,
         "options": [{"id": "A", "description": <criteria["A"]>}, ...]}   # sorted A..E

SemIf assigns answer letters by option position, so sorted keys make the letter the model
reads equal to our key. Prompts longer than --max-tokens (whole rendered prompt) get 413;
nothing is truncated.
"""
import argparse
import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from semif_phase1 import mlx_backend
from semif_phase1.direct import encode_prompt

MODEL = 'Qwen/Qwen3.5-4B'
REVISION = '851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a'
SRC = Path.home() / 'dev/jev-likes/semif/src'


def to_row(req):
    state, instructions, criteria = req['state'], req['instructions'], req['criteria']
    if not isinstance(criteria, dict) or not criteria:
        raise ValueError('criteria must be a nonempty object')
    return {'id': 'bench', 'state': state, 'question': instructions,
            'options': [{'id': k, 'description': criteria[k]} for k in sorted(criteria)]}


class Server:
    def __init__(self, args):
        self.max_tokens, self.bits = args.max_tokens, args.mlx_bits
        self.lock = threading.Lock()
        commit = subprocess.run(['git', '-C', str(SRC), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
        t = time.perf_counter()
        self.model, self.tokenizer, self.metadata = mlx_backend.load_model(MODEL, REVISION, args.mlx_bits)
        print(f'loaded in {time.perf_counter() - t:.1f}s', flush=True)
        self.health = {'name': 'semif', 'returns_probabilities': True, 'max_input_tokens': self.max_tokens,
                       'detail': {'commit': commit, 'model': MODEL, 'revision': REVISION, 'bits': args.mlx_bits,
                                  'dtype': self.metadata['dtype'], 'mode': 'direct',
                                  'max_tokens_counts': 'whole rendered chat prompt (system+state JSON+question+options)',
                                  'mlx_version': self.metadata['mlx_version'],
                                  'mlx_lm_source': self.metadata['mlx_lm_source']}}

    def choose(self, req):
        row = to_row(req)
        with self.lock:
            # Count tokens exactly as the scorer does, without its limit, so only the length case becomes 413.
            n = len(encode_prompt(self.tokenizer, row, sys.maxsize)[0])
            if n > self.max_tokens:
                return 413, {'error': 'unsupported', 'input_tokens': n,
                             'reason': f'{n} input tokens exceed SemIf max_tokens {self.max_tokens}; no truncation'}
            r = mlx_backend.score(self.model, self.tokenizer, row, self.metadata, self.max_tokens)
        return 200, {'probabilities': dict(zip(r['option_ids'], r['probabilities'])),
                     'input_tokens': r['input_tokens'], 'prompt_sha256': r['prompt_sha256'],
                     'option_logits': dict(zip(r['option_ids'], r['option_logits']))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8803)
    ap.add_argument('--max-tokens', type=int, default=4096, help='SemIf CLI default')
    ap.add_argument('--mlx-bits', type=int, choices=(4, 8), help='default: source precision (BF16)')
    args = ap.parse_args()
    srv, port = Server(args), args.port

    class H(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            body = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            self._send(200, srv.health) if self.path == '/health' else self._send(404, {'error': 'not found'})

        def do_POST(self):
            if self.path != '/choose':
                return self._send(404, {'error': 'not found'})
            try:
                req = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
                self._send(*srv.choose(req))
            except Exception as e:  # noqa: BLE001 - surfaced to the runner as 500
                self._send(500, {'error': type(e).__name__, 'message': str(e)[:500]})

    print(f'serving semif on 127.0.0.1:{port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()


if __name__ == '__main__':
    main()
