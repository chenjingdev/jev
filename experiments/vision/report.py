"""Turn results.json into summary.md: accuracy against chance per spelling.

    uv run python experiments/vision/report.py
"""

from __future__ import annotations

import collections
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import dataset  # noqa: E402

RESULTS = HERE / "results.json"
SUMMARY = HERE / "summary.md"


def fmt(value, places: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{places}f}"
    return str(value)


def stats(rows: list[dict], chance: float) -> dict:
    """Accuracy, chance, mode-collapse share and mean gold probability."""
    if not rows:
        return {}
    picks = collections.Counter(r["choice"] for r in rows)
    top_pick, top_count = picks.most_common(1)[0]
    return {
        "n": len(rows),
        "acc": sum(1 for r in rows if r["correct"]) / len(rows),
        "chance": chance,
        "collapse": top_count / len(rows),
        "top_pick": top_pick,
        "gold_p": statistics.fmean(r["gold_prob"] for r in rows),
        "top1_p": statistics.fmean(r["top1_prob"] for r in rows),
        "in_tok": statistics.fmean(r["input_tokens"] or 0 for r in rows),
        "latency": statistics.median(r["latency_ms"] for r in rows if r.get("latency_ms")),
    }


def table(header: list[str], lines: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(line) + " |" for line in lines]
    return "\n".join(out)


def main() -> int:
    body = json.loads(RESULTS.read_text(encoding="utf-8"))
    calls = [r for r in body["calls"] if not r.get("error")]
    errors = [r for r in body["calls"] if r.get("error")]
    meta = body.get("meta", {})
    enc = [r for r in calls if r["axis"] == "encode"]
    pix = [r for r in calls if r["axis"] == "pixel"]
    parts: list[str] = []

    parts.append("# vision: results\n")
    parts.append(
        f"model {meta.get('model')}, {len(calls)} calls ok, {len(errors)} errors, "
        f"input {meta.get('input_tokens', 0):,} + output {meta.get('output_tokens', 0):,} tokens, "
        f"{meta.get('elapsed_s', 0):,.0f}s.\n"
    )

    # ---- encode: per format x question, all sizes pooled
    if enc:
        parts.append("## encode: colour grids, by spelling\n")
        parts.append("acc = share correct; chance = 1/palette averaged over the rows; collapse = share of calls that picked the single most-picked option; gold p = mean probability on the right answer.\n")
        for question in dataset.ENCODE_QUESTIONS:
            parts.append(f"### question `{question}`\n")
            lines = []
            for f in dataset.ENCODE_FORMATS:
                rows = [r for r in enc if r["format"] == f and r["question"] == question]
                if not rows:
                    continue
                chance = statistics.fmean(1 / r["palette"] for r in rows)
                s = stats(rows, chance)
                lines.append([
                    f, str(s["n"]), fmt(s["acc"]), fmt(s["chance"]), fmt(s["collapse"]),
                    s["top_pick"], fmt(s["gold_p"]), fmt(s["in_tok"], 0), fmt(s["latency"], 0),
                ])
            parts.append(table(
                ["format", "n", "acc", "chance", "collapse", "top pick", "gold p", "in tok", "ms"], lines,
            ) + "\n")

        parts.append("### by grid size and palette (question `pos`)\n")
        lines = []
        for f in dataset.ENCODE_FORMATS:
            cells = [f]
            for size in dataset.GRID_SIZES:
                for palette in dataset.PALETTE_SIZES:
                    rows = [
                        r for r in enc
                        if r["format"] == f and r["question"] == "pos"
                        and r["size"] == size and r["palette"] == palette
                    ]
                    cells.append(fmt(stats(rows, 1 / palette).get("acc")) if rows else "-")
            lines.append(cells)
        header = ["format"] + [f"{s}x{s} / {p} colours" for s in dataset.GRID_SIZES for p in dataset.PALETTE_SIZES]
        parts.append(table(header, lines) + "\n")

        parts.append("### by grid size and palette (question `mode`)\n")
        lines = []
        for f in dataset.ENCODE_FORMATS:
            cells = [f]
            for size in dataset.GRID_SIZES:
                for palette in dataset.PALETTE_SIZES:
                    rows = [
                        r for r in enc
                        if r["format"] == f and r["question"] == "mode"
                        and r["size"] == size and r["palette"] == palette
                    ]
                    cells.append(fmt(stats(rows, 1 / palette).get("acc")) if rows else "-")
            lines.append(cells)
        parts.append(table(header, lines) + "\n")

        # where in the grid does positional reading fail? (readable formats only)
        parts.append("### positional accuracy by row, readable spellings, 8x8\n")
        lines = []
        for f in ("names", "rgb", "hex", "ppm"):
            rows8 = [r for r in enc if r["format"] == f and r["question"] == "pos" and r["size"] == 8]
            if not rows8:
                continue
            cells = [f]
            for row in range(1, 9):
                sub = [r for r in rows8 if r["row"] == row]
                cells.append(f"{fmt(sum(1 for r in sub if r['correct']) / len(sub))} ({len(sub)})" if sub else "-")
            lines.append(cells)
        parts.append(table(["format"] + [f"row {i}" for i in range(1, 9)], lines) + "\n")

    # ---- pixel: MNIST
    if pix:
        parts.append("## pixel: MNIST digits 14x14, by spelling\n")
        lines = []
        for f in dataset.PIXEL_FORMATS:
            rows = [r for r in pix if r["format"] == f]
            if not rows:
                continue
            s = stats(rows, 0.1)
            lines.append([
                f, str(s["n"]), fmt(s["acc"]), "0.10", fmt(s["collapse"]), s["top_pick"],
                fmt(s["gold_p"]), fmt(s["in_tok"], 0), fmt(s["latency"], 0),
            ])
        parts.append(table(
            ["format", "n", "acc", "chance", "collapse", "top pick", "gold p", "in tok", "ms"], lines,
        ) + "\n")

        parts.append("### per digit (rows: spelling, cols: true digit, cell: correct/10)\n")
        lines = []
        for f in dataset.PIXEL_FORMATS:
            rows = [r for r in pix if r["format"] == f]
            if not rows:
                continue
            cells = [f]
            for d in range(10):
                sub = [r for r in rows if r["gold"] == str(d)]
                cells.append(str(sum(1 for r in sub if r["correct"])) if sub else "-")
            lines.append(cells)
        parts.append(table(["format"] + [str(d) for d in range(10)], lines) + "\n")

        parts.append("### confusion, best spelling (rows: true, cols: picked)\n")
        best = max(dataset.PIXEL_FORMATS, key=lambda f: stats([r for r in pix if r["format"] == f], 0.1).get("acc", -1))
        rows = [r for r in pix if r["format"] == best]
        lines = []
        for d in range(10):
            sub = [r for r in rows if r["gold"] == str(d)]
            counts = collections.Counter(r["choice"] for r in sub)
            lines.append([str(d)] + [str(counts.get(str(p), 0) or "") for p in range(10)])
        parts.append(f"spelling `{best}`\n\n" + table(["true \\ picked"] + [str(p) for p in range(10)], lines) + "\n")

    SUMMARY.write_text("\n".join(parts), encoding="utf-8")
    print("\n".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
