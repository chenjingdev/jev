# jevable.com 조사 — 남들은 Jev를 어디에 쓰는가

조사일 2026-09-21. 출처 https://jevable.com/ (프로젝트 194개, 각 항목은 X 게시물 링크와 큐레이터 확인 날짜를 달고 있다). 사이트가 매일 바뀌므로 그날 받은 목록을 `jevable-projects.json`에 그대로 남긴다(이름·설명·분류·태그·프로젝트 URL). 설명은 사이트의 JSON-LD 값이고 약 300자에서 잘려 있다.

분류별 개수: Games 39, Developer tools 34, Productivity 31, Agents 19, Experiments 18, Creative tools 16, Data & research 9, Finance 8, Browser extensions 7, Robotics 7, Marketing 6.

## 체스 (2건, 둘 다 Jev 단독으로 LLM과 대국)

둘 다 원문이 X에서 잘려 있고 로그인 없이는 나머지를 받을 수 없다. 받은 만큼만 적는다.

- **Jev vs. GLM at chess** — https://jevable.com/project/2101010773157761481 (@nutlope, 2026-09-18). **GLM 5.3이 29수 만에 체크메이트로 이겼다.** Jev는 수당 약 0.3초·$0.0001 미만, GLM은 약 5.8초·$0.008, 한 판 24센트. 저자 결론은 "각자의 강점에 맞게 쓰는 편이 좋다"에서 잘렸다.
- **Blitz chess against frontier models** — https://jevable.com/project/2100372930282573876 (@aimlapi, 2026-09-16). Jev V13 대 Fable 5.1 대 GPT-6 Astra, 5+0 블리츠, 한 수에 API 한 번. 결과는 잘렸다.

**우리 실험과의 관계.** 둘 다 "Jev 혼자 체스를 두면 어떤가"이고, 이 저장소는 그 질문을 이미 지났다. 우리 기록으로는 Jev 단독은 물론이고 엔진에 붙여도 대국 결과를 바꾸지 못하며(100판), 실제 이득은 근접 후보 사이 결정당 10cp 수준이다. 속도·비용 수치(0.3초, $0.0001/수)는 우리 측정(중앙값 243~293ms)과 같은 자리수라 서로 확인이 된다. **새로 배울 것은 체스 항목이 아니라 다른 분류에 있었다.**

## 가장 흔한 실전 패턴: 비싼 것을 쓰기 전에 Jev가 먼저 고른다

라우팅 계열이 이 사이트에서 가장 많고, 대부분 제품에 들어가 있다.

| 프로젝트 | 무엇을 고르는가 |
|---|---|
| Starchild prompt routing | 어떤 LLM으로 보낼지. 프롬프트 분류 평균 140ms, 비용 20배 절감·속도 6배 |
| Corent model routing | 요청·작업량·품질 요구를 보고 모델 선택 |
| Just-in-time model selection in Goose | 턴이 돌기 직전에 모델 선택 |
| Criteria-based model routing in Eve | 기준 기반 모델 라우팅 |
| Higgsfield model routing | 프롬프트를 보고 이미지·영상 생성 모델 선택 |
| Automatic agent and model selection | 에이전트·모델·컴퓨터·폴더까지 선택 |
| A prompt difficulty classifier | 사용자가 입력을 마치면 난이도를 재서 빠른 모드를 제안 |
| A page-by-page OCR router | PDF에서 **OCR이 실제로 필요한 페이지만** 고르고 나머지는 로컬 처리 |
| Email fraud detection with Jev and Kimi | Jev가 100통을 1.42초에 분류하고 **불확실한 것만** Kimi K3로 올려 96/100 |
| Cascade Search typed query filters | 27K 파라미터 모델이 먼저 파싱하고, **확신이 없는 단어만** Jev에게 묻는다 |
| Skill Router for Claude Code | 설치된 스킬 90개 중 이번에 쓸 것 고르기 |

**이 구조가 우리 `budget` 실험과 같은 모양인데 결과는 반대다.** 우리는 "깊이를 어디에 쓸까"에서 코드 기준선을 못 넘었다. 위 사례들과의 차이로 짚을 만한 것은 라벨의 성질이다. 이들이 고르는 것은 **이름 붙은 범주**(이 프롬프트는 어렵다, 이 페이지는 스캔본이다, 이 메일은 사기다)이고, 우리 체스 라벨은 이름이 없었다 — 무엇이 "깊이가 필요한 국면"인지는 사후에야 정의되고, 실제로는 대국 진행 정도에 가까웠다. 가설이며 이 조사로 검증된 것은 아니다.

두 사례는 방향도 다르다. **Email fraud**와 **Cascade Search**는 "이게 어려운가"를 묻지 않는다. 일단 답하게 한 뒤 **모델 자신이 확신 없는 건만** 비싼 쪽으로 올린다.

## 우리가 한 번도 안 해 본 자리: 굴려 보고 고르기

- **Doom with branching futures** — https://jevable.com/project/2101084662793666618 (@toksdotdev). Jev가 수를 고르고, 하네스가 microsandbox로 같은 체크포인트에서 **여러 미래를 병렬 실행**한 뒤 가장 좋은 결과에서 이어 간다. LLM은 결과를 보고 다음에 뭘 시도할지 지도한다.
- **Mario Never Dies** — 죽을 때마다 VM을 4갈래로 포크해 살아남은 쪽을 정사로 삼는다.

지금까지 이 저장소에서 Jev에게 준 자리는 (1) 후보 중 고르기, (2) 예산 배분 둘뿐이었다. **정책으로 굴리기**는 없었다.

## 그 밖에 기록해 둘 것

- **MuJoCo robot-arm control** — "처음엔 잘 못해서 매 갱신을 두 번의 호출로 쪼갰다: 무엇을 할지 정하고, 그다음 팔과 그리퍼를 어떻게 움직일지 정한다." 체스 체크 감지의 22/40 → 37/40과 같은 처방이 다른 도메인에서 독립적으로 나왔다.
- **Fourteen checks for every pull request** — diff 하나를 한 번의 호출로 보내 14개 유형 확률을 받는다. `bug-hunter/`와 같은 구조다.
- **Natural-language queries inside PostgreSQL** — `WHERE jev(people, '재택근무 가능해 보임')`. `sif`가 파이썬에서 하는 것을 SQL에서 한다.
- **Drawing, one decision at a time** — 픽셀을 병렬로 예측해 그림을 그린다.
- 게임 39건은 대부분 실시간 조작(팩맨, 테트리스, 지오메트리 대시, 격투, FPS)이고 탐색이 필요한 것은 루빅스 큐브와 위 두 건 정도다.

## 여기서 나온 다음 후보

1. **정책으로 굴리기.** 국면에서 Jev에게 짧은 수순을 여러 개 두게 하고, 코드가 결과를 채점해 제일 좋은 쪽을 고른다. 대조군은 무작위 정책 롤아웃이고 채점은 Stockfish다. `jev_escape_beam.py`가 하네스의 절반이다. 비용은 정직하게 봐야 한다 — 250ms × 롤아웃 8개 × 10수면 국면당 약 20초라 400국면이 아니라 50국면 규모다.
2. **자기 확신으로 올리기** (Email fraud·Cascade Search 방식). "이 국면이 어려운가"를 묻는 대신, Jev가 고르게 하고 **확신이 낮은 결정만** 깊게 다시 본다. 저장된 100판 결정 1,955개와 심판 점수로 API 없이 미리 재 봤다: 자기 확신은 자기 실수를 AUC 0.55~0.56으로 가리키고 코드 신호(후보 cp 폭, 후보 수)는 0.47~0.51로 우연이다. 다만 **쓸모 있는 예산 구간에서 재현되지 않는다** — 깊이 2 상대에서는 30%·50% 예산에서 우연을 넘지만(37.8%/67.6% 대 30%/50%), 깊이 4 상대에서는 10~30% 구간이 우연 이하다. 결과가 아니라 단서이고, 하려면 실험으로 따로 설계해야 한다.

