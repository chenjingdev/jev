"""Judge every twin pair and score the hunter against the human labels.

    op run --env-file=<(echo 'TYPESAFE_API_KEY="op://Personal/typesafe jev key/credential"') \
      -- uv run python bug-hunter/run_samples.py

Writes results.json next to this file and prints the summary. Three numbers:

- pairwise: the buggy twin gets the higher risk than its fixed twin
- smell hit: the expected smell is at or above the threshold on the buggy twin
- kind: the Choice names the expected smell on the buggy twin

The sif disk cache stays on, so a re-run costs nothing unless the questions
change.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import hunter  # noqa: E402
from samples import PAIRS  # noqa: E402

RESULTS = HERE / "results.json"


def _judge(name: str, source: str) -> hunter.Verdict:
    """Same file name for both twins: the only thing that differs is the source."""
    function = hunter.Function(file="samples.py", name=name, lineno=1, source=source)
    return hunter.judge(function)


def main() -> int:
    rows = []
    for pair in PAIRS:
        buggy = _judge(pair.name, pair.buggy)
        fixed = _judge(pair.name, pair.fixed)
        rows.append(
            {
                "name": pair.name,
                "expected_smell": pair.smell,
                "buggy": buggy.as_dict(),
                "fixed": fixed.as_dict(),
                "pairwise": buggy.risk > fixed.risk,
                "severity_pairwise": buggy.severity > fixed.severity,
                "smell_hit": pair.smell in buggy.smells,
                "smell_false_alarm": pair.smell in fixed.smells,
                "kind_match": buggy.kind == pair.smell,
                "fixed_kind_none": fixed.kind == "none",
            }
        )
    RESULTS.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    n = len(rows)
    print(f"쌍 {n}개")
    print(f"  버그 쌍둥이가 더 높은 위험      : {sum(r['pairwise'] for r in rows)}/{n}")
    print(f"  버그 쌍둥이가 더 높은 심각도    : {sum(r['severity_pairwise'] for r in rows)}/{n}")
    print(f"  기대한 냄새가 버그 쪽에서 탐지  : {sum(r['smell_hit'] for r in rows)}/{n}")
    print(f"  기대한 냄새가 고친 쪽에서도 탐지: {sum(r['smell_false_alarm'] for r in rows)}/{n}  (오탐)")
    print(f"  유력 종류 = 기대한 냄새         : {sum(r['kind_match'] for r in rows)}/{n}")
    print(f"  고친 쪽 유력 종류 = 없음        : {sum(r['fixed_kind_none'] for r in rows)}/{n}")

    buggy_risk = sum(r["buggy"]["risk"] for r in rows) / n
    fixed_risk = sum(r["fixed"]["risk"] for r in rows) / n
    print(f"  평균 위험: 버그 {buggy_risk:.2f} / 고침 {fixed_risk:.2f}")
    print()

    # Per-smell tally: hits on the buggy twin, false alarms on the fixed twin.
    hit, miss, alarm = Counter(), Counter(), Counter()
    for r in rows:
        smell = r["expected_smell"]
        (hit if r["smell_hit"] else miss)[smell] += 1
        if r["smell_false_alarm"]:
            alarm[smell] += 1
    print(f"  {'냄새':<8} {'탐지':>3} {'놓침':>3} {'오탐':>3}")
    for smell, (name, _) in hunter.SMELLS.items():
        print(f"  {name:<8} {hit[smell]:>3} {miss[smell]:>3} {alarm[smell]:>3}")
    print()

    print("쌍별 (위험 버그→고침, 심각도, 유력 종류):")
    for r in rows:
        b, f = r["buggy"], r["fixed"]
        flag = "" if r["pairwise"] else "  ✗"
        print(
            f"  {r['name']:<18} {b['risk']:.2f}→{f['risk']:.2f}  "
            f"{b['severity']}→{f['severity']}  {b['kind_label']}→{f['kind_label']}{flag}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
