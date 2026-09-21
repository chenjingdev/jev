"""Turn a take into demo.mp4, playing the Opus turns at FF x and everything else at 1x.

    uv run python gomoku/speedup.py take3.webm take3.json demo.mp4 --ff 8

The page shows a "⏩ 8배속" badge while Opus thinks (?ff=8), so the sped-up stretches
are labelled on screen. Segment boundaries come from the page's phase timeline.
"""

from __future__ import annotations

import argparse
import json
import subprocess


def segments(timeline: list[dict], duration: float, ff: float) -> list[tuple[float, float, float]]:
    """(start, end, speed) covering the whole take."""
    out: list[tuple[float, float, float]] = []
    edges = [(0.0, "idle")] + [(e["t"], e["phase"]) for e in timeline if 0 < e["t"] < duration] + [(duration, "end")]
    for (t, phase), (t2, _) in zip(edges, edges[1:]):
        if t2 - t < 0.05:
            continue
        out.append((t, t2, ff if phase == "opus" else 1.0))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video")
    ap.add_argument("timeline")
    ap.add_argument("out")
    ap.add_argument("--ff", type=float, default=8.0)
    ap.add_argument("--head", type=float, default=0.8, help="seconds to drop at the start")
    args = ap.parse_args()
    meta = json.loads(open(args.timeline).read())
    duration = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", args.video]).decode().strip())
    segs = [(max(a, args.head), b, f) for a, b, f in segments(meta["timeline"], duration, args.ff) if b > args.head]
    parts = []
    for i, (a, b, f) in enumerate(segs):
        parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=(PTS-STARTPTS)/{f}[v{i}]")
    concat = "".join(f"[v{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0,fps=30,format=yuv420p[out]"
    filt = ";".join(parts + [concat])
    subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-i", args.video, "-filter_complex", filt, "-map", "[out]", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-movflags", "+faststart", args.out])
    real = sum(b - a for a, b, _ in segs)
    shown = sum((b - a) / f for a, b, f in segs)
    print(f"{len(segs)} segments, real {real:.0f}s -> {shown:.0f}s ({sum(1 for s in segs if s[2] > 1)} sped up x{args.ff:g})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
