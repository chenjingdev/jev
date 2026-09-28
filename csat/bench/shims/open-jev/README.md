# open-jev shim (port 8801)

Upstream: https://github.com/daseinlabs/open-jev @ `6cb37c3cee9d8477d49d8ac0c99056e48ccc292c`, cloned to `~/dev/jev-likes/open-jev`, venv from `uv sync` (Python 3.14, mlx 0.32.2, mlx-lm 0.31.3, transformers 5.17.0; the optional `torch` extra is not installed because serving does not use it).

Model: `google/gemma-3-4b-it` (gated), downloaded to `~/dev/jev-likes/open-jev/models/gemma-3-4b-it` as upstream's `make model` does. Revision: `093f9f388b31de276ce2de164bdc2081324b9767` (also in `/health` `detail.model_revision`). Quantization: none, the bf16 weights as published, loaded by `mlx_lm.load` on the MLX backend (upstream default on Apple silicon).

## Start

```sh
# one-time, after accepting the license at https://huggingface.co/google/gemma-3-4b-it
cd ~/dev/jev-likes/open-jev
HF_TOKEN=... .venv/bin/hf download google/gemma-3-4b-it --local-dir models/gemma-3-4b-it

# server
cd ~/dev/jev-likes/open-jev && .venv/bin/python /Users/chenjing/dev/jev/csat/bench/shims/open-jev/serve.py   # 127.0.0.1:8801
```

## What it calls

`POST /choose` builds a native `SystemOneRequest` with one `choice` question (`instructions`, `criteria` = `{A..E: option text}`, `state` = our dict unchanged) and calls `openjev.systemone.system_one`, the same function behind upstream's `POST /v1/systemone`, with its defaults (`norm="sum"`, no chat template, batch size 8). Open-jev renders the prompt itself:

```
State:
<json.dumps(state, indent=2, ensure_ascii=False)>

Question:
<instructions>

Choose exactly one option.
Options:
- A: <option text>
...

Answer:
```

and scores the keys `A`..`E` as continuations. The returned probabilities are the native `probabilities` field, unchanged.

## Context limit

Open-jev itself enforces no length limit. The shim renders the exact native prompt, counts tokens with the scorer's own tokenizer path (`context_ids`), and returns 413 when prompt tokens plus the longest label exceed the model's `max_position_embeddings` (131072 = the model card's 128K input context; google's `config.json` omits the field, so the shim resolves the `Gemma3TextConfig` default via `transformers.AutoConfig`). It never truncates. `/health` reports this number as `max_input_tokens`.

## Checked (2026-09-27)

- Option-swap probe (hand-written questions, not from the dataset): with the correct text moved through positions A..E, the argmax followed the text for "대한민국의 수도는?" and "Which animal is a mammal?" (p≈0.999 at each position). For "2 + 3 = ?" it stayed on A (0.91–0.999) wherever "5" was: the native letter-label scoring has a strong A bias on numeric options.
- Smoke (6 questions × 5 rotations): 30/30 complete, median latency 3.8 s (0.9–21.4 s), physical footprint about 14 GB after the run.
