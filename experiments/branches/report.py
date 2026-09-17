"""Turn results.json into summary.md: one table per measurement, numbers only.

    uv run python experiments/branches/report.py
"""

from __future__ import annotations

import collections
import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dataset  # noqa: E402

RESULTS = HERE / "results.json"
SUMMARY = HERE / "summary.md"

CONDITION_LABELS = {
    "A": "A 기본(이름+설명)",
    "B": "B 설명 없음",
    "C": "C 순서 섞기(seed 3)",
    "D": "D 익명 이름",
    "E": "E 재현성(캐시 off 반복)",
}


def mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return statistics.fmean(values) if values else None


def fmt(value, places: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{places}f}"
    return str(value)


def table(header: list[str], rows: list[list[str]]) -> str:
    line = "| " + " | ".join(header) + " |"
    rule = "|" + "|".join("---" for _ in header) + "|"
    body = "\n".join("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join([line, rule, body])


def load() -> tuple[dict, list[dict]]:
    body = json.loads(RESULTS.read_text(encoding="utf-8"))
    calls = [c for c in body.get("calls", [])]
    return body.get("meta", {}), calls


def by(calls: list[dict], **filters) -> list[dict]:
    out = calls
    for key, value in filters.items():
        out = [c for c in out if c.get(key) == value]
    return out


def ok(calls: list[dict]) -> list[dict]:
    """Calls that produced an answer."""
    return [c for c in calls if not c.get("error")]


def accuracy(calls: list[dict]) -> float | None:
    calls = ok(calls)
    return sum(1 for c in calls if c["correct"]) / len(calls) if calls else None


def second_place_rate(calls: list[dict]) -> float | None:
    """Among wrong answers, the share where the gold category ranked second."""
    wrong = [c for c in ok(calls) if not c["correct"]]
    if not wrong:
        return None
    return sum(1 for c in wrong if c.get("gold_rank") == 2) / len(wrong)


def observations(calls: list[dict], conditions: tuple[str, ...]) -> dict[tuple[int, str], list[dict]]:
    """Group answers by (n, sample_id) across the given conditions."""
    groups: dict[tuple[int, str], list[dict]] = collections.defaultdict(list)
    for call in ok(calls):
        if call["condition"] in conditions:
            groups[(call["n"], call["sample_id"])].append(call)
    return groups


def agreement(groups: dict[tuple[int, str], list[dict]], n: int, expected: int) -> dict[str, float | None]:
    """Unanimity, pairwise agreement and gold-probability spread across repeats."""
    rows = [v for (gn, _), v in groups.items() if gn == n and len(v) == expected]
    if not rows:
        return {"groups": 0, "unanimous": None, "pairwise": None, "prob_sd": None,
            "prob_sd_max": None, "moved": None, "choices": None}
    unanimous = 0
    pairwise_hits = pairwise_total = 0
    spreads = []
    distinct = []
    for group in rows:
        choices = [g["choice"] for g in group]
        if len(set(choices)) == 1:
            unanimous += 1
        distinct.append(len(set(choices)))
        for i in range(len(choices)):
            for j in range(i + 1, len(choices)):
                pairwise_total += 1
                pairwise_hits += choices[i] == choices[j]
        probs = [g["gold_prob"] for g in group]
        spreads.append(statistics.stdev(probs) if len(probs) > 1 else 0.0)
    return {
        "groups": len(rows),
        "unanimous": unanimous / len(rows),
        "pairwise": pairwise_hits / pairwise_total if pairwise_total else None,
        "prob_sd": statistics.fmean(spreads),
        "prob_sd_max": max(spreads),
        "moved": sum(1 for s in spreads if s > 0),
        "choices": statistics.fmean(distinct),
    }


def agrees_with_a(calls: list[dict], n: int) -> float | None:
    """Share of condition C answers that match the condition A answer for the same message."""
    base = {c["sample_id"]: c["choice"] for c in ok(by(calls, n=n, condition="A"))}
    rows = [c for c in ok(by(calls, n=n, condition="C")) if c["sample_id"] in base]
    if not rows:
        return None
    return sum(1 for c in rows if c["choice"] == base[c["sample_id"]]) / len(rows)


def main() -> int:
    if not RESULTS.exists():
        print(f"missing {RESULTS}", file=sys.stderr)
        return 1
    meta, calls = load()
    answered = ok(calls)
    errors = [c for c in calls if c.get("error")]

    out: list[str] = []
    out.append("# 갈래 수 실험 결과")
    out.append("")
    out.append(
        f"- 모델: `{meta.get('model')}` (요청)·"
        f"`{(answered[0].get('model_resolved') if answered else None)}` (응답)"
    )
    out.append(f"- 지시문: `{meta.get('instructions')}`")
    out.append(f"- 기록된 호출: {len(calls)}건 (성공 {len(answered)}, 오류 {len(errors)})")
    out.append(f"- 계획 호출: {meta.get('planned_calls')}건")
    total_in = sum(c.get("input_tokens") or 0 for c in calls)
    total_out = sum(c.get("output_tokens") or 0 for c in calls)
    out.append(f"- 총 input tokens {total_in:,} / output tokens {total_out:,} (합계 {total_in + total_out:,})")
    out.append(f"- 총 소요 시간 {meta.get('elapsed_s', 0):,.1f}s")
    lat = [c["latency_ms"] for c in answered if c.get("latency_ms") is not None]
    if lat:
        out.append(
            f"- latency_ms 중앙값 {statistics.median(lat):,.1f} / 평균 {statistics.fmean(lat):,.1f} / "
            f"최소 {min(lat):,.1f} / 최대 {max(lat):,.1f}"
        )
    out.append(f"- 조건: " + ", ".join(f"{k}={v}" for k, v in CONDITION_LABELS.items()))
    out.append("")
    out.append(
        "- 조건 A·B·D는 디스크 캐시를 켜고, C·E는 끄고 호출했다. "
        "`sif/cache.py::_canonical`이 `sort_keys=True`로 캐시 키를 만들어 선택지 순서를 무시하므로, "
        "캐시를 켠 채로는 섞은 순서(C)와 반복(E)이 A의 답을 그대로 돌려받는다."
    )
    out.append("")

    ns = sorted({c["n"] for c in calls})

    # --- accuracy grid
    out.append("## 1. 정확도 (N × 조건)")
    out.append("")
    rows = []
    for n in ns:
        row = [str(n), str(len(dataset.samples_for(n)))]
        for condition in "ABCDE":
            subset = by(calls, n=n, condition=condition)
            value = accuracy(subset)
            row.append(f"{fmt(value)} ({len(ok(subset))})" if value is not None else "-")
        row.append(fmt(accuracy(by(calls, n=n))))
        rows.append(row)
    out.append(table(["N", "문장", "A", "B", "C", "D", "E", "전체"], rows))
    out.append("")
    out.append("괄호 안은 그 칸의 호출 수.")
    out.append("")

    # --- per-condition detail
    out.append("## 2. 조건별 상세 (N × 조건)")
    out.append("")
    rows = []
    for n in ns:
        for condition in "ABCDE":
            subset = ok(by(calls, n=n, condition=condition))
            if not subset:
                continue
            latencies = [c["latency_ms"] for c in subset if c.get("latency_ms") is not None]
            tokens = [c["input_tokens"] for c in subset if c.get("input_tokens")]
            golds = [c["gold_prob"] for c in subset]
            rows.append([
                str(n),
                condition,
                str(len(subset)),
                fmt(accuracy(subset)),
                fmt(mean(golds), 4),
                fmt(mean(c["top1_prob"] for c in subset), 4),
                fmt(mean(c["margin"] for c in subset), 4),
                fmt(mean(c["confidence"] for c in subset), 4),
                fmt(min(golds), 2),
                str(sum(1 for g in golds if g < 1.0)),
                fmt(second_place_rate(subset)),
                fmt(statistics.median(latencies), 1) if latencies else "-",
                fmt(mean(tokens), 1),
            ])
    out.append(table(
        ["N", "조건", "호출", "정확도", "정답확률", "top1확률", "마진(top1-top2)", "confidence",
         "정답확률 최솟값", "정답확률<1.0 건수", "오답중 정답2위", "latency중앙(ms)", "input토큰평균"],
        rows,
    ))
    out.append("")

    # --- order shuffling
    out.append("## 3. 순서 섞기 (조건 C, seed 3개)")
    out.append("")
    groups_c = observations(calls, ("C",))
    rows = []
    for n in ns:
        stats = agreement(groups_c, n, len(dataset.C_SEEDS))
        rows.append([
            str(n),
            str(stats["groups"]),
            fmt(stats["unanimous"]),
            fmt(stats["pairwise"]),
            fmt(stats["choices"], 2),
            fmt(stats["prob_sd"], 4),
            fmt(stats["prob_sd_max"], 4),
            fmt(stats["moved"]),
            fmt(agrees_with_a(calls, n)),
            fmt(accuracy(by(calls, n=n, condition="C"))),
        ])
    out.append(table(
        ["N", "문장", "3회 모두 일치", "쌍별 일치율", "서로 다른 답 수(평균)", "정답확률 표준편차(평균)",
         "표준편차 최댓값", "확률이 흔들린 문장 수", "A와 일치율", "C 정확도"],
        rows,
    ))
    out.append("")
    out.append("표준편차는 문장별 3회 관측의 표본 표준편차를 문장 전체로 평균한 값.")
    out.append("")

    # --- reproducibility
    out.append("## 4. 재현성 (조건 A 1회 + E 2회, 캐시 off)")
    out.append("")
    groups_e = observations(calls, ("A", "E"))
    rows = []
    for n in ns:
        stats = agreement(groups_e, n, 1 + dataset.E_REPEATS)
        rows.append([
            str(n),
            str(stats["groups"]),
            fmt(stats["unanimous"]),
            fmt(stats["pairwise"]),
            fmt(stats["choices"], 2),
            fmt(stats["prob_sd"], 4),
            fmt(stats["prob_sd_max"], 4),
            fmt(stats["moved"]),
            fmt(accuracy(by(calls, n=n, condition="E"))),
        ])
    out.append(table(
        ["N", "문장", "3회 모두 일치", "쌍별 일치율", "서로 다른 답 수(평균)", "정답확률 표준편차(평균)",
         "표준편차 최댓값", "확률이 흔들린 문장 수", "E 정확도"],
        rows,
    ))
    out.append("")

    # --- confusion pairs at N=20 A
    biggest = max(ns) if ns else None
    out.append(f"## 5. 오답 쌍 상위 10개 (N={biggest}, 조건 A)")
    out.append("")
    wrong = [c for c in ok(by(calls, n=biggest, condition="A")) if not c["correct"]]
    pairs = collections.Counter((c["gold"], c["choice"]) for c in wrong)
    if pairs:
        rows = [
            [str(rank), gold, choice, str(count),
             fmt(mean(c["gold_prob"] for c in wrong if (c["gold"], c["choice"]) == (gold, choice))),
             fmt(mean(c["top1_prob"] for c in wrong if (c["gold"], c["choice"]) == (gold, choice)))]
            for rank, ((gold, choice), count) in enumerate(pairs.most_common(10), start=1)
        ]
        out.append(table(["#", "정답", "선택", "건수", "정답확률 평균", "선택확률 평균"], rows))
        out.append("")
        out.append(f"조건 A, N={biggest}에서 오답은 총 {len(wrong)}건 / {len(ok(by(calls, n=biggest, condition='A')))}건.")
    else:
        out.append(f"조건 A, N={biggest}에서 오답 없음 (정확도 1.000).")
    out.append("")

    out.append(f"## 5b. 2위로 올라온 카테고리 상위 10쌍 (N={biggest}, 조건 A)")
    out.append("")
    out.append(
        "정확도가 포화해 혼동 행렬이 비므로, 정답 다음으로 확률이 높았던 카테고리를 센다. "
        "2위 확률이 0인 호출(나머지가 전부 0이라 2위가 임의로 정해지는 경우)은 제외한다."
    )
    out.append("")
    subset = [c for c in ok(by(calls, n=biggest, condition="A")) if c.get("top2") and c["top2_prob"] > 0]
    runner = collections.Counter((c["gold"], c["top2"]) for c in subset if c["correct"])
    rows = []
    for rank, ((gold, second), count) in enumerate(runner.most_common(10), start=1):
        group = [c for c in subset if (c["gold"], c["top2"]) == (gold, second)]
        rows.append([
            str(rank), gold, second, str(count),
            fmt(mean(c["top2_prob"] for c in group), 4),
            fmt(mean(c["margin"] for c in group), 4),
        ])
    out.append(
        table(["#", "정답", "2위", "건수", "2위 확률 평균", "마진 평균"], rows)
        if rows
        else f"N={biggest} 조건 A에서 2위 확률이 0보다 큰 호출이 없음."
    )
    out.append("")
    out.append(
        f"조건 A·N={biggest} 80건 중 2위 확률이 0보다 큰 호출은 {len(subset)}건, "
        f"나머지는 정답 1.00 / 나머지 전부 0.00."
    )
    out.append("")
    out.append(f"같은 표를 전체 조건(N={biggest}, A·B·C·D·E 640건)으로 확장하면:")
    out.append("")
    wide = [c for c in ok(by(calls, n=biggest)) if c.get("top2") and c["top2_prob"] > 0]
    wide_runner = collections.Counter((c["gold"], c["top2"]) for c in wide)
    wide_rows = []
    for rank, ((gold, second), count) in enumerate(wide_runner.most_common(10), start=1):
        group = [c for c in wide if (c["gold"], c["top2"]) == (gold, second)]
        wide_rows.append([
            str(rank), gold, second, str(count),
            fmt(mean(c["top2_prob"] for c in group), 4),
            fmt(mean(c["margin"] for c in group), 4),
            ", ".join(sorted({c["condition"] for c in group})),
        ])
    out.append(
        table(["#", "정답", "2위", "건수", "2위 확률 평균", "마진 평균", "조건"], wide_rows)
        if wide_rows
        else "데이터 없음"
    )
    out.append("")

    out.append("## 5c. 정답 확률이 가장 낮았던 호출 15건 (전체 조건)")
    out.append("")
    lowest = sorted(ok(calls), key=lambda c: c["gold_prob"])[:15]
    rows = [[
        fmt(c["gold_prob"], 2), fmt(c["margin"], 2), str(c["n"]), c["condition"] + c["variant"],
        c["gold"], str(c.get("top2")), fmt(c["top2_prob"], 2), c["text"],
    ] for c in lowest]
    out.append(table(["정답확률", "마진", "N", "조건", "정답", "2위", "2위확률", "문장"], rows))
    out.append("")

    # --- per-category accuracy at N=20 A
    out.append(f"## 6. 카테고리별 정확도 (N={biggest}, 조건 A)")
    out.append("")
    subset = ok(by(calls, n=biggest, condition="A"))
    rows = []
    for category in dataset.all_category_names():
        rows_for = [c for c in subset if c["gold"] == category]
        if not rows_for:
            continue
        rows.append([
            category,
            str(len(rows_for)),
            fmt(accuracy(rows_for)),
            fmt(mean(c["gold_prob"] for c in rows_for), 4),
            fmt(min(c["gold_prob"] for c in rows_for), 2),
            fmt(mean(c["confidence"] for c in rows_for), 4),
            ", ".join(sorted({c["choice"] for c in rows_for if not c["correct"]})) or "-",
            ", ".join(sorted({str(c["top2"]) for c in rows_for if c["top2_prob"] > 0})) or "-",
        ])
    out.append(table(
        ["카테고리", "문장", "정확도", "정답확률 평균", "정답확률 최솟값", "confidence 평균", "오답 선택", "2위 카테고리"],
        rows,
    ))
    out.append("")

    # --- position effect
    out.append(f"## 7. 정답 선택지의 제시 위치별 정확도 (N={biggest}, 조건 C)")
    out.append("")
    subset = ok(by(calls, n=biggest, condition="C"))
    rows = []
    if subset:
        buckets: dict[str, list[dict]] = collections.defaultdict(list)
        for call in subset:
            position = call.get("gold_pos")
            if position is None:
                continue
            third = position / max(call["n"], 1)
            key = "앞 1/3" if third < 1 / 3 else ("가운데 1/3" if third < 2 / 3 else "뒤 1/3")
            buckets[key].append(call)
        for key in ("앞 1/3", "가운데 1/3", "뒤 1/3"):
            group = buckets.get(key, [])
            if group:
                rows.append([
                    key,
                    str(len(group)),
                    fmt(accuracy(group)),
                    fmt(mean(c["gold_prob"] for c in group), 4),
                    fmt(min(c["gold_prob"] for c in group), 2),
                    fmt(mean(c["margin"] for c in group), 4),
                ])
    out.append(table(["정답 위치", "호출", "정확도", "정답확률 평균", "정답확률 최솟값", "마진 평균"], rows) if rows else "데이터 없음")
    out.append("")

    if errors:
        out.append("## 8. 오류")
        out.append("")
        counter = collections.Counter(e["error"].split(":")[0] for e in errors)
        out.append(table(["오류", "건수"], [[k, str(v)] for k, v in counter.most_common()]))
        out.append("")

    out.append(f"<!-- generated {time.strftime('%Y-%m-%d %H:%M:%S')} by experiments/branches/report.py -->")
    SUMMARY.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {SUMMARY} ({len(calls)} calls, {len(errors)} errors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
