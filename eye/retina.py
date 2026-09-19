"""The retina: a screenshot in, a coarse word grid out. Nothing here calls Jev.

    uv run python eye/retina.py --show            # grid of the main display, painted on the overlay
    uv run python eye/retina.py --region 0,0,1280,720 --json

`experiments/vision` set the shape: Jev reads a grid of one word per cell up to
about 16 wide, cannot read pixels, and reads lists well. So the retina emits a
16x9 grid of labels plus a list of the texts it found, with the cell of each.

Labels per cell, decided in this order:
    button  a detected interactable element that shows words (the words go in `elements`)
    icon    a detected interactable element without words
    text    an OCR box overlaps the cell (the text itself goes in `texts`)
    blank   the cell is one flat colour
    edge    a straight colour change across the cell (a border, a divider)
    image   anything else: pictures, dense UI without readable text

Interactable elements come from OmniParser's icon detector (a YOLO trained on
screenshots, `models/omniparser_icon_detect.pt`, AGPL). Text is macOS Vision
OCR (Korean + English). blank/edge/image are pixel statistics on the greyscale
cell. The capture is `screencapture`, which has the screen-recording
permission this session already uses.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import Quartz
import Vision
from AppKit import NSScreen
from Foundation import NSURL

sys.path.insert(0, str(Path(__file__).resolve().parent))

COLS, ROWS = 16, 9

#: Greyscale spread below this is one flat colour. Tuned by eye on `--show`.
BLANK_STD = 3.0
#: An edge cell: nearly all its variance lies along one axis.
EDGE_RATIO = 0.85

LANGS = ["ko-KR", "en-US"]

DETECTOR = Path(__file__).resolve().parent / "models" / "omniparser_icon_detect.pt"
#: OmniParser's own thresholds: low confidence, aggressive overlap suppression.
DETECT_CONF = 0.1
DETECT_IOU = 0.1
DETECT_SIZE = 1280
_detector = None


@dataclass(frozen=True)
class Region:
    """A rectangle in screen points, top-left origin."""

    x: float
    y: float
    w: float
    h: float

    def cell(self, r: int, c: int) -> Region:
        cw, ch = self.w / COLS, self.h / ROWS
        return Region(self.x + c * cw, self.y + r * ch, cw, ch)

    def block(self, r: int, c: int, rows: int, cols: int, overlap: float = 0.5) -> Region:
        """Block (r, c) of a coarse `rows` x `cols` split of this region, grown
        by `overlap` of a block on every side (clipped) so a row of tabs that
        straddles a boundary is whole in at least one block."""
        bw, bh = self.w / cols, self.h / rows
        x0 = max(self.x, self.x + (c - overlap) * bw)
        y0 = max(self.y, self.y + (r - overlap) * bh)
        x1 = min(self.x + self.w, self.x + (c + 1 + overlap) * bw)
        y1 = min(self.y + self.h, self.y + (r + 1 + overlap) * bh)
        return Region(x0, y0, x1 - x0, y1 - y0)

    def around(self, r: int, c: int, span: int = 3) -> Region:
        """The `span`x`span` block of cells centred on (r, c), clipped to this region."""
        cw, ch = self.w / COLS, self.h / ROWS
        c0 = min(max(c - span // 2, 0), COLS - span)
        r0 = min(max(r - span // 2, 0), ROWS - span)
        return Region(self.x + c0 * cw, self.y + r0 * ch, span * cw, span * ch)


@dataclass(frozen=True)
class Text:
    text: str
    box: Region  # screen points
    row: int
    col: int
    confidence: float


@dataclass(frozen=True)
class Element:
    """A detected interactable: a button when it shows words, else an icon."""

    kind: str
    box: Region
    row: int
    col: int
    text: str
    confidence: float


@dataclass
class View:
    """What the retina saw: the grid, the texts, and where on screen it looked."""

    region: Region
    labels: list[list[str]]
    texts: list[Text] = field(default_factory=list)
    elements: list[Element] = field(default_factory=list)

    def cell_id(self, r: int, c: int) -> str:
        return f"r{r + 1}c{c + 1}"

    def grid_text(self) -> str:
        return "\n".join(" ".join(row) for row in self.labels)

    def state(self) -> dict:
        """The mapping handed to Jev: the `words` spelling plus a text list."""
        return {
            "format": f"a screen reduced to a {COLS}-column by {ROWS}-row grid of cell labels, "
                      "one word per cell, one row per line, top row first; labels are blank, text, edge, image",
            "width": COLS,
            "height": ROWS,
            "grid": self.grid_text(),
            "texts": [f"{self.cell_id(t.row, t.col)} {t.text}" for t in self.texts],
            "elements": [
                f"{self.cell_id(e.row, e.col)} {e.kind}" + (f" {e.text}" if e.text else "") for e in self.elements
            ],
        }

    def options(self) -> dict[str, str]:
        """Every non-blank cell as a Choice option, described in words."""
        by_cell: dict[tuple[int, int], list[str]] = {}
        for t in self.texts:
            by_cell.setdefault((t.row, t.col), []).append(t.text)
        kinds: dict[tuple[int, int], list[str]] = {}
        for e in self.elements:
            kinds.setdefault((e.row, e.col), []).append(e.kind + (f" '{e.text}'" if e.text else ""))
        out: dict[str, str] = {}
        for r, row in enumerate(self.labels):
            for c, label in enumerate(row):
                if label == "blank":
                    continue
                words = [label, self._where(r, c)]
                if (r, c) in kinds:
                    words.append("has: " + ", ".join(kinds[(r, c)])[:120])
                if (r, c) in by_cell:
                    words.append("says: " + " / ".join(by_cell[(r, c)])[:120])
                line = self.row_of(r, c)
                if line:
                    words.append("in row: " + line)
                out[self.cell_id(r, c)] = ", ".join(words)
        return out

    def row_of(self, r: int, c: int, reach: float = 400.0) -> str:
        """The words on the same line as the cell's element, left to right - the
        context that tells a '〉' in the browser toolbar from one in the page."""
        cell = self.region.cell(r, c)
        anchors = [e.box for e in self.elements if e.row == r and e.col == c] or \
                  [t.box for t in self.texts if t.row == r and t.col == c]
        if not anchors:
            return ""
        a = anchors[0]
        cy = a.y + a.h / 2
        band = [t for t in self.texts
                if abs(t.box.y + t.box.h / 2 - cy) < max(a.h, 12) * 0.6
                and abs(t.box.x + t.box.w / 2 - (a.x + a.w / 2)) < reach and t.confidence >= 0.3]
        band.sort(key=lambda t: t.box.x)
        return " ".join(t.text for t in band)[:160]

    def blocks(self, rows: int = 3, cols: int = 4) -> dict[str, str]:
        """A coarse split as Choice options: each block summarised by what it
        holds - counts of buttons and icons, then its readable words in reading
        order. Twelve short lines instead of ninety cells for the first pick."""
        out: dict[str, str] = {}
        for br in range(rows):
            for bc in range(cols):
                box = self.region.block(br, bc, rows, cols)
                inside = lambda b: box.x <= b.x + b.w / 2 < box.x + box.w and box.y <= b.y + b.h / 2 < box.y + box.h
                texts = [t for t in self.texts if inside(t.box) and t.confidence >= 0.5 and len(t.text) >= 2]
                elements = [e for e in self.elements if inside(e.box)]
                if not texts and not elements:
                    continue
                buttons = sum(e.kind == "button" for e in elements)
                icons = len(elements) - buttons
                words = " ".join(t.text for t in sorted(texts, key=lambda t: (t.box.y // 20, t.box.x)))[:200]
                v = ("top", "middle", "bottom")[br * 3 // rows]
                h = ("left", "centre-left", "centre-right", "right")[bc * 4 // cols]
                out[f"b{br + 1}{bc + 1}"] = f"{v}-{h}, {buttons} buttons, {icons} icons, says: {words}"
        return out

    @staticmethod
    def _where(r: int, c: int) -> str:
        v = "top" if r < ROWS / 3 else "bottom" if r >= 2 * ROWS / 3 else "middle"
        h = "left" if c < COLS / 3 else "right" if c >= 2 * COLS / 3 else "centre"
        return f"{v}-{h}"

    def center(self, cell_id: str) -> tuple[float, float]:
        """Where to aim in a cell: the detected element nearest its centre, else the centre."""
        r, c = parse_cell(cell_id)
        cell = self.region.cell(r, c)
        cx, cy = cell.x + cell.w / 2, cell.y + cell.h / 2
        inside = [e for e in self.elements if e.row == r and e.col == c]
        if not inside:
            return cx, cy
        best = min(inside, key=lambda e: (e.box.x + e.box.w / 2 - cx) ** 2 + (e.box.y + e.box.h / 2 - cy) ** 2)
        return best.box.x + best.box.w / 2, best.box.y + best.box.h / 2


def parse_cell(cell_id: str) -> tuple[int, int]:
    r, c = cell_id[1:].split("c")
    return int(r) - 1, int(c) - 1


# ------------------------------------------------------------------ capture


def main_display() -> Region:
    f = NSScreen.mainScreen().frame()
    return Region(0, 0, f.size.width, f.size.height)


def scale() -> float:
    return float(NSScreen.mainScreen().backingScaleFactor())


def capture(region: Region, path: Path) -> None:
    subprocess.run(
        ["screencapture", "-x", "-R", f"{region.x:.0f},{region.y:.0f},{region.w:.0f},{region.h:.0f}", str(path)],
        check=True,
    )


def load_image(path: Path):
    source = Quartz.CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(str(path)), None)
    return Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)


def grey_pixels(image) -> np.ndarray:
    """The image as a (h, w) float greyscale array, honouring the row stride."""
    w, h = Quartz.CGImageGetWidth(image), Quartz.CGImageGetHeight(image)
    stride = Quartz.CGImageGetBytesPerRow(image)
    data = Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(image))
    raw = np.frombuffer(bytes(data), dtype=np.uint8)
    channels = stride // w
    px = raw.reshape(h, stride)[:, : w * channels].reshape(h, w, channels)[:, :, :3].astype(np.float32)
    return px.mean(axis=2)


# ------------------------------------------------------------------ OCR


def ocr(image, region: Region, image_w: int, image_h: int) -> list[Text]:
    """Vision text boxes, converted from normalised bottom-left to screen points."""
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setRecognitionLanguages_(LANGS)
    request.setUsesLanguageCorrection_(True)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, None)
    ok, error = handler.performRequests_error_([request], None)
    if not ok:
        print(f"retina: OCR failed: {error}", file=sys.stderr)
        return []
    px_to_pt = region.w / image_w
    texts: list[Text] = []

    def to_screen(bb) -> Region:
        return Region(
            region.x + bb.origin.x * image_w * px_to_pt,
            region.y + (1 - bb.origin.y - bb.size.height) * image_h * px_to_pt,
            bb.size.width * image_w * px_to_pt,
            bb.size.height * image_h * px_to_pt,
        )

    for obs in request.results() or []:
        cand = obs.topCandidates_(1)
        if not cand:
            continue
        top = cand[0]
        line = str(top.string())
        confidence = float(top.confidence())
        # one Text per word: a line like "이미지 동영상 쇼핑" is three tabs, and the
        # zoom stage needs to tell them apart
        pieces: list[tuple[str, Region]] = []
        start = 0
        for word in line.split(" "):
            if word:
                rect, _ = top.boundingBoxForRange_error_((start, len(word)), None)
                if rect is not None:
                    pieces.append((word, to_screen(rect.boundingBox())))
            start += len(word) + 1
        if not pieces:
            pieces = [(line, to_screen(obs.boundingBox()))]
        for word, box in pieces:
            cx, cy = box.x + box.w / 2, box.y + box.h / 2
            col = min(COLS - 1, max(0, int((cx - region.x) / region.w * COLS)))
            row = min(ROWS - 1, max(0, int((cy - region.y) / region.h * ROWS)))
            texts.append(Text(word, box, row, col, confidence))
    return texts


# ------------------------------------------------------------------ detector


def detect(path: Path, region: Region, image_w: int, texts: list[Text]) -> list[Element]:
    """Interactable boxes from the OmniParser detector, in screen points; a box
    that overlaps OCR text is a button and carries the words, else an icon."""
    global _detector
    if not DETECTOR.exists():
        return []
    if _detector is None:
        from ultralytics import YOLO
        _detector = YOLO(str(DETECTOR))
    result = _detector.predict(
        str(path), imgsz=DETECT_SIZE, conf=DETECT_CONF, iou=DETECT_IOU, device="mps", verbose=False
    )[0]
    px_to_pt = region.w / image_w
    out: list[Element] = []
    for xyxy, conf in zip(result.boxes.xyxy.tolist(), result.boxes.conf.tolist()):
        x0, y0, x1, y1 = (v * px_to_pt for v in xyxy)
        box = Region(region.x + x0, region.y + y0, x1 - x0, y1 - y0)
        words = [t.text for t in texts if _overlap(box, t.box) > 0.5 * t.box.w * t.box.h]
        cx, cy = box.x + box.w / 2, box.y + box.h / 2
        col = min(COLS - 1, max(0, int((cx - region.x) / region.w * COLS)))
        row = min(ROWS - 1, max(0, int((cy - region.y) / region.h * ROWS)))
        out.append(Element("button" if words else "icon", box, row, col, " ".join(words)[:60], conf))
    return out


def _overlap(a: Region, b: Region) -> float:
    w = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
    h = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    return max(0.0, w) * max(0.0, h)


# ------------------------------------------------------------------ the grid


def classify(cell: np.ndarray) -> str:
    """blank / edge / image from a greyscale cell."""
    if cell.std() < BLANK_STD:
        return "blank"
    # variance of the row means vs the column means: a horizontal divider makes
    # rows differ and columns agree; a vertical one the reverse
    row_var = cell.mean(axis=1).var()
    col_var = cell.mean(axis=0).var()
    total = cell.var()
    if total > 0 and max(row_var, col_var) / total > EDGE_RATIO:
        return "edge"
    return "image"


def see(region: Region | None = None, keep: Path | None = None) -> View:
    """Capture the region and reduce it to a View. The cursor overlay is hidden
    for the capture so the eye never reads its own labels."""
    from cursor_client import Cursor

    region = region or main_display()
    cursor = Cursor()
    cursor.hide()
    time.sleep(0.05)
    try:
        return _see(region, keep)
    finally:
        cursor.show()


def _see(region: Region, keep: Path | None) -> View:
    # the image source decodes lazily, so the file must outlive both reads
    with tempfile.TemporaryDirectory() as tmp:
        path = keep or Path(tmp) / "shot.png"
        capture(region, path)
        image = load_image(path)
        w, h = Quartz.CGImageGetWidth(image), Quartz.CGImageGetHeight(image)
        grey = grey_pixels(image)
        texts = ocr(image, region, w, h)
        elements = detect(path, region, w, texts)

    labels = [["blank"] * COLS for _ in range(ROWS)]
    for r in range(ROWS):
        for c in range(COLS):
            y0, y1 = int(r * h / ROWS), int((r + 1) * h / ROWS)
            x0, x1 = int(c * w / COLS), int((c + 1) * w / COLS)
            labels[r][c] = classify(grey[y0:y1, x0:x1])
    for t in texts:
        # every cell the box overlaps reads as text, not only the centre one
        c0 = max(0, int((t.box.x - region.x) / region.w * COLS))
        c1 = min(COLS - 1, int((t.box.x + t.box.w - region.x) / region.w * COLS))
        r0 = max(0, int((t.box.y - region.y) / region.h * ROWS))
        r1 = min(ROWS - 1, int((t.box.y + t.box.h - region.y) / region.h * ROWS))
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                labels[r][c] = "text"
    for e in elements:
        # an element is one thing, so it labels the cell that holds its centre
        if e.kind == "button" or labels[e.row][e.col] != "button":
            labels[e.row][e.col] = e.kind
    return View(region, labels, texts, elements)


# ------------------------------------------------------------------ cli


def show(view: View) -> None:
    """Paint the grid on the overlay: non-blank cells as heat."""
    from cursor_client import Cursor

    cursor = Cursor()
    cells = []
    strength = {"button": 0.8, "icon": 0.7, "text": 0.5, "image": 0.3, "edge": 0.15}
    for r, row in enumerate(view.labels):
        for c, label in enumerate(row):
            if label != "blank":
                cell = view.region.cell(r, c)
                cells.append([cell.x + 2, cell.y + 2, cell.w - 4, cell.h - 4, strength[label]])
    cursor.heat(cells)
    cursor.label(f"{len(view.texts)} texts")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", help="x,y,w,h in screen points; default the main display")
    parser.add_argument("--show", action="store_true", help="paint the grid on the cursor overlay")
    parser.add_argument("--json", action="store_true", help="print the Jev state as JSON")
    parser.add_argument("--keep", type=Path, help="keep the screenshot at this path")
    args = parser.parse_args()

    region = Region(*(float(v) for v in args.region.split(","))) if args.region else None
    started = time.perf_counter()
    view = see(region, args.keep)
    elapsed = time.perf_counter() - started

    if args.json:
        print(json.dumps(view.state(), ensure_ascii=False, indent=1))
    else:
        print(view.grid_text())
        print()
        for t in view.texts:
            print(f"{view.cell_id(t.row, t.col):7} {t.confidence:.2f}  {t.text}")
        for e in view.elements:
            print(f"{view.cell_id(e.row, e.col):7} {e.confidence:.2f}  {e.kind} {e.text}")
    print(f"\n{len(view.texts)} texts, {len(view.elements)} elements, {sum(l != 'blank' for row in view.labels for l in row)} non-blank cells, {elapsed:.2f}s", file=sys.stderr)
    if args.show:
        show(view)
    return 0


if __name__ == "__main__":
    sys.exit(main())
