"""Walk: several steps of the eye with real clicks, until the goal looks done.

    op run --env-file=<(echo 'TYPESAFE_API_KEY="op://Agent/typesafe jev key/credential"') \
      -- uv run python eye/walk.py --display 3 --goal "검색을 연다"

Each step is `step.look` twice (screen, then the 3x3 zoom) followed by a real
click at the picked element. Before the click the screen stage's answers gate it:

    done  >= DONE_AT   the goal already shows on screen   -> stop, no click
    risky >= RISKY_AT  the click looks irreversible       -> stop, no click, report
    target < SURE_AT   the pick is a guess                -> stop, no click, report

After the click the eye looks again and judges `done` twice: on the screen as
it is, and on what changed - the texts that appeared and disappeared since the
click. The second reading is the one that works: a whole screen is 300+ texts
of tabs, bookmarks and URLs and the goal drowns in it, the diff is the page
that just loaded. If nothing changed, the click did nothing (missed, or the
page is slow); one such repeat stops the walk rather than clicking the same
spot for ever. The walk also
stops at `--max-steps`, and never clicks outside the chosen display.

The real pointer moves. Run this on a display the user has agreed to give up.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

import Quartz
from AppKit import NSScreen

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import retina  # noqa: E402
import sif  # noqa: E402
import step  # noqa: E402
from cursor_client import Cursor  # noqa: E402

DONE_AT = 0.7
RISKY_AT = 0.5
SURE_AT = 0.3  # below this the screen-stage pick is a guess; a guess is not clicked
CHANGED = "The change on screen shows that the goal has been carried out."
SETTLE = 1.2  # seconds for the app to redraw after a click


def display(n: int) -> retina.Region:
    """Display `n` (1-based, NSScreen order) as a top-left-origin region."""
    screens = NSScreen.screens()
    if not 1 <= n <= len(screens):
        raise SystemExit(f"walk: display {n} of {len(screens)}")
    main_h = NSScreen.mainScreen().frame().size.height
    f = screens[n - 1].frame()
    return retina.Region(f.origin.x, main_h - (f.origin.y + f.size.height), f.size.width, f.size.height)


def inside(region: retina.Region, x: float, y: float) -> bool:
    return region.x <= x < region.x + region.w and region.y <= y < region.y + region.h


def click(x: float, y: float) -> None:
    """A real left click: move, press, release, with the pauses apps expect."""
    point = Quartz.CGPointMake(x, y)
    for kind in (Quartz.kCGEventMouseMoved, Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
        event = Quartz.CGEventCreateMouseEvent(None, kind, point, Quartz.kCGMouseButtonLeft)
        # no modifiers, whatever the session thinks is held: a stuck Command
        # once turned every click into "open in a new tab"
        Quartz.CGEventSetFlags(event, 0)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        time.sleep(0.08)


def words(view: retina.View) -> list[str]:
    """Readable texts in reading order; OCR guesses and single characters out."""
    return [
        t.text for t in sorted(view.texts, key=lambda t: (t.row, t.col))
        if t.confidence >= 0.5 and len(t.text) >= 2 and any(ch.isalnum() for ch in t.text)
    ]


def changed(goal: str, before: retina.View, after: retina.View) -> float:
    """How much the change from `before` to `after` looks like the goal being done."""
    b, a = words(before), words(after)
    state = {
        "goal": goal,
        "texts_that_appeared_after_the_click": [t for t in a if t not in set(b)][:60],
        "texts_that_disappeared": [t for t in b if t not in set(a)][:60],
    }
    return float(sif.check(state, CHANGED))


def fingerprint(view: retina.View) -> str:
    body = view.grid_text() + "\n" + "\n".join(sorted(t.text for t in view.texts))
    return hashlib.sha1(body.encode()).hexdigest()[:10]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--display", type=int, default=1, help="1-based NSScreen index; clicks stay inside it")
    parser.add_argument("--max-steps", type=int, default=4)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    sif.configure(model=step.MODEL, cache=not args.no_cache, log=True, timeout=30.0)
    cursor = Cursor()
    cursor.clear()
    screen = display(args.display)
    print(f"display {args.display}: {screen}   done>={DONE_AT} stops, risky>={RISKY_AT} stops")

    previous: retina.View | None = None
    last_click: tuple[float, float] | None = None
    for n in range(1, args.max_steps + 1):
        view, answers, latency, count = step.look(cursor, args.goal, screen, "screen")
        target = answers["target"]
        done, risky = answers["done"].noul, answers["risky"].noul
        ranked = sorted(target.probabilities.items(), key=lambda kv: -kv[1])[:5]
        print(f"\nstep {n} [screen] {count} candidates, {len(view.texts)} texts, Jev {latency * 1000:.0f}ms")
        print(f"  target: {target.choice}  ({view.options()[target.choice]})")
        print("  top5:   " + " ".join(f"{cid} {p:.2f}" for cid, p in ranked))
        if previous is not None:
            if fingerprint(view) == fingerprint(previous):
                cursor.label("no change after the click - stopping")
                print("  the screen did not change after the last click; stopping.")
                return 2
            by_change = changed(args.goal, previous, view)
            print(f"  risky:  {risky:.2f}    done: {done:.2f} on the screen, {by_change:.2f} on the change")
            done = max(done, by_change)
        else:
            print(f"  risky:  {risky:.2f}    done: {done:.2f}")
        previous = view
        if done >= DONE_AT:
            cursor.label(f"done {done:.2f}")
            print(f"  done {done:.2f} >= {DONE_AT}: goal appears achieved; stopping.")
            return 0
        if risky >= RISKY_AT:
            cursor.label(f"risky {risky:.2f} - not clicking")
            print(f"  risky {risky:.2f} >= {RISKY_AT}: not clicking; stopping for a human.")
            return 3
        sure = target.probabilities.get(target.choice, 0)
        if sure < SURE_AT:
            cursor.label(f"only {sure:.2f} sure - not clicking")
            print(f"  the pick is only {sure:.2f} sure (< {SURE_AT}): not clicking; stopping for a human.")
            return 5

        r, c = retina.parse_cell(target.choice)
        time.sleep(0.5)
        zoom, zanswers, zlat, zcount = step.look(cursor, args.goal, view.region.around(r, c), "zoom")
        zt = zanswers["target"]
        print(f"  [zoom] {zcount} candidates, Jev {zlat * 1000:.0f}ms -> {zt.choice} {zt.probabilities.get(zt.choice, 0):.2f}  ({zoom.options()[zt.choice]})")
        x, y = zoom.center(zt.choice)
        if not inside(screen, x, y):
            print(f"  ({x:.0f}, {y:.0f}) is outside display {args.display}; not clicking.")
            return 4
        if last_click is not None and abs(x - last_click[0]) < 8 and abs(y - last_click[1]) < 8:
            cursor.label("same spot again - stopping")
            print(f"  ({x:.0f}, {y:.0f}) is where the last click went and it did not help; stopping.")
            return 2
        last_click = (x, y)
        time.sleep(0.4)
        cursor.click()
        click(x, y)
        print(f"  clicked ({x:.0f}, {y:.0f})")
        # step away so a hover tooltip does not sit in the next capture
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventMouseMoved, Quartz.CGPointMake(x + 40, y + 40), Quartz.kCGMouseButtonLeft))
        time.sleep(SETTLE)

    view, answers, latency, _ = step.look(cursor, args.goal, screen, "screen")
    done = max(answers["done"].noul, changed(args.goal, previous, view))
    print(f"\nafter {args.max_steps} steps: done {done:.2f}" + (" - achieved." if done >= DONE_AT else " - not there yet."))
    return 0 if done >= DONE_AT else 1


if __name__ == "__main__":
    sys.exit(main())
