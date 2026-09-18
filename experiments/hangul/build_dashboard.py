"""experiments/hangul/dashboard.html 생성.

results.json(v2)과 results_v1.json을 읽어 브라우저에서 볼 수 있게 줄인 뒤
dashboard_template.html의 __DATA__ 자리에 끼워 넣는다. 표준 라이브러리만 쓴다.
원본 JSON 파일은 읽기만 하고 절대 쓰지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

RESULTS = HERE / "results.json"
RESULTS_V1 = HERE / "results_v1.json"
TEMPLATE = HERE / "dashboard_template.html"
OUTPUT = HERE / "dashboard.html"

TOP_K = 10
PLACEHOLDER = "__DATA__"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def top_probabilities(probabilities: dict[str, float]) -> dict[str, float]:
    """확률 내림차순 상위 TOP_K개만 남긴다 (메모리 안에서만)."""
    ranked = sorted(probabilities.items(), key=lambda kv: kv[1], reverse=True)
    return dict(ranked[:TOP_K])


def trim_v2(data: dict[str, Any]) -> dict[str, Any]:
    """calls[*].answers[*].probabilities를 상위 TOP_K개로 자른다. state 등은 유지."""
    trimmed_calls = []
    for call in data.get("calls", []):
        call = dict(call)
        answers = {}
        for question, answer in call.get("answers", {}).items():
            answer = dict(answer)
            if isinstance(answer.get("probabilities"), dict):
                answer["probabilities"] = top_probabilities(answer["probabilities"])
            answers[question] = answer
        call["answers"] = answers
        trimmed_calls.append(call)

    out = dict(data)
    out["calls"] = trimmed_calls
    return out


def trim_v1_runs(data: dict[str, Any]) -> list[dict[str, Any]]:
    """v1은 runs만, 그중에서도 표에 쓰는 필드만. stop은 text로 되살린다."""
    runs = []
    for run in data.get("runs", []):
        text = run.get("text", "")
        runs.append(
            {
                "topic": run.get("topic"),
                "mode": run.get("mode"),
                "text": text,
                "calls": run.get("calls"),
                "seconds": run.get("seconds"),
                "stop": "end" if text.endswith(".") else "loop",
            }
        )
    return runs


def main() -> None:
    v2 = trim_v2(load_json(RESULTS))
    v1_runs = trim_v1_runs(load_json(RESULTS_V1))

    payload = json.dumps(
        {"v2": v2, "v1_runs": v1_runs},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    # <script id="data"> 안에 들어가므로 </script 를 깨 둔다. JSON에서 \/ 는 / 와 같다.
    payload = payload.replace("</script", "<\\/script")

    template = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise SystemExit(f"{TEMPLATE.name}에 {PLACEHOLDER} 자리가 없다")

    html = template.replace(PLACEHOLDER, payload)
    OUTPUT.write_text(html, encoding="utf-8")

    print(f"{OUTPUT} {OUTPUT.stat().st_size} bytes")


if __name__ == "__main__":
    main()
