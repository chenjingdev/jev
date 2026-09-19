"""A virtual mouse: an overlay cursor that shows where Jev is looking and moving.

    uv run python eye/cursor.py            # start the overlay, listen on the socket
    uv run python eye/cursor.py --demo     # start it and drive it in a loop

The overlay is a transparent, click-through window above everything, on every
Space. It never touches the real pointer; it is only for watching. Another
process drives it through a unix socket with one JSON object per line:

    {"op": "move", "x": 800, "y": 400}                 glide to a point (ms optional)
    {"op": "click"}                                    pulse at the current position
    {"op": "look", "x": 700, "y": 350, "w": 200, "h": 100, "label": "결제하기 0.83"}
    {"op": "heat", "cells": [[x, y, w, h, p], ...]}    ghost cells with probabilities
    {"op": "label", "text": "쌓기 → 오른쪽 벽"}         status line under the cursor
    {"op": "clear"}                                    drop look/heat/label
    {"op": "show"} / {"op": "hide"}

Coordinates are screen points with the origin at the top-left of the main
display, the same frame `screencapture` and Vision use. Use `Cursor` from
`cursor_client.py` instead of writing to the socket by hand.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import socket
import sys
import threading
import time

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSMakeRect,
    NSScreen,
    NSString,
    NSView,
    NSWindow,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
)
from Foundation import NSObject, NSTimer
from Quartz import CGShieldingWindowLevel

SOCKET_PATH = os.environ.get("JEV_CURSOR_SOCKET", "/tmp/jev-cursor.sock")

FPS = 60
GLIDE_MS = 350        # default travel time for a move
CLICK_MS = 450        # pulse duration
TRAIL = 24            # positions kept for the tail

#: One colour for the whole overlay so it reads as a single agent on screen.
INK = (0.10, 0.75, 0.55)


def _ease(t: float) -> float:
    """Ease-in-out cubic: the cursor leaves and arrives softly."""
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


class State:
    """Everything the view draws, owned by the main thread; the socket thread
    only queues commands."""

    def __init__(self) -> None:
        self.x = 0.0
        self.y = 0.0
        self.from_xy = (0.0, 0.0)
        self.to_xy = (0.0, 0.0)
        self.move_start = 0.0
        self.move_ms = GLIDE_MS
        self.click_at = 0.0
        self.look: dict | None = None
        self.heat: list[list[float]] = []
        self.label: str | None = None
        self.visible = True
        self.trail: list[tuple[float, float]] = []
        self.lock = threading.Lock()
        self.queue: list[dict] = []

    def post(self, command: dict) -> None:
        with self.lock:
            self.queue.append(command)

    def drain(self) -> list[dict]:
        with self.lock:
            commands, self.queue = self.queue, []
        return commands

    def apply(self, command: dict, now: float) -> None:
        op = command.get("op")
        if op == "move":
            self.from_xy = (self.x, self.y)
            self.to_xy = (float(command["x"]), float(command["y"]))
            self.move_start = now
            self.move_ms = float(command.get("ms", GLIDE_MS))
        elif op == "click":
            self.click_at = now
        elif op == "look":
            self.look = command
        elif op == "heat":
            self.heat = command.get("cells", [])
        elif op == "label":
            self.label = command.get("text")
        elif op == "clear":
            self.look, self.heat, self.label = None, [], None
        elif op == "show":
            self.visible = True
        elif op == "hide":
            self.visible = False

    def tick(self, now: float) -> None:
        elapsed = (now - self.move_start) * 1000
        t = 1.0 if self.move_ms <= 0 else min(1.0, elapsed / self.move_ms)
        k = _ease(t)
        self.x = self.from_xy[0] + (self.to_xy[0] - self.from_xy[0]) * k
        self.y = self.from_xy[1] + (self.to_xy[1] - self.from_xy[1]) * k
        if t < 1.0 or not self.trail or self.trail[-1] != (self.x, self.y):
            self.trail.append((self.x, self.y))
            del self.trail[:-TRAIL]


class OverlayView(NSView):
    """Draws the cursor, its tail, the click pulse, the gaze box and the heat cells."""

    state: State
    screen_h: float

    def initWithFrame_state_(self, frame, state: State):
        self = objc.super(OverlayView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.state = state
        self.screen_h = frame.size.height
        return self

    def isFlipped(self) -> bool:
        # top-left origin, so the drawing code can use screen coordinates as-is
        return True

    def drawRect_(self, rect) -> None:
        s = self.state
        if not s.visible:
            return
        now = time.monotonic()
        r, g, b = INK

        # heat: ghost cells, opacity by probability
        for cell in s.heat:
            x, y, w, h, p = cell[:5]
            NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, 0.08 + 0.5 * float(p)).setFill()
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(x, y, w, h), 6, 6).fill()

        # look: the gaze box
        if s.look:
            x, y, w, h = (float(s.look[k]) for k in ("x", "y", "w", "h"))
            NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, 0.9).setStroke()
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSMakeRect(x, y, w, h), 8, 8)
            path.setLineWidth_(3)
            path.stroke()
            if s.look.get("label"):
                draw_text(str(s.look["label"]), x, y - 26)

        # tail: fading dots along the recent path
        n = len(s.trail)
        for i, (tx, ty) in enumerate(s.trail[:-1]):
            a = 0.35 * (i + 1) / n
            NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, a).setFill()
            NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(tx - 3, ty - 3, 6, 6)).fill()

        # click pulse: an expanding ring
        age = (now - s.click_at) * 1000
        if 0 <= age < CLICK_MS:
            k = age / CLICK_MS
            radius = 10 + 40 * k
            NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, 0.8 * (1 - k)).setStroke()
            ring = NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(s.x - radius, s.y - radius, 2 * radius, 2 * radius)
            )
            ring.setLineWidth_(3)
            ring.stroke()

        # the cursor itself: an arrow with a white outline so it reads on any background
        arrow = NSBezierPath.bezierPath()
        arrow.moveToPoint_((s.x, s.y))
        arrow.lineToPoint_((s.x, s.y + 26))
        arrow.lineToPoint_((s.x + 7, s.y + 20))
        arrow.lineToPoint_((s.x + 12, s.y + 31))
        arrow.lineToPoint_((s.x + 16, s.y + 29))
        arrow.lineToPoint_((s.x + 11, s.y + 18))
        arrow.lineToPoint_((s.x + 19, s.y + 18))
        arrow.closePath()
        NSColor.whiteColor().setStroke()
        arrow.setLineWidth_(4)
        arrow.stroke()
        NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, 1.0).setFill()
        arrow.fill()

        if s.label:
            draw_text(s.label, s.x + 22, s.y + 30)


def draw_text(text: str, x: float, y: float) -> None:
    """A label on a filled pill, top-left at (x, y) in the flipped view."""
    attrs = {
        NSFontAttributeName: NSFont.boldSystemFontOfSize_(15),
        NSForegroundColorAttributeName: NSColor.whiteColor(),
    }
    string = NSString.stringWithString_(text)
    size = string.sizeWithAttributes_(attrs)
    pad = 6
    r, g, b = INK
    NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, 0.92).setFill()
    NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(x - pad, y - pad, size.width + 2 * pad, size.height + 2 * pad), 6, 6
    ).fill()
    string.drawAtPoint_withAttributes_((x, y), attrs)


class Driver(NSObject):
    """Main-thread timer: apply queued commands, advance the animation, redraw."""

    state: State
    view: OverlayView

    def initWithState_view_(self, state: State, view: OverlayView):
        self = objc.super(Driver, self).init()
        self.state = state
        self.view = view
        return self

    def tick_(self, _timer) -> None:
        now = time.monotonic()
        for command in self.state.drain():
            self.state.apply(command, now)
        self.state.tick(now)
        self.view.setNeedsDisplay_(True)


def serve(state: State, path: str) -> None:
    """Accept JSON lines on a unix socket, forever. Runs on its own thread."""
    if os.path.exists(path):
        os.unlink(path)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    server.listen(4)
    while True:
        conn, _ = server.accept()
        threading.Thread(target=_handle, args=(state, conn), daemon=True).start()


def _handle(state: State, conn: socket.socket) -> None:
    with conn, conn.makefile("r", encoding="utf-8") as lines:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                state.post(json.loads(line))
            except json.JSONDecodeError:
                print(f"cursor: bad line {line!r}", file=sys.stderr)


def demo(path: str) -> None:
    """Drive the overlay in a loop so it can be seen without any Jev call."""
    from cursor_client import Cursor

    time.sleep(0.5)
    cursor = Cursor(path)
    w, h = 1400, 800
    while True:
        cursor.label("두리번")
        for i in range(6):
            x = 200 + (i % 3) * w / 3 + 80 * math.sin(i)
            y = 150 + (i // 3) * h / 2
            cursor.look(x - 60, y - 40, 180, 90, label=f"칸 {i}  {0.3 + 0.1 * i:.2f}")
            cursor.move(x, y, ms=400)
            time.sleep(0.6)
        cursor.heat([[200 + c * 120, 700, 110, 60, (c + 1) / 8] for c in range(8)])
        cursor.label("고르는 중")
        time.sleep(1.0)
        cursor.move(200 + 7 * 120 + 55, 730, ms=500)
        time.sleep(0.6)
        cursor.click()
        cursor.label("클릭")
        time.sleep(1.0)
        cursor.clear()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", default=SOCKET_PATH)
    parser.add_argument("--demo", action="store_true", help="also run a demo driver")
    args = parser.parse_args()

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    # one window over the union of every display, in Cocoa (bottom-left) coordinates
    frames = [s.frame() for s in NSScreen.screens()]
    left = min(f.origin.x for f in frames)
    bottom = min(f.origin.y for f in frames)
    right = max(f.origin.x + f.size.width for f in frames)
    top = max(f.origin.y + f.size.height for f in frames)
    frame = NSMakeRect(left, bottom, right - left, top - bottom)

    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        frame, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False
    )
    window.setOpaque_(False)
    window.setBackgroundColor_(NSColor.clearColor())
    window.setHasShadow_(False)
    window.setIgnoresMouseEvents_(True)
    window.setLevel_(CGShieldingWindowLevel())
    window.setCollectionBehavior_(
        NSWindowCollectionBehaviorCanJoinAllSpaces
        | NSWindowCollectionBehaviorStationary
        | NSWindowCollectionBehaviorFullScreenAuxiliary
    )

    state = State()
    main_h = NSScreen.mainScreen().frame().size.height
    # The view is flipped (top-left origin, y down) and covers the union of the
    # displays. A screen point (sx, sy) - top-left of the main display, y down -
    # is Cocoa (sx, main_h - sy), which is view point (sx - left, sy + top - main_h).
    # Shifting the bounds origin by (left, main_h - top) makes screen points draw
    # as-is, on every display.
    view = OverlayView.alloc().initWithFrame_state_(
        NSMakeRect(0, 0, frame.size.width, frame.size.height), state
    )
    view.setBoundsOrigin_((left, main_h - top))
    window.setContentView_(view)
    window.orderFrontRegardless()

    driver = Driver.alloc().initWithState_view_(state, view)
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        1 / FPS, driver, "tick:", None, True
    )

    threading.Thread(target=serve, args=(state, args.socket), daemon=True).start()
    if args.demo:
        threading.Thread(target=demo, args=(args.socket,), daemon=True).start()
    print(f"cursor: overlay {int(frame.size.width)}x{int(frame.size.height)}, socket {args.socket}")
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
