# sif

semantic if. TypeSafe의 판단 모델 Jev를 평범한 제어문처럼 쓴다.

Jev는 참/거짓, 선택, 점수 세 가지만 돌려주는 모델이다. 조건을 코드로 쓸 수 없는 것,
예를 들어 "이 문의가 급한가", "이 명령이 위험한가"를 if문 조건에 넣을 수 있게 된다.

## 저장소 구조

Jev로 하는 실험은 전부 이 저장소에 모은다. 라이브러리 하나, 실험 여럿, 데모 프로젝트 여럿.

| 경로 | 무엇 |
|---|---|
| `src/sif/` | `sif` 라이브러리 (Python). 위 사용법. |
| `tests/` | `sif` 테스트 |
| `examples/` | `sif` 데모 스크립트 |
| `experiments/<이름>/` | 측정 실험 하나당 폴더. 스크립트 + 결과 + `README.md`(질문·방법·수치). `branches`, `limits`, `hangul`, `chess`, `vision`. |
| `tetris/` | Jev가 플레이하는 테트리스 (Node). 자체 `README.md`와 `docs/neurons-spec.md`. |
| `guardrail/` | 튜닙 Safety Check를 흉내낸 한국어 유해성 가드레일 (Python). 문장 → 카테고리 12개 확률 + 심각도 4단계. 자체 `README.md`. |
| `2048-puzzle/` | Jev가 플레이하는 2048, 타일이 그림 조각 (Node). **종료된 실패 실험** — 성적이 전부 엔진과 프롬프트에서 나왔다. 사유와 측정표는 자체 `README.md`. |
| `bug-hunter/` | Python 함수를 주루룩 먹이면 버그 냄새 10개 확률 + 심각도로 위험한 순서로 정렬하는 버그헌터. 자체 `README.md`. |
| `gomoku/` | Jev가 백을 두는 오목 (Python). 엔진이 후보 자리마다 사실 한 줄을 붙인 정답지를 주고 Jev가 고른다. 상대는 사람·엔진 봇·Claude Opus·Gomocup 엔진 Rapfi. 자체 `README.md`. |
| `chess/` | Jev 체스 판독과 엔진 대결 실험. Lichess CC0 국면 판독 화면은 :3461, 엔진 수와 Jev 개입을 분리해 보여주는 3D 아레나는 :3470. 자체 `README.md`. |
| `sliding-puzzle/` | 그림을 5×6으로 자른 슬라이딩 퍼즐 (Python). Jev는 "다음에 벗길 줄"만 고르고 밀기는 코드가 BFS로. 숫자는 정확히 따르지만 어느 숫자가 중요한지는 못 찾고, 지시문에 규칙을 적어 주면 따른다. 3×3 한 칸씩 버전부터의 과정이 자체 `README.md`. |
| `research/` | Jev 같은 모델이 어떻게 만들어지는지 조사한 자료. 복제본 카탈로그와 원리 정리. |

새 데모 프로젝트는 `tetris/`처럼 루트에 폴더 하나로, 새 측정 실험은 `experiments/` 아래에 둔다.
키는 어디서든 1Password 참조(`op run`)로만 주입하고 디스크에 쓰지 않는다.

## 설치

```sh
uv sync
```

## 사용

```python
import sif

if sif.true(message, "The customer is demanding immediate action"):
    team = sif.switch(message, {"refund": "Wants money back", "shipping": None, "praise": None})
    anger = sif.score(message, ["Calm", "Annoyed", "Furious"], "How angry is the customer?")
```

| 함수 | 역할 | 반환 |
|---|---|---|
| `check(state, question)` | 참일 확률 | float |
| `true(state, question, threshold=0.5)` | 확률을 임계값으로 자른 것 | bool |
| `switch(state, options)` | 갈래 하나 고르기 | str |
| `decide(state, options)` | switch와 같되 확률과 confidence 유지 | Decision |
| `score(state, levels, instructions)` | 순서 있는 단계 위의 위치 | float |
| `ask(state, **questions)` | 여러 질문을 한 요청에 묶기 | dict |

```python
answers = sif.ask(
    message,
    urgent="The message is urgent",
    topic=sif.options(["refund", "shipping", "praise"]),
    anger=sif.scale(["Calm", "Annoyed", "Furious"], "How angry"),
)
answers["urgent"].noul      # 0.987
answers["topic"].choice     # "refund"
answers["anger"].score      # 1.42
```

`ask()` 안의 질문들은 병렬로 평가되고 서로의 답을 보지 못한다.

모든 함수는 `default=`를 받는다. 타임아웃이나 서버 과부하 같은 일시적 오류에는 그 값을
돌려주고 경고를 남긴다. 키가 없거나 요청 형식이 틀린 경우는 default가 있어도 예외를 낸다.

## 실행

API 키는 1Password에 있고 디스크에 쓰지 않는다.

```sh
op run \
  --env-file=<(echo 'TYPESAFE_API_KEY="op://Agent/typesafe jev key/credential"') \
  -- uv run python examples/demo.py
```

데모를 두 번 실행하면 두 번째는 캐시에서 나오고 API 호출이 없다.

## 캐시와 로그

- 캐시: `~/.cache/sif/cache.sqlite`. 키는 model + state + questions. `SIF_CACHE=0` 또는 `sif.configure(cache=False)`로 끈다.
- 로그: `~/.cache/sif/calls.jsonl`. 호출당 한 줄, raw probabilities와 usage, `latency_ms`, `cached`를 남긴다. `SIF_LOG=0` 또는 `sif.configure(log=False)`로 끈다.

`sif.configure(model=..., timeout=..., cache=..., log=...)`로 공유 클라이언트를 재설정한다.

## 테스트

```sh
uv run pytest -q
```

테스트는 클라이언트를 가짜로 바꾸므로 API 키가 필요 없다.
