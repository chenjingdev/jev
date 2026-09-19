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

`step.look`을 반복한다: 화면 → 줌 → **진짜 클릭**(Quartz `CGEventPost`, modifier 0) → 1.2초 → 다시 화면. 클릭 앞에 문 넷: `done ≥ 0.7`이면 목표가 이미 보이니 멈춤, `risky ≥ 0.5`면 사람 몫으로 멈춤, 화면 단계 고른 확률이 `0.3` 미만이면 찍기라서 멈춤, 직전에 누른 자리를 또 고르면 멈춤. 클릭은 `--display N` 밖으로는 절대 안 나간다.

```sh
op run --env-file=<(echo 'TYPESAFE_API_KEY="op://Agent/typesafe jev key/credential"') \
  -- uv run python eye/walk.py --display 3 --goal "자동완성 목록에서 '2048 cube'를 골라 검색한다" --max-steps 3
```

**결과 (2026-09-19, 디스플레이 3의 Chrome, 구글 검색 페이지)**:

- 자동완성이 열린 화면에서 "'2048 cube'를 골라 검색": 1걸음째 그 행 옆 아이콘을 눌러 빗나감, 2걸음째 `button '2048 cube'`를 눌러 **결과 페이지가 떴다**. 그런데 `done`이 0.24라 3걸음째 주소창을 눌렀다. 목표는 됐는데 된 줄 모른다.
- `done`이 낮은 이유: 화면 하나가 글자 300~400개(탭·북마크·URL 조각)라 목표가 그 속에 묻힌다. 같은 화면에 질문을 바꿔 물어도 0.19~0.62. 그래서 **변화로 판정**하는 `changed()`를 넣었다 — 클릭 전후에 나타난/사라진 글자(신뢰도 0.5 이상, 두 글자 이상)만 주고 "이 변화가 목표가 이뤄진 것을 보여주나". 같은 장면에서 0.76. 지금은 둘 중 큰 값을 쓴다.
- 그 판정도 속는다: "이미지 탭을 연다"에 1걸음째 지식 패널의 그림을 눌러 다른 검색 결과로 갔는데, 페이지가 바뀌었으니 `changed` 0.82로 "됐다"고 했다. 화면 단계 확률이 0.14였다 — 그래서 확신 문(`SURE_AT`)을 넣었고, 다시 돌리니 OCR이 "이미지"를 "이니시"로 읽어 0.15에서 **안 누르고 멈췄다**. 맞는 행동이다.
- 삽질 하나: 페이지를 되돌리려고 합성 키 이벤트로 Cmd+←를 보냈더니 세션에 **Cmd가 눌린 채로 남아** 이후 클릭이 전부 "새 탭에서 열기"가 됐다(탭 4개, 접근성 트리로 찾아 닫음). `click()`이 이제 flags를 0으로 박는다.

정리하면 잇기·가드레일·복구는 돌고, 병목은 둘이다. **화면 단계의 첫 고르기**가 후보 89개 앞에서 0.15~0.33으로 퍼진다(Threads 57개일 땐 0.90). **`done`**은 화면 전체로는 못 보고 변화로는 과신한다. 둘 다 "글자가 너무 많다"가 원인이라, 다음은 후보를 줄이는 쪽 — 브라우저 크롬(탭·북마크·주소창)과 페이지를 나누거나, 디텍터 상자만 후보로 주거나.

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

1. 후보 줄이기: 첫 고르기가 후보 89개에서 퍼진다. 디텍터 상자만 선택지로, 또는 창의 크롬과 내용을 나눠 두 번 고르기.
2. `done`을 목표에서 뽑은 "보여야 할 것" 목록으로 판정하기(변화만 보면 과신한다).
3. 아이콘 **뜻**: 디텍터는 "여기 아이콘이 있다"까지다. 톱니인지 돋보기인지는 SF Symbols 대조나 상자 크롭 분류가 필요하다.
4. 디텍터가 놓치는 앱이 나오면 `collect.py`의 접근성 트리 상자로 fine-tune.
