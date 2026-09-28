# 시험 원자료 출처

벤치마크에 쓴 시험지·정답 PDF와 페이지 이미지는 저장소에 넣지 않았다(`.gitignore`). 아래 링크에서 받을 수 있고,
각 폴더의 파이프라인(`fetch` 단계)이 같은 링크에서 다시 받아 페이지 이미지를 만든다.
파일별 sha256은 표에 적은 매니페스트에 있어, 다시 받은 파일이 같은 것인지 확인할 수 있다.
문제의 저작권은 한국교육과정평가원에 있다.

## 2027학년도 대학수학능력시험 9월 모의평가 (2026-09-03 시행)

순위표(`csat/bench`)의 기준 시험이다.

- 목록 페이지: https://www.haksi.kr/exams/2027/09
- 영어 듣기 대본: https://www.suneung.re.kr/boardCnts/view.do?boardID=1500236&boardSeq=5096541&lev=0&m=0403&s=suneung
- 매니페스트: `csat/exams/2027-09/source-manifest.json`
- 받기: `.venv/bin/python csat/exams/exam_pipeline.py 2027-09 fetch`

| 과목 | 문제지 | 정답 |
|---|---|---|
| english-listening-script | [PDF](https://www.suneung.re.kr/boardCnts/fileDown.do?fileSeq=eca5a6a29a36b847e04fe637b7a7ab08) | – |
| 경제 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-economics-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-economics-answer) |
| 공업 일반 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-industrial-general-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-industrial-general-answer) |
| 국어 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-korean-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-korean-answer) |
| 농업 기초 기술 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-agriculture-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-agriculture-answer) |
| 독일어Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-german-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-german-1-answer) |
| 동아시아사 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-east-asia-history-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-east-asia-history-answer) |
| 러시아어Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-russian-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-russian-1-answer) |
| 물리학Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-physics-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-physics-1-answer) |
| 물리학Ⅱ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-physics-2-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-physics-2-answer) |
| 베트남어Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-vietnamese-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-vietnamese-1-answer) |
| 사회·문화 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-social-culture-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-social-culture-answer) |
| 상업 경제 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-commerce-economics-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-commerce-economics-answer) |
| 생명과학Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-biology-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-biology-1-answer) |
| 생명과학Ⅱ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-biology-2-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-biology-2-answer) |
| 생활과 윤리 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-life-ethics-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-life-ethics-answer) |
| 성공적인 직업생활 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-successful-career-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-successful-career-answer) |
| 세계사 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-world-history-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-world-history-answer) |
| 세계지리 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-world-geography-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-world-geography-answer) |
| 수산·해운 산업 기초 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-fishery-maritime-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-fishery-maritime-answer) |
| 수학 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-math-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-math-answer) |
| 스페인어Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-spanish-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-spanish-1-answer) |
| 아랍어Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-arabic-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-arabic-1-answer) |
| 영어 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-english-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-english-answer) |
| 윤리와 사상 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-ethics-thought-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-ethics-thought-answer) |
| 인간 발달 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-human-development-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-human-development-answer) |
| 일본어Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-japanese-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-japanese-1-answer) |
| 정치와 법 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-politics-law-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-politics-law-answer) |
| 중국어Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-chinese-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-chinese-1-answer) |
| 지구과학Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-earth-science-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-earth-science-1-answer) |
| 지구과학Ⅱ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-earth-science-2-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-earth-science-2-answer) |
| 프랑스어Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-french-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-french-1-answer) |
| 한국사 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-korean-history-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-korean-history-answer) |
| 한국지리 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-korean-geography-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-korean-geography-answer) |
| 한문Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-hanja-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-hanja-1-answer) |
| 화학Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-chemistry-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-chemistry-1-answer) |
| 화학Ⅱ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-chemistry-2-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2027-09-g3-chemistry-2-answer) |

## 2026학년도 대학수학능력시험 (2025-11 시행)

보조 순위와 처음 진단(`csat/all_subjects`, `csat/decompose`, `csat/format_combo`)에 썼다. 두 형이 있는 과목은 홀수형.

- 목록 페이지: https://www.haksi.kr/exams/2026/11
- 영어 듣기 대본: https://tutoria.tistory.com/1466
- 매니페스트: `csat/all_subjects/source-manifest.json`
- 받기: `.venv/bin/python csat/all_subjects/fetch_sources.py`

| 과목 | 문제지 | 정답 |
|---|---|---|
| 경제 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-economics-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-economics-answer) |
| 공업 일반 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-industrial-general-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-industrial-general-answer) |
| 국어 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-korean-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-korean-answer) |
| 농업 기초 기술 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-agriculture-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-agriculture-answer) |
| 독일어Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-german-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-german-1-answer) |
| 동아시아사 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-east-asia-history-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-east-asia-history-answer) |
| 러시아어Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-russian-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-russian-1-answer) |
| 물리학Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-physics-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-physics-1-answer) |
| 물리학Ⅱ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-physics-2-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-physics-2-answer) |
| 베트남어Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-vietnamese-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-vietnamese-1-answer) |
| 사회·문화 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-social-culture-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-social-culture-answer) |
| 상업 경제 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-commerce-economics-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-commerce-economics-answer) |
| 생명과학Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-biology-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-biology-1-answer) |
| 생명과학Ⅱ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-biology-2-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-biology-2-answer) |
| 생활과 윤리 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-life-ethics-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-life-ethics-answer) |
| 성공적인 직업생활 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-successful-career-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-successful-career-answer) |
| 세계사 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-world-history-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-world-history-answer) |
| 세계지리 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-world-geography-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-world-geography-answer) |
| 수산·해운 산업 기초 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-fishery-maritime-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-fishery-maritime-answer) |
| 수학 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-math-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-math-answer) |
| 스페인어Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-spanish-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-spanish-1-answer) |
| 아랍어Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-arabic-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-arabic-1-answer) |
| 영어 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-english-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-english-answer) |
| 윤리와 사상 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-ethics-thought-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-ethics-thought-answer) |
| 인간 발달 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-human-development-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-human-development-answer) |
| 일본어Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-japanese-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-japanese-1-answer) |
| 정치와 법 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-politics-law-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-politics-law-answer) |
| 중국어Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-chinese-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-chinese-1-answer) |
| 지구과학Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-earth-science-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-earth-science-1-answer) |
| 지구과학Ⅱ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-earth-science-2-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-earth-science-2-answer) |
| 프랑스어Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-french-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-french-1-answer) |
| 한국사 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-korean-history-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-korean-history-answer) |
| 한국지리 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-korean-geography-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-korean-geography-answer) |
| 한문Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-hanja-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-hanja-1-answer) |
| 화학Ⅰ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-chemistry-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-chemistry-1-answer) |
| 화학Ⅱ | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-chemistry-2-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2026-11-g3-chemistry-2-answer) |

## 2025학년도 대학수학능력시험 일부 과목 (2024-11 시행)

형식 비교의 검증용(`csat/prompt_study/validation_2025`, `csat/format_combo`)으로 썼다.

- 목록 페이지: https://www.haksi.kr/exams/2025/11
- 매니페스트: `csat/prompt_study/validation_2025/sources.json`

| 과목 | 문제지 | 정답 |
|---|---|---|
| chemistry-1 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2025-11-g3-chemistry-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2025-11-g3-chemistry-1-answer) |
| english | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2025-11-g3-english-odd-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2025-11-g3-english-odd-answer) |
| korean-history | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2025-11-g3-korean-history-odd-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2025-11-g3-korean-history-odd-answer) |
| life-ethics | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2025-11-g3-life-ethics-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2025-11-g3-life-ethics-answer) |
| physics-1 | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2025-11-g3-physics-1-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2025-11-g3-physics-1-answer) |
| politics-law | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2025-11-g3-politics-law-exam) | [PDF](https://www.haksi.kr/api/mock-exams/file?id=2025-11-g3-politics-law-answer) |

