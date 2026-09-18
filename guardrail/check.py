"""Screen sentences from the command line.

    op run --env-file=<(echo 'TYPESAFE_API_KEY="op://Personal/typesafe jev key/credential"') \
      -- uv run python guardrail/check.py "이 개새끼야 꺼져"

With no argument it reads one sentence per line from stdin (or interactively).
`--json` prints the verdict as JSON instead of the table.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import guard  # noqa: E402

BAR_WIDTH = 20


def render(verdict: guard.Verdict) -> str:
    """The verdict as a small table: headline, then one bar per category."""
    head = "안전" if verdict.safe else f"{' + '.join(verdict.labels) or '(카테고리 없음)'}"
    lines = [
        f"문장   : {verdict.text}",
        f"판정   : {head}",
        f"심각도 : {verdict.severity_label} ({verdict.severity:.2f}/3, confidence {verdict.severity_confidence:.2f})",
    ]
    for cid, (name, _) in guard.CATEGORIES.items():
        p = verdict.probabilities[cid]
        bar = "█" * round(p * BAR_WIDTH)
        mark = "◀" if p >= verdict.threshold else ""
        lines.append(f"  {name:<8} {p:4.2f} {bar:<{BAR_WIDTH}} {mark}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Jev 가드레일: 문장의 유해성 카테고리와 심각도를 판별")
    parser.add_argument("text", nargs="*", help="판별할 문장. 비우면 stdin에서 한 줄씩 읽음")
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    parser.add_argument(
        "--threshold", type=float, default=guard.DEFAULT_THRESHOLD, help="카테고리 탐지 확률 임계값"
    )
    args = parser.parse_args()

    if args.text:
        texts = [" ".join(args.text)]
    else:
        if sys.stdin.isatty():
            print("문장을 한 줄씩 입력하세요 (Ctrl-D로 종료)", file=sys.stderr)
        texts = [line.strip() for line in sys.stdin if line.strip()]

    for i, text in enumerate(texts):
        verdict = guard.screen(text, threshold=args.threshold)
        if args.json:
            print(json.dumps(verdict.as_dict(), ensure_ascii=False))
        else:
            if i:
                print()
            print(render(verdict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
