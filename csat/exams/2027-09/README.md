# 2027학년도 9월 모의평가 객관식 텍스트 데이터 (순위 산정용)

2026-09-03 시행 고3 9월 모의평가를 `csat/all_subjects`(2026 수능)와 같은 전사·검수 규칙으로 텍스트화했다.
`csat/bench/PROTOCOL.md` 13번의 순위 산정 문항 풀이다. **이 데이터로 풀이 모델을 돌린 적은 없다.**

- `dataset.json`: 객관식 **884문항**, status `complete`, 대기 페이지 없음. 스키마는 `all_subjects/dataset.json`과 같고 `exam_id`·`exam_name`만 추가했다.
- `gold.json`: 정답·배점. 정답표 PDF에서만 만들었고 전사·검수 요청에는 넣지 않았다.
- 884는 정답표에서 원문자 정답을 센 결과다. 2026 수능과 같은 숫자가 나왔을 뿐 코드에 고정하지 않았다.

## 구성

| 영역 | 문항 |
|---|---:|
| 농업 기초 기술 (`agriculture`) | 20 |
| 아랍어Ⅰ (`arabic-1`) | 30 |
| 생명과학Ⅰ (`biology-1`) | 20 |
| 생명과학Ⅱ (`biology-2`) | 20 |
| 화학Ⅰ (`chemistry-1`) | 20 |
| 화학Ⅱ (`chemistry-2`) | 20 |
| 중국어Ⅰ (`chinese-1`) | 30 |
| 상업 경제 (`commerce-economics`) | 20 |
| 지구과학Ⅰ (`earth-science-1`) | 20 |
| 지구과학Ⅱ (`earth-science-2`) | 20 |
| 동아시아사 (`east-asia-history`) | 20 |
| 경제 (`economics`) | 20 |
| 영어 (`english`) | 45 |
| 윤리와 사상 (`ethics-thought`) | 20 |
| 수산·해운 산업 기초 (`fishery-maritime`) | 20 |
| 프랑스어Ⅰ (`french-1`) | 30 |
| 독일어Ⅰ (`german-1`) | 30 |
| 한문Ⅰ (`hanja-1`) | 30 |
| 인간 발달 (`human-development`) | 20 |
| 공업 일반 (`industrial-general`) | 20 |
| 일본어Ⅰ (`japanese-1`) | 30 |
| 국어 공통 (`korean-common`) | 34 |
| 한국지리 (`korean-geography`) | 20 |
| 한국사 (`korean-history`) | 20 |
| 국어 언어와 매체 (`korean-language`) | 11 |
| 국어 화법과 작문 (`korean-speech`) | 11 |
| 생활과 윤리 (`life-ethics`) | 20 |
| 수학 미적분 (`math-calculus`) | 6 |
| 수학 공통 (`math-common`) | 15 |
| 수학 기하 (`math-geometry`) | 6 |
| 수학 확률과 통계 (`math-probability`) | 6 |
| 물리학Ⅰ (`physics-1`) | 20 |
| 물리학Ⅱ (`physics-2`) | 20 |
| 정치와 법 (`politics-law`) | 20 |
| 러시아어Ⅰ (`russian-1`) | 30 |
| 사회·문화 (`social-culture`) | 20 |
| 스페인어Ⅰ (`spanish-1`) | 30 |
| 성공적인 직업생활 (`successful-career`) | 20 |
| 베트남어Ⅰ (`vietnamese-1`) | 30 |
| 세계지리 (`world-geography`) | 20 |
| 세계사 (`world-history`) | 20 |

정답표 합계와 과목별로 모두 일치한다(`gold.json` 884 = `dataset.json` 884).

**제외**: 수학 단답형 13문항(공통 16~22번, 확률과 통계·미적분·기하 각각 29~30번). 공통 문항은 한 번만 넣었다.
**포함**: 영어 듣기 1~17번은 평가원 공식 대본으로, 독해 18~45번은 이번 시험지로 새로 전사했다(재사용 없음).

## 결정 사항

- **문제지 형태**: 평가원 게시판에 영역별 `문제지.pdf`가 하나씩만 있다. 홀수형·짝수형 파일이 없고, PDF 첫 쪽이나 정답표에도 형 표시가 없다. 그래서 그 한 가지 형태를 썼다. 2026 수능 파일과 달리 홀수형으로 확인된 것은 아니다.
- **듣기**: 학시의 `english-listening`은 mp3 zip(음원)뿐이다. 대본은 평가원 게시판에 올라온 공식 `영어영역듣기평가대본.pdf`를 썼다. 음원은 해시만 기록하고 저장하지 않았다.
- **영역 경계**: 국어와 수학 선택과목 경계는 각 쪽 머리글에서 읽었다. 국어는 공통 1~12쪽, 화작 13~16쪽, 언매 17~20쪽이다. 수학은 공통 1~8쪽, 확통 9~12쪽, 미적 13~16쪽, 기하 17~20쪽이다.
- **2026 전용 처리**: 농업 1쪽 실습 단계 번호는 이번 시험에서 다시 확인했다. 단계 1~4만 있어 문항 번호를 가로채지 않으므로 예외 처리가 필요 없었다. 아랍어는 양방향 제어문자를 지운 뒤 번호를 찾았다.
- **세트 머리말**: `[a～b]` 머리말이 앞쪽에 있는 문항은 그 쪽까지 문맥 이미지로 함께 보냈다. 영어 33~34번과 37번이 해당한다.

## 품질

- 175쪽 가운데 156쪽은 자동 검수만으로 `reviewed`가 됐다. Sol low가 전사하고 Terra low가 원본에 대조했으며, 최대 3회 수정했다.
- 19쪽은 원본 이미지를 확대해 직접 확인하고 고쳤다(`human_reviewed`, 106문항). 기록은 `human-review/<page>.json`에 있고, 적용된 내용은 각 전사 파일의 `human_review`에 들어 있다.
  - 대상 쪽: arabic-1-01, arabic-1-03, biology-1-03, earth-science-1-01, earth-science-1-02, earth-science-2-03, economics-01, german-1-02, industrial-general-02, korean-12, korean-geography-03, korean-geography-04, korean-history-03, korean-history-04, physics-1-01, physics-1-02, physics-2-04, vietnamese-1-01, world-history-01
- `arabic-1-01`은 자동 검수를 통과했지만 1번 밑줄 위치가 틀려 있었다(سُوقُ가 아닌 다른 낱말로 표시됨).
- 검수기 지적이 틀린 경우도 여러 번 있었다: 국어 32~34번 [A] 범위, 지구과학Ⅰ 8번 화살표, 한국지리 18번 범례 대응. 검수기 지적을 반영한 수정 패치가 새 오류를 만든 경우도 있었다: 생명과학Ⅰ 15번, 물리학Ⅰ 5번.
- 따라서 **자동 `reviewed` 쪽에도 그림 세부 오류가 남아 있을 수 있다.** 특히 여러 번 수정을 거친 그래프·지도 문항이 그렇다.
- 일부 그래프 설명에는 눈금 기준 근삿값이 들어 있다(예: 지구과학Ⅰ 3·8·9번). 2026년 세계지리 전사와 같은 방식이다.
- 우선 점검할 후보는 자동 `reviewed`이면서 수정을 2회 이상 거쳤고 그림 문항이 있는 61쪽이다: agriculture-02, agriculture-03, agriculture-04, arabic-1-02, biology-1-01, biology-1-02, biology-2-01, biology-2-03, chemistry-1-04, chemistry-2-04, chinese-1-01, chinese-1-03, commerce-economics-01, earth-science-1-03, earth-science-2-01, earth-science-2-02, earth-science-2-04, east-asia-history-01, east-asia-history-03, east-asia-history-04, economics-02, economics-03, economics-04, fishery-maritime-04, french-1-02, french-1-03, german-1-03, hanja-1-02, human-development-01, human-development-03, human-development-04, industrial-general-01, industrial-general-03, japanese-1-02, japanese-1-03, korean-13, korean-14, korean-16, korean-geography-01, korean-geography-02, life-ethics-03, math-14, physics-1-03, physics-1-04, physics-2-01, physics-2-02, physics-2-03, russian-1-04, social-culture-02, social-culture-04, spanish-1-01, successful-career-02, successful-career-03, vietnamese-1-02, vietnamese-1-04, world-geography-02, world-geography-03, world-geography-04, world-history-02, world-history-03, world-history-04
- 남은 경고(`warnings`)는 0건이다. 그림이 있는 문항은 444개다.

## 재현

```bash
.venv/bin/python csat/exams/exam_pipeline.py 2027-09 fetch        # 원문·대본 다운로드, source-manifest.json
.venv/bin/python csat/exams/exam_pipeline.py 2027-09 manifest     # gold.json, page-tasks.json (정답은 여기서만)
.venv/bin/python csat/exams/exam_pipeline.py 2027-09 transcribe --workers 6   # 127.0.0.1:11435 프록시 필요, 완료 쪽은 재사용
.venv/bin/python csat/exams/exam_pipeline.py 2027-09 human-review # human-review/*.json 적용
.venv/bin/python csat/exams/exam_pipeline.py 2027-09 build --require-complete
.venv/bin/pytest csat -q
```

- 설정은 `config.json`에 있고, 코드는 `csat/exams/exam_pipeline.py` 하나다.
- 프롬프트와 JSON 복구·검증 함수는 `all_subjects/transcribe.py`에서 그대로 가져온다. `all_subjects`의 코드와 산출물은 건드리지 않았다.
- 호출 기록은 `call-traces/`에 있다(Sol 303회, Terra 304회).

## 원문

- 목록: https://www.haksi.kr/exams/2027/09 (73개 파일 = 36과목 × 시험지·정답 + 듣기 음원)
- 학시 파일 API는 suneung.re.kr `fileDown.do`로 302 리다이렉트된다. 최종 URL은 `source-manifest.json`의 `resolved_url`과 `sources/*/*.source.txt`에 있다.
- 듣기 대본: https://www.suneung.re.kr/boardCnts/view.do?boardID=1500236&boardSeq=5096541&lev=0&m=0403&s=suneung
- 듣기 음원(zip): sha256 `15001cdbba093a35d8267cb99612d125f793220cfcfbfc35c4c75e760412e42b`

| 과목 | 종류 | 쪽 | sha256 (앞 16자, 전체는 source-manifest.json) |
|---|---|---:|---|
| agriculture | answer | 1 | `da4e57e11d52b8b7` |
| agriculture | exam | 4 | `086790e8f8b0d485` |
| arabic-1 | answer | 1 | `211317d09417c0f9` |
| arabic-1 | exam | 4 | `e0cf958ed38730fa` |
| biology-1 | answer | 1 | `d9990b3a4df372c4` |
| biology-1 | exam | 4 | `8bb5bbbe3768318d` |
| biology-2 | answer | 1 | `7d067515055d2155` |
| biology-2 | exam | 4 | `e79dc29374fb1ea4` |
| chemistry-1 | answer | 1 | `d2614882ed737e8c` |
| chemistry-1 | exam | 4 | `aa37bc86fd0cab67` |
| chemistry-2 | answer | 1 | `a4e40314c4433f57` |
| chemistry-2 | exam | 4 | `9a2c50d6c65618df` |
| chinese-1 | answer | 1 | `9e1f05a3c6125260` |
| chinese-1 | exam | 4 | `060590d57509dcf6` |
| commerce-economics | answer | 1 | `ccbcd549da27ec2e` |
| commerce-economics | exam | 4 | `9fc96702fb8af9e0` |
| earth-science-1 | answer | 1 | `0f2ac0c726e922bf` |
| earth-science-1 | exam | 4 | `6bf30b30594d2937` |
| earth-science-2 | answer | 1 | `172b9390af113ba3` |
| earth-science-2 | exam | 4 | `96a240426403a191` |
| east-asia-history | answer | 1 | `365330321010e650` |
| east-asia-history | exam | 4 | `ada8bfda1c885816` |
| economics | answer | 1 | `64c7bf7206961210` |
| economics | exam | 4 | `fbc57ea7a6c88d22` |
| english | answer | 1 | `c49d980f3ff9db1b` |
| english | exam | 8 | `745d64d94e071973` |
| english-listening-script | exam | 17 | `078aeb4d4496f44b` |
| ethics-thought | answer | 1 | `8d618c1fd0587cde` |
| ethics-thought | exam | 4 | `b75fe957f3c0ffe5` |
| fishery-maritime | answer | 1 | `d58ddef65bf61347` |
| fishery-maritime | exam | 4 | `3db246add241bf95` |
| french-1 | answer | 1 | `fbb623de0d5c32c8` |
| french-1 | exam | 4 | `0d09306d49ac7e8d` |
| german-1 | answer | 1 | `1f0ca43bbda32a38` |
| german-1 | exam | 4 | `e227d868294e2f21` |
| hanja-1 | answer | 1 | `3f8978f3842a5cea` |
| hanja-1 | exam | 4 | `a9554768c6267591` |
| human-development | answer | 1 | `4319381466d4d66d` |
| human-development | exam | 4 | `5adcd3f7951dfdc2` |
| industrial-general | answer | 1 | `91dee351c2e784bd` |
| industrial-general | exam | 4 | `cc89b220508d088a` |
| japanese-1 | answer | 1 | `c99dcb47d9dc8204` |
| japanese-1 | exam | 4 | `1b096a4c15723237` |
| korean | answer | 1 | `94c8a8b5871c6723` |
| korean | exam | 20 | `28432c2ccfc85f22` |
| korean-geography | answer | 1 | `bbc15d88a34058c9` |
| korean-geography | exam | 4 | `45e64bb24310b43a` |
| korean-history | answer | 1 | `7bfde4750bfc82c2` |
| korean-history | exam | 4 | `63139e9cd044661d` |
| life-ethics | answer | 1 | `10519b4282139e0d` |
| life-ethics | exam | 4 | `9a853c920d4e3152` |
| math | answer | 1 | `3eced4925977b77c` |
| math | exam | 20 | `4ecfeb0cad6e5239` |
| physics-1 | answer | 1 | `c8849339779dba6c` |
| physics-1 | exam | 4 | `aeda97f215c39214` |
| physics-2 | answer | 1 | `8e7d8ad277233b21` |
| physics-2 | exam | 4 | `14ae38fa97c34ec5` |
| politics-law | answer | 1 | `b4d1892af4c3cde4` |
| politics-law | exam | 4 | `82947bd1ecd50124` |
| russian-1 | answer | 1 | `89ba5f2a654eb8a9` |
| russian-1 | exam | 4 | `7ae6f3492ca8423a` |
| social-culture | answer | 1 | `7f576eab31c26c7c` |
| social-culture | exam | 4 | `d945df6dae123d0b` |
| spanish-1 | answer | 1 | `2b8e455f94757386` |
| spanish-1 | exam | 4 | `94c57ba1f9469d4a` |
| successful-career | answer | 1 | `a5e13ed423a4d895` |
| successful-career | exam | 4 | `31fbab84a855537f` |
| vietnamese-1 | answer | 1 | `576e0d0557d47f52` |
| vietnamese-1 | exam | 4 | `ccac81cc22239901` |
| world-geography | answer | 1 | `e05d2f49ffe2a85b` |
| world-geography | exam | 4 | `f3e845ef8f4e5dd0` |
| world-history | answer | 1 | `2d34bc6dec66f835` |
| world-history | exam | 4 | `f4f569891e02f497` |
