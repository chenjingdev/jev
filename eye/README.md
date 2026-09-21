# 시각 센서

이 폴더의 목적은 **이미지 픽셀을 구조화된 관찰 정보로 바꾸는 것**이다. 브라우저는 입력과 출력을 확인하는 테스트 UI다.

```text
이미지 → ScreenParser → OCR → 영역·글자 결합 → 조건부 BLIP → 관찰 JSON
```

## 실행

```sh
uv sync --extra perception
uv run --extra perception python eye/sensor_server.py
```

[센서 테스트 화면](http://127.0.0.1:8768/)에서 `센서 시작`을 누르고 왼쪽 문서 작업실을 직접 조작한다. 검색·체크박스·문서 열기·설정 변경 때마다 픽셀을 분석하고 오른쪽 결과를 갱신한다. `현재 화면 분석`은 한 번만 분석하며, `센서 중지`는 다음 관찰을 멈춘다. 모델은 첫 분석에서 로드하고 이후 재사용한다. Jev API 키는 필요 없다.

테스트 UI는 800×800 캔버스에 직접 그린다. 화면에 표시하는 **동일한 캔버스 비트맵**을 `toBlob`으로 PNG로 보내므로, 화면 공유나 브라우저 캡처 권한이 필요 없다. 입력용 HTML 컨트롤은 키보드·IME·접근성을 담당하며, 그 이름·좌표·상태는 모델에 전달하지 않는다. 인식 박스는 별도 SVG에 표시하여 센서 입력에 섞이지 않는다. 이 방식은 자체 제작한 테스트 UI를 위한 것이며, 임의의 웹사이트 화면을 캡처하는 기능은 아니다.

화면 변경은 300ms 동안 모아서 분석하고, 추론 중 다시 바뀌면 이전 결과를 버리고 최신 프레임을 읽는다. 같은 화면을 계속 분석하거나 요청을 병렬로 쌓지 않는다. 상태가 바뀌었다는 알림은 재분석 시점에만 사용하며, 상태의 정답은 주입하지 않는다.

1280픽셀보다 큰 데스크톱 화면은 전체 프레임과 겹치는 타일을 함께 탐지한다. 타일의 중심 소유 영역으로 경계 중복을 막고, 내부 경계에서 잘린 물체를 제외한 뒤 전역 이미지 좌표로 합친다. 전체 프레임은 큰 영상·창 영역을 보존하고 타일은 작은 글자·버튼을 원본에 가까운 크기로 찾는다. 각 탐지 패스의 최대 요소는 600개다. BLIP 설명은 프레임당 우선순위가 높은 글자 없는 아이콘 32개로 제한한다.

`다른 이미지로 시험하기`에서 파일·예제 이미지를 넣거나 이미지를 붙여넣을 수도 있다. 서버는 이미지 바이트만 받아 모델을 실행한다.

## 파일 역할

| 파일 | 역할 |
|---|---|
| `perceive.py` | 공통 센서 파이프라인 `Retina`와 이미지 분석 CLI |
| `perception_models.py` | ScreenParser/대체 탐지기와 BLIP 추론 |
| `ocr_backends.py` | Apple Vision / EasyOCR 어댑터 |
| `scene.py` | 영역·글자 결합과 관찰 JSON |
| `sensor_server.py` | 로컬 이미지 분석 HTTP 서버 |
| `attention.py` | FastSAM 영역·OCR 요약과 Jev의 목적 기반 coarse-to-fine 선택 |
| `attention_experiment.py` | 실제 화면에서 두 단계 영역 선택과 클릭 좌표를 검증하는 실험 |
| `accessibility_probe.py` | macOS 네이티브 AX 트리의 구조·좌표·액션·응답성을 읽기 전용으로 측정 |
| `lab/` | 이미지 입력·영역 표시·모델 출력 확인 UI |
| `fixtures/` | 고정 입력 이미지와 사람이 조작하는 캔버스 테스트 UI |

## 모델·출력

- 기본 탐지기: `docling-project/ScreenParser`, YOLO11-L, 55종류. 고정 revision의 가중치를 사용한다.
- OCR: Mac은 Apple Vision, Windows는 EasyOCR ko/en. `--ocr easyocr`로 직접 지정할 수 있다.
- BLIP: `macpaw-research/blip-icon-captioning`. 글자가 없는 작은 요소를 잘라 설명한다.
- 출력: 이미지 픽셀 좌표의 `box`, `type`, `text`, `description`, 기하학적 `group`, 출처와 모델 점수.
- `state`는 아직 미구현이라 null이다. 아이콘 설명은 틀릴 수 있으며 점수는 보정 전 모델 점수다.
- 입력 이미지는 분석 중 임시 파일로만 사용하고 삭제한다. JSON 저장은 CLI의 `--out` 또는 UI의 내려받기로 명시적으로 한다.

```sh
uv run --extra perception python eye/perceive.py screenshot.png --out observations.json
uv run --extra perception --extra portable pytest -q tests
```

Windows는 `uv sync --extra perception --extra portable`로 EasyOCR를 추가한다. 탐지/BLIP는 가능한 MPS 또는 CUDA를 사용하고, 없으면 CPU를 사용한다. EasyOCR는 CUDA 또는 CPU를 사용한다. Windows 실기기 검증은 아직 수행하지 않았다.

macOS에서 실행 중인 앱의 접근성 품질과 권장 입력 경로를 점검할 수 있다. 이 검사는 CDP나 DOM을 사용하지 않으며, 품질 값은 라우팅 휴리스틱이지 확률이 아니다. `--include-text`를 지정하지 않으면 노드의 제목과 설명을 출력하지 않는다.

```sh
uv run python eye/accessibility_probe.py --app Chrome
```

목적 기반 영역 선택 실험은 화면 이미지를 준비한 뒤 Jev 키를 Agent vault에서 주입해 실행한다.

```sh
op-away run op run \
  --env-file=<(echo 'TYPESAFE_API_KEY="op://Agent/typesafe jev key/credential"') \
  -- uv run --extra perception python eye/attention_experiment.py screenshot.png \
  --out eye/reports/assets/attention-run
```

## 범위

자동화 러너, 고정 8단계 시나리오, 클릭·타자 실행, 가상 커서, 실행 추적 패널은 제거했다. 앞으로 추가할 작업도 센서의 탐지 품질, 아이콘 의미, 시각적 상태 인식, 속도와 관찰 출력에 집중한다. 다른 프로그램은 관찰 JSON을 소비하면 된다.
