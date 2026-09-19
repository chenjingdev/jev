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

## 앞으로

1. `retina.py` — 스크린샷 → 16×9 라벨 격자(`blank text button image edge icon`). 글자는 Vision OCR, 나머지는 픽셀 통계.
2. `step.py` — 목표 문장 + 격자 → Jev `ask()`로 "볼 칸 / 위험한가 / 직전 행동 성공했나" → 커서로 표시. 두 단계 사카드(전체 → 고른 영역 확대).
3. 실제 클릭은 마지막에, 가드레일 뒤에.
