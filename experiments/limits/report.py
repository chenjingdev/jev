"""Turn results.json into summary.md: one table per measurement, numbers only.

    uv run python experiments/limits/report.py
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


# ------------------------------------------------------------------- helpers


def mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return statistics.fmean(values) if values else None


def median(values) -> float | None:
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def p95(values) -> float | None:
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    return values[min(len(values) - 1, int(round(0.95 * (len(values) - 1))))]


def fmt(value, places: int = 3) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.{places}f}"
    return str(value)


def table(header: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "데이터 없음"
    line = "| " + " | ".join(header) + " |"
    rule = "|" + "|".join("---" for _ in header) + "|"
    body = "\n".join("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join([line, rule, body])


def load() -> tuple[dict, list[dict]]:
    body = json.loads(RESULTS.read_text(encoding="utf-8"))
    return body.get("meta", {}), body.get("calls", [])


def by(calls: list[dict], **filters) -> list[dict]:
    out = calls
    for key, value in filters.items():
        out = [c for c in out if c.get(key) == value]
    return out


def ok(calls: list[dict]) -> list[dict]:
    return [c for c in calls if not c.get("error")]


def accuracy(calls: list[dict]) -> float | None:
    rows = [c for c in ok(calls) if c.get("correct") is not None]
    return sum(1 for c in rows if c["correct"]) / len(rows) if rows else None


def stats_row(calls: list[dict]) -> list[str]:
    """The block of numbers every axis table repeats."""
    rows = ok(calls)
    golds = [c["gold_prob"] for c in rows if c.get("gold_prob") is not None]
    latencies = [c.get("latency_ms") for c in rows]
    tokens = [c.get("input_tokens") for c in rows]
    return [
        str(len(rows)),
        fmt(accuracy(rows)),
        fmt(mean(golds), 4),
        fmt(min(golds), 2) if golds else "-",
        fmt(mean(c["margin"] for c in rows), 4),
        str(sum(1 for g in golds if g < 1.0)),
        fmt(median(latencies), 1),
        fmt(p95(latencies), 1),
        fmt(mean(tokens), 1),
    ]


STATS_HEADER = [
    "호출", "정확도", "정답확률 평균", "정답확률 최솟값", "마진 평균",
    "정답확률<1.0", "latency 중앙(ms)", "latency p95(ms)", "input토큰 평균",
]


def top3_text(call: dict) -> str:
    return ", ".join(f"{name} {value:.2f}" for name, value in call.get("top3", []))


def wrong_rows(calls: list[dict]) -> list[list[str]]:
    rows = []
    for call in sorted(ok(calls), key=lambda c: (c.get("axis", ""), c.get("condition", ""), c.get("sample_id", ""))):
        if call.get("correct") is False:
            rows.append([
                call.get("axis", ""),
                call.get("condition", ""),
                call.get("sample_id", ""),
                (call.get("text") or "")[:60],
                call.get("gold") or "",
                call.get("choice") or "",
                fmt(call.get("gold_prob"), 2),
                top3_text(call),
            ])
    return rows


WRONG_HEADER = ["축", "조건", "id", "문장", "정답", "선택", "정답확률", "확률 상위 3개"]


# ---------------------------------------------------------------------- report


def main() -> int:
    if not RESULTS.exists():
        print(f"missing {RESULTS}", file=sys.stderr)
        return 1
    meta, calls = load()
    answered = ok(calls)
    errors = [c for c in calls if c.get("error")]

    out: list[str] = []
    out.append("# 한계 실험 결과 (5축)")
    out.append("")
    resolved = next((c.get("model_resolved") for c in answered if c.get("model_resolved")), None)
    out.append(f"- 모델: `{meta.get('model')}` (요청) · `{resolved}` (응답)")
    out.append(f"- 지시문: `{meta.get('instructions')}`")
    out.append(f"- 축 4 지시문: `{meta.get('long_instructions')}`")
    out.append(
        f"- 선택지 풀: 정답 가능 {len(dataset.CATEGORIES)}개 + 방해 갈래 "
        f"{len(dataset.DISTRACTORS)}개 = {len(dataset.ALL_CATEGORIES)}개"
    )
    out.append(f"- 기록된 호출: {len(calls)}건 (성공 {len(answered)}, 오류 {len(errors)})")
    total_in = sum(c.get("input_tokens") or 0 for c in calls)
    total_out = sum(c.get("output_tokens") or 0 for c in calls)
    out.append(f"- 총 input tokens {total_in:,} / output tokens {total_out:,} (합계 {total_in + total_out:,})")
    out.append(f"- 총 소요 시간 {meta.get('elapsed_s', 0):,.1f}s")
    out.append(f"- 총 비용 ${(total_in + total_out) * 0.042 / 1e6:.4f} (input·output $0.042/Mtok 기준)")
    lat = [c.get("latency_ms") for c in answered]
    out.append(
        f"- latency_ms 중앙값 {fmt(median(lat), 1)} / p95 {fmt(p95(lat), 1)} / "
        f"최대 {fmt(max((v for v in lat if v is not None), default=None), 1)}"
    )
    if meta.get("max_options_accepted"):
        out.append(
            f"- 선택지 상한: {meta['max_options_accepted']}개 통과, "
            f"{meta.get('min_options_refused')}개 거부"
        )
    out.append("")
    out.append(
        "축 3(반복)과 선택지 상한 탐색만 캐시를 끄고 호출했다. "
        "`sif/cache.py::_canonical`이 `sort_keys=True`로 캐시 키를 만들어 같은 질문의 반복이 "
        "첫 답을 그대로 돌려받기 때문."
    )
    out.append("")

    # ---------------------------------------------------------------- axis 1
    width = by(calls, axis="width")
    out.append("## 축 1. 갈래 폭 (width)")
    out.append("")
    out.append("정답 명확한 문장 160개, 카테고리 80개. N>80의 추가 갈래는 다른 도메인 방해 갈래.")
    out.append("")
    rows = []
    for n in dataset.N_VALUES:
        subset = by(width, n=n)
        if not subset:
            continue
        rows.append([str(n), str(len(dataset.width_samples(n)))] + stats_row(subset))
    out.append(table(["N", "문장"] + STATS_HEADER, rows))
    out.append("")
    wrong = [c for c in ok(width) if c.get("correct") is False]
    out.append(f"오답 {len(wrong)}건 / 성공 호출 {len(ok(width))}건.")
    out.append("")
    if wrong:
        out.append(table(WRONG_HEADER, wrong_rows(width)))
        out.append("")
        pairs = collections.Counter((c["gold"], c["choice"]) for c in wrong)
        out.append("오답 쌍 상위 10개:")
        out.append("")
        out.append(table(
            ["정답", "선택", "건수", "N"],
            [[gold, choice, str(count),
              ", ".join(str(x) for x in sorted({c["n"] for c in wrong if (c["gold"], c["choice"]) == (gold, choice)}))]
             for (gold, choice), count in pairs.most_common(10)],
        ))
        out.append("")
    out.append("N별 2위로 올라온 카테고리 상위 5개 (정답 맞힌 호출 중 2위 확률>0):")
    out.append("")
    rows = []
    for n in dataset.N_VALUES:
        subset = [c for c in ok(by(width, n=n)) if c.get("correct") and (c.get("top2_prob") or 0) > 0]
        counter = collections.Counter(c["top2"] for c in subset)
        rows.append([
            str(n), str(len(subset)),
            ", ".join(f"{name}({count})" for name, count in counter.most_common(5)) or "-",
        ])
    out.append(table(["N", "2위 확률>0 호출", "2위 카테고리"], rows))
    out.append("")
    out.append("방해 갈래(정답이 될 수 없는 175개)가 선택된 횟수:")
    out.append("")
    distractor_names = {c.name for c in dataset.DISTRACTORS}
    rows = []
    for n in dataset.N_VALUES:
        subset = ok(by(width, n=n))
        picked = [c for c in subset if c["choice"] in distractor_names]
        counter = collections.Counter(c["choice"] for c in picked)
        rows.append([
            str(n), str(len(subset)), str(len(picked)),
            ", ".join(f"{name}({count})" for name, count in counter.most_common(5)) or "-",
        ])
    out.append(table(["N", "호출", "방해 갈래 선택", "선택된 방해 갈래"], rows))
    out.append("")

    # ---------------------------------------------------------------- axis 2
    neighbors = by(calls, axis="neighbors")
    out.append("## 축 2. 근접 갈래 (neighbors)")
    out.append("")
    out.append("가족 8개 × 카테고리 4개 × 문장 3개 = 96문장. 단서는 단어 하나.")
    out.append("")
    rows = []
    for condition, label in (("fam", "가족 4갈래"), ("all80", "전체 80갈래")):
        subset = by(neighbors, condition=condition)
        if subset:
            rows.append([label] + stats_row(subset))
    out.append(table(["조건"] + STATS_HEADER, rows))
    out.append("")
    out.append("가족별 정확도:")
    out.append("")
    rows = []
    for family, members in dataset.NEIGHBOR_FAMILIES:
        row = [family, ", ".join(members)]
        for condition in ("fam", "all80"):
            subset = by(neighbors, condition=condition, family=family)
            row.append(f"{fmt(accuracy(subset))} ({len(ok(subset))})")
        rows.append(row)
    out.append(table(["가족", "카테고리", "가족 4갈래", "전체 80갈래"], rows))
    out.append("")
    wrong = [c for c in ok(neighbors) if c.get("correct") is False]
    out.append(f"오답 {len(wrong)}건 / 성공 호출 {len(ok(neighbors))}건.")
    out.append("")
    if wrong:
        out.append(table(WRONG_HEADER, wrong_rows(neighbors)))
        out.append("")

    # ---------------------------------------------------------------- axis 3
    ambiguous = by(calls, axis="ambiguous")
    out.append("## 축 3. 애매 문장 (ambiguous)")
    out.append("")
    out.append(
        "두 카테고리에 걸친 문장 40개, 20갈래, 캐시 off로 3회 반복. "
        "기대 분배는 사람이 미리 적어 둔 값."
    )
    out.append("")
    expected_by_id = {item.id: dict(item.expected) for item in dataset.AMBIGUOUS}
    rows = []
    for repeat in range(1, dataset.AMBIGUOUS_REPEATS + 1):
        subset = ok(by(ambiguous, repeat=repeat))
        if not subset:
            continue
        hits = 0
        mae = []
        tvd = []
        for call in subset:
            expected = expected_by_id[call["sample_id"]]
            top2 = {name for name, _ in call.get("top3", [])[:2]}
            hits += top2 == set(expected)
            probs = call.get("probabilities", {})
            mae.append(mean(abs(weight - probs.get(name, 0.0)) for name, weight in expected.items()))
            names = set(expected) | set(probs)
            tvd.append(0.5 * sum(abs(expected.get(n, 0.0) - probs.get(n, 0.0)) for n in names))
        tops = [c["top1_prob"] for c in subset]
        rows.append([
            f"r{repeat}", str(len(subset)),
            fmt(hits / len(subset)),
            fmt(mean(mae), 4), fmt(mean(tvd), 4),
            fmt(mean(tops), 4), fmt(min(tops), 2),
            str(sum(1 for t in tops if t >= 1.0)),
            fmt(median(c.get("latency_ms") for c in subset), 1),
        ])
    out.append(table(
        ["반복", "호출", "top2 집합 일치율", "기대-실제 절대오차(평균)", "TVD 평균",
         "top1 확률 평균", "top1 최솟값", "top1=1.00 건수", "latency 중앙(ms)"],
        rows,
    ))
    out.append("")
    out.append("top1 확률 분포 (3회 합계 120건):")
    out.append("")
    buckets = [("1.00", 1.0, 1.01), ("0.90~0.99", 0.90, 1.0), ("0.70~0.89", 0.70, 0.90),
               ("0.50~0.69", 0.50, 0.70), ("<0.50", 0.0, 0.50)]
    tops = [c["top1_prob"] for c in ok(ambiguous)]
    out.append(table(
        ["top1 확률", "건수", "비율"],
        [[label, str(sum(1 for t in tops if low <= t < high)),
          fmt(sum(1 for t in tops if low <= t < high) / len(tops)) if tops else "-"]
         for label, low, high in buckets],
    ))
    out.append("")
    groups: dict[str, list[dict]] = collections.defaultdict(list)
    for call in ok(ambiguous):
        groups[call["sample_id"]].append(call)
    complete = {k: sorted(v, key=lambda c: c["repeat"]) for k, v in groups.items()
                if len(v) == dataset.AMBIGUOUS_REPEATS}
    flipped = {k: v for k, v in complete.items() if len({c["choice"] for c in v}) > 1}
    flips = sum(sum(1 for a, b in zip(v, v[1:]) if a["choice"] != b["choice"]) for v in complete.values())
    out.append(
        f"3회 모두 같은 top1: {len(complete) - len(flipped)}/{len(complete)}문장, "
        f"뒤집힌 문장 {len(flipped)}개, 인접 반복 사이 뒤집힘 {flips}회."
    )
    out.append("")
    if flipped:
        out.append(table(
            ["id", "문장", "기대", "3회 선택", "3회 top1 확률"],
            [[k, (v[0].get("text") or "")[:44],
              ", ".join(f"{n} {w:.1f}" for n, w in expected_by_id[k].items()),
              " → ".join(c["choice"] for c in v),
              " → ".join(f"{c['top1_prob']:.2f}" for c in v)]
             for k, v in sorted(flipped.items())],
        ))
        out.append("")
    out.append("문장별 기대 분배와 실제 확률 (r1):")
    out.append("")
    rows = []
    for item in dataset.AMBIGUOUS:
        call = next((c for c in ok(by(ambiguous, sample_id=item.id, repeat=1))), None)
        if call is None:
            continue
        probs = call.get("probabilities", {})
        rows.append([
            item.id, item.text[:40],
            ", ".join(f"{n} {w:.1f}" for n, w in item.expected.items()),
            ", ".join(f"{n} {probs.get(n, 0.0):.2f}" for n in item.expected),
            call["choice"], fmt(call["top1_prob"], 2),
            "O" if {n for n, _ in call.get("top3", [])[:2]} == set(item.expected) else "X",
        ])
    out.append(table(["id", "문장", "기대", "실제(기대 카테고리)", "top1", "top1 확률", "top2 집합"], rows))
    out.append("")

    # ---------------------------------------------------------------- axis 4
    length = by(calls, axis="length")
    out.append("## 축 4. 긴 state (length)")
    out.append("")
    out.append(
        "이전 20개 카테고리 문장 20개를 무관한 한국어 약관·공지 텍스트 안에 묻고 20갈래로 물었다. "
        "필러는 문의처럼 보이는 문장을 쓰지 않는다."
    )
    out.append("")
    rows = []
    tiers = sorted({t for t in (c.get("tier") for c in ok(length)) if t is not None})
    for tier in tiers:
        subset = by(length, tier=tier, position="middle")
        if not subset:
            continue
        rows.append([f"{tier:,}", fmt(mean(c.get("state_chars") for c in ok(subset)), 0)] + stats_row(subset))
    out.append(table(["목표 state 토큰", "state 문자수 평균"] + STATS_HEADER, rows))
    out.append("")
    out.append("위치별 (최상위 길이):")
    out.append("")
    rows = []
    top_tier = max(tiers) if tiers else None
    for position, label in (("front", "앞"), ("middle", "중간"), ("end", "끝")):
        subset = by(length, tier=top_tier, position=position)
        if subset:
            rows.append([label] + stats_row(subset))
    out.append(table(["위치"] + STATS_HEADER, rows))
    out.append("")
    wrong = [c for c in ok(length) if c.get("correct") is False]
    out.append(f"오답 {len(wrong)}건 / 성공 호출 {len(ok(length))}건.")
    out.append("")
    if wrong:
        out.append(table(WRONG_HEADER, wrong_rows(length)))
        out.append("")
    long_errors = [c for c in length if c.get("error")]
    if long_errors:
        out.append("축 4 오류:")
        out.append("")
        out.append(table(
            ["call_id", "목표 토큰", "위치", "state 문자수", "status", "본문"],
            [[c["call_id"], str(c.get("tier")), str(c.get("position")), str(c.get("state_chars")),
              str(c.get("status")), (c.get("body") or c.get("error") or "")[:90]] for c in long_errors],
        ))
        out.append("")

    # ---------------------------------------------------------------- axis 5
    traps = by(calls, axis="traps")
    out.append("## 축 5. 함정 문장 (traps)")
    out.append("")
    out.append("정답은 하나로 명확하지만 표면 단서가 오도하는 문장 50개, 유형별 10개.")
    out.append("")
    rows = []
    for condition, label in (("n20", "20갈래"), ("n80", "80갈래")):
        subset = by(traps, condition=condition)
        if subset:
            rows.append([label] + stats_row(subset))
    out.append(table(["조건"] + STATS_HEADER, rows))
    out.append("")
    kinds = {trap.id: trap.kind for trap in dataset.TRAPS}
    rows = []
    for kind in dict.fromkeys(trap.kind for trap in dataset.TRAPS):
        row = [kind]
        for condition in ("n20", "n80"):
            subset = [c for c in by(traps, condition=condition) if kinds.get(c["sample_id"]) == kind]
            row.append(f"{fmt(accuracy(subset))} ({len(ok(subset))})")
            row.append(fmt(mean(c["gold_prob"] for c in ok(subset)), 3))
        rows.append(row)
    out.append(table(
        ["유형", "20갈래 정확도", "20갈래 정답확률", "80갈래 정확도", "80갈래 정답확률"], rows,
    ))
    out.append("")
    wrong = [c for c in ok(traps) if c.get("correct") is False]
    out.append(f"오답 {len(wrong)}건 / 성공 호출 {len(ok(traps))}건.")
    out.append("")
    if wrong:
        out.append(table(WRONG_HEADER, wrong_rows(traps)))
        out.append("")

    # ---------------------------------------------------------------- summary
    out.append("## 축별 한 줄 (숫자만)")
    out.append("")
    lines = []
    for n in dataset.N_VALUES:
        subset = by(width, n=n)
        if subset:
            lines.append(f"N={n} {fmt(accuracy(subset))}")
    out.append(f"- 축 1: 정확도 " + ", ".join(lines))
    lines = []
    for condition, label in (("fam", "가족 4갈래"), ("all80", "전체 80갈래")):
        subset = by(neighbors, condition=condition)
        if subset:
            lines.append(f"{label} {fmt(accuracy(subset))}")
    out.append(f"- 축 2: 정확도 " + ", ".join(lines))
    tops = [c["top1_prob"] for c in ok(ambiguous)]
    hits = 0
    for call in ok(ambiguous):
        if {n for n, _ in call.get("top3", [])[:2]} == set(expected_by_id[call["sample_id"]]):
            hits += 1
    out.append(
        f"- 축 3: top2 집합 일치 {hits}/{len(ok(ambiguous))}, "
        f"top1=1.00 {sum(1 for t in tops if t >= 1.0)}/{len(tops)}, "
        f"top1 평균 {fmt(mean(tops), 3)}, 뒤집힌 문장 {len(flipped)}/{len(complete)}"
    )
    lines = []
    for tier in tiers:
        subset = by(length, tier=tier, position="middle")
        if subset:
            lines.append(f"{tier:,} {fmt(accuracy(subset))}")
    out.append(
        f"- 축 4: 정확도 " + ", ".join(lines)
        + f" / 오류 {len(long_errors)}건"
    )
    lines = []
    for condition, label in (("n20", "20갈래"), ("n80", "80갈래")):
        subset = by(traps, condition=condition)
        if subset:
            lines.append(f"{label} {fmt(accuracy(subset))}")
    out.append(f"- 축 5: 정확도 " + ", ".join(lines))
    out.append("")

    out.append("## 전체 오답 목록")
    out.append("")
    all_wrong = wrong_rows(calls)
    out.append(f"성공 호출 {len(answered)}건 중 오답 {len(all_wrong)}건.")
    out.append("")
    out.append(table(WRONG_HEADER, all_wrong))
    out.append("")

    if errors:
        out.append("## 오류")
        out.append("")
        counter = collections.Counter(
            (e.get("axis"), e.get("status"), (e.get("error") or "").split(":")[0]) for e in errors
        )
        out.append(table(
            ["축", "status", "오류", "건수"],
            [[str(axis), str(status), str(name), str(count)]
             for (axis, status, name), count in counter.most_common()],
        ))
        out.append("")
        out.append(table(
            ["call_id", "status", "본문"],
            [[e["call_id"], str(e.get("status")), (e.get("body") or e.get("error") or "")[:120]]
             for e in errors[:40]],
        ))
        out.append("")

    out.append(f"<!-- generated {time.strftime('%Y-%m-%d %H:%M:%S')} by experiments/limits/report.py -->")
    SUMMARY.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {SUMMARY} ({len(calls)} calls, {len(errors)} errors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
