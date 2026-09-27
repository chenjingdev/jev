"""CLM-8B shim for the Jev-like knowledge benchmark (csat/bench/adapters contract, port 8806).

Runs on the remote AMD Windows box `amd` in C:\\Users\\chenj\\dev\\jev-likes\\clm\\.venv (torch ROCm).
The Mac reaches it through `ssh -N -L 8806:127.0.0.1:8806 amd`.

Maps a request onto CLM's native System One path, unchanged:
    clm.Engine.answer(state, {"answer": {"type": "choice", "instructions": ..., "criteria": {A..E: text}}},
                      model="clm-latest")
Heads, state rendering (clm.schema.to_text), scale*cos and softmax are CLM's own code. The only thing
replaced is the encoder transport: upstream calls a vLLM `--runner pooling` Qwen3-8B server at
/v1/embeddings; vLLM does not run on Windows, so `LocalQwen3Embedder` reproduces that server in-process
with transformers (same tokenization, bf16, last-token pooling of the final-norm hidden state, L2).

Token limit: every text that reaches the encoder (the state text = to_text(state) + "\\n\\n" +
instructions, and each option text) is counted with the Qwen3 tokenizer exactly as vLLM tokenizes it.
If any one exceeds MAX_TOKENS (8192, CLM's documented raised limit) the request gets 413; nothing is cut.
"""
import argparse
import hashlib
import json
import os
import subprocess
import threading
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault('HF_HUB_OFFLINE', '1')   # set before any HF import; encoder + head are already cached

import numpy as np
import torch
import transformers.modeling_utils
from transformers import AutoModel, AutoTokenizer

# transformers pre-allocates one ~14 GiB block before loading shards (a speed-only warm-up). On this
# unified-memory iGPU that single allocation intermittently fails with HIP OOM while 53 GiB is free, so
# skip it; weights still load shard by shard onto the GPU. No effect on the numbers.
transformers.modeling_utils.caching_allocator_warmup = lambda *a, **k: None

from clm.engine import DEFAULT_MODEL, Engine
from clm.heads import default_checkpoint
from clm.schema import build_pairs

CKPT = default_checkpoint()
if not CKPT:  # the shim runs offline; fetch the public head once with `.venv\Scripts\clm-download`
    raise SystemExit('CLM head not found in ~/.cache/clm: run .venv\\Scripts\\clm-download once first')

ENCODER = 'Qwen/Qwen3-8B'
ENCODER_REVISION = os.environ.get('CLM_ENCODER_REVISION', 'b968826d9c46dd6066d109eabc6255188de91218')
MAX_TOKENS = 8192               # README: `--max-model-len 8192` + `clm-serve --max-tokens 8192`
REPO = os.environ.get('CLM_REPO', r'C:\Users\chenj\dev\jev-likes\clm\repo')
DEVICE = os.environ.get('CLM_DEVICE', 'cuda')
ATTN = os.environ.get('CLM_ATTN', 'sdpa')


class TooLong(Exception):
    pass


class LocalQwen3Embedder:
    """Drop-in for clm.embedder.Embedder: .embed(texts) -> ([n, 4096] float32 L2-normalised, tokens).

    Reproduces `vllm serve Qwen/Qwen3-8B --runner pooling` + POST /v1/embeddings {"input": [str, ...]}:
    - tokenization: tokenizer(text) with add_special_tokens=True (vLLM's default for embeddings;
      Qwen3's tokenizer adds no BOS/EOS, checked at start-up), no chat template;
    - pooling: LAST token of the final (post-RMSNorm) hidden state, then L2 normalisation;
    - dtype: bf16 (the checkpoint's torch_dtype, vLLM's default), pooled vector cast to float32;
    - each text runs as its own unpadded sequence, like vLLM's per-request pooling.
    Upstream would truncate to max_tokens (truncate_prompt_tokens); here an over-long text raises TooLong.
    """

    def __init__(self, max_tokens=MAX_TOKENS, cache_size=4096):
        self.tok = AutoTokenizer.from_pretrained(ENCODER, revision=ENCODER_REVISION)
        self.model = AutoModel.from_pretrained(ENCODER, revision=ENCODER_REVISION, dtype=torch.bfloat16,
                                               device_map={'': 0} if DEVICE == 'cuda' else None,
                                               low_cpu_mem_usage=True, attn_implementation=ATTN).eval()
        if DEVICE != 'cuda':
            self.model.to(DEVICE)
        self.device = next(self.model.parameters()).device
        self.max_tokens = max_tokens
        self.cache = OrderedDict()
        self.cache_size = cache_size
        probe = 'probe text'
        self.special_tokens_added = (self.tok(probe)['input_ids'] != self.tok(probe, add_special_tokens=False)['input_ids'])

    def ids(self, text):
        return self.tok(text)['input_ids']          # add_special_tokens=True, as vLLM does

    @torch.inference_mode()
    def _one(self, ids):
        x = torch.tensor([ids], device=self.device)
        h = self.model(input_ids=x, attention_mask=torch.ones_like(x)).last_hidden_state[0, -1]
        v = h.float().cpu().numpy()
        return v / (np.linalg.norm(v) + 1e-12)

    def embed(self, texts):
        vecs, tokens = {}, 0
        for t in dict.fromkeys(texts):
            v = self.cache.get(t)
            if v is None:
                ids = self.ids(t)
                if len(ids) > self.max_tokens:
                    raise TooLong(f'{len(ids)} tokens > {self.max_tokens}')
                v = self._one(ids)
                tokens += len(ids)
                self.cache[t] = v
                while len(self.cache) > self.cache_size:
                    self.cache.popitem(last=False)
            else:
                self.cache.move_to_end(t)
            vecs[t] = v
        return np.stack([vecs[t] for t in texts]).astype(np.float32), tokens

    def healthy(self):
        return True


def _commit():
    try:
        return subprocess.check_output(['git', '-C', REPO, 'rev-parse', 'HEAD'], text=True).strip()
    except Exception:
        return None


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


embedder = LocalQwen3Embedder()
engine = Engine(embedder=embedder, checkpoint=CKPT, device=DEVICE)
LOCK = threading.Lock()


def health():
    free, total = torch.cuda.mem_get_info() if torch.cuda.is_available() else (None, None)
    head = engine.heads[DEFAULT_MODEL]
    return {
        'name': 'clm',
        'returns_probabilities': True,
        'max_input_tokens': MAX_TOKENS,
        'detail': {
            'commit': _commit(),
            'model': DEFAULT_MODEL,
            'checkpoint': os.path.basename(CKPT),
            'checkpoint_sha256': HEAD_SHA,
            'head_cfg': head.cfg, 'logit_scale_exp': head.scale,
            'encoder': ENCODER, 'encoder_revision': ENCODER_REVISION,
            'embedder': 'transformers AutoModel bf16, last-token pooling, L2 (vLLM pooling reproduction)',
            'attn_implementation': embedder.model.config._attn_implementation,
            'tokenizer_adds_special_tokens': embedder.special_tokens_added,
            'max_tokens_per_text': MAX_TOKENS,
            'device': str(embedder.device),
            'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            'torch': torch.__version__,
            'gpu_mem_allocated_gib': round(torch.cuda.memory_allocated() / 2**30, 2) if torch.cuda.is_available() else None,
            'gpu_mem_max_allocated_gib': round(torch.cuda.max_memory_allocated() / 2**30, 2) if torch.cuda.is_available() else None,
            'gpu_mem_free_gib': round(free / 2**30, 2) if free else None,
            'gpu_mem_total_gib': round(total / 2**30, 2) if total else None,
        },
    }


HEAD_SHA = _sha256(CKPT)


def choose(body):
    state, criteria = body['state'], dict(body['criteria'])
    qs = {'answer': {'type': 'choice', 'instructions': body['instructions'], 'criteria': criteria}}
    # Count what CLM will send to the encoder, using CLM's own pair builder.
    state_txt, _, cand_txts = build_pairs(state, qs)['answer']
    n_state = len(embedder.ids(state_txt))
    n_opts = [len(embedder.ids(t)) for t in cand_txts]
    if n_state > MAX_TOKENS or max(n_opts) > MAX_TOKENS:
        return 413, {'error': 'unsupported', 'input_tokens': n_state,
                     'reason': f'encoder text over {MAX_TOKENS} tokens (state+instructions {n_state}, '
                               f'options {n_opts}); CLM would truncate'}
    t0 = time.perf_counter()
    try:
        with LOCK:
            r = engine.answer(state, qs, model=DEFAULT_MODEL)
    except TooLong as e:  # defensive: the pre-count above should already have caught it
        return 413, {'error': 'unsupported', 'reason': str(e), 'input_tokens': n_state}
    ans = r['answers']['answer']
    return 200, {'probabilities': ans['probabilities'], 'input_tokens': n_state, 'option_tokens': n_opts,
                 'usage': r['usage'], 'model': r['model'], 'server_ms': round((time.perf_counter() - t0) * 1000, 1)}


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
            return self._send(200, health())
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
    ap.add_argument('--port', type=int, default=8806)
    a = ap.parse_args()
    print('clm shim ready', json.dumps(health(), ensure_ascii=False), flush=True)
    ThreadingHTTPServer(('127.0.0.1', a.port), H).serve_forever()
