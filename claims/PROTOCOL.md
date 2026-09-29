# 제작자 벤치마크 교차 실행 — 실행 전 조건 (2026-09-28)

목적: Jev-like 제작자가 성능 근거로 내세운 벤치마크를 모아, 8개 시스템(Jev와 Jev-like 7개)에 같은 조건으로 돌린다. 두 가지를 본다.

- 제작자가 발표한 수치가 우리 실행에서도 나오는가
- 각 제작자가 고른 시험에서도 Jev와의 순서가 수능·게임 벤치마크(`csat/bench`, `gamebench`)와 같은가

모델을 부르기 전에 이 문서를 고정한다.

## 1. 세트

세트는 `claims/build.py`와 `claims/build_ext.py`로 만든다. 원본은 sha256으로 고정하고 `claims/sets/<세트>/manifest.json`에 기록한다. 정답(`gold.json`)은 채점할 때만 읽는다.

| 세트 | 문항 | 인용한 제작자 | 비고 |
|---|---:|---|---|
| typed-decisions | 2,000 | Julia-1, Laya (jevmlx도 실행 가능) | HF `LocalLLaMA/typed-decisions`@c76749ec. choice·score·noul을 모두 보기 고르기로 준다(Julia 재현 스크립트와 같다) |
| kev-transfer-v4 | 764 | Kev | test 분할. Kev 발표 수치는 clean 행만 쓴다 |
| semif-authored144 | 144 | SemIf | |
| semif-wanli256 | 256 | SemIf | |
| semif-typesafe102 | 102 | SemIf | Jev가 받은 형태(문서 객체 state)로 준다. SemIf 0.845는 문자열 state 형태에서 잰 값이다 |
| openjev-synthetic400 | 400 | open-jev | 질문 없음(`""`). 지시가 context 안에 있다 |
| jevbench-agnews100 · emotion100 · banking77-100 | 100씩 | Julia-1 (Jev 기준치 0.910 · 0.480 · 0.870) | `AbdelStark/jev-benchmarks`@0d610cc, BTZSC. Banking77은 보기 72개 전부다. Julia의 64%는 모델이 만든 상위 16개 후보로 잰 값이라 같은 조건이 아니다 |
| laya-agnews400 · emotion400 · banking77-400 | 400씩 | Laya | Laya `bench_apps.py`. Banking77은 보기 77개이고, 앞 400행이라 의도 10개만 들어 있다 |
| jevmlx-typesafe45 | 363 | jevmlx | TypeSafe 공개 사례 45건의 필드별 문항. 0~3 척도를 벗어난 2문항은 뺐다. jevmlx 스키마대로 렌더링한다 |

**만들지 못한 것:**
- Julia의 Banking77 상위 16개 후보: 모델이 후보를 고르는 방식이라 모델 없이 재현할 수 없다.
- CLM: 인용한 벤치마크가 보기 고르기 형식의 공개 데이터가 아니다(시뮬레이션, 궤적 best-of-N, 비공개 데이터).
- Laya 앱 테마 7종: 5종이 예/아니오이고 Jev 기준치가 없다.

**보기 수:** 보기가 26개를 넘으면 키를 A~Z 다음 AA, AB, …로 이어 붙인다(`gamebench/run.py keys`). 26개 이하 문항은 요청이 바뀌지 않는다. Julia는 보기 2~20개만 받으므로 Banking77은 처리 못 함으로 기록된다.

## 2. 실행

1. **시스템:** jev-1.13.0, kev, semif, open-jev, jevmlx, laya, clm, julia. 어댑터·설정은 `csat/bench`와 같다. state는 원본이 문자열이나 목록이면 그대로 보낸다.
2. **보조 시스템 `laya-typed`:** Laya가 typed-decisions로 추가 학습한 체크포인트다. Laya의 0.766을 재현하는 데만 쓰고, 순위에는 넣지 않는다. 그 데이터로 학습한 모델이라 공평한 비교가 아니다.
3. **보기 순환:** min(n, 5)개의 서로 다른 순환 이동. 확률을 원래 보기로 되돌려 평균한 최댓값이 답이다. 제작자 수치와 맞대는 용도로 순환 0(원래 순서) 한 번의 정확도도 따로 보고한다.
4. **계산 장치:** 모든 로컬 시스템을 GPU에서 돌린다. MLX는 jevmlx·open-jev·SemIf, MPS는 Laya·Julia, `amd`(ROCm)는 CLM·Kev이다. Kev는 처음 508회를 Mac(MLX)에서 돌리다 속도 때문에 `amd`의 torch 경로로 옮겼다. torch는 Kev README가 발표 수치를 낸 경로다. 옮기기 전에 Mac 결과 36건과 비교해 답이 모두 같았고, 확률 차이는 최대 0.02였다. `amd`에는 fla·causal_conv1d 커널이 없어 transformers의 참조 구현을 쓴다. 느리지만 결과는 같다. Julia는 공식 지원이 cpu·cuda뿐이라 shim이 입력만 mps로 옮긴다. 게임 문항 105개에서 cpu와 답이 모두 같았고, 확률 차이는 최대 1.4e-5였다.
5. **처리 못 한 문항:** 입력 길이 등으로 처리하지 못한 문항은 몰래 자르지 않는다. 정확도에서는 오답으로 센다.

## 3. 지표 (사전 고정)

6. **주 지표:** 세트별 정확도(순환 평균 기준)와 95% bootstrap 구간(문항 단위, 1만 회, 시드 20260928).
7. **우연 보정 점수:** (acc − 1/n)/(1 − 1/n)을 세트 안에서 문항 평균한다. 보기 수가 세트마다 달라서 세트를 가로지르는 비교는 이것으로 한다.
8. **제작자 수치 대조:** manifest에 적힌 발표 수치와 Jev 기준치를 우리 값 옆에 둔다. 모델 크기·체크포인트·분할이 다르면 표에 적는다(예: Kev 발표는 4B·27B이고, 우리는 9B다).
9. **Jev 대비 비교:** 같은 문항끼리 McNemar 검정을 한다.
10. **결과를 본 뒤의 수정:** 세트나 어댑터를 고치면 새 태그로 다시 돌리고 이전 결과와 섞지 않는다.

## 4. 추가: Jeff (2026-09-29 고정, 실행 전)

Jeff(firelex/jeff@2c1bfce)가 README에서 인용한 패널을 세트로 추가하고, Jeff 체크포인트 세 개를 시스템으로 추가한다. 앞의 13세트 결과와 문항·요청이 겹치지 않으므로(요청 해시가 다르다) 태그는 `claims` 그대로 쓴다. 기존 시스템은 새 세트만 추가로 돈다.

**세트** (`claims/build_jeff.py`). 원본은 Jeff 제작자 코드로 만든 두 파일이고 sha256을 고정한다.

| 세트 | 문항 | 원본 |
|---|---:|---|
| jeff-bbh750 | 750 | `python -m jeff.panel` (시드 20260926) |
| jeff-fpb999 | 999 | 〃 |
| jeff-judgebench350 | 350 | 〃 |
| jeff-ragtruth1500 | 1,500 | 〃 (전부 noul) |
| jeff-winogrande1000 | 1,000 | 〃 |
| jeff-jevbenchhard105 | 105 | `python -m jeff.jevbench` (jevbench@d06ee95 public hard, score 6문항 제외. choice 67, noul 38) |

- **noul 변환:** 공통 계약이 보기 고르기뿐이라 noul은 [거짓 문구, 참 문구] 두 보기로 준다. 문구는 criteria 값, 없으면 Jeff 기본값("No / false", "Yes / true")이다. Jeff 평가기도 noul을 같은 두 보기, 같은 순서로 채점하므로 문제는 같다.
- **보기 문구:** criteria 값, 값이 없으면 키(Jeff 렌더링과 같다).

**시스템** (`csat/bench/shims/jeff/serve.py`)

| 시스템 | 체크포인트@리비전 | 실행 경로 |
|---|---|---|
| jeff-0.8b | mstrasser/Jeff-Qwen3.5-0.8B@d66458d | Jeff MLX 백엔드, Mac |
| jeff-2b | mstrasser/Jeff-Qwen3.5-2B@30824ca | Jeff MLX 백엔드, Mac |
| jeff-gemma4-e2b | mstrasser/Jeff-Gemma4-E2B@afcb75a | Jeff torch 경로(`jeff.server.predict`와 같은 계산), `amd` ROCm. Jeff MLX 백엔드는 Qwen만 돈다 |

- **처리 못 함(413):** 보기가 `max_options`(26)를 넘는 문항(Banking77)과 8,192토큰을 넘는 입력. 둘 다 Jeff 자신의 제한이다.
- **같은 분포 학습:** Jeff 학습 데이터에 RAGTruth 학습 split, WinoGrande 학습 split, 금융 뉴스 감정(twitter_financial)이 들어 있다. 평가 문항과 겹치지는 않지만 RAGTruth·WinoGrande·FPB는 같은 분포라 결과 해석에 적는다. Julia의 Emotion(학습에 emotion 재생 포함)도 같은 경우다.
- **제작자 수치 재현:** 제작자 평가기(`jeff.evaluate`의 `predict_local`·`metrics`)로 패널과 JevBench hard를 먼저 돌려 README 수치와 맞대 본다. 결과는 `~/dev/jev-likes/jeff/runs/eval/`에 둔다.

**실행 장치 기록 (실행 중 결정, 2026-09-30)**

- MLX 시스템(open-jev, jevmlx, Jeff)은 버퍼 캐시를 2 GiB로 묶었다(`mx.set_cache_limit`, `MLX_CACHE_GB`). 메모리 압박으로 두 번 중단된 뒤 넣었고 점수에는 영향이 없다.
- Laya·laya-typed의 새 세트는 `amd`(torch 2.9.1+rocm7.2.1, transformers는 Mac과 같은 버전)에서 돌렸다. Mac 기록과 표본 비교에서 Laya 36/36, laya-typed 18/18 같은 답, 확률 차이 최대 0.02였다. laya-typed가 앞 13세트에서 비어 있던 부분도 이때 채웠다.
- Julia도 `amd`에서 돌려 봤으나 표본 255개 중 252개만 같은 답(확률 차이 최대 0.16)이라 Mac(MPS)에서 다시 돌렸다. 점수는 Mac 결과이고, `amd` 결과는 `julia-amd`로 따로 두었다. 새 6세트 정확도 차이는 세트마다 1%p 이내였다.
- Jeff 세 모델은 CSAT(`2027-09`), 게임 v1(`v1`), 언어 시험(`lang-en`)도 같은 장치로 돌렸다.
