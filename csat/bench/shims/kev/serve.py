"""Kev shim for the Jev-like benchmark (adapters/__init__.py contract, PROTOCOL.md 1절).

Kev's own server (`python -m kev.serve`) already speaks TypeSafe System One. This shim only
  1. turns our request into one System One Choice question, exactly the shape the Jev adapter sends:
       {"state": <our state object>, "model": "kev-latest",
        "questions": {"answer": {"type": "choice", "instructions": <instructions>, "criteria": {"A": <option text>, ...}}}}
     and forwards it unchanged to kev.serve;
  2. refuses (413) any input Kev would silently truncate. kev.serve encodes with strict=False, which cuts the state at
     SERVE_MAX_STATE tokens without telling the caller. The shim runs Kev's own to_record + encode(strict=True) with the
     same tokenizer and limits first, so a 413 fires exactly when Kev would have truncated (or rejected a question row).

No prompt wording, few-shot, temperature or option changes are added. Run with Kev's venv:
  ~/dev/jev-likes/kev/src/.venv/bin/python serve.py --upstream http://127.0.0.1:18804 --run jaredpalmer/kev-9b@<sha>
"""
import argparse
import json
import subprocess
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from kev.api import SystemOneRequest, to_record
from kev.checkpoint import Checkpoint
from kev.model import SERVE_MAX_BRANCH, SERVE_MAX_STATE, ContextOverflow, encode, load_tokenizer

KEV_SRC = Path.home() / 'dev' / 'jev-likes' / 'kev' / 'src'
QID = 'answer'


def kev_request(body):
    return {'state': body['state'], 'model': 'kev-latest',
            'questions': {QID: {'type': 'choice', 'instructions': body['instructions'], 'criteria': body['criteria']}}}


class Shim:
    def __init__(self, upstream, run):
        self.upstream = upstream.rstrip('/')
        ck = Checkpoint(run)
        meta = ck.meta
        self.tok = load_tokenizer(meta.base, revision=meta.base_revision)   # the tokenizer Checkpoint.load gives kev.serve
        commit = subprocess.run(['git', '-C', str(KEV_SRC), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
        with urllib.request.urlopen(self.upstream + '/v1/models', timeout=30) as r:
            card = json.loads(r.read())['models'][0]
        if card['run'] != run:
            raise SystemExit(f'kev.serve serves {card["run"]!r}, shim was started for {run!r}')
        self.health = {'name': 'kev', 'returns_probabilities': True, 'max_input_tokens': SERVE_MAX_STATE,
                       'detail': {'commit': commit, 'model': f'{run} on {meta.base}@{meta.base_revision}',
                                  'quant': f'none ({card["dtype"]} as stored, LoRA merged, backend {card["backend"]})',
                                  'temperature': card['temperature'], 'device': card['device'],
                                  'limits': {'state_tokens': SERVE_MAX_STATE, 'state_plus_question_row_tokens': SERVE_MAX_BRANCH},
                                  'upstream': self.upstream}}

    def precheck(self, req):
        """-> (ok, input_tokens, reason). Kev's own encoder in strict mode: raises where kev.serve would truncate."""
        rec, _ = to_record(SystemOneRequest(**req))
        try:
            enc = encode(self.tok, rec, max_state=SERVE_MAX_STATE, max_branch=SERVE_MAX_BRANCH, strict=True)
        except ContextOverflow as e:
            n = len(encode(self.tok, rec, max_state=10 ** 9, max_branch=10 ** 9)['ids'])
            return False, n, str(e)
        return True, len(enc['ids']), None

    def choose(self, body):
        if set(body) - {'state', 'instructions', 'criteria'} or not isinstance(body.get('criteria'), dict):
            return 400, {'error': 'bad request'}
        req = kev_request(body)
        ok, n, reason = self.precheck(req)
        if not ok:
            return 413, {'error': 'unsupported', 'reason': reason, 'input_tokens': n}
        data = json.dumps(req, ensure_ascii=False).encode()
        r = urllib.request.Request(self.upstream + '/v1/systemone', data, {'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(r, timeout=900) as resp:
                out = json.loads(resp.read())
        except urllib.error.HTTPError as e:   # after the strict pre-check a 422 is a real error, not "unsupported"
            return 502, {'error': f'kev.serve {e.code}', 'detail': e.read().decode()[:500]}
        probs = out['answers'][QID]['probabilities']
        if out['usage']['input_tokens'] != n:
            return 502, {'error': f'token count mismatch: shim {n}, kev.serve {out["usage"]["input_tokens"]}'}
        return 200, {'probabilities': probs, 'input_tokens': n, 'kev_latency_ms': out['latency_ms']}


def handler(shim):
    class H(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            b = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

        def do_GET(self):
            if self.path == '/health':
                return self._send(200, shim.health)
            self._send(404, {'error': 'not found'})

        def do_POST(self):
            if self.path != '/choose':
                return self._send(404, {'error': 'not found'})
            try:
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self._send(*shim.choose(body))
            except Exception as e:
                self._send(500, {'error': type(e).__name__, 'message': str(e)[:500]})

        def log_message(self, fmt, *args):
            pass
    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8804)
    ap.add_argument('--upstream', default='http://127.0.0.1:18804')
    ap.add_argument('--run', required=True, help='the exact --run kev.serve was started with')
    a = ap.parse_args()
    shim = Shim(a.upstream, a.run)
    print('kev shim', json.dumps(shim.health, ensure_ascii=False), flush=True)
    ThreadingHTTPServer(('127.0.0.1', a.port), handler(shim)).serve_forever()


if __name__ == '__main__':
    main()
