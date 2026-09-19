"""The retina: a screenshot in, a coarse word grid out. Nothing here calls Jev.

    uv run python eye/retina.py --show            # grid of the main display, painted on the overlay
    uv run python eye/retina.py --region 0,0,1280,720 --json

`experiments/vision` set the shape: Jev reads a grid of one word per cell up to
about 16 wide, cannot read pixels, and reads lists well. So the retina emits a
16x9 grid of labels plus a list of the texts it found, with the cell of each.

Labels per cell, decided in this order:
    text    an OCR box overlaps the cell (the text itself goes in `texts`)
    blank   the cell is one flat colour
    edge    a straight colour change across the cell (a border, a divider)
    image   anything else: icons, pictures, dense UI without readable text

Text is macOS Vision OCR (Korean + English). blank/edge/image are pixel
statistics on the greyscale cell. The capture is `screencapture`, which has
the screen-recording permission this session already uses.
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

COLS, ROWS = 16, 9

#: Greyscale spread below this is one flat colour. Tuned by eye on `--show`.
BLANK_STD = 3.0
#: An edge cell: nearly all its variance lies along one axis.
EDGE_RATIO = 0.85

LANGS = ["ko-KR", "en-US"]


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


@dataclass
class View:
    """What the retina saw: the grid, the texts, and where on screen it looked."""

    region: Region
    labels: list[list[str]]
    texts: list[Text] = field(default_factory=list)

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
        }

    def options(self) -> dict[str, str]:
        """Every non-blank cell as a Choice option, described in words."""
        by_cell: dict[tuple[int, int], list[str]] = {}
        for t in self.texts:
            by_cell.setdefault((t.row, t.col), []).append(t.text)
        out: dict[str, str] = {}
        for r, row in enumerate(self.labels):
            for c, label in enumerate(row):
                if label == "blank":
                    continue
                words = [label, self._where(r, c)]
                if (r, c) in by_cell:
                    words.append("says: " + " / ".join(by_cell[(r, c)])[:120])
                out[self.cell_id(r, c)] = ", ".join(words)
        return out

    @staticmethod
    def _where(r: int, c: int) -> str:
        v = "top" if r < ROWS / 3 else "bottom" if r >= 2 * ROWS / 3 else "middle"
        h = "left" if c < COLS / 3 else "right" if c >= 2 * COLS / 3 else "centre"
        return f"{v}-{h}"

    def center(self, cell_id: str) -> tuple[float, float]:
        r, c = parse_cell(cell_id)
        cell = self.region.cell(r, c)
        return cell.x + cell.w / 2, cell.y + cell.h / 2


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
    for obs in request.results() or []:
        cand = obs.topCandidates_(1)
        if not cand:
            continue
        bb = obs.boundingBox()
        x = region.x + bb.origin.x * image_w * px_to_pt
        y = region.y + (1 - bb.origin.y - bb.size.height) * image_h * px_to_pt
        w = bb.size.width * image_w * px_to_pt
        h = bb.size.height * image_h * px_to_pt
        box = Region(x, y, w, h)
        cx, cy = x + w / 2, y + h / 2
        col = min(COLS - 1, max(0, int((cx - region.x) / region.w * COLS)))
        row = min(ROWS - 1, max(0, int((cy - region.y) / region.h * ROWS)))
        texts.append(Text(str(cand[0].string()), box, row, col, float(cand[0].confidence())))
    return texts


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
    """Capture the region and reduce it to a View."""
    region = region or main_display()
    # the image source decodes lazily, so the file must outlive both reads
    with tempfile.TemporaryDirectory() as tmp:
        path = keep or Path(tmp) / "shot.png"
        capture(region, path)
        image = load_image(path)
        w, h = Quartz.CGImageGetWidth(image), Quartz.CGImageGetHeight(image)
        grey = grey_pixels(image)
        texts = ocr(image, region, w, h)

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
    return View(region, labels, texts)


# ------------------------------------------------------------------ cli


def show(view: View) -> None:
    """Paint the grid on the overlay: non-blank cells as heat, OCR boxes as-is."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from cursor_client import Cursor

    cursor = Cursor()
    cells = []
    strength = {"text": 0.6, "image": 0.35, "edge": 0.2}
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
    if args.show:
        # the overlay would be in the shot: hide it for the capture
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from cursor_client import Cursor
        Cursor().hide()
        time.sleep(0.05)
    view = see(region, args.keep)
    if args.show:
        Cursor().show()
    elapsed = time.perf_counter() - started

    if args.json:
        print(json.dumps(view.state(), ensure_ascii=False, indent=1))
    else:
        print(view.grid_text())
        print()
        for t in view.texts:
            print(f"{view.cell_id(t.row, t.col):7} {t.confidence:.2f}  {t.text}")
    print(f"\n{len(view.texts)} texts, {sum(l != 'blank' for row in view.labels for l in row)} non-blank cells, {elapsed:.2f}s", file=sys.stderr)
    if args.show:
        show(view)
    return 0


if __name__ == "__main__":
    sys.exit(main())
