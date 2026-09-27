# kev shim (port 8804)

Kev (https://github.com/jaredpalmer/kev) behind the benchmark shim contract (`adapters/__init__.py`).

## What runs

| | |
|---|---|
| Kev code | `~/dev/jev-likes/kev/src`, commit `5920c5fe4ca8e0970ed4209ac2c9b8e18bea5109`, venv `src/.venv` (`uv sync --extra serve`, Python 3.13) |
| Model | `jaredpalmer/kev-9b@2629c06a5aeb0feb3b9783bafed17ed8f39ecf5c` (LoRA r16 + pointer head) |
| Base | `Qwen/Qwen3.5-9B-Base@68c46c4b3498877f3ef123c856ecfde50c39f404` (18 GB on disk) |
| Quant | none. Kev's MLX path runs the base as stored (bf16) with the LoRA merged; the project ships no quantized variant |
| Temperature | 2.297, the checkpoint's own fitted value (served default; `KEV_TEMPERATURE` unset) |
| Memory | ~19 GB phys_footprint (kev.serve process, Metal) |
| Context | state ≤ 65,536 tokens (`SERVE_MAX_STATE`), state + one question row ≤ 73,728 (`SERVE_MAX_BRANCH`) |

Why 9B: the project says to start with 4B and go to 9B on a bigger machine; both are listed for a 32 GB Mac. This is a
knowledge benchmark and the README's knowledge gap depends mostly on the base (MMLU: 9B 0.74). 27B has no Mac path.

## Start / stop

```bash
cd ~/dev/jev-likes/kev
HF_TOKEN=$(cat ~/.cache/huggingface/token) nohup src/.venv/bin/python -m kev.serve \
  --run jaredpalmer/kev-9b@2629c06a5aeb0feb3b9783bafed17ed8f39ecf5c --port 18804 > serve.log 2>&1 & echo $! > serve.pid
# wait for "Uvicorn running" in serve.log (~1-2 min: loads the base and merges the LoRA)
nohup src/.venv/bin/python ~/dev/jev/csat/bench/shims/kev/serve.py \
  --run jaredpalmer/kev-9b@2629c06a5aeb0feb3b9783bafed17ed8f39ecf5c > shim.log 2>&1 & echo $! > shim.pid

kill $(cat shim.pid) $(cat serve.pid)
```

## Mapping

Our request becomes one System One Choice question, the same shape the Jev adapter sends, forwarded unchanged:

```json
{"state": <state object>, "model": "kev-latest",
 "questions": {"answer": {"type": "choice", "instructions": <instructions>, "criteria": {"A": "<option text>", ...}}}}
```

Kev renders the state object as `key: value` lines (`kev.api.render`) and each option as `A: <option text>`
(`kev.api.option_text`), then tokenizes both (`kev.model.encode`). No wording, examples or settings are added.

## Truncation

`kev.serve` encodes with `strict=False`: a state longer than 65,536 tokens is cut silently (only an internal
`state_truncated` flag records it). The shim therefore runs Kev's own `to_record` + `encode(strict=True)` with the same
tokenizer and limits before forwarding and answers **413** when that raises. After the pre-check, any 422 from kev.serve is
returned as 502 (a real error, not `unsupported`). The shim also checks that kev.serve's `usage.input_tokens` equals its
own count.

## Checks done (2026-09-27)

- Swap test (synthetic question, not from the dataset): with 서울 at C, p(C)=0.987; swapping the texts of A and C gave
  p(A)=0.987, same 155 input tokens. The probability follows the option text.
- 413: a ~156k-token state returned 413 `state exceeds 65536 tokens`.
- Smoke (`--tag smoke`, 6 questions × 5 rotations): 30/30 complete. Median latency 851 ms (rotations 1-4 reuse Kev's
  state-prefix cache); rotation 0 median 1,973 ms, max 6.2 s (korean-language:42, 3,134 chars).
