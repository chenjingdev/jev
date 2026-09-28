# jevmlx shim (port 8802)

- Upstream: https://github.com/bnsd55/jevmlx @ `7e0d746081b88412ccd7d84a5ffdcf9d61b36904`
- Install: `~/dev/jev-likes/jevmlx/repo` (clone), `./setup.sh` → its own `.venv` (Python 3.12, mlx-lm, editable jevmlx)
- Model: alias `quality` (the jevmlx default, "best accuracy") = `mlx-community/Qwen2.5-7B-Instruct-4bit`,
  HF revision `c26a38f6a37d0a51b4e9a1eb3026530fa35d9fed`, MLX 4bit, about 4 GB
- Scoring: `labels` (default), temperature 1.0, no calibration, no prior correction
- Context limit: 8192 tokens, the same as `jevmlx serve --max-prompt-tokens`. Counted over the context
  with the model tokenizer (`add_special_tokens=False`), as serve does. Over the limit → 413 `unsupported`, never truncated.

## Start / stop

```bash
cd ~/dev/jev
HF_TOKEN=$(cat ~/.cache/huggingface/token) \
  ~/dev/jev-likes/jevmlx/repo/.venv/bin/python csat/bench/shims/jevmlx/serve.py --port 8802
curl -s localhost:8802/health
pkill -f shims/jevmlx/serve.py
```

## Mapping (native Python API `jevmlx.choose(context, {name: description}, instructions)`)

- `criteria` {A..E: option text} → the options dict. The labels renderer prints `"A" — "<option text>"`, and the scorer scores `"A"`..`"E"`.
- `instructions` → choose()'s native `instructions` parameter (the enum field description, rendered as `// "..."`).
- `state` → context = `json.dumps(state, indent=2, ensure_ascii=False)`. jevmlx serve uses `json.dumps(state, indent=2)`. The only difference is ensure_ascii=False, so Korean is not sent as `\uXXXX` escapes.
- The shim runs the body of `choose()` (`run_parallel_generation` with the same one-field schema and defaults) and reads
  `field_telemetry["choice"]["top_choices"]`, which gives the probabilities for all 5 keys. `choose()` itself returns only the top 3 (`alternatives`).
- Not used: HTTP `/v1/systemone`. It passes only the criteria keys to the model and drops the option text (`_systemone_to_schema`).
