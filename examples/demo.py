"""Run the four sif verbs against the real Jev API on one Korean support message.

    PATH="$HOME/.local/bin:$PATH" op run \
      --env-file=<(echo 'TYPESAFE_API_KEY="op://Personal/typesafe jev key/credential"') \
      -- uv run python examples/demo.py

Run it twice: the second run is served from the disk cache and makes no API call.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import sif
from sif.log import DEFAULT_PATH

MESSAGE = (
    "어제 주문한 상품이 아직도 안 왔어요. 결혼식 선물이라 내일까지 안 오면 아무 의미가 없습니다. "
    "지금 당장 환불해 주세요. 고객센터는 전화도 안 받고 정말 답답하네요."
)

TOPICS = {
    "환불": "돈을 돌려달라는 요구",
    "배송": "배송 지연이나 분실 문의",
    "불만": "서비스나 응대에 대한 항의",
    "칭찬": "만족했다는 감사 인사",
    "기타": None,
}

ANGER = ["차분함", "짜증남", "몹시 화남"]


def log_position() -> int:
    """Byte offset of the end of the call log, so we can read only new lines."""
    path = Path(DEFAULT_PATH)
    return path.stat().st_size if path.exists() else 0


def new_records(since: int) -> tuple[list[dict], int]:
    """Records appended to the call log since byte offset `since`."""
    path = Path(DEFAULT_PATH)
    if not path.exists():
        return [], since
    text = path.read_text(encoding="utf-8")[since:]
    records = [json.loads(line) for line in text.splitlines() if line.strip()]
    return records, path.stat().st_size


def report(label: str, value: object, records: list[dict]) -> None:
    """Print one verb's result next to its latency, tokens and cache status."""
    print(f"  {label:<8} = {value}")
    for record in records:
        usage = record.get("usage") or {}
        tokens = usage.get("input_tokens")
        print(
            f"           latency={record['latency_ms']:8.1f}ms  "
            f"cached={str(record['cached']):<5}  "
            f"input_tokens={tokens if tokens is not None else '-'}"
        )


def main() -> int:
    print("문의:", MESSAGE)
    print()

    cursor = log_position()
    all_records: list[dict] = []

    print("[true]   급한 건인가?")
    urgent = sif.true(MESSAGE, "고객이 즉각적인 처리를 요구하고 있다", default=False)
    records, cursor = new_records(cursor)
    all_records += records
    report("urgent", urgent, records)

    print("[switch] 어느 갈래인가? (환불/배송/불만/칭찬/기타)")
    topic = sif.decide(MESSAGE, TOPICS, "이 문의는 어떤 종류인가?", default="기타")
    records, cursor = new_records(cursor)
    all_records += records
    report("topic", f"{topic.choice}  (confidence={topic.confidence:.3f})", records)
    for name, probability in sorted(topic.probabilities.items(), key=lambda kv: -kv[1]):
        print(f"             {name:<4} {probability:.4f}")

    print("[score]  얼마나 짜증났나? (0=차분함 … 2=몹시 화남)")
    anger = sif.score(MESSAGE, ANGER, "고객이 얼마나 화가 나 있는가?", default=0.0)
    records, cursor = new_records(cursor)
    all_records += records
    report("anger", f"{anger:.3f}", records)

    print("[ask]    셋을 한 요청으로 묶어서")
    answers = sif.ask(
        MESSAGE,
        urgent="고객이 즉각적인 처리를 요구하고 있다",
        topic=sif.options(TOPICS, "이 문의는 어떤 종류인가?"),
        anger=sif.scale(ANGER, "고객이 얼마나 화가 나 있는가?"),
    )
    records, cursor = new_records(cursor)
    all_records += records
    report(
        "bundle",
        f"urgent={answers['urgent'].noul:.3f}  "
        f"topic={answers['topic'].choice}  "
        f"anger={answers['anger'].score:.3f}",
        records,
    )

    print()
    live = [r for r in all_records if not r["cached"]]
    cached = [r for r in all_records if r["cached"]]
    tokens = [(r.get("usage") or {}).get("input_tokens") or 0 for r in live]
    print(f"요청 {len(all_records)}건 중 API 호출 {len(live)}건, 캐시 히트 {len(cached)}건")
    if live:
        print(f"요청당 input_tokens: {tokens}")
        print(f"총 input_tokens: {sum(tokens)}  (${sum(tokens) * 0.042 / 1_000_000:.6f})")

    if live and not any(tokens):
        print("경고: API 호출이 토큰을 하나도 쓰지 않았다. 폴백이 걸린 것 같다.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
