# laya shim (port 8805)

Laya(https://github.com/NandhaKishorM/laya)를 벤치마크 shim 계약(`csat/bench/adapters/__init__.py`)으로 노출한다.

## 설치 (2026-09-27)

```bash
mkdir -p ~/dev/jev-likes/laya && cd ~/dev/jev-likes/laya
git clone https://github.com/NandhaKishorM/laya repo      # commit 4066d5d5fbf08b66c6757ddeedbd797bd7655bc0 (laya 0.3.20)
~/.local/bin/uv venv -p 3.12 .venv
~/.local/bin/uv pip install -p .venv/bin/python -e ./repo  # torch 2.14.0, transformers 5.17.0
```

공식 repo를 MPS에서 그대로 쓴다. MLX 포트(laya-mlx)는 쓰지 않는다.

## 실행

```bash
cd ~/dev/jev   # 저장소 루트
~/dev/jev-likes/laya/.venv/bin/python csat/bench/shims/laya/serve.py   # 127.0.0.1:8805, 기본 LAYA_DEVICE=mps
```

## 체크포인트

- `Router` 이름 `multilingual` = HF `convaiinnovations/laya`, subfolder `multilingual` (laya-multilingual, mmBERT-base 322M).
  Router가 기본으로 받는 번들 repo이며, 받은 스냅샷 revision은 `55cf4c4ebb4ebe31b2550e8bdf3bd21b99753851`.
  (별도 repo `convaiinnovations/laya-multilingual`은 쓰지 않았다.)
- 이유: 문항이 한국어이고, 프로젝트가 100+ 언어용으로 낸 체크포인트가 이것이다. 요청마다 `model="multilingual"`로
  고정한다. 자동 라우팅에 맡기면 영어 문항은 영어 체크포인트(ModernBERT-large)로 가서 과목 간 모델이 달라진다.

## 입력 매핑

```python
router.predict(state, {"answer": {"type": "choice", "instructions": instructions, "criteria": {A..E: 보기 원문}}},
               model="multilingual", max_len=8192, head_max_len=512)
```

state는 dict 그대로(Laya가 `json.dumps(ensure_ascii=False)`로 직렬화), instructions·보기 문구는 손대지 않는다.
Laya가 모델에 넣는 순서: `[CLS] choice question: <instructions> [SEP] [MASK] A: <보기> [MASK] B: ... [SEP] <state> [SEP]`,
각 `[MASK]` 위치 은닉벡터로 보기별 logit을 낸다. 응답의 `probabilities`(A~E)를 그대로 돌려준다.

## 컨텍스트 한도와 413

- `max_len=8192`: README가 laya-multilingual 장문용으로 안내하는 값(체크포인트 기본 1024).
- `head_max_len=512`: 문서화된 호출 인자(기본 256). 고정 instructions가 137토큰이라 기본값이면 보기 합이
  ~119토큰을 넘을 때 instructions가 잘린다. 둘 다 잘림만 바꾸는 값이라, 기본값에서도 안 잘리는 입력은 결과가 같다
  (math-common:3에서 확률 완전 일치 확인).
- **보기 하나당 48토큰 상한**: `laya.common.build_sequence`에 `truncation=True, max_length=48`로 박혀 있고 인자로 못 바꾼다.
  `"A: <보기>"`가 48토큰을 넘는 문항은 413이다. 긴 보기가 많은 국어 문항이 주로 여기 걸린다.
- 판정: 잘림 없는 전체 길이를 직접 계산하고 Laya의 `build_sequence`가 만든 시퀀스 길이와 비교한다. 짧아지면 413
  (`input_tokens` = 잘림 없는 전체 토큰 수, `reason`에 원인). 토크나이저 자체는 기본으로 자르지 않는다(20001토큰 그대로 확인).

## 참고 (2026-09-27 확인)

- `"A: "` 키 접두는 Laya의 `render_options`가 붙인다(shim이 넣은 문구 아님).
- 확률은 Laya가 소수 4자리로 반올림해 합이 정확히 1이 아닐 수 있다. shim은 재정규화하지 않는다.
- `model="multilingual"`로 고정해도 언어 감지는 돌고 `lang`이 넘어가지만, 이 체크포인트 설정에 언어별 온도가 없어 결과에 영향 없다.
- 받은 revision `55cf4c4e…`는 `laya/revisions.py`의 `PINNED_REVISIONS["convaiinnovations/laya"]`(저자 검토 핀)과 같다.
- 보기 전달 확인: 디코드한 입력 시퀀스에 `[MASK] A: <보기>`가 marker 위치에 있음. 보기 문구를 비우거나 바꾸면 출력이 바뀐다.
  단 두 보기 문구를 맞바꿔도 확률이 문구를 따라가지 않았다(biology-2:5 B↔E 교환 후에도 B 최고, E 최저).
  모델 선호가 키·위치에 크게 좌우된다는 뜻이고, PROTOCOL 2절 순환 평균이 상쇄하는 대상이다.
