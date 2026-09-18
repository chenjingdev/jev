# Jev Neurons — 구현 명세 (v1)

대상: `/Users/chenjing/dev/jev/tetris`. 세 설계안(Jev Cortex, Chorus, Sense→Hands→Verdict)과 두 심사평을 합성한 단일 명세다. 승자인 **Jev Cortex**(감각 → 연합 → 운동 → 억제)를 골격으로 하고, 심사가 권한 접목을 붙였으며, 연극(theater)으로 지목된 질문은 삭제하거나 실제 판단으로 재구성했다. 결정 근거는 부록 A(연극 원장)에 한 줄씩 남긴다.

이 문서가 두 작업 패키지(서버 / 프런트엔드)가 **서로 대화하지 않고** 코딩하는 계약이다. 5절의 JSON 필드명·타입과 부록 B의 상수표는 동결(frozen)이며, 바꾸려면 이 문서를 먼저 고친다.

---

## 1. 한 문단 요약

조각이 나올 때마다 엔진이 먼저 본다(도달 가능한 착지 전부, 높이·구멍·굴곡·우물·T슬롯 같은 지각). 그 지각이 다섯 개의 **의도 뉴런**(생존·정리·빌드·현금·스핀, 각각 독립된 noul)과 **위험 선호**(score), **계획 유지**(stay noul)에 동시에 닿고, 0.5를 넘긴 뉴런만 발화한다(요청 1). 발화한 뉴런마다 자기 가치관과 위험 선호가 지시문에 박힌 **운동 뉴런**(후보 전체에 대한 Choice)이 자리를 제안하고, 항상 켜져 있는 회색 **습관 뉴런**(측정된 variant C 지시문 그대로)이 "평범한 강한 플레이어"의 자리를 함께 제안한다(요청 2). 서로 다른 제안들이 보드 위에 각 뉴런의 색으로 그려진 뒤, **중재 뉴런**이 보드도 후보 목록도 지표도 보지 못한 채 제안들의 결과 서술과 최근 흐름만으로 어느 본능을 따를지 고르고, 같은 요청 안에서 **코치 뉴런**이 제안마다 거부권을 심사하며, **유지 뉴런**이 다음 조각으로 넘길 계획 강도를 정한다(요청 3). 최종 분포 = 중재 확률 × (1 − 거부 확률)이고, 이것이 기존 고스트 히트맵의 % 라벨이 된다. 화면에서 보이는 것: 보드 위에 서로 다른 색의 반투명 조각들이 각자의 %와 색 알약(pill)을 달고 떠 있고, 그중 하나에는 빨간 VETO 줄이 그어지고, 하나는 흰 테두리로 선택되며, 오른쪽 패널의 다섯 원 중 두세 개가 빛나고 그 원에서 보드의 고스트로 시냅스 선이 이어진다. 연극이 아닌 이유: (1) 요청 1의 발화가 요청 2에서 **어느 질문이 존재하는지**(gating)와 **지시문 텍스트**({activation}, {appetite})를 바꾸고, 요청 3의 지시문에 요청 1의 발화가 **문장으로**({DIRECTIVE}) 들어간다. (2) 중재는 발화 가중치를 보지 못하므로 argmax(가중치)를 뒤집을 수 있고, 뒤집은 횟수가 화면에 찍힌다. (3) 거부는 고스트의 확률을 0으로 만들 수 있는 유일한 경로다. (4) 습관 뉴런의 argmax와 최종 선택이 다른 조각 수("뉴런이 바꾼 조각")가 실시간으로 표시되어, 층들이 실제로 수를 바꾸는지 숫자로 증명한다. (5) 화면의 모든 밝기는 돌아온 확률이고, 돌아오지 않은 값을 흉내 내는 애니메이션은 "요청 진행 중"으로만 표시한다.

---

## 2. 뉴런 목록

### 2.0 팔레트와 라벨 (동결)

| id | 층 | 한국어 | 색 (hue) | 비고 |
|---|---|---|---|---|
| `survive` | 의도 | 생존 | `#ff4d6d` | 조각 팔레트의 Z 빨강(`#f87171`)보다 뜨거운 장미색 |
| `clean` | 의도 | 정리 | `#2ee6d6` | I 시안(`#22d3ee`)과 구분되는 민트 |
| `build` | 의도 | 빌드 | `#7c8cff` | J 파랑(`#60a5fa`)보다 보라 쪽 인디고 |
| `cash` | 의도 | 현금 | `#ffd166` | O 노랑(`#facc15`)보다 따뜻한 금색 |
| `spin` | 의도 | 스핀 | `#f472b6` | T 보라(`#c084fc`)와 구분되는 핑크 |
| `default` | 운동(긴장성) | 습관 | `#9aa3b8` | 의도가 아니다. 항상 켜진 회색 뉴런 |
| — | 억제 | 거부 | `var(--warn)` `#f87171` | 빨간 링·빗금·VETO 알약 |
| — | 엔진 규칙 | 강제 | `#fb923c` 주황 | 뇌간 강제 발화(엔진 규칙) 표시 전용 |

조각 색과 겹칠 위험은 **고스트가 항상 2px 흰 외곽선 + 알약을 달고, 피질 단계 동안 쌓인 스택을 0.7 알파로 어둡게** 그려서 없앤다(6절).

`INTENTS = ["survive","clean","build","cash","spin"]` 순서는 동률 처리와 정렬의 기준이다. `flatten`(평탄)은 삭제했다(부록 A-5).

### 2.1 요청 1 — 감각/연합층 (`/api/sense`)

모든 요청 1 지시문 앞에 서버가 다음 `SCENE` 문장을 그대로 붙인다(뉴런마다 독립 질문이므로 반복한다).

```
SCENE = "A game of Tetris is in progress. `board` shows the stack, rows top to bottom, '.' for empty and letters for locked pieces. `surface` lists the ten column heights from left to right. `facts` holds what the engine measured: the peak height, holes (empty cells with something above them), bumpiness, the deepest well and its depth, how many rows are nearly full, and how many pieces have passed since the last line clear. `now` is the piece about to be played, `next` the one after it, and `queue` the five pieces coming next in order. `recent` lists the last moves with the goal that led each one. `memory` holds the plan carried over from the previous piece. "
```

#### `survive` — 의도, noul, 생존 `#ff4d6d`

```
SCENE + "You are the SURVIVE neuron of this player. Should THIS piece serve survival above everything else: bring the stack down or away from the spawn columns, even if it clears nothing and leaves an ugly surface? Say yes only when continuing to stack or to set something up would be reckless here. A tall stack with a clean surface and friendly pieces in `queue` can still be safe; a lower stack can be in trouble when the pieces in `queue` do not fit it, or when the last moves in `recent` have been going badly."
true:  "Yes: reduce the danger first, whatever it costs."
false: "No: there is room to play for something better than safety."
```
쓰임: `a_survive = noul`. 발화 판정·가중치·모터 gating·지시문 치환(4절 gate). 원의 밝기.

#### `clean` — 의도, noul, 정리 `#2ee6d6`

```
SCENE + "You are the CLEAN neuron of this player. Should this piece be spent on repairing the stack: filling the pits and ledges that are already there, uncovering a buried hole, levelling a cliff between neighbouring columns, even if it clears nothing and sets up nothing? Weigh how much the damage in `board` will cost over the next pieces in `queue` against what those pieces could do if the surface were left alone. A hole the next clear will remove is not worth a piece; a hole under a tall column is."
true:  "Yes: pay this piece to fix the surface now."
false: "No: the damage can wait, or is not worth a piece."
```
쓰임: `a_clean`. 동일.

#### `build` — 의도, noul, 빌드 `#7c8cff`

```
SCENE + "You are the BUILD neuron of this player. Is this the moment to keep one deep well open at an edge and stack cleanly beside it, holding out for a four-line clear? Consider whether an I is in `queue` and how far away it is, how tall the columns beside the well already are, how clean the well is, and how much height the player can afford to carry while waiting."
true:  "Yes: keep the well open and invest in the stack beside it."
false: "No: waiting for the I is not worth it right now."
```
쓰임: `a_build`. 동일 (발화 → `motor_build` 존재 여부와 `{activation}` 치환, `directive` 문장의 한 구).

#### `cash` — 의도, noul, 현금 `#ffd166`

```
SCENE + "You are the CASH neuron of this player. Should this piece cash in: take a line clear that is on offer now, even a single, even at the price of a rougher surface, instead of keeping those rows for a bigger clear later? Weigh what `queue` brings, how long it has been since the last clear (`facts`), and whether waiting would pay more than it risks."
true:  "Yes: take the clear now."
false: "No: keep the rows for a bigger payout."
```
쓰임: `a_cash`. 동일.

#### `spin` — 의도, noul, 스핀 `#f472b6`

```
SCENE + "You are the SPIN neuron of this player. Is a T-spin worth playing for on this piece: taking one now when `tspin_available_now` is true, or shaping an overhang slot for a T that is coming in `queue`? Say yes only when the reward justifies the awkward surface and the roof hole a slot costs, and when a T will arrive before the slot is buried."
true:  "Yes: play for the T-spin."
false: "No: a spin is not worth it here."
```
쓰임: `a_spin`. 동일. `tspin_available_now`는 엔진이 주는 지각이고, "지금 그 값이 있을 때 그 대가를 치를지"가 판단이다.

#### `appetite` — 연합, score(0..3), 위험 선호 게이지 (색 없음, 게이지 초록→호박→빨강)

```
SCENE + "How much risk should this player accept on this piece? This is temperament, not arithmetic: a bold player accepts a temporary hole or a taller stack for a bigger payoff; a cautious one refuses it. Read the stack, what is still coming in `queue`, how the last moves in `recent` went, and how long it has been since a line clear."
0: "None. Play it dead safe: refuse any placement that adds a hole or height, whatever it promises."
1: "Low. Accept a small compromise, a bump or one row of height, only when it clearly pays back within a piece or two."
2: "Moderate. Accept a hole or a tall column when a real setup is within reach with the pieces still in `queue`."
3: "Bold. Go for the big clear or the spin even if a miss leaves the board ugly."
```
쓰임: `appetite = score`(기대값, 소수 1자리), `appetite_word = none|low|moderate|bold` (a<0.5 | <1.5 | <2.5 | else). 요청 2의 모든 운동 지시문과 요청 3의 중재·거부 지시문에 **텍스트로 치환**된다. 측정 게이트 (c)(d)를 통과하지 못하면 삭제한다(부록 A-3).

#### `stay` — 연합(재귀), noul, 계획 유지 링크 (색: 이전 조각의 `led_by` 색)

`memory.previous_intent`가 `null`이거나 `memory.hold === 0`이면(지난 판정이 "Drop") **서버가 질문을 생략**하고 응답의 `stay`는 `null`이다.

```
SCENE + "The previous piece was led by the `memory.previous_intent` goal, and the last verdict asked to hold that plan with strength `memory.hold` (0 drop, 1 keep). Looking at the stack, `now` and `queue`, is that plan still the right one to continue with this piece, or has something changed: a danger appeared, a clear opened up, the slot is gone, or the I has arrived?"
true:  "Yes: continue the plan so the previous pieces' work pays off."
false: "No: start fresh with this piece."
```
쓰임: `stay ≥ 0.5`이면 `a[previous_intent] = max(a[previous_intent], stay × memory.hold)`이고 그 뉴런은 발화 집합에 들어간다(4절). 이것이 요청 3의 `hold`와 함께 재귀 루프를 만든다.

### 2.2 요청 2 — 운동층 (`/api/motor`)

운동 질문은 `intent.fired`에 든 의도마다 하나(`motor_<intent>`) + 항상 `motor_default`. 각 질문은 후보 전체에 대한 Choice이며 criteria = `{candidateId: summary}` (모든 운동 뉴런이 **같은** criteria 맵을 받는다). 서버가 `{activation}`(해당 의도의 `intent.activations[i]`, 소수 2자리; 뇌간 강제 시 `"forced by height"`), `{appetite}`, `{appetite_word}`를 치환한다. 모든 운동 지시문 끝에 서버가 `MOTOR_PRE`를 붙인다.

```
MOTOR_PRE = " `candidates` describes every placement the piece `now` can reach: each entry's `summary` says where it lands and what the engine measured afterwards, and `board_after` shows the resulting stack. `board`, `surface` and `facts` describe the stack before the move; `queue` lists the next five pieces. Each option key below is a candidate id and its description is that candidate's summary."
```

#### `motor_survive` — 운동, choice, 생존색

```
"You are the SURVIVE neuron of this player. The appraisal in `intent` activated you at {activation} for this piece and set the risk appetite at {appetite} of 3 ({appetite_word}). Choose the placement a player whose one goal right now is getting the stack down and away from the top would make, staying inside that appetite. Judge what each placement does to the danger of topping out over the next few pieces, not just the tallest column: where the stack will sit under the spawn columns, whether the pieces in `queue` will still have somewhere to go, and whether a hole taken now is cheaper than the height it saves. With a bold appetite you may leave a hole to buy height; with none, accept only the safest placement that keeps the surface honest." + MOTOR_PRE
```

#### `motor_clean` — 운동, choice, 정리색

```
"You are the CLEAN neuron of this player. The appraisal in `intent` activated you at {activation} for this piece and set the risk appetite at {appetite} of 3 ({appetite_word}). Choose the placement a player whose one goal right now is repairing the surface would make, staying inside that appetite. Judge whether the placement mends what is already wrong: fills a pit or a ledge, brings a row closer to clearing, stops burying an old hole, and covers nothing that would become a new hole. A placement that looks tidy but delays uncovering an old hole is not clean. With a low appetite refuse any new hole; with a bolder one a hole may be taken if it uncovers a bigger mess sooner." + MOTOR_PRE
```

#### `motor_build` — 운동, choice, 빌드색

```
"You are the BUILD neuron of this player. The appraisal in `intent` activated you at {activation} for this piece and set the risk appetite at {appetite} of 3 ({appetite_word}). Choose the placement a player whose one goal right now is setting up a four-line clear would make, staying inside that appetite. Judge whether the placement keeps one deep well open at an edge and piles cleanly beside it so an I from `queue` will clear several lines at once. Filling the well betrays this goal; stacking tall beside it is the point. With a bold appetite stack higher and wait for the I; with a low one keep the pile modest and the well shallow." + MOTOR_PRE
```

#### `motor_cash` — 운동, choice, 현금색

```
"You are the CASH neuron of this player. The appraisal in `intent` activated you at {activation} for this piece and set the risk appetite at {appetite} of 3 ({appetite_word}). Choose the placement a player whose one goal right now is taking value off the table would make, staying inside that appetite. Judge which placement takes the most now: lines cleared by this piece, a T-spin if one is offered, and how quickly another clear follows given `queue`. A clear that leaves a hole is still cash; whether that price is acceptable is the appetite's call: with none, only clear cleanly; with bold, take the biggest clear on the table." + MOTOR_PRE
```

#### `motor_spin` — 운동, choice, 스핀색

```
"You are the SPIN neuron of this player. The appraisal in `intent` activated you at {activation} for this piece and set the risk appetite at {appetite} of 3 ({appetite_word}). Choose the placement a player whose one goal right now is a T-spin would make, staying inside that appetite. Judge whether the placement takes a T-spin now, or leaves or creates an overhang slot a T can twist into, with the rows beside the slot filled so the spin clears lines, and whether a T will arrive from `queue` before the slot is buried. A slot a spin cannot reach is worthless. With a bold appetite you may leave the slot's roof as a temporary hole; with a low one only shape a slot that costs nothing." + MOTOR_PRE
```

#### `motor_default` — 운동(긴장성), choice, 습관 회색 — 항상 전송

`intent`를 **읽지 않는다**(지시문에 언급 없음). 첫 문장은 `experiments/judge.mjs` variant C의 지시문과 글자 그대로 같다. 이것이 "단일 Choice Jev"의 기준선이며, 최종 선택과 이 뉴런의 argmax가 다른 조각 수가 "뉴런이 바꾼 조각" 카운터다.

```
"Choose the placement a strong Tetris player would make: clear lines, avoid creating holes, and keep the stack low and flat." + MOTOR_PRE
```

criteria 옵션 설명 예 (`candidateSummaryV2`, 4.1절):
```
c7: "T piece, rotation 1 (nub pointing right); lands at columns 6-7, rows 15-17; placed with a T-spin; clears 1 line; after: max height 6 (+1), holes 2 (+1), bumpiness 9, aggregate height 31; keeps the well at column 9 open (depth 4); leaves a T-spin slot: no; top of piece 12 rows below the ceiling"
```

쓰임: 각 뉴런 i의 `P_i` = probabilities, 제안 `π_i = argmax P_i`, 뉴런 확신 `m_i = P_i(π_i)`. 발화 뉴런 간 argmax 불일치가 보드 위의 "서로 다른 색 와이어" 순간이다.

### 2.3 요청 3 — 판정층 (`/api/arbitrate`)

이 요청의 state에는 **보드 ASCII, surface, facts, 후보 목록, 발화 가중치(activations)가 없다.** 중재자는 제안들의 결과 서술(정성적, 숫자 지표 없음), 발화된 의도 이름, 위험 선호, 최근 흐름, 기억만 본다. 서버가 `{DIRECTIVE}`, `{LEADING}`, `{appetite}`, `{appetite_word}`, `{id}`, `{BACKERS}`를 치환한다.

`DIRECTIVE` = **서버가** `intent.fired` 순서대로 다음 구를 `" and "`로 이어 만든다(`server/questions.js`의 `directiveOf(fired, forced)`; 클라이언트는 만들지 않는다): survive→`"bring the danger down first"` (`forced`이면 `"bring the danger down first (forced by height)"`), clean→`"repair the surface"`, build→`"keep the well open and stack cleanly beside it"`, cash→`"take the clear now"`, spin→`"play for the T-spin"`. 서버는 이 문장을 R3 state의 `intent.directive`에 넣고 응답의 `directive`로 에코한다.

#### `arbitrate` — 판정, choice(제안 id 중 하나), 색: 승자 backer의 색

```
"Several motor neurons of the same Tetris player each proposed a placement for the piece `now`; `proposals` lists them by candidate id, with the goal that backs each one and what the engine says the move does. The appraisal asked this piece to {DIRECTIVE}, with a {appetite_word} appetite for risk ({appetite} of 3). `queue` lists the next five pieces, `recent` the last moves with the goal that led each one, and `memory` the plan carried over from the previous piece. You cannot see the board; you see only what the neurons proposed. Pick the proposal to play. The goal that was asked for does not win by right: it loses when its proposal costs too much for this appetite, and another goal, or plain habit, wins when its proposal serves the asked-for goal nearly as well at a lower price, or keeps alive a plan that `recent` and `memory` show the player has been building. Choose as a player choosing between their own competing instincts."
```
옵션 설명(제안마다 하나):
- 뉴런 제안: `"{BACKERS} proposed this: {effects}"` — `{BACKERS}` = backedBy를 대문자로 `" and "`로 연결, `default`는 `HABIT`. 예: `"BUILD and HABIT proposed this: T piece, rotation 1 (nub pointing right); lands at columns 6-7, rows 15-17; clears no lines; keeps the well open; no new hole; peak higher; leaves a T-spin slot"`.
- ALT 제안(`alt: true`): `"Second thought of the {LEADING} neuron: {effects}"`.
- 설명에 가중치·확신·숫자 지표를 넣지 않는다.

쓰임: `A(π) = probabilities[π]`. 4절 combine.

#### `veto_{id}` — 억제, noul, 제안마다 하나 (`veto_c7`, `veto_c1`, …), 색: 빨강

```
"A coach is watching over the player's shoulder. The appraisal asked this piece to {DIRECTIVE}, with a {appetite_word} appetite for risk ({appetite} of 3). Consider `proposals.{id}`, one of the moves on the table for the piece `now`. Would the coach put a hand on the player's arm and stop this move? Stop it only for reasons a coach would state: it takes a risk the appetite does not cover, it throws away a setup that `recent` and `memory` show the player has been building, or it defeats the very goal that backs it. Do not stop a move merely for being imperfect, and do not stop it because another proposal looks better."
true:  "Stop it: the move overreaches for this appetite, wastes a plan the player has been building, or defeats its own goal."
false: "Let it through: the move is consistent with its goal and the appetite, even if it is not the best possible."
```
쓰임: `V(π) = noul`. `arbitrate`와 **같은 요청에서 병렬로** 평가되므로 코치는 중재 결과를 모른다. UI 문구는 "동시에 심사"로만 쓴다(부록 A-4). 최종 확률 `A·(1−V)`, `V ≥ HARD_VETO(0.65)`이면 0.

#### `hold` — 판정(재귀), score(0..2), 계획 유지, 색: 흰 자물쇠 글리프

선택된 제안을 알 수 없으므로(같은 요청) **계획 전체**에 대해 묻는다. 기억에 기록되는 `previous_intent = ledBy(chosen)`는 산술 결합이며 UI 라벨은 "계획 유지"다(특정 뉴런에 대한 약속으로 표기하지 않는다).

```
"Whichever proposal is played, should the next piece keep serving the same plan ({DIRECTIVE}) or start fresh? Judge from `proposals`, `queue`, `recent` and `memory` whether this piece's plan is a down-payment that only pays off if it is followed through, such as a well kept open or a slot being shaped, or whether it finishes the job."
0: "Drop: the job is done after this piece, or the plan is wrong."
1: "Lean: the plan probably still applies, but the next piece should re-judge it."
2: "Hold: the next piece should continue this plan; this piece only makes sense if it is followed through."
```
쓰임: `memory.hold = score / 2` (0..1), `memory.previous_intent = ledBy(chosen)`이 `INTENTS`에 있으면 그 이름, 아니면 `null`. 다음 조각의 `stay`가 읽는다. 타임라인 사각형에 자물쇠 글리프(`hold ≥ 0.5`).

### 2.4 엔진 규칙 (Jev 질문이 아님 — 화면에서도 엔진 규칙으로 그린다)

- **뇌간 강제(brainstem)**: `facts.maxHeight ≥ BRAINSTEM_HEIGHT(14)`이고 `survive`가 발화 집합에 없으면 강제로 넣는다(`forced = true`). 주황 링과 "강제" 라벨. `{activation}`은 `"forced by height"`로 치환.
- **지각(percepts)**: `facts`, `tspin_available_now`, `candidateSummaryV2`, `effects`는 모두 엔진 계산. 힌트가 아니라 망막이다(측정 사실 C).
- **반사(reflex)는 없다**: 두 심사 모두 "깨끗한 테트리스 후보가 79조각 시뮬레이션에서 0회"라 했다. 삭제(부록 A-7). 테트리스도 T스핀도 피질을 지난다.

---

## 3. 요청 순서

조각당 순차 요청 3회. 각 요청의 상태(state)는 Jev가 읽는 snake_case JSON이다. 클라이언트(app.js)가 지각과 융합을 모두 계산하고 서버는 얇다(검증 → state/questions 조립 → `systemOne` 1회 → 원답 반환).

### R0 — 엔진 (요청 없음, `public/neurons.js` + `engine.js` + `srs.js`)

`candidates = reachablePlacements(G.board, type)`; 비어 있으면 게임 오버. `candidates.length === 1`이면 Jev 없이 그 자리(모든 층 어둡게, phase '외길').
계산: `surface = computeMetrics(board).heights`, `facts`, `tspinAvailableNow`, 후보마다 `summary = candidateSummaryV2(...)`, `boardAfterAscii`, `effects(...)`. `queue = G.queue.slice(0,5)`(항상 ≥8 채워져 있음), `recent = G.log.slice(-6)`, `memory`.

### R1 — `/api/sense` (연합)

state:
```
{
  "board": "<ASCII 21 lines>",
  "surface": [h0..h9],
  "facts": {"max_height":9,"holes":2,"bumpiness":7,"well_column":9,"well_depth":4,"rows_nearly_full":1,"pieces_since_clear":3},
  "now":"T", "next":"I", "queue":["I","O","S","Z","L"],
  "tspin_available_now": false,
  "recent":[{"piece":"S","columns":[3,4,5],"lines":0,"tspin":null,"led_by":"build","vetoed":false}, …≤6],
  "game":{"pieces":21,"lines":6,"score":1300,"tspins":1},
  "memory":{"previous_intent":"build","hold":0.5}
}
```
questions: `survive, clean, build, cash, spin` (noul) · `appetite` (score) · `stay` (noul, `memory.previous_intent`가 null이거나 `memory.hold`가 0이면 생략) — 최대 7개, 병렬.
앞으로 넘기는 것: `intent = gate(sense, appetite, facts, memory)` (4.2절) → R2·R3 state와 지시문 치환.

### R2 — `/api/motor` (운동)

state:
```
{
  "intent":{"leading":"build","activations":{"survive":0.02,"clean":0.31,"build":0.92,"cash":0.61,"spin":0.00},
            "appetite":1.8,"appetite_word":"moderate","fired":["build","cash"],"forced":false,"stayed":true},
  "board":"<ASCII>", "surface":[…], "facts":{…}, "now":"T","next":"I","queue":[…], "tspin_available_now":false,
  "candidates":{"c0":{"summary":"…","board_after":"<ASCII>"}, …}
}
```
questions: `motor_<i>` for i in `intent.fired` (≤3) + `motor_default` — 2..4개 Choice, 같은 criteria.
앞으로 넘기는 것: `proposals = proposalsFrom(motor, intent, candidates)` (4.3절), `effects` 문자열 → R3.

### R3 — `/api/arbitrate` (판정)

state:
```
{
  "now":"T","next":"I","queue":[…],
  "intent":{"leading":"build","fired":["build","cash"],"forced":false,"appetite":1.8,"appetite_word":"moderate",
            "directive":"keep the well open and stack cleanly beside it and take the clear now"},   // directive는 서버가 fired·forced에서 만든다
  "recent":[…], "game":{…}, "memory":{…},
  "proposals":{"c7":{"backed_by":["build","default"],"alt":false,"effects":"…"},
               "c1":{"backed_by":["cash"],"alt":false,"effects":"…"}}
}
```
questions: `arbitrate` (choice over proposal ids) · `veto_<id>` (noul, 제안마다) · `hold` (score) — 4..6개, 병렬.
앞으로 넘기는 것: `combine(...)` → 최종 분포·선택·`ledBy` → `recent`와 `memory`(다음 조각의 R1).

### 지연과 비용 (README 측정치: 요청당 평균 300 ms(200–650), 현재 게임 요청당 입력 평균 5,900 토큰, 그중 criteria 1개 ≈ 후보 수 × 55 토큰; `candidateSummaryV2`는 후보당 ≈ +20 토큰)

| 요청 | 입력 토큰 (후보 25개, 발화 2 + 습관) | 최악 (후보 36개 T, 발화 3 + 습관) | 지연 중앙 |
|---|---|---|---|
| R1 | ≈ 1,300 (보드 250 + facts/queue/recent 250 + 지시문 7개 × ~110) | ≈ 1,400 | ~280 ms |
| R2 | ≈ 5,200 (state: 보드 + 후보 {summary, board_after}; V2 요약은 후보당 ≈ 75 토큰) + 3 × 1,900 (criteria) ≈ **10,900** | ≈ 7,300 + 4 × 2,700 ≈ **18,100** | ~320 ms |
| R3 | ≈ 900 (제안 ≤4 × ~80 + 지시문 4..6개) | ≈ 1,100 | ~270 ms |
| 합계 | ≈ **13,000 토큰 ≈ $0.00055** | ≈ **20,600 토큰 ≈ $0.00087** | **≈ 900 ms 중앙, p95 ≈ 1.2 s** |

출력 토큰은 질문당 ~5개 × ≤17 질문 ≈ 85 토큰, 무시 가능. `JEV_FANOUT=1`(부록 B)은 R2의 state(≈ 5.2k)를 질문마다 다시 보내므로 R2가 ≈ 4 × (5.2k + 1.9k) ≈ 28k 토큰, 조각당 ≈ 30k 토큰 ≈ $0.0013이 된다. 정직하게 계산하고 기본은 끈다.

프리페치(다음 조각의 R1을 현재 조각의 이동 애니메이션 중에 발사)는 `G.opts.prefetch`로 켤 수 있으나 기본 off: 쇼의 동기화가 깨진다.

---

## 4. 최종 착지 규칙

모두 `public/neurons.js`의 순수 함수. 상수는 부록 B.

### 4.1 지각 (엔진)

- `facts(board)`: `computeMetrics` + `wellColumn = wellDepth ≥ 2 ? wellCol : null`, `rowsNearlyFull = 채워진 칸 ≥ NEARLY_FULL(8)인 행 수`, `piecesSinceClear`(G에서 유지).
- `depthAt(heights, c) = min(left, right) − heights[c]` (가장자리의 바깥은 Infinity).
- `wellPhrase(before, cand)`: `before.wellDepth < 2`이면 `""`; `depthAt(after.heights, W) ≥ 2`이면 `"; keeps the well at column W open (depth d)"`; 아니면 `"; fills the well at column W"`.
- `hasTSlot(boardAfter) = reachablePlacements(boardAfter,"T").some(c => c.tspin === "full" && c.linesCleared ≥ 1)`.
- `candidateSummaryV2(type, cand, boardBefore)` = 기존 `placementSummary` 문자열 + `wellPhrase` + `"; leaves a T-spin slot: yes|no"` + `"; top of piece R rows below the ceiling"` (R = min row of cells). 70 토큰 이하.
- `effects(type, cand, boardBefore)` (R3 전용, 숫자 지표 없음) = `"{type} piece, rotation {rot} ({label}); lands at columns a-b, rows c-d; [placed with a T-spin; ]clears N line(s)|clears no lines; keeps the well open|fills the well|no well; adds a hole|adds N holes|uncovers a hole|no new hole; peak higher|peak unchanged|peak lower; leaves a T-spin slot|no T-spin slot"`.

### 4.2 gate — R1 답 → intent

```
a[i] = sense[i]                                  // i ∈ INTENTS, noul p
stayed = false
if memory.previous_intent = k ≠ null and memory.hold > 0 and sense.stay ≠ null and sense.stay ≥ FIRE_P:
    a[k] = max(a[k], sense.stay × memory.hold); stayed = true
leading = argmax a   (동률: memory.previous_intent가 동률 안에 있으면 그것, 아니면 INTENTS 순서)
fired = { i : a[i] ≥ FIRE_P } ∪ { leading } ∪ ( stayed ? {k} : ∅ )
forced = facts.max_height ≥ BRAINSTEM_HEIGHT and survive ∉ fired
if forced: fired ∪= { survive }
fired를 a 내림차순(동률 INTENTS 순)으로 정렬; |fired| > MAX_FIRED(3)인 동안 leading도 아니고 (forced인) survive도 아닌 가장 약한 원소를 제거
appetite = round(appetite.value, 1); appetite_word = none|low|moderate|bold  (a < 0.5 | < 1.5 | < 2.5 | else)
intent = { leading, activations: a (소수 2자리), appetite, appetite_word, fired, forced, stayed }
// directive 문장은 클라이언트가 만들지 않는다: 서버가 fired·forced에서 도출해 R3 state에 넣고 응답으로 에코한다 (2.3절)
```
R2 요청에는 `intent` 전체를, R3 요청에는 `activations`·`stayed`를 **뺀** 부분집합을 보낸다(5절).

### 4.3 proposalsFrom — R2 답 → 제안 집합 Π

```
for i in fired ∪ {default}: P_i = motor[i].probabilities (알려진 후보 id만; 없는 id는 0); π_i = argmax P_i (동률 → 낮은 인덱스)
Π = unique({ π_i }) ; backers(π) = [ i ∈ fired (a 내림차순) with π_i = π ] ++ (π_default = π ? ["default"] : [])
if |Π| < 2: ALT = argmax P_leading over ids \ {π_leading}; Π ∪= {ALT}; backers(ALT) = [leading]; alt = true   // ALT의 backer는 leading (심사 수정)
w_i = a[i] (i ∈ fired), w_default = W_DEFAULT(0.5)
E(π) = Σ_{i ∈ backers(π)} w_i · P_i(π)      // ALT: w_leading · P_leading(ALT). 표시·동률용, 최종 확률에는 쓰지 않음
m_i = P_i(π_i)                               // 뉴런 확신
disagreement = |unique({π_i : i ∈ fired})| > 1
fork = (a의 상위 두 값의 차 < FORK_GAP(0.15)) and (그 두 뉴런의 π가 다름)
motorField_i = P_i의 상위 2·3위 (Π에 없는 것) — 흐린 고스트 전용
```
|Π| ∈ [2, 4] (fired ≤ 3 + default; ALT는 |Π| < 2일 때만).

### 4.4 combine — R3 답 → 최종 분포와 선택

```
A(π) = arbitrate.probabilities[π] ?? 0 ; V(π) = veto[π] ?? 0
raw(π) = A(π) · (1 − V(π))
hardVetoed = { π : V(π) ≥ HARD_VETO(0.65) }
final(π) = π ∈ hardVetoed ? 0 : raw(π)
if Σ final = 0: final = raw, allVetoed = true          // 코치가 전부 막으면 한숨 쉬고 raw로
if Σ final = 0 still: final = 균등                        // A가 전부 0인 방어
final을 Σ = 1로 정규화; Π 밖의 후보는 0
chosen = argmax final (동률 → 큰 E → 낮은 maxHeight after → 낮은 후보 인덱스)
ledBy = backers(chosen) 중 fired에 속한 것 가운데 a가 가장 큰 것; 없으면 "default"; ALT면 leading
override = leading ∉ backers(chosen)                    // ALT의 backers = [leading]이므로 ALT 승리는 override가 아님
changed  = chosen ≠ π_default                            // "뉴런이 바꾼 조각"
vetoedTop = (argmax A) ∈ hardVetoed                       // "중재 1위 거부"
memoryNext = { previous_intent: ledBy ∈ INTENTS ? ledBy : null, hold: hold.value / 2 }
```

### 4.5 히트맵 (보드의 고스트) — 기존 % 라벨 규칙 유지

- 제안 π마다 고스트 1개: `p = final(π)`, `alpha = p ≥ GHOST_LABEL_MIN_P ? max(MIN_GHOST_ALPHA, MAX_GHOST_ALPHA · p / maxP) : MAX_GHOST_ALPHA · p / maxP`(현행 공식), 라벨 `round(100·p) + "%"`(현행 글꼴·검은 외곽선), 색 = `backers(π)[0]`의 hue(default 회색, ALT는 leading hue + 흰 점선 외곽), 알약 = backers 한국어 라벨을 `·`로 연결(예 `빌드·습관`), 동심 링 = backer마다 하나(안쪽 3/6/9 px, 각 backer hue).
- `π ∈ hardVetoed`: 알파 0.1, 바운딩 박스에 2px 빨간 링, 대각 빨간 빗금, 알약 `VETO`, 라벨 `0%`.
- `chosen`: 3px 흰 외곽선(느린 펄스), 알약 접미 ` · 선택`.
- 운동장(motor field): 발화 뉴런 i의 상위 2·3위(Π 밖)를 그 hue로 알파 0.22/0.12, 라벨 없음; R3 도착 시 0.06으로.
- 실패 경로(R3 실패): `chosen = argmax E`, `ledBy = "fallback"`, 고스트 라벨 대신 알약 `FALLBACK`, `final`은 E 정규화.

---

## 5. API 계약

서버(`server.js`)는 키를 쥔 얇은 게이트웨이다. 세 엔드포인트 모두: `POST`, JSON 본문 ≤ 4 MB, 검증 실패 → `400 {"error": string}`, TypeSafe 실패(SDK 재시도 1회 후) → `502 {"error":"TypeSafe request failed after one retry","detail":string,"status":number|undefined}`, 예외 → `500 {"error":"internal error"}`. 성공 응답은 항상 `latencyMs`(정수 ms), `usage {input_tokens, output_tokens}`, `model`(응답 모델명), `instructions {질문이름: 실제 전송된 지시문 전문}`을 포함한다. 응답의 확률은 SDK가 준 값 그대로(소수 2자리 반올림된 채) 넘긴다. `POST /api/decide`는 **변경 없이** 유지한다(뉴런 끄기 토글용).

검증 공통: `pieceType`, `nextType` ∈ `["I","O","T","S","Z","J","L"]`; `queue`는 같은 집합의 문자열 배열, 길이 1..5; `boardAscii`는 21줄 문자열; `surface`는 길이 10의 정수 배열; `facts`는 아래 7개 키가 모두 숫자(`wellColumn`만 `null` 허용); `recent`는 길이 ≤ 6의 배열, 각 원소 `{piece, columns:number[], lines:number, tspin:"full"|"mini"|null, ledBy:string|null, vetoed:boolean}`; `game`은 4개 숫자; `memory`는 `{previousIntent: INTENT|null, hold: 0..1}`. 알려진 의도명 상수 `KNOWN_INTENTS = ["survive","clean","build","cash","spin"]`는 서버와 `neurons.js`에 각각 복사해 두고 이 문서로 고정한다.

### 5.1 `POST /api/sense`

요청:
```json
{
  "boardAscii": "0123456789\n..........\n…",
  "surface": [0,0,3,4,4,5,5,6,7,2],
  "facts": {"maxHeight":9,"holes":2,"bumpiness":7,"wellColumn":9,"wellDepth":4,"rowsNearlyFull":1,"piecesSinceClear":3},
  "pieceType": "T", "nextType": "I", "queue": ["I","O","S","Z","L"],
  "tspinAvailableNow": false,
  "recent": [{"piece":"S","columns":[3,4,5],"lines":0,"tspin":null,"ledBy":"build","vetoed":false}],
  "game": {"pieces":21,"lines":6,"score":1300,"tspins":1},
  "memory": {"previousIntent":"build","hold":0.5}
}
```
서버 동작: state = 3절 R1의 snake_case 객체(키 이름 매핑: `boardAscii→board`, `pieceType→now`, `nextType→next`, `tspinAvailableNow→tspin_available_now`, `facts.maxHeight→max_height` 등 camel→snake, `recent[].ledBy→led_by`, `memory.previousIntent→previous_intent`). questions = 5 noul + `appetite` score + (`memory.previousIntent !== null && memory.hold > 0`일 때만) `stay` noul. `systemOne({state, model, questions})` 1회.

응답 200:
```json
{
  "sense": {"survive":0.02,"clean":0.31,"build":0.92,"cash":0.61,"spin":0.00,"stay":0.77},
  "appetite": {"value":1.8,"confidence":0.64,"probabilities":{"0":0.05,"1":0.25,"2":0.55,"3":0.15}},
  "instructions": {"survive":"…","clean":"…","build":"…","cash":"…","spin":"…","appetite":"…","stay":"…"},
  "latencyMs": 281, "usage": {"input_tokens":1290,"output_tokens":35}, "model": "jev-1.13.0"
}
```
`stay`는 질문을 생략했으면 `null`이고 `instructions.stay`도 없다.

### 5.2 `POST /api/motor`

요청:
```json
{
  "intent": {"leading":"build","activations":{"survive":0.02,"clean":0.31,"build":0.92,"cash":0.61,"spin":0.00},
             "appetite":1.8,"appetiteWord":"moderate","fired":["build","cash"],"forced":false,"stayed":true},
  "boardAscii":"…","surface":[…],"facts":{…},"pieceType":"T","nextType":"I","queue":[…],"tspinAvailableNow":false,
  "candidates": [{"id":"c0","summary":"T piece, rotation 0 …","boardAfterAscii":"0123456789\n…"}]
}
```
검증 추가: `intent.fired`는 `KNOWN_INTENTS`의 부분집합, 길이 1..3, 중복 없음; `intent.activations`는 5개 키 모두 0..1; `appetite` 0..3; `appetiteWord ∈ {none,low,moderate,bold}`; `candidates` 1..255, id 문자열 중복 없음, `summary`·`boardAfterAscii` 문자열.
서버 동작: state = 3절 R2(`intent`는 `appetiteWord→appetite_word`만 바꿔 그대로). criteria = `{id: summary}`. questions = `motor_<i>` (i ∈ fired, 텍스트에 `{activation}`=`activations[i].toFixed(2)` 또는 `forced && i==="survive"`이면 `"forced by height"`, `{appetite}`=`appetite.toFixed(1)`, `{appetite_word}` 치환) + `motor_default`. `JEV_FANOUT=1`이면 질문마다 `systemOne`을 같은 state로 `Promise.all`; usage 합산, `latencyMs`는 벽시계.

응답 200:
```json
{
  "motor": {
    "build":   {"choice":"c7","confidence":0.71,"probabilities":{"c0":0.00,"c1":0.12,"c7":0.71,"…":0}},
    "cash":    {"choice":"c1","confidence":0.55,"probabilities":{…}},
    "default": {"choice":"c7","confidence":0.80,"probabilities":{…}}
  },
  "instructions": {"motor_build":"…","motor_cash":"…","motor_default":"…"},
  "fanout": false,
  "latencyMs": 318, "usage": {"input_tokens":8710,"output_tokens":20}, "model": "jev-1.13.0"
}
```
`motor`의 키는 접두사 `motor_`를 뗀 이름이다.

### 5.3 `POST /api/arbitrate`

요청:
```json
{
  "pieceType":"T","nextType":"I","queue":["I","O","S","Z","L"],
  "intent": {"leading":"build","fired":["build","cash"],"forced":false,"appetite":1.8,"appetiteWord":"moderate"},
  "recent":[…],"game":{…},"memory":{"previousIntent":"build","hold":0.5},
  "proposals": [
    {"id":"c7","backedBy":["build","default"],"alt":false,"effects":"T piece, rotation 1 (nub pointing right); lands at columns 6-7, rows 15-17; clears no lines; keeps the well open; no new hole; peak higher; leaves a T-spin slot"},
    {"id":"c1","backedBy":["cash"],"alt":false,"effects":"…"}
  ]
}
```
검증 추가: `proposals` 2..4, id 중복 없음; `backedBy`는 `KNOWN_INTENTS ∪ {"default"}`의 비어 있지 않은 부분집합; `alt` boolean; `effects` 문자열; `intent.fired`는 `KNOWN_INTENTS`의 부분집합 1..3, `intent.leading ∈ fired`. 요청에 `directive`가 있으면 무시한다.
서버 동작: `directive = directiveOf(intent.fired, intent.forced)` (2.3절) → state = 3절 R3(보드·surface·facts·candidates·activations 없음, `intent.directive`는 서버가 채움). questions = `arbitrate` choice(옵션 설명 2.3절 규칙: `backedBy` 대문자, `default→HABIT`, `alt`면 "Second thought of the {LEADING} neuron") + 제안마다 `veto_<id>` noul + `hold` score.

응답 200:
```json
{
  "arbitrate": {"choice":"c7","confidence":0.71,"probabilities":{"c7":0.71,"c1":0.29}},
  "veto": {"c7":0.12,"c1":0.70},
  "hold": {"value":1.4,"confidence":0.6,"probabilities":{"0":0.1,"1":0.4,"2":0.5}},
  "directive": "keep the well open and stack cleanly beside it and take the clear now",
  "instructions": {"arbitrate":"…","veto_c7":"…","veto_c1":"…","hold":"…"},
  "latencyMs": 266, "usage": {"input_tokens":920,"output_tokens":30}, "model": "jev-1.13.0"
}
```

### 5.4 클라이언트 오류 정책 (app.js)

- R1, R2 실패(HTTP ≠ 200 또는 네트워크): 현행 `askJev` 루프 — 토스트 + 자동 일시정지 + 재개 시 재시도.
- R3 실패: **일시정지하지 않는다.** `chosen = argmax E`, `ledBy = "fallback"`, `hold = 0`, 알약 `FALLBACK`, 토스트 3초. 통계 `fallbacks` 증가.
- 응답의 `choice`가 알려진 id가 아니면 probabilities에서 알려진 id 중 최대를 쓴다(현행 방어와 동일).

---

## 6. 시각화 명세

### 6.1 유지되는 것

보드 캔버스와 `drawCell`, 고스트 % 라벨(굵은 모노, 검은 외곽선), 통계 hero 숫자(평균 응답, 비용), `.below-board`의 다음 조각 미리보기와 phase 텍스트, `replayPath` 이동 애니메이션, 줄 제거 플래시, 잠금 후 대기 슬라이더(기본값 300 → **0**), 토스트, 게임 오버 오버레이. `THINKING_ALPHA` 와이어 후보 표시(요청 1 동안).

### 6.2 DOM / 레이아웃 (`index.html`)

측면 패널 폭은 `--side-w`(app.js가 보드 열 높이 − 보드 폭 − 간격으로 계산, 데스크톱 약 360–420px). 카드 순서(데스크톱, 위→아래):

1. `.card.card-cortex` `<h2>피질</h2>` — `<svg id="cortex" viewBox="0 0 400 330" width="100%">` + `<div id="timeline">`(40개 `<i>`) + `<div id="thought" class="mono">`.
2. `.card.card-props` `<h2>제안</h2>` — `<div id="props">` 제안 행 ≤4 (기존 `#cands` 카드를 대체).
3. `.card.card-stats` `<h2>통계</h2>` — hero 2칸(`stAvg` "평균 응답 · 조각당 호출 3회", `stCost`), `.stats` 격자에 조각/줄/점수/T스핀 + **불일치/뒤집기/거부/바꿈**(`stDisagree stOverride stVeto stChanged`), `.fine`에 `R1 <b id="stR1">280</b> · R2 <b id="stR2">318</b> · R3 <b id="stR3">266</b> ms · 토큰 <b id="stTok">`.
4. `.card.card-controls` — 일시정지/새 게임, 슬라이더, `<label><input type="checkbox" id="optNeurons" checked> 뉴런</label>`(끄면 `/api/decide` 단일 Choice 경로), `<label><input type="checkbox" id="optPrefetch"> 미리 묻기</label>`.

폰(≤ 900px) CSS `order`: `.board-wrap`(1) → `.below-board`(2) → `.card-cortex`(3) → `.card-props`(4) → `.card-stats`(5) → `.card-controls`(6). 기존 `nth-child` 규칙을 클래스 선택자로 바꾼다.

추가 요소:
- `<svg id="synapses">`: `<main>` 위에 `position:absolute; inset:0; pointer-events:none; z-index:5`. 피질 원의 중심(`getBoundingClientRect`)에서 보드 고스트 중심(캔버스 rect + 셀 좌표)으로 선. `resize` 시 재계산. ≤ 900px에서는 숨김(`display:none`).
- `.board-wrap`의 `box-shadow` 색을 CSS 변수 `--lead`로(기본 보라). `--dim`(피질 단계 동안 스택 알파 0.7)은 캔버스 쪽에서 처리.
- `.below-board`의 "다음" 옆에 회색 작은 글자로 큐 5개 `I O S Z L`(`#queueText`).
- 헤더 hook: `조각마다 엔진이 보고, 다섯 의도 뉴런이 발화하고, 운동 뉴런들이 자리를 제안하고, 중재와 코치가 동시에 심사한다.`

### 6.3 피질 SVG (`viewBox 0 0 400 330`, 한 번 만들고 속성만 갱신)

- **행 0 (y 6–40) 감각·엔진**: 열 높이 막대 10개(x 12 + 12·c, 폭 9, 높이 = h/20 × 28, 회색), 오른쪽에 칩 텍스트 `높이 9 · 구멍 2 · 굴곡 7 · 우물 10열 −4 · 꽉찬 줄 1`, 그 아래 `큐 I O S Z L`. 스폰 즉시 갱신.
- **행 1 (y 70–125) 뉴런**: 의도 원 5개 r=13, 중심 x = 45, 105, 165, 225, 285, y = 95, 라벨 `생존 정리 빌드 현금 스핀`(y 122), 원 안에 활성값 `.92`(mono 9px). 유휴: fill hue 알파 0.12. 도착 시 150ms 전환: `fill-opacity = 0.15 + 0.85·a`, `r = 13 + 6·a`, `filter: drop-shadow(0 0 (4 + 10·a)px hue)`. 발화: 1.5px 흰 링. 강제: 주황 링 + 위에 `강제` 텍스트. stayed: 원 위에 자물쇠 글리프. 습관 원 r=10, x=335, 회색, 항상 알파 0.5, 라벨 `습관`. 위험 선호 게이지 x=378, y 70–125, 폭 12, 4칸, 채움 높이 a/3, 색 초록→호박→빨강. STAY 노드 r=7, x=18, y=95, 점선 경로가 행 3의 HOLD 노드에서 왼쪽 가장자리로 올라옴(재귀 링크); `stay ≥ 0.5`면 이전 `led_by` 색으로 빛남.
- **행 2 (y 150–210) 운동·제안**: 제안 칩 ≤4 (x 12 + 96·k, 폭 88, 높이 40): `[hue 사각 10px] c7 · .71` 위줄, 아랫줄 한국어 후보 라벨(`candidateLabel`). 습관만 backer인 칩은 회색. 행 1의 발화 원에서 자기 제안 칩으로 선(stroke hue, 폭 1 + 3·a); 여러 원이 같은 칩으로 모이면 선이 합쳐진다. 미니보드는 그리지 않는다(보드 위 와이어가 그 역할).
- **행 3 (y 230–318) 판정**: y 230에 두 개의 얇은 화살표 라벨 `중재`와 `코치`가 **나란히** 아래 막대들로 내려온다(순차가 아니라 병렬임을 그림으로 고정). 제안마다 막대(y 246 + 20·k, 높이 14): `[hue 스와치][A 구간: hue, 폭 ∝ A][V 구간: 빨강, 오른쪽에서 폭 ∝ V, 반투명 겹침][최종 % 텍스트]`; `hardVetoed`면 `VETO` 태그, `chosen`이면 왼쪽 3px 흰 테두리 + `선택`. HOLD 노드 r=7, x=18, y=300, 채움 = hold/2, 라벨 `유지`. 막대 아래 한 줄(`#verdictLine`, mono 10px): `fork`면 두 hue를 반반 칠한 `FORK` 태그를 앞에 붙임(같은 태그를 보드 캔버스 오른쪽 위 모서리에도 알약으로 그림) · `중재: 빌드 c7 승 · 코치: 현금 c1 거부` / `vetoedTop`이면 `중재 1위 c7 → 코치 거부 → c3 선택` / `override`면 승자 hue로 `중재가 우선순위를 뒤집음 (빌드 → 현금)` / backer가 습관뿐이면 `습관이 이김 (빌드 → 습관)`.
- 모든 원·칩·막대에 `<title>` = 그 질문에 실제 전송된 지시문(`instructions[...]`), 거부 막대는 `veto_<id>` 전문. 제안 행(`#props`)의 `title`도 동일("가짜 없음" 증명, 현행 후보 행과 같은 방식).
- **타임라인** `#timeline`: 조각당 7×7px 사각형 40개 슬라이딩, 배경 = `ledBy` hue(습관 회색, fallback 검정), 거부가 있었으면 빨간 1px 외곽, `hold ≥ 0.5`면 흰 점.
- `#thought` 한 줄: `빌드 .92 · 현금 .61 · 선호 1.8 → 빌드 c7 .71 / 현금 c1 .55 / 습관 c7 .80 → 중재 c7 .71 · 거부 c1 .70 → c7 61%`.

### 6.4 제안 카드 (`#props`)

행마다: `[hue 점] c7 · T 회전 1 · 7–8열 · 1줄 제거` / 아래 미니 막대들: 발화 뉴런 + 습관마다 그 hue로 `P_i(π)` 폭(6px 높이, 라벨 두 글자) / 오른쪽 굵은 `61%` / 태그 `선택` `VETO` `ALT`. 정렬은 `final` 내림차순.

### 6.5 조각당 애니메이션 타임라인 (ms, 전형값)

| t | 사건 | 화면 |
|---|---|---|
| 0 | 스폰, `POST /api/sense` | phase `감각`. 1px 흰 스캔라인이 보드를 200ms에 위→아래로 훑음. 모든 후보 와이어(현행 THINKING). 행 0 막대 갱신, 큐 글자. 쌓인 스택 알파 0.7로. 원들은 알파 0 상태로 리셋. |
| 0–300 | R1 진행 중 | 행 0에서 5개 원으로 내려가는 회색 선에 점선 흐름(`.inflight` dash 애니메이션). **이 애니메이션은 "요청이 나가 있다"는 뜻일 뿐, 답을 흉내 내지 않는다.** phase note `감각: 뉴런 7개에 자극 전달 중…` |
| ~300 | R1 도착, 즉시 `POST /api/motor` | 원 5개가 동시에 150ms로 실제 a로 점등(위 규칙), 발화 링, 강제 주황 링, stayed 자물쇠, 게이지 채움, `--lead` = leading hue(보드 글로우 색 전환 300ms). phase `연합 · 빌드 .92 · 현금 .61 발화 · 위험 선호 1.8/3`. |
| 300–600 | R2 진행 중 | 발화 원에서 빈 제안 칩으로 가는 선이 점선 흐름. 습관 원도 자기 칩으로. |
| ~600 (=tR2) | R2 도착, 즉시 `POST /api/arbitrate` | 발화 순서대로 80ms씩 어긋나게: 그 뉴런의 argmax를 보드에 **와이어 외곽선**(hue, lineWidth 2)으로 그림, 같은 셀에 k개가 겹치면 하나의 외곽선 폭 2k + 글로우; 알약(`빌드`) 부착; 습관의 argmax는 회색 점선 외곽. 운동장 고스트(상위 2·3위)가 흐리게. 칩 채움 `c7 · .71`. `#synapses`에 원→와이어 중심 선(`stroke-dashoffset` 180ms). phase `운동 · 빌드 c7 · 현금 c1 · 습관 c7 → 제안 2개`. **이 상태를 최소 `WIRE_HOLD_MS`(500) 유지.** |
| 600–900 | R3 진행 중 | 행 3의 빈 막대, `중재`·`코치` 화살표 둘 다 펄스. |
| max(tR3, tR2 + 500) | R3 도착 → 판정 공개 | 와이어가 채워진 고스트로 200ms 크로스페이드(색·알파·동심 링), % 라벨이 0에서 `round(100·final)`까지 200ms 카운트업, 거부 고스트에 빨간 링·빗금·`VETO`·알파 0.1, 시냅스 빨간 점선으로, 선택 고스트 3px 흰 외곽 펄스 + ` · 선택`. 행 3 막대 채움, `#verdictLine`(+ `FORK` 태그·보드 모서리 알약), 타임라인 사각형 추가, HOLD 채움과 재귀 링크 점등, `#props` 갱신. phase `판정 · 빌드 c7 61% 선택 · 현금 c1 거부`. |
| +600 | `GHOST_MS` 홀드 | **스크린샷 순간.** |
| +300–500 | 이동 | `replayPath` 프레임(현행), 이동 조각에 `ledBy` hue 2px 링. 고스트·와이어·시냅스 220ms 페이드. 스택 알파 1.0으로. |
| 잠금 | 줄 플래시 240ms(있을 때), 기억·통계·로그 갱신, 슬라이더 대기(기본 0) | 원·막대는 다음 스폰까지 상태 유지, 자물쇠는 다음 조각의 R1까지. |

조각당 벽시계 ≈ 900 (요청) + 600 (홀드) + ~450 (이동) ≈ **2.0–2.3 s**. 후보가 1개면 모든 층이 어둡고 phase `외길`로 바로 이동.

### 6.6 색 매핑 요약

`intent hue → (원 fill, 행 1→2 선, 제안 칩, 보드 와이어 외곽선, 고스트 fill, 알약 배경, 동심 링, 시냅스 선, 행 3 A 구간, 타임라인 사각형, 이동 조각 링, `--lead` 글로우)`. 습관 회색은 같은 경로. 거부 빨강은 (링, 빗금, VETO 알약, 행 3 V 구간, 시냅스 점선, 타임라인 외곽)에만. 강제 주황은 원 링과 `강제` 텍스트에만. 흰색은 선택 외곽선·발화 링·자물쇠·라벨 텍스트에만.

### 6.7 한 장의 스크린샷 (모르는 사람이 보는 것)

어두운 보드 위에 반투명한 T 조각 두세 개: 인디고 `빌드·습관 · 선택 61%`가 오른쪽 우물 옆에 서 있고(안쪽에 인디고·회색 두 겹 링), 금색 `현금 27%`가 거의 찬 줄 위에 누워 있고, 민트 `정리`에는 빨간 링과 빗금과 `VETO 0%`. 각 조각에서 가는 색 선이 오른쪽 패널의 빛나는 원으로 이어진다. 패널에는 다섯 원 중 두 개가 밝고(빌드 .92, 현금 .61) 세 개는 어둡고, 게이지가 2/3쯤 차 있고, `중재`와 `코치` 두 화살표가 나란히 막대들로 내려오며, 한 줄이 `중재: 빌드 c7 승 · 코치: 정리 c3 거부`라고 적혀 있다. 아무것도 읽지 않아도 "여러 본능이 자리를 제안했고, 코치가 하나를 빨갛게 지웠고, 인디고가 이겼다"가 보인다.

### 6.8 폰 (≤ 900px)

카드가 보드 아래로 쌓인다(6.2 순서). SVG는 viewBox로 축소(360px에서 원 r ≈ 12px, 읽힘). `#synapses` 없음. 고스트는 hue·알약·%·링·VETO를 그대로 지니므로 선 없이도 이야기가 남는다. 제안 카드 미니 막대는 유지, `#thought`는 2줄 줄바꿈 허용.

---

## 7. 구현 분할

세 패키지가 **동시에** 시작한다. 공유 코드는 없다: 공유하는 것은 이 문서(5절 JSON, 부록 B 상수, 2절 텍스트)뿐이다. 서버 엔지니어는 `public/`을 건드리지 않고, 프런트 엔지니어는 `server.js`를 건드리지 않는다. 통합은 두 쪽이 각자 스텁으로 테스트를 통과시킨 뒤 실서버(`localhost:3456`, 이미 실행 중 — 새로 띄우지 말고 코드 반영 후 사용자가 재시작)로 한 번 붙여 본다.

### 패키지 S — 서버 (한 명)

파일: `server/questions.js`(새, 순수: SCENE/MOTOR_PRE/텍스트 상수, `DIRECTIVE_PHRASE`, `directiveOf(fired, forced)`, `KNOWN_INTENTS`, `validateSense/Motor/Arbitrate(body) → string|null`, `buildSense(body) → {state, questions}`, `buildMotor(body)`, `buildArbitrate(body)`, `substitute(text, vars)`), `server.js`(라우팅 3개 추가, `handleSense/Motor/Arbitrate`, `JEV_FANOUT` 처리, 응답 조립·로그, `/api/decide` 유지), `test/questions.test.js`.

작업:
1. `server/questions.js`에 2절 텍스트를 **글자 그대로** 상수로 옮긴다.
2. 검증기 3개(5절 규칙 전부).
3. 빌더 3개: camel→snake 매핑, `stay` 생략 규칙, `motor_<i>` 는 fired만 + `motor_default` 항상, 치환 토큰, R3 옵션 설명 규칙(`HABIT`, `Second thought of the {LEADING} neuron`), `veto_<id>`를 제안마다, `hold`.
4. `server.js`: 세 핸들러, `instructions` 에코, `latencyMs`/`usage`/`model`, 502 정책, `JEV_FANOUT` `Promise.all`(usage 합산), 로그 한 줄(`R1 fired=[build,cash] app=1.8 …`).
5. `experiments/neurons.mjs`는 패키지 M으로.

테스트(`node --test`):
- 검증: 각 엔드포인트의 필수 필드 누락·타입 오류·범위 초과(`fired` 4개, 후보 256개, 제안 1개/5개, `leading ∉ fired`, 잘못된 조각 문자)가 문자열 오류를 돌려주고, 5절 예시 본문이 `null`을 돌려준다.
- 빌더: `buildSense`가 `previousIntent: null` 또는 `hold: 0`이면 `stay`를 만들지 않고, 아니면 만든다; state 키가 정확히 3절 목록과 같다(스냅샷).
- 빌더: `buildMotor`가 `fired = ["build","cash"]`일 때 질문 키가 정확히 `{motor_build, motor_cash, motor_default}`이고, 세 질문의 criteria가 동일 객체 내용이며, `motor_build` 텍스트에 `0.92`, `1.8`, `moderate`가 들어 있고 `{`가 남아 있지 않다; `forced` survive에 `forced by height`.
- `directiveOf`: `["build","cash"]` → `"keep the well open and stack cleanly beside it and take the clear now"`; `["survive"], forced` → `"bring the danger down first (forced by height)"`; 빈 배열은 throw.
- 빌더: `buildArbitrate`가 제안 2개에 대해 `{arbitrate, veto_c7, veto_c1, hold}`를 만들고, state의 `intent.directive`가 `directiveOf`의 결과이며 요청의 `directive` 필드는 무시되고, 옵션 설명이 `"BUILD and HABIT proposed this: …"` / `"Second thought of the BUILD neuron: …"`이며, state에 `board`, `surface`, `facts`, `candidates`, `activations` 키가 **없다**.
- 백틱 키 검사: 각 요청의 모든 지시문(옵션·루브릭 설명 포함, 치환 후)에서 백틱으로 감싼 식별자(`` `x` `` 또는 `` `x.y` ``의 첫 토큰)가 그 요청의 state를 재귀적으로 훑어 모은 키 집합에 존재한다(예: R2의 `summary`·`board_after`는 `candidates.<id>` 아래에 있으므로 통과). 불일치는 조용한 연극이므로 반드시 실패해야 한다.
- `substitute`가 알 수 없는 토큰을 남기면 throw.
- 팬아웃: `JEV_FANOUT=1`에서 `systemOne` 스텁이 질문 수만큼 호출되고 usage가 합산된다.

### 패키지 F — 프런트엔드 (한 명)

파일: `public/neurons.js`(새, 순수, 브라우저·Node 공용), `public/app.js`, `public/index.html`, `test/neurons.test.js`.

작업:
1. `neurons.js`: `INTENTS`, `HUES`, `LABELS_KO`, 상수(부록 B), `facts(board, piecesSinceClear)`, `depthAt`, `wellPhrase`, `hasTSlot`, `candidateSummaryV2`, `effects`, `appetiteWord`, `gate(sense, appetite, facts, memory)`, `proposalsFrom(motor, intent, candidates)`, `combine(arb, veto, hold, proposals, intent, candidates)`, `ghostsFrom(result)`(4.5절 고스트 배열), `fallbackCombine(proposals)`.
2. `app.js`: `askJev(gen, path, payload)`로 일반화; `playPiece`를 R0→R1→R2→R3→홀드→이동으로 재구성; `G`에 `intent, motor, proposals, verdict, memory, wires, rings, cortex:{phase,t0,tR1,tR2,tR3}, opts:{neurons,prefetch}`; `stats`에 `calls, r1Sum, r2Sum, r3Sum, disagreements, overrides, vetoes, changed, forced, fallbacks`; `G.log` 항목에 `{piece, intent, directive (R3 응답 에코), motorPicks, proposals, arbitrate, veto, hold, final, chosen, ledBy, override, changed, fork, vetoedTop, latency:{r1,r2,r3}, tokens}`; `recent`/`memory` 유지·`newGame` 초기화; `window.__jev = G` 유지.
3. 캔버스: `drawCell`에 색 인자, 고스트 `{cells,p,alpha,color,tag,rings,vetoed,chosen,faint,dashed}`, 와이어 외곽선(폭 2k), 알약, 동심 링, 빨간 링·빗금, 흰 선택 외곽 펄스, % 카운트업, 스캔라인, 스택 0.7 알파, 이동 조각 링.
4. `index.html`: 6.2 카드·순서·CSS 변수·폰 `order`·토글·hook.
5. 피질 SVG 빌드/갱신 함수, `#props`, `#timeline`, `#thought`, `#verdictLine`, `<title>` 부착.
6. 뉴런 끄기 토글: `/api/decide` 현행 경로(기존 코드 유지) — 통계 hero 문구 `조각당 호출 1회`로 전환.
7. **마지막**: `#synapses` 오버레이(레이아웃 측정, resize 재계산, ≤900px 비활성). 이 항목에 다른 항목이 의존하지 않는다.

테스트(`node --test`, 순수 함수만):
- `gate`: (a) 두 noul ≥ 0.5 → 둘 다 fired, a 내림차순; (b) 전부 < 0.5 → argmax 하나만; (c) 넷이 ≥ 0.5 → 3개로 잘리고 leading은 남는다; (d) `max_height 14`, survive 0.1 → forced, survive 포함, 잘림에서 survive·leading 모두 생존; (e) `previous_intent = build, hold 0.8, stay 0.9` → `a.build ≥ 0.72`, stayed, build ∈ fired; (f) `previous_intent = null` → stay 무시; (g) 동률에서 previous_intent 우선, 없으면 INTENTS 순; (h) `memory.hold = 0`이면 stay 값과 무관하게 stayed = false; (i) `appetite_word` 경계값 0.5/1.5/2.5.
- `proposalsFrom`: 두 뉴런 같은 argmax → 제안 1 + ALT(backers `[leading]`, alt true); 서로 다름 → ALT 없음; default만 다른 자리 → backers `["default"]`; 알 수 없는 id 무시; `E` 계산; `disagreement`/`fork`.
- `combine`: `V ≥ 0.65` → 0; 전부 hard-veto → `allVetoed`이고 raw 사용; Σ final = 1; 동률 → 큰 E → 낮은 maxHeight; `override`가 ALT 승리에서 false, 약한 backer 승리에서 true, default 단독 승리에서 true; `changed`; `vetoedTop`; `memoryNext`(default 승리면 previous_intent null, hold = value/2).
- `candidateSummaryV2`/`effects`: 우물 유지·채움·없음 세 보드에서 정확한 문구; T슬롯 yes/no; `effects`에 숫자 지표(`max height`, `bumpiness`, `aggregate`)가 없다; `top of piece R rows below the ceiling`.
- `facts`: `rowsNearlyFull`, `wellColumn null` when depth < 2.
- `ghostsFrom`: 색·알파·라벨·링 수·vetoed·chosen 플래그; 운동장 항목은 라벨 없음.
- `fallbackCombine`: argmax E, `ledBy "fallback"`.

### 패키지 M — 측정 하네스 (한 명, 또는 S가 F 이후에)

파일: `experiments/neurons.mjs`(SDK 직접 호출, `public/neurons.js`와 `server/questions.js`의 빌더를 import; judge.mjs의 8-보드 하네스 재사용 + 풀 게임 3판 시뮬레이션), `experiments/neurons-README.md`(결과 표).

게이트(모두 숫자로 보고; 실패 시 부록 A의 처분을 실행):
- (a) 공발화율: `|{a_i ≥ 0.5}| ≥ 2`인 조각 ≥ 30%; 어떤 noul이 > 90% 또는 < 5% 발화하면 문구 수정.
- (b) 규칙 쌍둥이(noul마다): survive vs `max_height ≥ 10`, clean vs `holes > 0`, build vs `I ∈ queue ∧ well_depth ≥ 2`, cash vs `∃ 후보 linesCleared > 0`, spin vs `tspin_available_now`. 일치 ≥ 90% → 그 noul은 규칙이다: 문구를 바꾸거나 삭제.
- (c) `appetite` vs `max_height` Spearman |ρ| > 0.9 → appetite 삭제(치환 토큰 제거).
- (d) appetite 민감도: 같은 보드에 appetite 0 / 3을 강제 치환 → 운동 argmax가 (보드, 뉴런) 쌍의 ≥ 20%에서 바뀜; 아니면 (c)와 같이 삭제.
- (e) 산술 쌍둥이(운동 뉴런마다, Dellacherie 계열 가중치: survive −maxHeight, clean −holes, build +well kept, cash +score, spin +tspin/slot): argmax 일치 ≥ 90% → 문구 수정 또는 삭제.
- (f) 운동 불일치율(fired만) ≥ 30%; 습관 포함 ≥ 40%.
- (g) 뒤집기율 10–40% (|fired| = 1 구간 별도 보고). 0% → R3 연극(중재 삭제 검토); > 50% → R1 잡음.
- (h) 제안당 hard-veto ≤ 40%; 넘으면 `HARD_VETO` 상향 또는 문구 수정.
- (i) 묶음 vs 단독(variant D): 묶인 `motor_default`의 휴리스틱 대비 ρ ≥ 0.35(단독 C는 0.41); 미달 시 `JEV_FANOUT=1` 기본.
- (j) 역량: 5판 평균 조각 ≥ 30, 줄 ≥ 단일 Choice 기준의 80%.
- (k) 바꿈율(`changed`) 보고; < 10%면 층들이 수를 거의 바꾸지 않는 것.

---

## 부록 A — 연극 원장 (심사 지적 → 처분)

1. **`priority` 단일 6지선다 → 의도별 독립 noul 5개**(심사 2 PRIMARY, 심사 1의 "상위 2 강제 발화"는 채택하지 않음). 근거: limits 실험에서 애매한 문장조차 Choice top1이 1.00인 경우 20%, ≥ 0.9가 53% — 6지선다는 구조적으로 원 하나만 켠다. 독립 noul은 0.01 반올림에서도 둘 이상이 진짜로 ≥ 0.5일 수 있다.
2. **|fired| = 1일 때 중재가 같은 뉴런의 1위 vs 2위를 고르는 문제** → 항상 켜진 `motor_default`(측정된 variant C 지시문)를 제안으로 넣는다. 발화가 하나여도 서로 다른 틀의 제안이 둘 있고, ALT는 두 argmax가 같을 때만 등장한다. 습관은 의도가 아니며 회색으로만 그린다. 또한 심사 1의 접목 7("최종 ≠ 단일 Choice argmax" 카운터)을 이 뉴런 하나로 해결한다(`changed`).
3. **`appetite` → 운동 텍스트 → 거부 근거 사슬이 측정되지 않음**; `appetite`가 max_height의 단조 함수일 수 있음 → 유지하되 게이트 (c)(d)에 종속. 실패하면 토큰과 지시문 절을 삭제하고 게이지를 없앤다.
4. **`veto_{id}`가 `arbitrate`와 같은 요청이라 코치는 중재 결과를 모른다** → 예산(순차 ≤ 3회)상 4번째 요청은 넣지 않는다. 대신 **문구와 그림을 병렬로 고정**: `중재`·`코치` 화살표가 나란히 내려오고, 문장은 "동시에 심사", 중재 1위가 거부되면 `중재 1위 c7 → 코치 거부 → c3 선택`. "코치가 중재의 선택을 막았다"는 서술은 금지.
5. **`flatten` ≈ argmin(bumpiness)**(심사 1) → 삭제. "다음 조각들이 편한 표면"은 습관 뉴런의 "keep the stack low and flat"이 이미 덮는다.
6. **`priority`가 `facts`의 규칙 4개로 예측될 위험** → noul마다 규칙 쌍둥이 게이트 (b). 지시문은 `queue`·`recent`(지표에 없는 재료)를 읽도록 썼다.
7. **반사(reflex)** → 삭제(두 심사 모두 실측 0회). 전용 애니메이션 경로 하나가 사라진다.
8. **뇌간 16은 늦다** → 14. 엔진 규칙이며 주황으로 그린다. Jev의 판단으로 표기하지 않는다.
9. **override 카운터 인플레이션**(ALT 승리가 뒤집기로 잡힘) → `backers(ALT) = [leading]`.
10. **중재자가 후보 요약의 숫자 지표로 "가장 낮은 스택"을 계산할 수 있음**(심사 1·2) → R3 state에서 보드·surface·facts·후보·activations 제거, 제안은 `effects`(정성 서술)만. 심사 2의 "요약은 유지"와 심사 1의 "사후 지표 제거"를 정성 서술로 동시에 만족.
11. **`recent.led_by`로 인한 의도 고착** → noul이 독립이라 완화. 명시적 기억은 `hold → memory → stay` 루프로 교체(심사 2). 타임라인 한 색이 15조각 이상 이어지면 `stay` 문구에 "a goal that has led many pieces in a row deserves scrutiny"를 추가.
12. **묶음 전송이 분포를 바꿈**(branches README) → 게이트 (i), `JEV_FANOUT` 대체 경로, 비용 4배를 정직하게 표기.
13. **활성 밝기가 대부분 on/off일 것** → 시각은 이진에 맞춰 설계(발화 링 vs 어두움), 그라데이션은 보너스. 로그에 뉴런별 분산 기록, 게이트 (a).
14. **`hold`/`commit`이 특정 뉴런에 대한 약속인 척함**(심사 1, Chorus) → 계획 전체에 대해 묻고 `previous_intent = ledBy(chosen)`는 산술 결합으로 명시, UI 라벨 "계획 유지".
15. **`E(π)`, `fork`, `disagreement`, `changed`, `ledBy`, 우물/T슬롯 판정, 뇌간** — 산술이며 산술로 표기한다. Jev의 답으로 그리지 않는다.

## 부록 B — 상수표 (동결, `public/neurons.js`에 export, Node 테스트)

| 이름 | 값 | 쓰임 |
|---|---|---|
| `FIRE_P` | 0.5 | noul 발화 문턱 (stay 포함) |
| `MAX_FIRED` | 3 | 운동 뉴런 상한 (+ 습관 1) |
| `BRAINSTEM_HEIGHT` | 14 | survive 강제 발화 높이 |
| `HARD_VETO` | 0.65 | 고스트를 0으로 만드는 거부 확률 |
| `W_DEFAULT` | 0.5 | 습관 뉴런의 E 가중치 (표시·동률 전용) |
| `FORK_GAP` | 0.15 | FORK 배지: 상위 두 활성 차이 |
| `NEARLY_FULL` | 8 | `rows_nearly_full` 기준 채운 칸 수 |
| `GHOST_MS` | 450 | 판정 공개 후 홀드 |
| `WIRE_HOLD_MS` | 350 | R2 와이어 최소 유지 (R3 요청과 겹침) |
| `COUNTUP_MS` | 200 | % 라벨 카운트업 |
| `FADE_MS` | 220 | 고스트·시냅스 페이드 (현행) |
| `MAX_GHOST_ALPHA / MIN_GHOST_ALPHA / GHOST_LABEL_MIN_P / THINKING_ALPHA` | 0.55 / 0.14 / 0.03 / 0.18 | 현행 유지 |
| `FIELD_ALPHA` | [0.22, 0.12] → 0.06 | 운동장 고스트 (R2 도착 / R3 도착 후) |
| `RING_INSET_PX` | [3, 6, 9] | backer 동심 링 |
| 서버 `JEV_FANOUT` | env, 기본 unset | R2 팬아웃 |
| 서버 `MODEL` | `jev-latest` | 현행 |

## 부록 C — 용어

발화(fire) = noul ≥ 0.5. 활성(activation) = noul p. 제안(proposal) = 운동 뉴런의 argmax. 중재(arbitrate) = 제안 중 선택 Choice. 거부(veto) = 코치 noul. 유지(hold) = 다음 조각 계획 강도. 습관(default) = 의도 없는 기준 운동 뉴런. 뒤집기(override) = 선택의 backer에 leading이 없음. 바꿈(changed) = 선택 ≠ 습관의 argmax. 불일치(disagreement) = 발화 뉴런들의 argmax가 둘 이상.
