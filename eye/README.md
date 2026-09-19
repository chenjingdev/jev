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

스크린샷 한 장을 16×9 격자로 줄인다. 칸마다 단어 하나: `text`(Vision OCR 상자가 걸침), `blank`(한 색), `edge`(한 방향으로만 색이 바뀜), `image`(나머지). OCR로 읽은 글자는 칸 번호와 함께 별도 목록으로 나간다 — 칸 안에 글자를 넣으면 "토큰 하나 = 칸 하나"가 깨진다는 게 실험 결과다. Jev는 호출하지 않는다.

```sh
uv run python eye/retina.py --show                    # 메인 화면을 격자로 줄여 오버레이에 칠함
uv run python eye/retina.py --region 2560,0,2560,1440 --json
```

메인 디스플레이 2560×1440 기준 OCR 포함 4초. 한국어+영어.

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

1. 여러 걸음 잇기: 클릭 → 다시 보기 → `done`으로 멈추기. 실제 클릭은 `risky` 가드레일 뒤에.
2. 아이콘: 위 학습 재시도(요소 크롭 + CLIP) 또는 SF Symbols 대조.
