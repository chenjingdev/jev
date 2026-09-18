"""Screen every sample and score the guardrail against the human labels.

    op run --env-file=<(echo 'TYPESAFE_API_KEY="op://Personal/typesafe jev key/credential"') \
      -- uv run python guardrail/run_samples.py

Writes results.json next to this file and prints the summary. The sif disk
cache stays on, so a re-run after a code change that does not touch the
questions costs nothing.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import guard  # noqa: E402
from samples import SAMPLES  # noqa: E402

RESULTS = HERE / "results.json"


def main() -> int:
    rows = []
    for sample in SAMPLES:
        verdict = guard.screen(sample.text)
        got = frozenset(verdict.categories)
        rows.append(
            {
                "text": sample.text,
                "expected_categories": sorted(sample.categories),
                "expected_severity": sample.severity,
                "got_categories": sorted(got),
                "got_severity": verdict.level,
                "severity_score": verdict.severity,
                "probabilities": verdict.probabilities,
                "safe_match": (not sample.categories) == verdict.safe,
                "exact_match": got == sample.categories,
                "severity_match": verdict.level == sample.severity,
            }
        )
    RESULTS.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    n = len(rows)
    safe_ok = sum(r["safe_match"] for r in rows)
    exact_ok = sum(r["exact_match"] for r in rows)
    sev_ok = sum(r["severity_match"] for r in rows)
    sev_off1 = sum(abs(r["got_severity"] - r["expected_severity"]) <= 1 for r in rows)

    # Per-category precision / recall over the multi-label sets.
    tp, fp, fn = Counter(), Counter(), Counter()
    for r in rows:
        exp, got = set(r["expected_categories"]), set(r["got_categories"])
        for c in got & exp:
            tp[c] += 1
        for c in got - exp:
            fp[c] += 1
        for c in exp - got:
            fn[c] += 1

    print(f"샘플 {n}건")
    print(f"  안전/유해 이진 판정 일치 : {safe_ok}/{n}")
    print(f"  카테고리 집합 완전 일치   : {exact_ok}/{n}")
    print(f"  심각도 정확히 일치        : {sev_ok}/{n}   (±1 단계 이내 {sev_off1}/{n})")
    print()
    print(f"  {'카테고리':<10} {'TP':>3} {'FP':>3} {'FN':>3}")
    for cid, (name, _) in guard.CATEGORIES.items():
        print(f"  {name:<10} {tp[cid]:>3} {fp[cid]:>3} {fn[cid]:>3}")
    print()
    print("불일치:")
    for r in rows:
        if r["exact_match"] and r["severity_match"]:
            continue
        exp_c = "+".join(guard.CATEGORIES[c][0] for c in r["expected_categories"]) or "안전"
        got_c = "+".join(guard.CATEGORIES[c][0] for c in r["got_categories"]) or "안전"
        exp_s = guard.SEVERITY[r["expected_severity"]]
        got_s = guard.SEVERITY[r["got_severity"]]
        print(f"  {r['text']}")
        print(f"    기대 {exp_c} / {exp_s}   →   결과 {got_c} / {got_s} ({r['severity_score']:.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
