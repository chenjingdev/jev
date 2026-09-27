# clm shim (port 8806, runs on `amd`)

CLM-8B (https://github.com/Contrastive-LM/CLM) behind the benchmark shim contract (`adapters/__init__.py`).
Unlike the other shims it runs on the remote AMD Windows box `amd`, not on this Mac, and is reached through an SSH tunnel.

## What runs (2026-09-27)

| | |
|---|---|
| Host | `amd`: Windows 11, AMD Radeon 8060S (Strix Halo iGPU, gfx1151), torch sees 53.9 GiB of GPU memory |
| Dir | `C:\Users\chenj\dev\jev-likes\clm\` (`repo\`, `.venv\`, `shim\serve.py`, `shim.log`) |
| CLM code | `repo\`, commit `bb42c6c5bf914fd449bed2f6ca65be80602cb1f7`, `pip install --no-deps -e repo` (no vLLM) |
| Head | `Contrastive-LM/CLM-v0.1-8B` @ `e939398d4556fcd9400c76fa8c5a513202f42b0a`, `CLM_v0.1-8B.pt` sha256 `b2b4a8c9…4eda5`, in `~\.cache\clm\` (public, fetched once with `.venv\Scripts\clm-download`, no token; the shim runs with `HF_HUB_OFFLINE=1` and exits if the head is missing). cfg width 1536, depth 3, gelu, layernorm, 512-d, exp(logit_scale)=100 |
| Encoder | `Qwen/Qwen3-8B` @ `b968826d9c46dd6066d109eabc6255188de91218` (already in the HF cache, loaded with `HF_HUB_OFFLINE=1`), bf16 |
| Env | Python 3.12 venv; torch `2.9.1+rocm7.2.1` + rocm_sdk 7.2.1 wheels from `repo.radeon.com/rocm/windows/rocm-rel-7.2.1/`, transformers 4.57.6 |
| GPU memory | 15.3 GiB after load, peak 17.5 GiB during the smoke run (`torch.cuda.max_memory_allocated`, reported in `/health`) |

## Start / stop

Copy the shim and start it detached (a plain `Start-Process` dies with the SSH session). From the Mac:

```bash
scp csat/bench/shims/clm/serve.py amd:C:/Users/chenj/dev/jev-likes/clm/shim/serve.py
# on amd (PowerShell; send with `powershell -NoProfile -EncodedCommand` so `$` is not expanded by the ssh layer):
$root='C:\Users\chenj\dev\jev-likes\clm'
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CurrentDirectory=$root; CommandLine=
  "cmd.exe /c set PYTHONIOENCODING=utf-8&& cd /d $root && .venv\Scripts\python.exe shim\serve.py --port 8806 > shim.log 2>&1"}
# ready when shim.log has "clm shim ready" (~1 min: 16 GB of shards)

ssh -f -N -o ExitOnForwardFailure=yes -L 8806:127.0.0.1:8806 amd      # tunnel on the Mac
.venv/bin/python csat/bench/run.py --system clm ...

# stop: on amd
Get-CimInstance Win32_Process | ? { $_.CommandLine -like '*shim\serve.py*' } | % { Stop-Process -Id $_.ProcessId -Force }
pkill -f 'L 8806:127.0.0.1:8806'                                      # on the Mac
```

## Mapping

One System One choice question through CLM's own in-process engine, nothing added:

```python
clm.Engine(embedder=LocalQwen3Embedder(), checkpoint=CLM_v0.1-8B.pt).answer(
    state, {"answer": {"type": "choice", "instructions": instructions, "criteria": {"A": "<option>", ...}}},
    model="clm-latest")
```

What CLM does with it (its code, not the shim's): the state object is rendered by `clm.schema.to_text` as
`key: value` blocks separated by blank lines, then `"\n\n" + instructions` is appended; this one text goes through the
state head. Each option text goes verbatim (no key prefix) through the action head. Probability =
softmax(100 · cos(state_head, action_head)), temperature 1. The response's `probabilities` is returned unchanged.

## Encoder: reproducing the vLLM pooling server

Upstream serves Qwen3-8B with `vllm serve Qwen/Qwen3-8B --runner pooling` and `clm.embedder.Embedder` posts plain strings
to `/v1/embeddings`. vLLM does not run on Windows, so `LocalQwen3Embedder` (in `serve.py`) is a drop-in for that
`Embedder` (`.embed(texts) -> (L2-normalised float32 [n, 4096], tokens)`), reproducing the server:

- Tokenization: `tokenizer(text)` with `add_special_tokens=True`, as vLLM does for embeddings. For Qwen3 this adds nothing
  (no BOS, no EOS; checked at start-up, `tokenizer_adds_special_tokens: false` in `/health`). No chat template, since the
  serving path sends raw strings (`train/embed_utils.py`'s chat-template recipe is for the DeepSWE fine-tune precompute,
  not for `clm-serve`).
- Pooling: last token of the final hidden state after the final RMSNorm (`AutoModel` = `Qwen3Model`,
  `last_hidden_state[0, -1]`), then L2 normalisation (vLLM normalises, and CLM's client normalises again).
- bf16 weights (the checkpoint's dtype, vLLM's default). The pooled vector is cast to float32.
- One unpadded sequence per text, as vLLM pools each request separately.

Deviations, none of which change the recipe: attention kernel is torch SDPA on ROCm (the math fallback, as flash and
mem-efficient attention are experimental on this GPU) instead of vLLM's CUDA kernels; no prefix caching (a speed feature);
CLM's embedder LRU is replaced by an equivalent in-shim LRU (same text → same vector); transformers' one-shot 14 GiB
`caching_allocator_warmup` is disabled because it intermittently hits HIP OOM on this unified-memory iGPU (speed-only).

## Faithfulness evidence

- Playground screenshot `assets/playground.png` ("captured against a real `clm-serve` (`clm-latest`, Qwen3-8B encoder on
  one RTX 4090)", current schema: options embedded verbatim). Same state and three questions here:

  | | screenshot | this shim (SDPA) | eager attention |
  |---|---|---|---|
  | urgency p(true) | 84.8% | 83.6% | 83.5% |
  | department billing / technical | 98.8% / 1.21% | 98.76% / 1.25% | 98.97% / 1.04% |
  | frustration score | 2.00 | 1.99998 | 1.99997 |

  The attention kernel alone moves the tail by ~0.2 points, and the screenshot sits between the two, so the gap is the
  bf16 kernel noise level.
- HF model card `engine.rank("What causes tides on Earth?", …)`: top prob 0.993; here 0.99319.
- The Quickstart code comment in the GitHub README (urgency 0.41022, billing 0.93878, frustration 1.98386, 106 cold tokens)
  does **not** match (here 98 tokens). The screenshot does, and the comment's numbers disagree with the screenshot too.
  Key-prefixed options, which the schema comment says were dropped, and an appended EOS were tried and neither reproduces it,
  so the comment most likely comes from an earlier head or schema. Recorded, not chased further.
- Option swap (synthetic boiling-point question): A=correct had p(A)=0.92753. Swapping the texts of A and E gave
  p(E)=0.92753 and the other keys unchanged. Keys never reach the encoder, so the permutation is exact by construction and
  was confirmed.

## Token limit and 413

`MAX_TOKENS = 8192` per encoder text (CLM's documented raised limit: `--max-model-len 8192` + `clm-serve --max-tokens 8192`).
The shim builds the texts with CLM's own `clm.schema.build_pairs` and counts them with the Qwen3 tokenizer as vLLM does:
(1) the state text `to_text(state) + "\n\n" + instructions`, (2) each option text separately. If any one is over 8192
tokens it returns 413 (`input_tokens` = state-text tokens, `reason` lists all counts). Upstream would silently truncate
(`truncate_prompt_tokens`); here nothing is cut. Checked: a 24,009-token state → 413.

## Smoke (2026-09-27)

`run.py --system clm --tag smoke --ids korean-common:10 biology-2:5 english:30 math-common:3 korean-history:1 korean-language:42`:
30/30 complete, 0 unsupported, 0 error. Median latency 12 ms over all 30 (Mac → tunnel → shim). Rotations 1-4 reuse the
same state and option texts, so they are served from CLM's vector cache. Rotation 0 (cold): 1.1-5.9 s, median ~2.2 s,
longest korean-language:42 (3,134 chars).
