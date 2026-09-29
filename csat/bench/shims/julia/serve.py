"""Julia-1 shim for the Jev-like knowledge benchmark (csat/bench/adapters contract, port 8807).

Runs in ~/dev/jev-likes/julia/.venv. Maps a request onto Julia's typed API with the model card's
recommended settings:
    load_model(REPO, device="cpu", strict_encoding=True, max_length=8192, head_length=512)
(device="mps" by default here: upstream supports cpu/cuda only, so the shim moves inputs to mps; see _pack_to_device)
    engine.predict(state=state, questions={"answer": {"type": "choice", "instructions": ..., "criteria": {A..: text}}})
No added wording. The typed path returns the raw softmax (display rounding is not applied).
With strict_encoding Julia refuses rather than truncates; the shim runs Julia's own sequence builder
first and returns 413 for those refusals, so nothing is silently cut.
"""
import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from julia import load_model
from julia.data import sequence
from julia.router.engine import FastEngine

DEVICE = os.environ.get('JULIA_DEVICE', 'mps')
_pack = FastEngine._pack


def _pack_to_device(self, encoded):
    # Upstream moves inputs only for cuda. On mps the same tensors are moved here; nothing else changes.
    # Checked 2026-09-28 on 105 gamebench v1 items: same choice on all, max probability diff 1.4e-05 vs cpu.
    batch = _pack(self, encoded)
    return {k: v.to(self.device) for k, v in batch.items()} if self.device.type == 'mps' else batch


FastEngine._pack = _pack_to_device

REPO = os.path.expanduser('~/dev/jev-likes/julia/repo')
REVISION = 'a85b127321d580d65176c89ced8273f305745d85'  # SupersonicLabs/Julia-1 on the Hub, fetched 2026-09-28
MAX_LEN = 8192
HEAD_LEN = 512
# Refusal messages of julia.data.sequence(strict=True); only these ValueErrors count as unsupported
REFUSALS = ('Option exceeds 48-token', 'Question/options exceed', 'Game state exceeds', 'Reserved model marker')

engine = load_model(REPO, device=DEVICE, strict_encoding=True, max_length=MAX_LEN, head_length=HEAD_LEN)
LOCK = threading.Lock()
POLICY = json.loads(open(os.path.join(REPO, 'inference-policy.json')).read())

HEALTH = {
    'name': 'julia',
    'returns_probabilities': True,
    'max_input_tokens': MAX_LEN,
    'detail': {
        'checkpoint': 'SupersonicLabs/Julia-1 (mmBERT-small + decision head, 144.3M)',
        'revision': REVISION,
        'weights_sha256': POLICY.get('weights_sha256'),
        'device': str(engine.device),
        'cpu_threads': int(os.environ.get('JULIA_CPU_THREADS', '4')),
        'max_length': MAX_LEN, 'head_length': HEAD_LEN, 'option_token_cap': 48, 'strict_encoding': True,
    },
}


def choose(body):
    state, criteria = body['state'], dict(body['criteria'])
    row = dict(state=state, question=body['instructions'], type='choice', options=list(criteria.values()))
    if not 2 <= len(criteria) <= 20:  # julia.data.validate_row: "options must contain 2–20" (model contract)
        return 413, {'error': 'unsupported', 'reason': f'{len(criteria)} options; Julia accepts 2-20'}
    try:
        enc = sequence(engine.tokenizer, row, MAX_LEN, HEAD_LEN, strict=True)
    except ValueError as e:
        if str(e).startswith(REFUSALS):
            return 413, {'error': 'unsupported', 'reason': str(e)}
        raise
    q = {'type': 'choice', 'instructions': body['instructions'], 'criteria': criteria}
    with LOCK:
        r = engine.predict(state=state, questions={'answer': q})
    return 200, {'probabilities': r['answers']['answer']['probabilities'], 'input_tokens': len(enc['ids'])}


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/health':
            return self._send(200, HEALTH)
        self._send(404, {'error': 'not found'})

    def do_POST(self):
        if self.path != '/choose':
            return self._send(404, {'error': 'not found'})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
            code, obj = choose(body)
        except Exception as e:  # surfaced as 500 so the runner records an error, never a fake answer
            code, obj = 500, {'error': type(e).__name__, 'message': str(e)[:500]}
        self._send(code, obj)

    def log_message(self, fmt, *args):
        pass


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8807)
    a = ap.parse_args()
    print('julia shim ready', json.dumps(HEALTH, ensure_ascii=False), flush=True)
    ThreadingHTTPServer(('127.0.0.1', a.port), H).serve_forever()
