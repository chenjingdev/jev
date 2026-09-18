"""Rank the functions in some Python files by how likely Jev thinks they are buggy.

    op run --env-file=<(echo 'TYPESAFE_API_KEY="op://Personal/typesafe jev key/credential"') \
      -- uv run python bug-hunter/hunt.py src/sif/core.py guardrail/

Prints a table, riskiest first. `--json` prints one JSON object per function
instead, `--top N` keeps the first N rows, `--dry-run` only lists the functions
that would be sent and how many requests that is.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hunter  # noqa: E402

BAR_WIDTH = 12


def render_table(verdicts: list[hunter.Verdict]) -> str:
    """One line per function: risk bar, severity, kind, detected smells."""
    width = max((len(v.function.location) + len(v.function.name) + 1 for v in verdicts), default=20)
    lines = [f"{'위험':>5}  {'심각도':<4} {'함수':<{width}}  {'가장 유력':<8} 탐지된 냄새"]
    for v in verdicts:
        bar = "█" * round(v.risk * BAR_WIDTH)
        where = f"{v.function.location} {v.function.name}"
        smells = ", ".join(v.labels) or "-"
        lines.append(
            f"{v.risk:5.2f}  {v.severity_label:<4} {where:<{width}}  {hunter.KINDS[v.kind]:<8} {smells}  {bar}"
        )
    return "\n".join(lines)


def render_detail(verdict: hunter.Verdict) -> str:
    """Every smell probability for one function, like guardrail/check.py."""
    v = verdict
    lines = [
        f"함수     : {v.function.location} {v.function.name}",
        f"위험     : {v.risk:.2f}  ({' + '.join(v.labels) or '냄새 없음'})",
        f"심각도   : {v.severity_label} ({v.severity:.2f}/3, confidence {v.severity_confidence:.2f})",
        f"유력 종류: {hunter.KINDS[v.kind]} (confidence {v.kind_confidence:.2f})",
    ]
    for smell, (name, _) in hunter.SMELLS.items():
        p = v.probabilities[smell]
        bar = "█" * round(p * 20)
        mark = "◀" if p >= v.threshold else ""
        lines.append(f"  {name:<7} {p:4.2f} {bar:<20} {mark}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Jev 버그헌터: 함수들을 버그 가능성 순으로 정렬")
    parser.add_argument("paths", nargs="+", help="Python 파일 또는 디렉터리")
    parser.add_argument("--json", action="store_true", help="함수마다 JSON 한 줄")
    parser.add_argument("--detail", action="store_true", help="함수마다 냄새별 확률 전부 출력")
    parser.add_argument("--top", type=int, default=None, help="상위 N개만")
    parser.add_argument("--threshold", type=float, default=hunter.DEFAULT_THRESHOLD, help="냄새 탐지 임계값")
    parser.add_argument("--dry-run", action="store_true", help="보낼 함수 목록만 출력, API 호출 없음")
    args = parser.parse_args()

    functions = hunter.load_functions(args.paths)
    if not functions:
        print("함수를 찾지 못했습니다", file=sys.stderr)
        return 1

    if args.dry_run:
        chars = sum(len(f.source) for f in functions)
        for f in functions:
            print(f"{f.location:<40} {f.name:<30} {len(f.source):>6} chars")
        print(f"\n함수 {len(functions)}개, 요청 {len(functions)}회, 질문 {len(hunter.SMELLS) + 2}개/요청, 소스 {chars:,} chars")
        return 0

    verdicts = hunter.hunt(functions, threshold=args.threshold)
    if args.top:
        verdicts = verdicts[: args.top]

    if args.json:
        for v in verdicts:
            print(json.dumps(v.as_dict(), ensure_ascii=False))
    elif args.detail:
        print("\n\n".join(render_detail(v) for v in verdicts))
    else:
        print(render_table(verdicts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
