# research

Jev 같은 모델이 어떻게 만들어지는지 조사한 자료 모음. 실험 코드는 `experiments/`에, 데모는 루트에 두고
여기에는 읽을거리와 정리만 둔다.

이 생태계는 Jev 발표(2026-09-15) 며칠 뒤에 생긴 것이라 자료가 매일 바뀐다. 모든 파일과 수치에
조사일과 출처 URL을 달고, 다시 볼 때 최신인지 확인한다.

| 파일 | 무엇 |
|---|---|
| `how-jev-replicas-work.md` | 공통 원리. 텍스트를 만들지 않고 logit을 읽어 확률로 바꾸는 법, 판단 여러 개를 한 번에 돌리는 법, 학습·보정 방법 |
| `replicas.md` | 오픈소스 복제본 카탈로그. 베이스 모델, 학습 여부, 병렬화 방식, 공개 수치 |
| `replicas-detail.md` | 읽은 6개 상세. 특징·속도·성능 표와 후기(커뮤니티 반응, 내 평가) |
| `vision.md` | 시각 입력 전용 Jev 같은 것. openvons.vision(인코더 + 2.5만 파라미터 head), jev-visual(MLX VLM) |

## 공식 자료

- 발표 글: https://typesafe.ai/blog/introducing-system-one-models-and-jev (2026-09-15)
- 문서: https://docs.typesafe.ai/ — System One 개념, 프리미티브(Choice/Score/Noul), 확신도, 패턴
- 워크플로 평가 사이트: https://evals.typesafe.ai/ — 복제본들이 자기 점수를 비교하는 기준
- GitHub: https://github.com/typesafe-ai — SDK(Python/TS), `system-one-adapter-python`(일반 LLM을 같은 인터페이스로), skills
- GeekNews 한국어 요약: https://news.hada.io/topic?id=33751

## 다음에 볼 것

읽지 않은 복제본. 직접 클론해서 코드를 봐야 하는 것들. 위 두 문서는 README 요약 기준이라 파일 단위 주장은 미확인이다.

- 학습하는 계열: `Mapika/decider`(Qwen3.5-2B 파인튜닝), `kshetrajna12/reflex`, `vinnylarouge/jevlike`, `akash-kamat/system-one-gemma`(Gemma 3 270M + scoring head), `olonotolu/jevbetter`(가변 옵션 위 attention)
- Apple Silicon/MLX 계열: `daseinlabs/open-jev`(Gemma 3 4B MLX), `bnsd55/jevmlx`
- 서빙 계열: `openjev-sglang`(prefill only), `ikermoel/open-alternative-jev`(HF + vLLM), `sgoedecke/system-one`
- 다른 백본: `razorback16/openjev`·`JoshuaSP/open-jev`(DiffusionGemma), `zhengxuyu/litjev`(임의 Qwen을 판단 모델로)
- 큐레이션 목록 (매일 갱신): https://github.com/hellogumbo/awesome-jev , https://github.com/ozers/jevsome-projects (코드 줄까지 링크)
- 해설 글: Latent Space AINews "Jev, a System One Model that only decides", DataCamp "System One models explained", Anthony Maio "Jev: The Language Model That Will Not Talk"

## 아직 모르는 것

- 진짜 Jev의 모델 크기, 베이스, 학습 데이터. 발표 글은 RLCD(Reinforcement Learning for Calibrated Decisions)라는 이름만 밝히고 나머지는 FAQ 미답변이다.
- 복제본 중 실제로 RL을 돌린 곳이 있는지. 현재까지 본 것은 전부 지도학습(CE + Brier)이거나 학습 없음이다.
- 한국어 성능. 복제본들의 평가는 전부 영어 벤치마크다. `experiments/hangul`과 이어서 볼 것.
