"""Laya shim for the Jev-like knowledge benchmark (csat/bench/adapters contract, port 8805).

Runs in ~/dev/jev-likes/laya/.venv. Maps a request onto Laya's native System One path:
    Router.predict(state, {"answer": {"type": "choice", "instructions": ..., "criteria": {A..E: text}}},
                   model="multilingual", max_len=MAX_LEN, head_max_len=HEAD_MAX_LEN)
No added wording. Laya's own sequence builder silently truncates three things (option text at 48
tokens, instructions to the option budget, state to max_len); this shim rebuilds the untruncated
length and returns 413 whenever Laya's sequence is shorter than it, so nothing is silently cut.
"""
import argparse
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from laya import Router
from laya.common import build_sequence, encode_text, render_options, serialize_state

MODEL = 'multilingual'          # Router name -> convaiinnovations/laya, subfolder "multilingual" (mmBERT-base)
MAX_LEN = 8192                  # README: laya-multilingual reads up to 8,192 tokens with max_len=8192 (native cfg 1024)
HEAD_MAX_LEN = 512              # documented per-call override (native cfg 256) so the fixed instructions are never cut
OPTION_CAP = 48                 # hard-coded in laya.common.build_sequence: truncation=True, max_length=48 per option
REPO = os.path.expanduser('~/dev/jev-likes/laya/repo')

router = Router(device=os.environ.get('LAYA_DEVICE', 'mps'))
agent = router.load(MODEL)
tok = agent.tok
LOCK = threading.Lock()


def _commit():
    try:
        return subprocess.check_output(['git', '-C', REPO, 'rev-parse', 'HEAD'], text=True).strip()
    except Exception:
        return None


HEALTH = {
    'name': 'laya',
    'returns_probabilities': True,
    'max_input_tokens': MAX_LEN,
    'detail': {
        'commit': _commit(),
        'checkpoint': 'convaiinnovations/laya subfolder=multilingual (laya-multilingual, mmBERT-base)',
        'checkpoint_revision': getattr(agent, 'revision', None),
        'device': str(agent.device),
        'max_len': MAX_LEN, 'head_max_len': HEAD_MAX_LEN, 'option_token_cap': OPTION_CAP,
        'native_cfg': {'max_len': agent.cfg.get('max_len'), 'head_max_len': agent.cfg.get('head_max_len')},
    },
}


def enc(text):
    # No truncation kwarg: a fast tokenizer only truncates when asked (checked with >8192 tokens in README).
    return encode_text(tok, text, add_special_tokens=False)['input_ids']


def check_fits(state, qdef):
    """Return (untruncated_tokens, reason_or_None) using Laya's own rendering and sequence builder."""
    q = agent._to_internal(qdef)
    m = tok.mask_token
    head = enc('%s question: %s' % (q['t'], str(q['ins']).replace(m, ' ')))
    opts = [enc(' ' + o.replace(m, ' ')) for o in render_options(q)]
    st = enc(serialize_state(state).replace(m, ' '))
    full = 1 + len(head) + 1 + sum(1 + len(o) for o in opts) + 1 + len(st) + 1
    seq, markers = build_sequence(tok, state, q, MAX_LEN, HEAD_MAX_LEN, state_ids=st)
    if len(seq) == full and len(markers) == len(opts):
        return full, None
    parts = []
    long_opts = [k for k, o in zip(q['crit'], opts) if len(o) > OPTION_CAP]
    if long_opts:
        parts.append('option text over %d tokens (%s: %s)' % (OPTION_CAP, ','.join(map(str, long_opts)),
                                                           [len(o) for o in opts]))
    if full > MAX_LEN:
        parts.append('input over max_len=%d' % MAX_LEN)
    if not parts:
        parts.append('head (instructions+options) over head_max_len=%d' % HEAD_MAX_LEN)
    return full, '; '.join(parts) + ' -> Laya would truncate (%d of %d tokens kept)' % (len(seq), full)


def choose(body):
    state, criteria = body['state'], dict(body['criteria'])
    qdef = {'type': 'choice', 'instructions': body['instructions'], 'criteria': criteria}
    full, reason = check_fits(state, qdef)
    if reason:
        return 413, {'error': 'unsupported', 'reason': reason, 'input_tokens': full}
    with LOCK:
        r = router.predict(state, {'answer': qdef}, model=MODEL, max_len=MAX_LEN, head_max_len=HEAD_MAX_LEN)
    ans = r['answers']['answer']
    return 200, {'probabilities': ans['probabilities'], 'input_tokens': full,
                 'usage': r.get('usage'), 'model': r.get('routing', {}).get('model')}


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
    ap.add_argument('--port', type=int, default=8805)
    a = ap.parse_args()
    print('laya shim ready', json.dumps(HEALTH, ensure_ascii=False), flush=True)
    ThreadingHTTPServer(('127.0.0.1', a.port), H).serve_forever()
