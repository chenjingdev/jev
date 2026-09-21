# Jev 복제본은 어떻게 만드는가

조사일 2026-09-19. README 요약을 바탕으로 정리한 것이라 파일 단위 주장은 클론해서 확인하기 전까지 미확인이다.

## 한 줄 요약

텍스트를 생성하지 않는다. 옵션마다 답 자리(토큰 위치)를 정해 두고, forward pass 한 번으로 그 자리의 logit을 읽어
softmax하면 그것이 확률이다. Choice는 옵션 위 분포, Score는 순서 있는 단계 위 분포의 기댓값, Noul은 P(true).
복제본들은 전부 이 뼈대를 공유하고, (1) 학습을 하느냐, (2) 여러 판단을 어떻게 한 번에 돌리느냐, (3) 확률을 어떻게 보정하느냐에서 갈린다.

## 1. 뼈대: logit 읽기

일반 LLM에게 "A/B/C 중 뭐야?"라고 묻고 답 토큰을 샘플링하는 대신, 답이 나올 위치에서 `A`, `B`, `C` 토큰의 logit만 꺼낸다.

- 옵션을 단일 토큰 라벨에 매핑한다. system-one-open은 한 번에 52개까지(아마 알파벳 대소문자), 그 이상은 "none of the above" 슬롯을 넣고 청크로 나눠 마지막 라운드를 한 번 더 돈다. jevfire는 라벨이 정말 단일 토큰인지 토크나이저로 검증한다.
- 옵션 토큰 외의 logit은 버리므로 형식 오류(hallucination)는 구조적으로 0이다. 발표 글이 말하는 "can't hallucinate"가 이것이다.
- 다만 이렇게 나온 분포는 "주어진 옵션 중 상대적 선호"이지 "맞을 확률"이 아니다 (jevfire README가 명시). 보정 없이는 확신도로 못 쓴다. → 3절.

프롬프트 형식은 XML 태그(`<state>…</state>`)에 질문별 답 슬롯을 붙이는 식(system-one-open)이 흔하다.

## 2. 병렬화: 상태 하나, 판단 여러 개

`sif.ask()`처럼 질문 여러 개를 한 요청에 묶으려면 상태(state)를 한 번만 인코딩하고 질문·옵션 가지만 갈라야 한다. 세 가지 방식이 보인다.

| 방식 | 어떻게 | 누가 |
|---|---|---|
| prefix cache 재사용 | 공유 접두(지시 + 상태)를 KV cache에 올리고, 질문마다 접미만 붙여 배치로 보낸다. vLLM/SGLang이 알아서 블록을 공유한다. | jevfire (warm prefix로 12필드 2,167→255ms), SemIf ("parallel suffix reuse", 777판단 20/s on 3090), openjev-sglang |
| tree attention mask | 한 시퀀스 안에 가지들을 이어 붙이고 attention mask로 가지끼리 못 보게 막는다. position id도 가지별로 다시 센다. | NanoJev("44 candidate paths in one backbone forward"라고만 하고 방식은 미기재, 추정), jevmlx(추정) |
| prefix fork | 상태를 prefill한 뒤 cache를 배치 차원으로 복사해 가지를 병렬 실행. 순환층(Gated DeltaNet 등)이 섞인 하이브리드 모델은 attention mask로 가지를 격리할 수 없어서 이 방식이 필요하다. | qwen-rlcd (`system_one/fork.py`, fork vs 순차 오차 4.8e-5) |

인코더 계열(Verdict, ModernBERT)은 애초에 생성이 없으니 문서와 후보 라벨을 구분자로 이어 붙여 한 번에 양방향으로 본다. 후보 슬롯 25개(24 + 기권 1).

## 3. 학습과 보정

### 3-a. 학습 없음 (frozen)

SemIf, jevfire, mini-jev, jev-on-a-laptop, open-alternative-jev, typesafe-local 등 대다수. 공개 instruct 모델의 LM head를 그대로 쓴다.
장점은 어떤 모델이든 바로 된다는 것, 단점은 확률이 보정돼 있지 않고 옵션 이름 표현에 민감하다는 것.
SemIf 기준 Qwen3.5-4B Q4가 102행 부분집합에서 modal agreement 0.845, 같은 행에서 Jev는 balanced accuracy 0.883. 지표가 달라 직접 비교는 안 된다.

### 3-b. 지도학습 + proper scoring rule

Jev를 흉내내는 데 가장 재현 가능한 레시피. 정답이 있는 판단 데이터를 모아 CE에 Brier를 더해 학습하고, 끝나면 temperature scaling으로 보정한다.

- **system-one-open** (Gemma 4 E2B + attention LoRA / Gemma 3 270M)
  - 데이터: HF 공개 판단 데이터셋 92개(의도 분류, 모더레이션, NLI, 팩트체크, QA, 루브릭 채점, pairwise 판정) + 규칙 기반 합성 생성기(Doom 상태, 스마트홈 명령, 고객지원 분류, 보안 경보, 인보이스, 에이전트 트레이스, 카탈로그 매칭). 실제 태스크 23개는 held-out.
  - 손실: CE + Brier, 이후 temperature scaling. `train.py`, `build_data.py`, `evaluate.py`, `serve.py`(Modal FastAPI).
  - 결과: TypeSafe eval 공통 부분집합 343쌍에서 76.7% (Jev 86.9%). H100에서 27질문 데모 97ms.
- **Verdict-open-jev** (ModernBERT-base 151M)
  - 손실: L = CE + 1.0·Brier. 후처리 L-BFGS temperature scaling(T=1.4265). 기권 후보 `__insufficient_evidence__`를 학습에 넣어 OOD에서 기권하도록.
  - 결과: Banking77 held-out 1,000건 95.0% top-1, Brier 0.0756, 35ms 미만. temperature scaling 후 ECE가 1.13%→3.35%로 오히려 나빠짐(원문 그대로). 도메인 하나뿐이라 범용 Jev와는 거리가 있다.
- **NanoJev** (Qwen3-0.6B + decision heads)
  - Choice는 공유 스칼라 헤드 + set attention, Boolean은 단일 경로 sigmoid, Score는 단계 설명들을 평가해 기댓값. 후보 2~255개 동적.
  - 학습은 초기화 → 헤드 워밍업 → 전체 학습 3단계, "complete-question distribution loss". 데이터 출처는 README에 명시돼 있지 않고, 게임(미로, 스네이크) 환경의 이벤트 데이터로 보인다(추정).
  - 결과: 안전 모델 77.84% test / 76.56% OOD.

왜 Brier인가: proper scoring rule은 진짜 믿음을 그대로 보고할 때만 최대가 되므로 보정이 손실에 내장된다. qwen-rlcd는 RLCD를 "정답이 있는 질문 위에서 log score나 Brier를 보상으로 쓰는 RL"로 해석하고, RLHF가 아첨 때문에 보정을 망가뜨리는 것과 대비한다. 다만 qwen-rlcd는 아직 추론(fork)만 구현했고 학습은 M2로 미뤄져 있다.

### 3-c. 헤드 설계 선택지

| 방식 | 장점 | 단점 | 누가 |
|---|---|---|---|
| LM head의 옵션 토큰 logit | 학습 불필요 | 옵션이 단일 토큰이어야 함, 보정 안 됨 | frozen 계열, system-one-open(학습은 하되 슬롯 방식) |
| 가지 끝 hidden state에 선형 헤드, 질문 그룹 안에서 softmax | 옵션이 여러 토큰이어도 됨, 옵션 개수 자유 | 학습 필요 | qwen-rlcd(설계), NanoJev |
| 인코더 bi-encoder 유사도 | 매우 빠름, 양방향 | 컨텍스트 이해력이 디코더보다 약함 | Verdict |

## 4. 진짜 Jev와의 차이

발표 글이 밝힌 것: "frontier-intelligence function call", RLCD로 학습, 70~500ms, 입력 $0.042/MTok, 출력 무료, 형식 오류 0%.
밝히지 않은 것: 모델 크기, 베이스, 학습 데이터, RLCD의 실제 알고리즘. 복제본들은 전부 "인터페이스 패턴을 재현한 것이지 모델·학습을 재현한 것이 아니다"(SemIf)라고 선을 긋는다.
가장 좋은 복제본도 TypeSafe eval에서 10점 정도 뒤진다 (76.7 vs 86.9).

## 5. 직접 만든다면

system-one-open의 레시피(공개 판단 데이터 + 합성 생성기 → CE + Brier → temperature scaling)가 가장 재현 가능하고 평가 기준(TypeSafe eval)도 같다.
병렬화는 vLLM prefix cache로 시작하는 게 제일 싸고, 하이브리드 모델을 쓸 거면 qwen-rlcd의 prefix fork를 본다.
한국어를 하려면 데이터 믹스를 새로 짜야 한다 — 92개 데이터셋 목록에 한국어는 없는 것으로 보인다(미확인).

## 출처

- https://typesafe.ai/blog/introducing-system-one-models-and-jev
- https://github.com/mithalouni/system-one-open
- https://github.com/TheoLeeCJ/openjev (SemIf)
- https://github.com/TianyuCodings/NanoJev
- https://github.com/kikoncuo/jevfire
- https://github.com/shamazharikh/qwen-rlcd
- https://github.com/Heman10x-NGU/Verdict-open-jev
- https://github.com/hellogumbo/awesome-jev
