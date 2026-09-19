"""One step of the eye: look at the screen, ask Jev where to go, show it.

    op run --env-file=<(echo 'TYPESAFE_API_KEY="op://Agent/typesafe jev key/credential"') \
      -- uv run python eye/step.py --goal "Wi-Fi 설정을 연다"

Two saccades. Stage one sees the whole display as a 16x9 grid and Jev picks a
cell (160pt wide - several UI elements). Stage two crops the 3x3 cells around
that pick, sees it again as 16x9 (30pt cells) and Jev picks once more. Each
stage is one `sif.ask` with three questions:

    target  Choice over every non-blank cell    -> heat cells + the gaze box
    risky   "clicking there would be irreversible"
    done    "the goal already appears achieved"

Nothing is clicked. The overlay shows the pick and the pulse; the real pointer
stays where it is. Run `eye/cursor.py` first to watch; without it this still
prints the decisions.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import retina  # noqa: E402
import sif  # noqa: E402
from cursor_client import Cursor  # noqa: E402

MODEL = "jev-1.13.0"

TARGET = (
    "The state is a screen reduced to a grid of cell labels plus the texts found on it, "
    "and a goal. Which cell should be clicked next to make progress on the goal?"
)
RISKY = "Clicking the most likely target cell would trigger an irreversible action (payment, deletion, sending, closing without saving)."
DONE = "The goal already appears to be achieved on this screen."

STAGES = ("screen", "zoom")


def look(cursor: Cursor, goal: str, region: retina.Region | None, stage: str) -> tuple[retina.View, dict, float, float]:
    """See the region, ask Jev, paint the answer. Returns the view and the answers."""
    cursor.hide()
    time.sleep(0.05)
    view = retina.see(region)
    cursor.show()
    options = view.options()
    if not options:
        raise SystemExit("retina: nothing but blank cells; nothing to choose from")

    state = {"goal": goal, "stage": stage, "screen": view.state()}
    started = time.perf_counter()
    answers = sif.ask(
        state,
        target=sif.options(options, TARGET),
        risky=RISKY,
        done=DONE,
    )
    latency = time.perf_counter() - started

    target = answers["target"]
    probabilities = dict(target.probabilities)
    cells = []
    for cell_id, p in probabilities.items():
        if p <= 0.01:
            continue
        r, c = retina.parse_cell(cell_id)
        cell = view.region.cell(r, c)
        cells.append([cell.x + 2, cell.y + 2, cell.w - 4, cell.h - 4, p])
    cursor.heat(cells)
    r, c = retina.parse_cell(target.choice)
    box = view.region.cell(r, c)
    cursor.look(box.x, box.y, box.w, box.h, label=f"{target.choice} {probabilities.get(target.choice, 0):.2f}")
    x, y = view.center(target.choice)
    cursor.move(x, y, ms=450)
    cursor.label(f"{stage}: {options[target.choice][:40]}")
    return view, answers, latency, len(options)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goal", required=True, help="what the eye is trying to do, in words")
    parser.add_argument("--region", help="x,y,w,h in screen points; default the main display")
    parser.add_argument("--stages", type=int, default=2, choices=(1, 2))
    parser.add_argument("--no-cache", action="store_true", help="ask again even for an identical screen")
    args = parser.parse_args()

    sif.configure(model=MODEL, cache=not args.no_cache, log=True, timeout=30.0)
    cursor = Cursor()
    cursor.clear()
    region = retina.Region(*(float(v) for v in args.region.split(","))) if args.region else None

    for stage in STAGES[: args.stages]:
        view, answers, latency, n = look(cursor, args.goal, region, stage)
        target = answers["target"]
        ranked = sorted(target.probabilities.items(), key=lambda kv: -kv[1])[:5]
        print(f"[{stage}] {n} candidate cells, {len(view.texts)} texts, Jev {latency * 1000:.0f}ms")
        print(f"  target: {target.choice}  ({view.options()[target.choice]})")
        print("  top5:   " + "  ".join(f"{cid} {p:.2f}" for cid, p in ranked))
        print(f"  risky:  {answers['risky'].noul:.2f}    done: {answers['done'].noul:.2f}")
        r, c = retina.parse_cell(target.choice)
        region = view.region.around(r, c)
        time.sleep(0.6)

    cursor.click()
    x, y = view.center(target.choice)
    print(f"would click at ({x:.0f}, {y:.0f}) - not clicking.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
