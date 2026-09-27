# 2026 수능 전과목 객관식 비교

수학 단답형 13개와 공통 문항 중복을 제외한 **884문항**을 네 모델로 시험했다.

| 모델 | 정답 | 정답률 |
|---|---:|---:|
| Jev 1.13.0 | 619/884 | 70.0% |
| GPT-5.6 Luna low | 784/884 | 88.7% |
| GPT-5.6 Terra low | 818/884 | 92.5% |
| GPT-5.6 Sol low | 853/884 | 96.5% |

`report.html`에서 과목을 검색하고 모델 점수를 눌러 오답 원문 링크를 볼 수 있다.
`REPORT.md`에는 전체 집계, `answers.csv`에는 문항별 답, `summary.json`에는 검증된 집계가 있다.

이 결과는 **텍스트 변환본** 기준이다. 그림은 묘사로, 수식은 LaTeX로, 영어 듣기는 공식 대본으로 변환하여 네 모델 모두 같은 입력을 받았다. 전사·원문 대조 과정과 한계는 `PROTOCOL.md`와 각 전사 기록에 남겼다. 실제 시각·청각 시험이나 수능 등급으로 해석하지 않는다.

## 재현

```bash
# 원문 다운로드와 객관식 문항 목록
.venv/bin/python csat/all_subjects/fetch_sources.py
.venv/bin/python csat/all_subjects/prepare_manifest.py

# 원문 전사·대조. 기존 검증 완료 기록은 재사용한다.
.venv/bin/python csat/all_subjects/transcribe.py --workers 6

# 수동 원문 확인 기록이 포함된 완성 데이터 생성
.venv/bin/python csat/all_subjects/build_dataset.py --require-complete

# 기존에 같은 요청으로 완료한 답은 재사용한다.
op-away run op run --env-file=csat/.env.tpl -- \
  .venv/bin/python csat/all_subjects/run_benchmark.py --workers 8

# 현재 입력과 모든 응답을 대조한 뒤 채점·보고서 생성
.venv/bin/python csat/all_subjects/summarize.py
.venv/bin/python csat/all_subjects/render_report.py
.venv/bin/pytest csat -q
```

전사와 GPT 호출에는 기존 로컬 Codex 프록시 `127.0.0.1:11435`가 필요하다.
Jev 호출에는 `.env.tpl`의 Agent vault 참조를 사용한다. 기본 테스트 실행은 API를 호출하지 않는다.
전사 입력에 정답표를 섞지 않으며, 채점은 별도 프로그램에서 한다.

`sources/exam/`와 `sources/answer/`를 분리했고, `source-manifest.json`에 원문 URL·해시를 보존했다.
영어 듣기 대본은 `sources/exam/english-listening-script.pdf`이며 출처 URL은 같은 이름의 `.source.txt`에 있다.
기존 영어 독해 28문항은 요청이 일치하는 앞선 결과를 재사용했다.
문항별 응답은 `results/<model>/<question-id>-<request-hash>.json`에 저장된다.
원문 수정·정답을 본 재풀이로 점수를 고르는 절차는 없다. 전송 실패만 동일 요청으로 재시도한다.
