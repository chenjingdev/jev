# eye: Jev의 눈

Jev에게 화면을 보여주고, Jev가 어디를 보고 어디를 고르는지 사람이 지켜볼 수 있게 하는 프로젝트. 왜 이런 구조인지는 [`experiments/vision`](../experiments/vision/README.md)의 수치가 근거다: Jev는 픽셀(어떤 인코딩이든)을 못 읽고, 칸마다 단어 하나인 격자는 너비 8~16까지 정확히 짚는다.

## 지금 있는 것

### `cursor.py` — 가상 마우스

화면 맨 위에 떠 있는 투명 클릭 통과 창. 실제 포인터는 건드리지 않고 보여주기만 한다. 모든 Space·모든 디스플레이 위에 뜬다.

```sh
uv run python eye/cursor.py          # 오버레이 띄우기
uv run python eye/cursor.py --demo   # 띄우고 혼자 돌아다니게 하기
```

다른 프로세스가 유닉스 소켓(`/tmp/jev-cursor.sock`)으로 JSON 한 줄씩 보내서 움직인다. 파이썬에서는 `cursor_client.Cursor`:

```python
from cursor_client import Cursor
c = Cursor()
c.look(700, 350, 200, 100, label="결제하기 0.83")   # 시선 상자 + 라벨
c.heat([[x, y, w, h, p], ...])                     # 후보 칸들, 확률만큼 진하게
c.move(800, 400, ms=400)                           # 미끄러져 이동
c.click()                                          # 클릭 파동
c.label("고르는 중")                                # 커서 옆 상태 문구
c.clear()
```

좌표는 메인 디스플레이 왼쪽 위가 원점, y는 아래로. `screencapture`와 Vision 프레임워크가 쓰는 것과 같다. 오버레이가 안 떠 있으면 `Cursor`는 경고 한 줄 남기고 조용히 무시하므로 눈은 화면 없이도 돈다.

의존성은 `pyobjc-framework-Cocoa`, `pyobjc-framework-Quartz`뿐(`uv sync`).

### `retina.py` — 망막

스크린샷 한 장을 16×9 격자로 줄인다. 칸마다 단어 하나: `button`(디텍터 상자 + 글자), `icon`(디텍터 상자, 글자 없음), `text`(OCR 상자가 걸침), `blank`(한 색), `edge`(한 방향으로만 색이 바뀜), `image`(나머지). 읽은 글자와 찾은 요소는 칸 번호와 함께 별도 목록으로 나간다 — 칸 안에 글자를 넣으면 "토큰 하나 = 칸 하나"가 깨진다는 게 실험 결과다. Jev는 호출하지 않는다.

요소는 **오브젝트 디텍션**으로 찾는다: Microsoft OmniParser v2의 아이콘 디텍터(스크린샷으로 학습한 YOLO, `models/omniparser_icon_detect.pt`, AGPL-3.0, gitignore — 아래 명령으로 받는다). 화면 한 장 300ms(MPS). 칸 분류 head가 실패한 자리를 이게 맡는다: 라벨이 상자 단위라 요소 크기와 딱 맞는다. OCR은 줄이 아니라 **단어 단위** 상자로 쪼갠다 — "이미지 동영상 쇼핑"은 탭 셋이지 한 덩어리가 아니다. 클릭 좌표는 칸 중심이 아니라 칸 안에서 가장 가까운 요소 상자의 중심.

```sh
curl -L -o eye/models/omniparser_icon_detect.pt \
  https://huggingface.co/microsoft/OmniParser-v2.0/resolve/main/icon_detect/model.pt
```

```sh
uv run python eye/retina.py --show                    # 메인 화면을 격자로 줄여 오버레이에 칠함
uv run python eye/retina.py --region 2560,0,2560,1440 --json
```

메인 디스플레이 2560×1440 기준 OCR + 디텍터 5초(첫 호출은 모델 적재로 +10초). 한국어+영어. 캡처 동안 커서 오버레이는 스스로 숨긴다.

### `step.py` — 한 걸음

목표 문장을 받아 두 번 본다(사카드). 1단계: 화면 전체를 16×9로 보고 Jev가 칸 하나를 고른다(칸 160pt). 2단계: 그 칸 주변 3×3을 잘라 다시 16×9로 보고 한 번 더 고른다(칸 30pt). 단계마다 `sif.ask` 한 번에 질문 셋 — `target`(빈칸 아닌 칸 전부를 Choice 선택지로, 설명은 "라벨, 위치, 글자"), `risky`(되돌릴 수 없는 클릭인가), `done`(목표가 이미 이뤄졌나). 선택지를 코드가 열거하고 Jev가 고르는 테트리스 패턴이다. 행·열 번호를 출력하게 하지 않는 이유는 실험의 find_col 결과.

```sh
op run --env-file=<(echo 'TYPESAFE_API_KEY="op://Agent/typesafe jev key/credential"') \
  -- uv run python eye/step.py --region 2560,0,2560,1440 --goal "왼쪽 메뉴에서 검색을 연다"
```

첫 실행(Chrome의 Threads 페이지):

```
[screen] 57 candidate cells, 72 texts, Jev 633ms
  target: r2c1  (text, top-left, says: 6 threads / 0 추천 / + 새로운 스레드 / Q 검색)
  top5:   r2c1 0.90  r2c10 0.08  r1c9 0.02
[zoom] 75 candidate cells, 24 texts, Jev 316ms
  target: r6c2  (text, middle-left, says: Q 검색)
  top5:   r6c2 0.91  r1c3 0.04  r1c1 0.03
would click at (2605, 293) - not clicking.
```

커서는 "검색" 글자 위에 멈췄다. **클릭은 하지 않는다.** 오버레이에 히트맵·시선 상자·커서 이동·클릭 파동까지만 그린다.

터미널만 떠 있는 화면에 같은 목표(Wi-Fi 설정)를 주면 1단계 확률이 0.17로 퍼지고 메뉴 막대의 상태 아이콘 근처를 고른다 — 아이콘은 `image`로만 보여서 한 칸 옆을 짚었다. 아이콘 라벨이 다음 병목.

### `walk.py` — 여러 걸음, 실제 클릭

걸음 하나 = **훑기**(`step.glance`: 화면을 3×4 구역으로, 구역마다 "버튼 n개, 아이콘 n개, 글자: …" 한 줄 요약, Jev가 구역 하나) → **보기**(`step.look`: 그 구역을 16×9로, 칸 하나) → 칸에 디텍터 요소가 딱 하나면 그 중심을, 아니면 3×3 **줌** 한 번 더 → **진짜 클릭**(Quartz `CGEventPost`) → 1.2초 → 다시 훑기. 클릭 앞의 문 넷: `done ≥ 0.7`(이미 됐다), `risky ≥ 0.5`(되돌릴 수 없다), 고른 확률 `< 0.45`(찍기다), 방금 누른 자리를 또 골랐다 — 넷 다 안 누르고 멈춘다. `--display N` 밖은 절대 안 누른다. 상태에 `clicked_so_far`(이번 걸음까지 누른 것)가 들어가서 두 단계 목표를 처음부터 다시 하지 않는다.

```sh
op run --env-file=<(echo 'TYPESAFE_API_KEY="op://Agent/typesafe jev key/credential"') \
  -- uv run python eye/walk.py --display 3 --max-steps 3 \
  --goal "검색 결과 탭 줄의 '더보기' 메뉴를 열고, 그 메뉴에서 '도서'를 골라 도서 검색 결과를 본다"
```

**된 것 (2026-09-19, 디스플레이 3의 Chrome, 구글 검색 페이지)**:

```
step 1 [glance] 517 texts -> b11 0.46
  [screen] target r4c11 (button '더보기 •', button '금융', in row: 모드 전체 이미지 동영상 … 더보기 • 도구) 0.99
  [zoom] -> 더보기 0.98      clicked (3218, 280)
step 2 [glance] 518 texts -> b21 0.48   done: 0.09 on the screen, 0.14 on the change
  [screen] target r2c11 (button '뉴스', button '도서') 0.83
  [zoom] -> 도서 0.97        clicked (3207, 400)
step 3 [glance] 307 texts   done: 0.63 on the screen, 0.80 on the change -> stopping.
```

메뉴를 열고, 열린 메뉴에서 항목을 고르고, 됐다는 걸 알았다. 한 걸음짜리 "이미지 탭"도 같은 식으로 됐다(0.97 → 클릭 → 판정 0.75). 걸음 하나에 Jev 호출 셋, 2~3초.

여기까지 오는 데 고친 것들, 전부 실제로 틀려서 고친 것:

- **첫 고르기가 퍼졌다** — 화면 전체(글자 400개, 후보 89개)에서 바로 고르면 0.15~0.33. `glance`를 앞에 두니 그 안에서 0.9 이상. 구역은 반 칸씩 **겹치게** 잘라야 한다 — 탭 줄이 경계에서 반으로 잘려 '더보기'가 옆 구역에 있었다.
- **`done`이 화면 전체로는 못 본다** — 목표가 이뤄졌는데 0.24. 글자 400개에 묻힌다. 클릭 전후 **변화**(나타난/사라진 글자, 라벨별 칸 수)로 물으면 0.76. 그런데 변화만 주면 엉뚱한 그림을 눌러 페이지가 바뀌어도 0.82로 "됐다"고 한다. **뭘 눌렀는지**를 같이 주면 갈린다: 맞는 버튼 0.80, 엉뚱한 그림 0.55, 엉뚱한 버튼 0.13. 지금 `changed()`가 그 셋을 다 준다.
- **선택지에 줄 맥락** — 브라우저의 앞으로 버튼 `〉`를 "펼치기"로 골랐다. 선택지마다 `in row: …`(같은 줄의 글자들)를 붙이니 "〉 C google.com/…"과 "전체 이미지 동영상 … 더보기 도구"가 구별된다.
- **이력** — 메뉴가 열렸는데 또 '더보기'를 골랐다. 자기가 방금 뭘 했는지 모르니까. `clicked_so_far`를 상태에 넣었다.
- **칸에 요소가 둘** — '더보기'와 '금융'이 한 칸이라 칸 중심에 가까운 '금융'을 눌렀다(금융 페이지로 감). 요소가 둘 이상이면 줌.
- **클릭이 안 먹는 세 가지** — (1) 다른 모니터의 뒤에 있는 앱은 첫 클릭이 활성화에만 쓰이고 사라진다 → 누르기 전에 그 자리 앱을 `activate`. (2) `clickCount`가 0이면 웹 메뉴가 클릭으로 안 친다 → `kCGMouseEventClickState=1`. (3) 클릭 뒤 툴팁 피하려고 40pt 비켰더니 hover 메뉴가 닫혔다 → 포인터는 그 자리에 둔다.
- **합성 키의 Cmd가 세션에 눌린 채 남았다** — 되돌리려고 Cmd+←를 보낸 뒤 모든 클릭이 "새 탭에서 열기"가 됐다(탭 4개, 접근성 트리로 찾아 닫음). 마우스 이벤트는 flags를 0으로 박는다.

**안 된 것**: **입력창**. "검색창을 눌러 자동완성에서 고른다"는 못 한다 — 디텍터가 검색창을 상자로 안 잡고(안의 아이콘만), Vision 사각형 검출도 둥근 입력창은 못 잡는다. 글자만 있는 `text` 칸으로 보여서 Jev가 0.3대에서 찍다가 멈춘다. 다음 병목.

### `collect.py` + `head.py` — 학습하는 망막 (아직 실패)

`research/vision.md`의 openvons 레시피(얼린 인코더 + 작은 head, CE+Brier, temperature scaling)를 맥에서 시도한 것. 인코더는 macOS Vision의 feature print(768차원, 칸당 15ms, 다운로드 없음), 선생은 접근성 트리(학습 때만; 런타임엔 안 봄). 스크린샷은 저장하지 않고 칸의 벡터만 저장한다 — Slack·카카오톡에 개인 대화가 있어서.

```sh
uv run python eye/collect.py --apps "cmux,Slack,Finder"   # 앱마다 창 하나 캡처 → data/<앱>/*.npz
uv run python eye/head.py --holdout Slack --features fp    # 다른 앱으로 학습, Slack으로 시험
```

**결과 (2026-09-19, 앱 6개, 캡처 29장, 칸 5천)**: 한 앱을 통째로 빼고 시험하면 정확도 0.35~0.56, 특히 필요한 `icon` 재현율 0.11~0.61, `input` 0.03~0.25. 쓸 수 없다. 학습한 앱에서는 0.86이라 외운 것이지 배운 게 아니다.

원인 둘, 둘 다 수치로 확인:
- **선생의 라벨이 눈에 보이는 것과 다르다.** AX는 "버튼"을 동작으로 정의하고 망막은 생김새를 본다. Slack 사이드바 행은 AXButton이지만 픽셀은 글자다. 그래서 `button`을 빼고 생김새 기준(글자 있으면 text, 작으면 icon)으로 다시 라벨링했다. 그래도 위 수치다.
- **칸이 요소보다 크다.** 160pt 칸 안의 20pt 아이콘에 "icon"을 붙이면 벡터의 9할은 아이콘이 아닌 것을 본다. 48×27(30pt 칸)만으로 학습해도 나아지지 않았고, 픽셀 원본 특징(16×16)은 feature print보다 더 나빴다(0.26~0.32) — 인코더가 아무것도 안 뽑는 건 아니지만 UI 칸을 가르기엔 부족하다.

다음에 해볼 것이 있다면: 격자 칸이 아니라 **요소 크기의 크롭**을 학습 단위로, 인코더는 사진 유사도용 feature print 대신 CLIP 계열(MobileCLIP CoreML 또는 MLX SigLIP). 지금 망막은 규칙 + OCR로 간다 — Threads 데모는 그걸로 됐다.

## 앞으로

1. 입력창 찾기: 넓고 납작한 테두리 상자. 디텍터를 접근성 트리의 AXTextField 상자로 fine-tune하거나, 픽셀 규칙(긴 가로선 두 개 사이가 빈칸)으로.
2. 타자: 클릭 다음은 글자 넣기. `CGEventKeyboardSetUnicodeString`.
3. 줌 단계에도 확신 문: 지금은 화면 단계 고르기만 0.45로 막는다. 첫 walk가 줌 0.52로 주소창을 눌렀다.
4. 아이콘 **뜻**: 디텍터는 "여기 아이콘이 있다"까지다. 톱니인지 돋보기인지는 SF Symbols 대조나 상자 크롭 분류가 필요하다.
5. 디텍터가 놓치는 앱이 나오면 `collect.py`의 접근성 트리 상자로 fine-tune.
