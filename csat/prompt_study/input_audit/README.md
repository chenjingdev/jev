# Jev 오답의 실제 입력 설명 확인

2026학년도 프롬프트 비교에서 선택한 direct_ko의 오답을 우선 확인했다. 요청 로그의 원문을 읽었으며 이번 확인을 위해 문제 설명을 새로 작성해 당시 입력인 것처럼 제시하지 않았다.

**원본 그림과 다른 설명 3건을 확인했다.** 자동 전사·검수를 통과한 기록에도 오류가 남았다. 이 문항들을 모델 추론 실패로만 분류할 수 없다. 기존 점수는 손상된 입력을 포함한 실행 기록이며, 충실한 수능 입력에 대한 성능이나 프롬프트 개선 한계로 일반화하면 안 된다.

## 실제 전달 구조

- `state.question`: 질문 본문.
- `state.passage`: 지문·보기·표.
- `state.visual_description`: 그림을 말로 옮긴 설명.
- `questions.answer.instructions`: 기존 문구 또는 개선 후보 문구.
- `questions.answer.criteria`: A~E 선택지.

선택된 후보는 실제 질문을 instructions에 다시 넣고 아래 문장을 붙였다. 별도의 풀이 해설은 넣지 않았다.

> 제시된 지문·자료와 필요한 교과 지식을 바탕으로 이 질문의 정답인 선택지 하나를 고르세요.

## 2026학년도 오답 중 원문 불일치가 확인된 사례

### 물리학Ⅰ 10번 — 정답 5, Jev 1

당시 설명에서 그대로 발췌:

> A와 B 위에는 각각 오른쪽 방향 화살표가 있고 각 화살표 위에 \(p\)가 표시되어 있다. C 위에는 왼쪽 방향 화살표가 있고 화살표 위에 \(p\)가 표시되어 있다.

**원문 대조:** 원문은 세 물체 위에 p만 표시한다. 물체의 운동 방향 화살표는 없고, 오른쪽 화살표는 x축이다. 입력 설명이 존재하지 않는 운동 방향을 추가했다.

[실제 요청·응답 전체](/Users/chenjing/dev/jev/csat/prompt_study/development/direct_ko/physics-1-10.json) · [기존 프롬프트 요청](/Users/chenjing/dev/jev/csat/prompt_study/development/baseline/physics-1-10.json) · [원본 그림 확대](/Users/chenjing/dev/jev/csat/prompt_study/input_audit/2026-physics-1-10-diagram.png)

### 화학Ⅰ 3번 — 정답 3, Jev 1

당시 설명에서 그대로 발췌:

> 각 원자에는 중심과 두 전자 껍질이 그려져 있다.

**원문 대조:** 원문의 Y 원자에는 전자껍질 세 개가 있다. 설명에서 Y의 가운데 껍질과 그 전자 8개를 누락했다. 주기 판정에 영향을 주는 정보다.

[실제 요청·응답 전체](/Users/chenjing/dev/jev/csat/prompt_study/development/direct_ko/chemistry-1-3.json) · [기존 프롬프트 요청](/Users/chenjing/dev/jev/csat/prompt_study/development/baseline/chemistry-1-3.json) · [원본 그림 확대](/Users/chenjing/dev/jev/csat/prompt_study/input_audit/2026-chemistry-1-3-diagram.png)

### 한국지리 1번 — 정답 4, Jev 5

당시 설명에서 그대로 발췌:

> B는 제주도 남동쪽 해상에서 점선으로 둘러싸인 구역 밖에 있다.

**원문 대조:** 원문의 B는 제주도 주변 점선 영해선 안쪽에 있다. 설명의 안팎 관계가 반대다.

[실제 요청·응답 전체](/Users/chenjing/dev/jev/csat/prompt_study/development/direct_ko/korean-geography-1.json) · [기존 프롬프트 요청](/Users/chenjing/dev/jev/csat/prompt_study/development/baseline/korean-geography-1.json) · [원본 그림 확대](/Users/chenjing/dev/jev/csat/prompt_study/input_audit/2026-korean-geography-1-map.png)

## 원자료 접근

[전체 오답의 요청 로그 목록](/Users/chenjing/dev/jev/csat/prompt_study/input_audit/INDEX.md)에서 질문·보기·그림 설명·지시문·확률을 직접 확인할 수 있다. 2026년은 네 프롬프트 중 하나라도 틀린 문항, 2025년은 두 프롬프트 중 하나라도 틀린 문항의 합집합이다. 과목/문항이 같은 기록은 한 줄로 묶었다.

이번 대조는 일부 문항을 확인한 것이며 전수 검수가 아니다. 세 오류의 전체 점수 영향은 재실험하지 않아 아직 알 수 없다. 당시 입력·응답·점수 파일을 수정하지 않았다.
