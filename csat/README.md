# Jev 수능 문제 시험

전과목 객관식 884문항 비교도 완료했다. Jev 619개, Luna low 784개,
Terra low 818개, Sol low 853개 정답이다. 그림·듣기를 같은 텍스트 입력으로
변환한 시험이며, `all_subjects/report.html`과 `all_subjects/REPORT.md`에서
과목별 결과·오답 원문을 확인할 수 있다.

시험지·정답 PDF와 페이지 이미지는 저장소에 없다. 출처 링크는 `SOURCES.md`에 있다.

2026학년도 수능 영어 홀수형 독해 18~45번을 `jev-1.13.0`으로 시험했다.
최초 답변 **25/28개 정답, 55/63점**. 오답은 36·37·39번이다.
듣기는 제외했고 25번 도표는 텍스트 표로 전사했다.

상세 방법·문항별 결과·출처는 `reports/2026-english-reading.md`에 있다.

동일 입력으로 GPT-5.6 Luna·Terra·Sol을 모두 **low**에서 비교했다.
최초 답변은 Luna 24/28(52/63점), Terra 26/28(57/63점), Sol 28/28(63/63점)이다.
보기 순환 대조와 요청 입력 검증은 `reports/2026-english-model-comparison.md`에 있다.

```bash
# 기존 로컬 Codex API 프록시(127.0.0.1:11435)를 사용한다.
.venv/bin/python csat/run_openai_comparison.py --output-dir csat/results/new-openai-low-run
.venv/bin/python csat/summarize_comparison.py \
  --run-dir csat/results/new-openai-low-run \
  --output csat/reports/new-openai-low-comparison.md
```

```bash
.venv/bin/pytest csat -q
op-away run op run --env-file=csat/.env.tpl -- \
  .venv/bin/python csat/run_exam.py --output csat/results/new-run.json
```

기존 결과 파일은 덮어쓸 수 없다. 모델 입력은 `data/2026-english-reading.json`,
채점용 정답은 `data/2026-english-gold.json`으로 분리한다. 최초 보기 순서를
주 결과로 삼고 네 가지 추가 순환 배치를 대조한다. 공통 프롬프트는 고정하며,
대조 호출을 새 독립 문항으로 세지 않는다.

`build_english_2026.py`는 `sources/`의 PDF에서 입력 데이터를 재생성한다.
추출에는 pdfplumber와 pdftotext가 필요하다. 이 실행에서는 Codex의 번들
문서 Python 런타임을 사용했다. API 실행에는 프로젝트 `.venv`를 쓴다.

원문 문제의 저작권은 한국교육과정평가원에 있다. 공개 기출의 학습 데이터
포함 여부는 확인되지 않았으며, 이 한 회차를 전체 수능 능력으로 일반화하지 않는다.

## ㄱㄴㄷ 조합형: Jev 한계인가, 입력 형식인가 (2026-09-27)

Jev 오답 265개 중 114개가 ㄱㄴㄷ 조합형 234문항에서 나왔다(이 유형 정답 120/234, 51.3%. 나머지 유형은 499/650, 76.8%). 같은 텍스트 입력에서 GPT-5.6 low는 이 234문항을 Luna 193, Terra 200, Sol 221개 맞혔으므로 입력 자체가 풀 수 없는 수준은 아니다. 기존 입력은 진술 본문을 `passage` 끝 `<보기>`에만 두고, 선택지(`criteria`)에는 `"ㄱ, ㄴ"` 같은 기호만 넣었다.

재실행 변동: 기존 기록과 `prompt_study` 기준선 재실행 사이에서 234문항 중 26문항의 답이 바뀌었다(맞던 7개가 틀리고 틀리던 9개가 맞음, 120 대 122).

**1. 진술 분해 진단** (`decompose/`, 실행 전 조건 `decompose/PROTOCOL.md`). 진술 770개를 하나씩 Noul로 물었다.

| 항목 | 값 |
|---|---:|
| 진술 단위 정답 (p≥0.5를 참으로) | 534/770 (69.4%) — 전부 참이라고 답하면 445/770 (57.8%) |
| 참 진술 / 거짓 진술 정답 | 276/445 (62.0%) / 258/325 (79.4%) |
| 기존 정답 120 중 진술 판정 모두 맞음 / 하나 이상 틀림 | 71 / 49 |
| 기존 오답 114 중 진술 판정 모두 맞음(조합만 틀림) / 하나 이상 틀림 | 11 / 103 |
| 분해·조합 정답 (고정 규칙) | 126/234 (단일 120, 둘 다 102, 단일만 18, 분해만 24) |

기존 오답의 대부분(103/114)은 진술 하나를 따로 물어도 Jev가 틀리는 문항이다. 참 진술을 거짓으로 보는 쪽으로 치우쳐 있다. 다만 기존 정답 120개 중 49개도 진술 하나 이상을 따로 물으면 틀렸다. 진술별 Noul 역시 하나의 입력 형식이므로 69.4%는 Jev가 아는 것의 상한이 아니라 이 형식에서의 관측값이다. 호출 수가 문항당 2~4배(770회, 682,339토큰)인 다른 구조라 정답 수 비교는 개선 주장이 아닌 진단이며, 126 대 120은 재실행 변동 범위 안이다.

**2. 선택지를 진술 본문으로 풀어 쓰기** (`format_combo/`, 실행 전 조건 `format_combo/PROTOCOL.md`). Choice 1회 구조는 그대로 두고 `criteria` 값만 `옳은 것: ㄱ. … || 옳지 않은 것: ㄴ. … / ㄷ. …`로 바꿨다.

| 문항 | 기존 | 풀어 쓰기 | 좋아짐 / 나빠짐 | 쌍 부호검정 |
|---|---:|---:|---:|---:|
| 2026 ㄱㄴㄷ 234 | 120 | 133 | 34 / 21 | p≈0.10 |
| 2025 ㄱㄴㄷ 34 (2026 결과를 보고 형식을 고치지 않고 추가 확인) | 13 | 16 | 4 / 1 | p≈0.38 |

두 회차 모두 방향은 같지만 개선으로 확정하지 않는다. 2026은 prompt_study 재실행(122)과 비교해도 +11이다. 토큰은 2026 234문항 359,203개, 2025 34문항 55,371개다. 선택지 문자열이 길어진 만큼 입력이 늘었다. 두 회차의 부호검정을 합치지 않는다.

**해석.** ㄱㄴㄷ 오답은 대부분 조합 선택이 아니라 진술 판정에서 생긴다(기존 오답 중 조합만 틀린 경우 11/114). 형식을 풀어 쓰면 일부(2026 +13, 2025 +3)를 되찾는 것으로 보이지만, 풀어 쓴 뒤에도 Luna low(193)보다 60개 적다. 풀어 쓰기는 미확정 후보이며 `run_exam.py`의 기본 입력으로 채택하지 않았다. 과목별 진술 정답률이 낮은 곳은 동아시아사·생활과 윤리·한국지리·화학Ⅰ(36~49%)이다. 그림 설명 전사 오류가 섞여 있을 수 있어 절대 정확도는 확정치가 아니다.

```bash
op-away run op run --env-file=csat/.env.tpl -- .venv/bin/python csat/decompose/run_decompose.py
.venv/bin/python csat/decompose/analyze.py
op-away run op run --env-file=csat/.env.tpl -- .venv/bin/python csat/format_combo/run_format.py
op-away run op run --env-file=csat/.env.tpl -- .venv/bin/python csat/format_combo/run_format.py \
  --dataset csat/prompt_study/validation_2025/dataset.json --out csat/format_combo/results/spelled-2025
.venv/bin/python csat/format_combo/analyze.py
```
