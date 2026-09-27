# semif shim (port 8803)

SemIf (https://github.com/TheoLeeCJ/SemIf, 옛 이름 OpenJev)를 벤치마크 shim 계약(`adapters/__init__.py`)으로 부른다.

## 설치 (한 번)

```bash
mkdir -p ~/dev/jev-likes/semif && cd ~/dev/jev-likes/semif
git clone https://github.com/TheoLeeCJ/SemIf.git src        # commit 23cf1f39fc9534fe81437200959b6dfc7106e45a
~/.local/bin/uv venv --python 3.12 .venv
cd src && ~/.local/bin/uv pip install --python ../.venv/bin/python -e '.[test,mlx]'
```

`[mlx]` extra가 MLX 0.32.2와 MLX-LM `a63e24c3…`(0.32.0)을 고정한다. 모델은 첫 기동 때 HF 캐시로 받는다(약 9GB).

## 실행

```bash
~/dev/jev-likes/semif/.venv/bin/python csat/bench/shims/semif/serve.py        # 저장소 루트에서
curl -s 127.0.0.1:8803/health
```

기동 시 SemIf 로더가 safetensors 전체의 sha256을 계산하므로 로드에 수십 초가 걸린다.

## 설정 (프로젝트 기본값 그대로)

| 항목 | 값 |
|---|---|
| 모델 | `Qwen/Qwen3.5-4B` @ `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a` (SemIf README 고정 revision) |
| 정밀도 | 원본 그대로(BF16, 일부 FP32). `--mlx-bits` 미사용. 필요하면 `--mlx-bits 8/4`로 바꾸되 별도 결과로 취급 |
| 모드 | `direct`(요청마다 새로 채점). serial/shared 접두 캐시 재사용은 SemIf 문서상 실험적이라 쓰지 않음 |
| 입력 한도 | `--max-tokens 4096`(CLI 기본값). **렌더된 채팅 프롬프트 전체**(시스템 지시 + state JSON + 지시문 + 보기) 토큰 수 기준. 넘으면 413 + `input_tokens`, 자르지 않음 |
| MLX 할당 캐시 | 256 MiB(로더 기본값) |

## 입력 매핑

SemIf의 JSONL 한 줄과 똑같은 모양으로 옮기고 `semif_phase1.mlx_backend.score`(CLI `--backend mlx --mode direct`가 부르는 함수)를 직접 호출한다. 모델은 한 번만 올린다.

| 벤치 요청 | SemIf row |
|---|---|
| `state` (객체) | `state` 그대로 → 프롬프트의 `"evidence"` JSON |
| `instructions` | `question` → 프롬프트의 `"criterion"` |
| `criteria` {A..E: 보기 글} | `options` = `[{"id": "A", "description": 보기 글}, ...]` (키 정렬) → 프롬프트의 `{"letter", "description"}` |

SemIf는 보기 위치 순서대로 A, B, C… 글자를 붙이므로 키를 정렬해 넘기면 모델이 읽는 글자와 벤치 키가 같다. 시스템 지시문은 SemIf 고정문(`DIRECT_SYSTEM`)이고 shim이 덧붙이는 문구는 없다. 확률은 선언된 보기 글자 토큰(A..E)의 마지막 위치 logit에 softmax를 씌운 값이다(보정 전).

응답에는 `probabilities` 외에 진단용 `input_tokens`, `prompt_sha256`, `option_logits`가 붙는다(러너는 `probabilities`만 읽는다).

## 검증 (2026-09-27)

- 렌더된 프롬프트에 보기 글·지시문이 그대로 들어가고, 글자 A..E가 벤치 키와 일치함을 확인(korean-common:10, english:30, math-common:3, korean-language:42; 309–2195 토큰).
- 같은 row를 네이티브 CLI(`semif-score --backend mlx --mode direct`)로 돌린 결과와 shim 결과가 `prompt_sha256` 동일, 확률 차이 0.0.
- 보기 글 교환: korean-common:10에서 C↔A 글을 바꾸면 0.986이 C→A로 이동(0.988). english:30도 0.438(C)→0.443(A).
- 15k 토큰 입력 → 413 `{"input_tokens": 15245}`.
- 스모크 6문항×5순환 = 30건 모두 complete, 지연 중앙값 3.4초(첫 호출 포함 최대 18초).
