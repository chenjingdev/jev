"""Collect training cells for the retina head: screenshot + AX tree, per cell.

    uv run python eye/collect.py                    # one capture of the frontmost window
    uv run python eye/collect.py --apps cmux,Safari,Finder --rounds 5

The accessibility tree is the teacher: for every window it says where the
buttons, text fields, images and texts are, so every grid cell gets a label
without a human. Text the tree does not know about (terminal output, canvas
text, web pages with thin trees) is labelled by OCR. At run time the retina
never sees the tree.

What is stored, per cell: the Vision feature print of the cell (768 floats),
its label, and where it was (app, grid, row, col). Screenshots are not kept -
Slack and KakaoTalk show private conversations, and a feature print cannot be
turned back into pixels or text.

Two grids per window: 16x9 (stage-one cells) and 48x27 (stage-two cells, a
third the size). Blank and text cells are sampled down because they are most
of any screen; button/input/icon cells are all kept.
"""

from __future__ import annotations

import argparse
import random
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import ApplicationServices as AS
import numpy as np
import Quartz
import Vision
from AppKit import NSRunningApplication, NSWorkspace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import retina  # noqa: E402

DATA = HERE / "data"

#: Visual classes only. AX says "button" by behaviour; the retina sees
#: appearance, and a sidebar row that is a button looks exactly like text. So
#: buttons are resolved by what they show: words -> text, small glyph -> icon.
LABELS = ("blank", "text", "input", "icon", "image")
GRIDS = ((16, 9), (48, 27))

#: AX roles -> label. Anything not listed is a container and is skipped.
ROLE_LABEL: dict[str, str] = {
    "AXButton": "button", "AXPopUpButton": "button", "AXMenuButton": "button",
    "AXCheckBox": "button", "AXRadioButton": "button", "AXDisclosureTriangle": "button",
    "AXTextField": "input", "AXTextArea": "input", "AXSearchField": "input", "AXComboBox": "input",
    "AXImage": "icon",
    "AXStaticText": "text", "AXLink": "text", "AXHeading": "text", "AXMenuItem": "text",
    "AXCell": "text", "AXRow": "text",
}
#: When elements overlap in a cell, the most specific wins.
PRIORITY = {"input": 5, "icon": 3, "text": 2, "image": 1, "blank": 0}

#: An AXImage wider than this (points) is a picture, not an icon.
ICON_MAX = 48
#: Largest plausible size (w, h in points) per label; bigger elements are
#: containers that borrowed the role (a whole settings row as AXButton, a chat
#: pane as AXTextArea) and are dropped.
MAX_SIZE = {"input": (900, 320), "icon": (48, 48), "image": (4000, 4000), "text": (4000, 200)}
#: Elements covering more than this share of the window are containers.
CONTAINER_SHARE = 0.25
MAX_ELEMENTS = 4000
MAX_DEPTH = 40

#: Per capture and grid, how many blank / text cells to keep.
KEEP_COMMON = {"blank": 40, "text": 80, "image": 60}


@dataclass(frozen=True)
class Element:
    role: str
    x: float
    y: float
    w: float
    h: float
    has_text: bool = False


# ------------------------------------------------------------------ AX


def ax_value(element, attribute: str):
    err, value = AS.AXUIElementCopyAttributeValue(element, attribute, None)
    return value if err == 0 else None


def ax_point(value) -> tuple[float, float] | None:
    ok, point = AS.AXValueGetValue(value, AS.kAXValueCGPointType, None)
    return (point.x, point.y) if ok else None


def ax_size(value) -> tuple[float, float] | None:
    ok, size = AS.AXValueGetValue(value, AS.kAXValueCGSizeType, None)
    return (size.width, size.height) if ok else None


def window_frame(window) -> retina.Region | None:
    pos, size = ax_value(window, "AXPosition"), ax_value(window, "AXSize")
    if pos is None or size is None:
        return None
    (x, y), (w, h) = ax_point(pos), ax_size(size)
    return retina.Region(x, y, w, h)


def walk(window, frame: retina.Region) -> list[Element]:
    """Every labelled, positioned element inside the window, containers dropped."""
    out: list[Element] = []
    stack = [(window, 0)]
    seen = 0
    while stack and seen < MAX_ELEMENTS:
        node, depth = stack.pop()
        seen += 1
        role = ax_value(node, "AXRole")
        label = ROLE_LABEL.get(str(role), None)
        if label:
            pos, size = ax_value(node, "AXPosition"), ax_value(node, "AXSize")
            if pos is not None and size is not None:
                (x, y), (w, h) = ax_point(pos), ax_size(size)
                title = ax_value(node, "AXTitle") or ax_value(node, "AXValue") or ax_value(node, "AXDescription")
                element = Element(str(role), x, y, w, h, has_text=bool(str(title or "").strip()))
                max_w, max_h = MAX_SIZE[label_of(element)]
                if 0 < w <= max_w and 0 < h <= max_h and w * h < CONTAINER_SHARE * frame.w * frame.h:
                    out.append(element)
        if depth < MAX_DEPTH:
            children = ax_value(node, "AXChildren") or []
            stack.extend((child, depth + 1) for child in children)
    return out


#: A text field shorter than this is a label that happens to be editable
#: (Finder file names, KakaoTalk chat rows), not a place to type.
INPUT_MIN_H = 22


def label_of(element: Element) -> str:
    label = ROLE_LABEL[element.role]
    if label == "button":
        # by appearance: a labelled control reads as text, a bare small one as an icon
        if element.has_text and max(element.w, element.h) > ICON_MAX:
            return "text"
        return "icon" if max(element.w, element.h) <= ICON_MAX else "image"
    if label == "icon" and max(element.w, element.h) > ICON_MAX:
        return "image"
    if label == "input" and element.h < INPUT_MIN_H:
        return "text"
    return label


# ------------------------------------------------------------------ cells


def pixel_features(patch: np.ndarray) -> np.ndarray:
    """A cheap look at the cell: 16x16 contrast-normalised greyscale plus spread
    and gradient energy (259 floats). Not invertible to readable text."""
    h, w = patch.shape
    ys = (np.arange(16) * h / 16).astype(int)
    xs = (np.arange(16) * w / 16).astype(int)
    small = patch[np.minimum(ys, h - 1)][:, np.minimum(xs, w - 1)].astype(np.float32)
    std = float(patch.std())
    small = (small - small.mean()) / (small.std() + 1e-3)
    gx = np.abs(np.diff(patch, axis=1)).mean() if w > 1 else 0.0
    gy = np.abs(np.diff(patch, axis=0)).mean() if h > 1 else 0.0
    return np.concatenate([small.ravel(), [std / 64.0, gx / 32.0, gy / 32.0]]).astype(np.float32)


def feature_print(image) -> np.ndarray:
    request = Vision.VNGenerateImageFeaturePrintRequest.alloc().init()
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, None)
    ok, _ = handler.performRequests_error_([request], None)
    if not ok:
        raise RuntimeError("feature print failed")
    result = request.results()[0]
    data = result.data()
    return np.frombuffer(bytes(data), dtype=np.float32).copy()


def cell_labels(
    frame: retina.Region, elements: list[Element], texts: list[retina.Text], grey: np.ndarray, cols: int, rows: int
) -> list[list[str]]:
    """Grid labels from element overlap, OCR boxes for text the tree lacks, then
    blank/image from pixels for the rest."""
    labels = [["" for _ in range(cols)] for _ in range(rows)]
    boxes = [(label_of(e), e.x, e.y, e.w, e.h) for e in elements]
    boxes += [("text", t.box.x, t.box.y, t.box.w, t.box.h) for t in texts]
    for label, x, y, w, h in boxes:
        c0 = max(0, int((x - frame.x) / frame.w * cols))
        c1 = min(cols - 1, int((x + w - frame.x - 1) / frame.w * cols))
        r0 = max(0, int((y - frame.y) / frame.h * rows))
        r1 = min(rows - 1, int((y + h - frame.y - 1) / frame.h * rows))
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                if PRIORITY[label] > PRIORITY.get(labels[r][c], -1):
                    labels[r][c] = label
    h, w = grey.shape
    for r in range(rows):
        for c in range(cols):
            if not labels[r][c]:
                patch = grey[int(r * h / rows):int((r + 1) * h / rows), int(c * w / cols):int((c + 1) * w / cols)]
                labels[r][c] = "blank" if patch.std() < retina.BLANK_STD else "image"
    return labels


def capture_window(app_name: str, window, out_dir: Path, rng: random.Random) -> int:
    frame = window_frame(window)
    if frame is None or frame.w < 300 or frame.h < 200:
        return 0
    elements = walk(window, frame)
    if len(elements) < 5:
        print(f"  {app_name}: only {len(elements)} elements, skipped", file=sys.stderr)
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "shot.png"
        retina.capture(frame, path)
        image = retina.load_image(path)
        w, h = Quartz.CGImageGetWidth(image), Quartz.CGImageGetHeight(image)
        grey = retina.grey_pixels(image)
        texts = retina.ocr(image, frame, w, h)
        feats, pix, labels_out, meta = [], [], [], []
        for cols, rows in GRIDS:
            labels = cell_labels(frame, elements, texts, grey, cols, rows)
            picked: dict[str, list[tuple[int, int]]] = {}
            for r in range(rows):
                for c in range(cols):
                    picked.setdefault(labels[r][c], []).append((r, c))
            for label, cells in picked.items():
                if label in KEEP_COMMON and len(cells) > KEEP_COMMON[label]:
                    cells = rng.sample(cells, KEEP_COMMON[label])
                for r, c in cells:
                    rect = Quartz.CGRectMake(c * w / cols, r * h / rows, w / cols, h / rows)
                    cell = Quartz.CGImageCreateWithImageInRect(image, rect)
                    feats.append(feature_print(cell))
                    pix.append(pixel_features(grey[int(r * h / rows):int((r + 1) * h / rows), int(c * w / cols):int((c + 1) * w / cols)]))
                    labels_out.append(label)
                    meta.append((cols, rows, r, c))
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    np.savez_compressed(
        out_dir / f"{stamp}.npz",
        x=np.stack(feats), px=np.stack(pix), y=np.array(labels_out), meta=np.array(meta), app=app_name,
        frame=np.array([frame.x, frame.y, frame.w, frame.h]),
    )
    counts = {l: labels_out.count(l) for l in LABELS if l in labels_out}
    print(f"  {app_name} {int(frame.w)}x{int(frame.h)} {len(elements)} elements, {len(texts)} texts -> {len(feats)} cells {counts}")
    return len(feats)


# ------------------------------------------------------------------ driving apps


def activate(name: str) -> NSRunningApplication | None:
    apps = [a for a in NSWorkspace.sharedWorkspace().runningApplications() if a.localizedName() == name]
    if not apps:
        print(f"  {name}: not running", file=sys.stderr)
        return None
    apps[0].activateWithOptions_(0)
    time.sleep(0.8)
    return apps[0]


def nudge(app_name: str, key: str) -> None:
    """A safe key that changes what is on screen without typing into anything."""
    subprocess.run(
        ["osascript", "-e", f'tell application "System Events" to tell process "{app_name}" to key code {key}'],
        check=False, capture_output=True,
    )
    time.sleep(0.6)


#: Page Down / Page Up / End / Home: scroll-only keys.
NUDGES = ("121", "116", "119", "115")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apps", help="comma-separated app names to cycle; default the frontmost app once")
    parser.add_argument("--rounds", type=int, default=1, help="captures per app, with a scroll nudge between")
    parser.add_argument("--out", type=Path, default=DATA)
    args = parser.parse_args()

    if not AS.AXIsProcessTrusted():
        print("collect: this process is not trusted for accessibility; allow it in System Settings > Privacy > Accessibility", file=sys.stderr)
        return 1
    rng = random.Random(0)
    total = 0
    names = args.apps.split(",") if args.apps else [NSWorkspace.sharedWorkspace().frontmostApplication().localizedName()]
    for name in names:
        app = activate(name) if args.apps else NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            continue
        ax = AS.AXUIElementCreateApplication(app.processIdentifier())
        for round_ in range(args.rounds):
            windows = ax_value(ax, "AXWindows") or []
            front = ax_value(ax, "AXFocusedWindow")
            targets = [front] if front is not None else list(windows)[:1]
            for window in targets:
                total += capture_window(name, window, args.out / name.replace(" ", "_"), rng)
            if args.rounds > 1:
                nudge(name, NUDGES[round_ % len(NUDGES)])
    print(f"collect: {total} cells stored under {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
