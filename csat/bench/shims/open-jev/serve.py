"""open-jev shim for csat/bench (contract: csat/bench/adapters/__init__.py).

Runs inside open-jev's own venv (~/dev/jev-likes/open-jev/.venv) and calls open-jev's native
System One path in-process: `openjev.systemone.system_one(scorer, SystemOneRequest(...))`, the
same function `POST /v1/systemone` calls, with the same defaults (norm="sum", backend auto -> MLX,
batch_size 8, no chat template). Nothing is added to the prompt; open-jev renders it itself.

Our request -> native request:
  state        -> SystemOneRequest.state (dict as-is; open-jev renders it with json.dumps(indent=2, ensure_ascii=False))
  instructions -> questions["answer"].instructions
  criteria     -> questions["answer"].criteria  ({"A": option text, ...})
Native answer probabilities (keyed A..E) are returned unchanged.

Length: open-jev enforces no limit. Before scoring, the shim renders the exact native prompt,
tokenises it with the scorer's own context_ids(), and returns 413 if prompt + longest label
exceeds the model's max_position_embeddings. Nothing is truncated.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import threading
from typing import Union

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from openjev.systemone import ChoiceQuestion, SystemOneRequest, render_choice, system_one

REPO = Path(os.environ.get('OPENJEV_REPO', Path.home() / 'dev/jev-likes/open-jev'))
MODEL_DIR = Path(os.environ.get('OPENJEV_MODEL', REPO / 'models/gemma-3-4b-it'))
HF_REPO = 'google/gemma-3-4b-it'
NAME = 'open-jev'


class ChooseRequest(BaseModel):
    state: Union[str, dict, list]
    instructions: str
    criteria: dict[str, str]


def model_meta(model_dir: Path) -> dict:
    cfg = json.loads((model_dir / 'config.json').read_text())
    text = cfg.get('text_config', cfg)
    meta_file = model_dir / '.cache/huggingface/download/config.json.metadata'
    revision = meta_file.read_text().splitlines()[0].strip() if meta_file.exists() else None
    dtype = text.get('torch_dtype') or cfg.get('torch_dtype') or text.get('dtype') or cfg.get('dtype')
    mpe = text.get('max_position_embeddings')
    if mpe is None:  # google's config.json omits it; resolve the Gemma3TextConfig default (131072 = model card's 128K)
        from transformers import AutoConfig
        c = AutoConfig.from_pretrained(str(model_dir))
        mpe = getattr(c, 'text_config', c).max_position_embeddings
    return {'max_position_embeddings': int(mpe), 'revision': revision,
            'dtype': dtype, 'quantization': cfg.get('quantization')}


def repo_commit() -> str | None:
    try:
        return subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return None


def create_app(scorer, meta: dict) -> FastAPI:
    app = FastAPI()
    lock = threading.Lock()
    limit = meta['max_position_embeddings']
    health_info = {
        'name': NAME, 'returns_probabilities': True, 'max_input_tokens': limit,
        'detail': {'repo': 'https://github.com/daseinlabs/open-jev', 'repo_commit': repo_commit(),
                   'model_id': HF_REPO, 'model_revision': meta['revision'], 'model_dir': str(MODEL_DIR),
                   'quant': meta['quantization'] or f"none ({meta['dtype']} weights as downloaded)",
                   'backend': getattr(scorer, 'backend', None), 'native_path': 'openjev.systemone.system_one (= POST /v1/systemone)',
                   'norm': 'sum (system_one default)', 'limit_enforced_by': 'shim, prompt tokens + longest label vs max_position_embeddings'},
    }

    @app.get('/health')
    def health():
        return health_info

    @app.post('/choose')
    def choose(req: ChooseRequest):
        native = SystemOneRequest(state=req.state, model=NAME, questions={
            'answer': {'type': 'choice', 'instructions': req.instructions, 'criteria': req.criteria}})
        q = native.questions['answer']
        assert isinstance(q, ChoiceQuestion)
        prompt, labels = render_choice(native.state, q)
        with lock:
            n = len(scorer.context_ids(prompt, chat=False, sep='')) + max(len(scorer.option_ids(l)) for l in labels)
            if n > limit:
                return JSONResponse({'error': 'unsupported', 'reason': f'{n} tokens > max_position_embeddings {limit}',
                                     'input_tokens': n}, status_code=413)
            res = system_one(scorer, native, model_name=NAME)
        return {'probabilities': res.answers['answer'].probabilities, 'input_tokens': res.usage.input_tokens}

    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8801)
    a = ap.parse_args()
    from openjev import OptionScorer
    import mlx.core as mx
    import uvicorn
    # Bound MLX's buffer cache (it grows with every new input shape and pushed the Mac into memory
    # pressure on the claims run). Memory housekeeping only; scores are unchanged.
    mx.set_cache_limit(int(float(os.environ.get('MLX_CACHE_GB', '2')) * 2**30))
    scorer = OptionScorer(str(MODEL_DIR))  # native defaults: batch_size 8, backend auto (MLX here)
    scorer.score('warm up', ['a', 'b'])  # same warm-up as openjev.server
    uvicorn.run(create_app(scorer, model_meta(MODEL_DIR)), host=a.host, port=a.port, workers=1)


if __name__ == '__main__':
    main()
