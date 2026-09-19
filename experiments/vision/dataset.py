"""Two ways to hand Jev a picture as text, and the questions that check what it saw.

Jev's `state` is text, a mapping or a list - never bytes. So an image has to be
spelled out, and the question is which spelling Jev can read.

1. encode - tiny colour grids (4x4 / 8x8, 4 or 8 pure colours), the same image
   spelled nine ways from "red blue red" all the way down to a base64 PNG.
   Questions: the colour of one named cell (positional) and the colour that
   appears most often (needs no indexing, so a miss is about decoding).
2. pixel  - MNIST digits downsampled to 14x14, spelled five ways as a pixel grid.
   Question: which digit.

Every state is a mapping that says what it is (`format`, `width`, `height`,
`data`) and every instruction repeats the format, so the run measures reading,
not guessing. Colours are pure primaries/secondaries and the option descriptions
carry the numeric forms, so colour naming is not a hidden skill either.
"""

from __future__ import annotations

import base64
import gzip
import random
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

# ------------------------------------------------------------------ colours

#: name -> (r, g, b). All components are 0 or 255 so the hex/rgb spellings are
#: unambiguous; the first four are the small palette, all eight the large one.
COLORS: dict[str, tuple[int, int, int]] = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
}
PALETTES: dict[int, tuple[str, ...]] = {
    4: tuple(list(COLORS)[:4]),
    8: tuple(COLORS),
}


def color_options(size: int) -> dict[str, str]:
    """Choice options for one palette; the description spells the numbers."""
    out = {}
    for name in PALETTES[size]:
        r, g, b = COLORS[name]
        out[name] = f"RGB ({r}, {g}, {b}), hex {r:02x}{g:02x}{b:02x}"
    return out


# ------------------------------------------------------------------ grids

GRID_SIZES: tuple[int, ...] = (4, 8)
PALETTE_SIZES: tuple[int, ...] = (4, 8)
IMAGES_PER_CONDITION = 25

#: Spellings of one grid, roughly from most to least readable.
ENCODE_FORMATS: tuple[str, ...] = (
    "names",      # rows of colour names
    "rgb",        # rows of (r,g,b) triples
    "hex",        # rows of rrggbb
    "ppm",        # PPM P3: ASCII header + one integer per component
    "b64rgb",     # base64 of raw RGB bytes, row-major - 4 chars per pixel, aligned
    "b64rgb_off", # same bytes with one zero byte in front - alignment broken
    "b64bmp",     # base64 of a 24-bit BMP (54-byte header, BGR, bottom-up rows)
    "b64png0",    # base64 of a PNG whose deflate stream is stored (level 0)
    "b64png",     # base64 of an ordinary PNG (deflate level 9)
)


@dataclass(frozen=True)
class Grid:
    """One colour image: `cells[row][col]` is a colour name."""

    id: str
    size: int
    palette: int
    cells: tuple[tuple[str, ...], ...]
    row: int  # positional question target, 1-based from the top
    col: int  # positional question target, 1-based from the left

    @property
    def target(self) -> str:
        return self.cells[self.row - 1][self.col - 1]

    @property
    def mode(self) -> str:
        counts: dict[str, int] = {}
        for line in self.cells:
            for c in line:
                counts[c] = counts.get(c, 0) + 1
        return max(counts, key=lambda name: counts[name])

    def rgb_bytes(self) -> bytes:
        return b"".join(bytes(COLORS[c]) for line in self.cells for c in line)


def make_grids(size: int, palette: int, count: int = IMAGES_PER_CONDITION) -> list[Grid]:
    """Random grids with a unique most-common colour; the target cell cycles
    through colours so a constant answer cannot beat chance on either question."""
    rng = random.Random(f"vision-encode-{size}-{palette}")
    names = PALETTES[palette]
    grids: list[Grid] = []
    while len(grids) < count:
        cells = tuple(tuple(rng.choice(names) for _ in range(size)) for _ in range(size))
        counts = sorted((sum(line.count(n) for line in cells) for n in names), reverse=True)
        if counts[0] == counts[1]:
            continue
        wanted = names[len(grids) % len(names)]
        spots = [(r, c) for r in range(size) for c in range(size) if cells[r][c] == wanted]
        if not spots:
            continue
        r, c = rng.choice(spots)
        grids.append(Grid(
            id=f"g{size}p{palette}-{len(grids):02d}", size=size, palette=palette,
            cells=cells, row=r + 1, col=c + 1,
        ))
    return grids


# ------------------------------------------------------------------ spellings


def _bmp(grid: Grid) -> bytes:
    """24-bit uncompressed BMP. Rows are bottom-up and BGR; 4x4 and 8x8 rows
    are multiples of 4 bytes so there is no padding."""
    w = h = grid.size
    row_bytes = w * 3
    pixels = b"".join(
        b"".join(bytes(reversed(COLORS[c])) for c in grid.cells[r])
        for r in range(h - 1, -1, -1)
    )
    header = struct.pack("<2sIHHI", b"BM", 54 + len(pixels), 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(pixels), 2835, 2835, 0, 0)
    assert len(header) + len(info) == 54 and len(pixels) == row_bytes * h
    return header + info + pixels


def _png(grid: Grid, level: int) -> bytes:
    """8-bit RGB PNG, filter type 0 on every row."""
    w = h = grid.size

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"".join(bytes(COLORS[c]) for c in grid.cells[r]) for r in range(h))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, level))
        + chunk(b"IEND", b"")
    )


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def spell(grid: Grid, fmt: str) -> str:
    """The `data` field for one grid in one format."""
    if fmt == "names":
        return "\n".join(" ".join(line) for line in grid.cells)
    if fmt == "rgb":
        return "\n".join(" ".join("(%d,%d,%d)" % COLORS[c] for c in line) for line in grid.cells)
    if fmt == "hex":
        return "\n".join(" ".join("%02x%02x%02x" % COLORS[c] for c in line) for line in grid.cells)
    if fmt == "ppm":
        body = "\n".join(" ".join("%d %d %d" % COLORS[c] for c in line) for line in grid.cells)
        return f"P3\n{grid.size} {grid.size}\n255\n{body}"
    if fmt == "b64rgb":
        return _b64(grid.rgb_bytes())
    if fmt == "b64rgb_off":
        return _b64(b"\x00" + grid.rgb_bytes())
    if fmt == "b64bmp":
        return _b64(_bmp(grid))
    if fmt == "b64png0":
        return _b64(_png(grid, 0))
    if fmt == "b64png":
        return _b64(_png(grid, 9))
    raise ValueError(fmt)


FORMAT_TEXT: dict[str, str] = {
    "names": "rows of colour names separated by spaces, one row per line, top row first",
    "rgb": "rows of (r,g,b) triples separated by spaces, one row per line, top row first",
    "hex": "rows of rrggbb hex colour codes separated by spaces, one row per line, top row first",
    "ppm": "a PPM image in the P3 (plain ASCII) format: header, then r g b integers per pixel, row-major from the top-left",
    "b64rgb": "base64 of the raw RGB bytes of the image (3 bytes per pixel, row-major from the top-left, no header)",
    "b64rgb_off": "base64 of one zero padding byte followed by the raw RGB bytes of the image (3 bytes per pixel, row-major from the top-left)",
    "b64bmp": "base64 of a 24-bit uncompressed BMP file (54-byte header, then BGR pixels, bottom row first)",
    "b64png0": "base64 of an 8-bit RGB PNG file whose deflate stream is stored uncompressed",
    "b64png": "base64 of an ordinary 8-bit RGB PNG file (deflate-compressed)",
}


def encode_state(grid: Grid, fmt: str) -> dict:
    return {
        "format": FORMAT_TEXT[fmt],
        "width": grid.size,
        "height": grid.size,
        "colors_used": list(PALETTES[grid.palette]),
        "data": spell(grid, fmt),
    }


def position_instructions(grid: Grid) -> str:
    return (
        f"The state is a {grid.size}x{grid.size} colour image: {{format}}. "
        f"What colour is the pixel at row {grid.row}, column {grid.col} "
        f"(1-based, counted from the top-left corner)?"
    )


MODE_INSTRUCTIONS = (
    "The state is a {w}x{h} colour image: {format}. "
    "Which colour appears in the most pixels?"
)


def encode_instructions(grid: Grid, fmt: str, question: str) -> str:
    if question == "pos":
        return position_instructions(grid).replace("{format}", FORMAT_TEXT[fmt])
    if question == "mode":
        return MODE_INSTRUCTIONS.format(w=grid.size, h=grid.size, format=FORMAT_TEXT[fmt])
    raise ValueError(question)


ENCODE_QUESTIONS: tuple[str, ...] = ("pos", "mode")

# ------------------------------------------------------------------ MNIST

MNIST_URL = "https://ossci-datasets.s3.amazonaws.com/mnist/"
MNIST_FILES = ("t10k-images-idx3-ubyte.gz", "t10k-labels-idx1-ubyte.gz")
DIGITS_PER_CLASS = 10
PIXEL_SIZE = 14  # 28 -> 14 by 2x2 mean

PIXEL_FORMATS: tuple[str, ...] = (
    "binary",     # '#' for ink, '.' for paper
    "density",    # ' .:-=+*#%@' by grey level
    "braille",    # one braille character per 2x4 block of binary pixels
    "coords",     # (row,col) list of ink pixels
    "runlength",  # per row: alternating paper/ink run lengths
)

DENSITY_CHARS = " .:-=+*#%@"
INK = 96  # grey threshold for binary spellings, after downsampling


@dataclass(frozen=True)
class Digit:
    id: str
    label: int
    pixels: tuple[tuple[int, ...], ...]  # 14x14 grey 0..255

    def binary(self) -> list[list[bool]]:
        return [[v >= INK for v in row] for row in self.pixels]


def fetch_mnist() -> None:
    """Download the MNIST test set into data/ if it is not there."""
    import urllib.request

    DATA.mkdir(exist_ok=True)
    for name in MNIST_FILES:
        path = DATA / name
        if not path.exists():
            urllib.request.urlretrieve(MNIST_URL + name, path)


def load_digits(per_class: int = DIGITS_PER_CLASS) -> list[Digit]:
    """The first `per_class` test digits of each class, downsampled to 14x14."""
    fetch_mnist()
    images = gzip.open(DATA / MNIST_FILES[0]).read()
    labels = gzip.open(DATA / MNIST_FILES[1]).read()
    _, n, rows, cols = struct.unpack(">IIII", images[:16])
    assert rows == cols == 28
    taken: dict[int, int] = {d: 0 for d in range(10)}
    digits: list[Digit] = []
    for i in range(n):
        label = labels[8 + i]
        if taken[label] >= per_class:
            if all(v >= per_class for v in taken.values()):
                break
            continue
        offset = 16 + i * 784
        raw = images[offset:offset + 784]
        small = tuple(
            tuple(
                (raw[(2 * r) * 28 + 2 * c] + raw[(2 * r) * 28 + 2 * c + 1]
                 + raw[(2 * r + 1) * 28 + 2 * c] + raw[(2 * r + 1) * 28 + 2 * c + 1]) // 4
                for c in range(PIXEL_SIZE)
            )
            for r in range(PIXEL_SIZE)
        )
        digits.append(Digit(id=f"d{label}-{taken[label]}", label=label, pixels=small))
        taken[label] += 1
    digits.sort(key=lambda d: (d.label, d.id))
    return digits


def _braille(bits: list[list[bool]]) -> str:
    """Braille dots map (row, col) inside a 2x4 block: bit order 1,2,3,7 for the
    left column and 4,5,6,8 for the right one."""
    rows, cols = len(bits), len(bits[0])
    weights = [[0x01, 0x08], [0x02, 0x10], [0x04, 0x20], [0x40, 0x80]]
    lines = []
    for r0 in range(0, rows, 4):
        chars = []
        for c0 in range(0, cols, 2):
            code = 0x2800
            for dr in range(4):
                for dc in range(2):
                    r, c = r0 + dr, c0 + dc
                    if r < rows and c < cols and bits[r][c]:
                        code |= weights[dr][dc]
            chars.append(chr(code))
        lines.append("".join(chars))
    return "\n".join(lines)


def spell_digit(digit: Digit, fmt: str) -> str:
    bits = digit.binary()
    if fmt == "binary":
        return "\n".join("".join("#" if b else "." for b in row) for row in bits)
    if fmt == "density":
        return "\n".join(
            "".join(DENSITY_CHARS[min(9, v * 10 // 256)] for v in row) for row in digit.pixels
        )
    if fmt == "braille":
        return _braille(bits)
    if fmt == "coords":
        ink = [f"({r},{c})" for r, row in enumerate(bits) for c, b in enumerate(row) if b]
        return " ".join(ink)
    if fmt == "runlength":
        lines = []
        for row in bits:
            runs: list[int] = []
            current = False
            count = 0
            for b in row:
                if b == current:
                    count += 1
                else:
                    runs.append(count)
                    current, count = b, 1
            runs.append(count)
            lines.append(" ".join(str(n) for n in runs))
        return "\n".join(lines)
    raise ValueError(fmt)


PIXEL_FORMAT_TEXT: dict[str, str] = {
    "binary": "one character per pixel, '#' for ink and '.' for paper, one row per line, top row first",
    "density": "one character per pixel from the ramp ' .:-=+*#%@' (space is paper, @ is darkest ink), one row per line, top row first",
    "braille": "Unicode braille characters, each covering a 2-wide by 4-tall block of pixels (a raised dot is ink), one line per block row, top first",
    "coords": "a list of (row,col) coordinates of the ink pixels, 0-based from the top-left; every other pixel is paper",
    "runlength": "one row per line as run lengths, alternating paper then ink, starting with paper (a leading 0 means the row starts with ink)",
}


def pixel_state(digit: Digit, fmt: str) -> dict:
    return {
        "format": PIXEL_FORMAT_TEXT[fmt],
        "width": PIXEL_SIZE,
        "height": PIXEL_SIZE,
        "data": spell_digit(digit, fmt),
    }


def pixel_instructions(fmt: str) -> str:
    return (
        f"The state is a {PIXEL_SIZE}x{PIXEL_SIZE} black-and-white image of a single "
        f"handwritten digit: {PIXEL_FORMAT_TEXT[fmt]}. Which digit is written?"
    )


DIGIT_OPTIONS: dict[str, str] = {
    str(d): f"the digit {name}"
    for d, name in enumerate(("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"))
}

# ------------------------------------------------------------------ tokens

#: chars per token, measured on the limits run for English prose + JSON; the
#: base64 and symbol-heavy states tokenise worse, so this is a floor.
CHARS_PER_TOKEN = 3.2
TOKEN_BASE = 40


def estimate_tokens(state: Mapping, criteria: Mapping[str, str | None], instructions: str) -> float:
    import json

    payload = instructions + json.dumps(state, ensure_ascii=False) + json.dumps(dict(criteria))
    return TOKEN_BASE + len(payload) / CHARS_PER_TOKEN


# ------------------------------------------------------------------ checks


def validate() -> list[str]:
    problems = []
    for size in GRID_SIZES:
        for palette in PALETTE_SIZES:
            grids = make_grids(size, palette)
            if len(grids) != IMAGES_PER_CONDITION:
                problems.append(f"{size}x{size}/{palette}: {len(grids)} grids")
            targets = [g.target for g in grids]
            for name in PALETTES[palette]:
                if targets.count(name) < IMAGES_PER_CONDITION // palette:
                    problems.append(f"{size}x{size}/{palette}: target {name} under-represented")
            for g in grids:
                # every spelling must round-trip the bytes it claims to carry
                if base64.b64decode(spell(g, "b64rgb")) != g.rgb_bytes():
                    problems.append(f"{g.id}: b64rgb mismatch")
                png = base64.b64decode(spell(g, "b64png"))
                if zlib.decompress(png[41:41 + struct.unpack(">I", png[33:37])[0]])[1:size * 3 + 1] != g.rgb_bytes()[:size * 3]:
                    problems.append(f"{g.id}: png first row mismatch")
    return problems


# ------------------------------------------------------------------ feature grids

#: The eye's real input: a screen reduced to a coarse grid where each cell is one
#: label. Sizes run from the 8x8 the encode axis proved up to a 32x18 screen.
GRID_SHAPES: tuple[tuple[int, int], ...] = ((8, 8), (16, 9), (24, 14), (32, 18))  # (cols, rows)
FEATURE_LABELS: tuple[str, ...] = ("blank", "text", "button", "image", "edge", "input")
FEATURE_LETTERS: dict[str, str] = {
    "blank": ".", "text": "T", "button": "B", "image": "I", "edge": "E", "input": "N",
}
#: Sampling weights for the filler cells; `input` appears exactly once per grid.
FEATURE_WEIGHTS: tuple[int, ...] = (60, 20, 8, 6, 6, 0)
GRID_FORMATS: tuple[str, ...] = ("words", "letters")
GRID_QUESTIONS: tuple[str, ...] = ("pos", "find_row", "find_col")


@dataclass(frozen=True)
class FeatureGrid:
    id: str
    cols: int
    rows: int
    cells: tuple[tuple[str, ...], ...]
    row: int  # `pos` target, 1-based
    col: int
    input_row: int  # the unique `input` cell, 1-based
    input_col: int

    @property
    def target(self) -> str:
        return self.cells[self.row - 1][self.col - 1]


def make_feature_grids(cols: int, rows: int, count: int = IMAGES_PER_CONDITION) -> list[FeatureGrid]:
    """Random screens. The `pos` target cycles through the five filler labels and
    the unique `input` cell cycles through rows and columns."""
    rng = random.Random(f"vision-grid-{cols}x{rows}")
    fillers = FEATURE_LABELS[:-1]
    grids: list[FeatureGrid] = []
    while len(grids) < count:
        cells = [list(rng.choices(fillers, weights=FEATURE_WEIGHTS[:-1], k=cols)) for _ in range(rows)]
        ir = (len(grids) * 7) % rows
        ic = (len(grids) * 11) % cols
        cells[ir][ic] = "input"
        wanted = fillers[len(grids) % len(fillers)]
        spots = [(r, c) for r in range(rows) for c in range(cols) if cells[r][c] == wanted]
        if not spots:
            continue
        r, c = rng.choice(spots)
        grids.append(FeatureGrid(
            id=f"f{cols}x{rows}-{len(grids):02d}", cols=cols, rows=rows,
            cells=tuple(tuple(line) for line in cells), row=r + 1, col=c + 1,
            input_row=ir + 1, input_col=ic + 1,
        ))
    return grids


GRID_FORMAT_TEXT: dict[str, str] = {
    "words": "rows of cell labels separated by spaces, one row per line, top row first; labels are "
             + ", ".join(FEATURE_LABELS),
    "letters": "one character per cell, one row per line, top row first; "
               + ", ".join(f"{v}={k}" for k, v in FEATURE_LETTERS.items()),
}


def spell_feature_grid(grid: FeatureGrid, fmt: str) -> str:
    if fmt == "words":
        return "\n".join(" ".join(line) for line in grid.cells)
    if fmt == "letters":
        return "\n".join("".join(FEATURE_LETTERS[c] for c in line) for line in grid.cells)
    raise ValueError(fmt)


def feature_state(grid: FeatureGrid, fmt: str) -> dict:
    return {
        "format": GRID_FORMAT_TEXT[fmt],
        "width": grid.cols,
        "height": grid.rows,
        "data": spell_feature_grid(grid, fmt),
    }


def feature_instructions(grid: FeatureGrid, fmt: str, question: str) -> str:
    head = f"The state is a screen reduced to a {grid.cols}-column by {grid.rows}-row grid of cell labels: {GRID_FORMAT_TEXT[fmt]}. "
    if question == "pos":
        return head + f"What is in the cell at row {grid.row}, column {grid.col} (1-based from the top-left)?"
    if question == "find_row":
        return head + "Exactly one cell is an input field. Which row (1-based from the top) is it in?"
    if question == "find_col":
        return head + "Exactly one cell is an input field. Which column (1-based from the left) is it in?"
    raise ValueError(question)


def feature_criteria(grid: FeatureGrid, question: str) -> dict[str, str | None]:
    if question == "pos":
        return {name: None for name in FEATURE_LABELS}
    if question == "find_row":
        return {str(i): f"row {i}" for i in range(1, grid.rows + 1)}
    if question == "find_col":
        return {str(i): f"column {i}" for i in range(1, grid.cols + 1)}
    raise ValueError(question)


def feature_gold(grid: FeatureGrid, question: str) -> str:
    if question == "pos":
        return grid.target
    if question == "find_row":
        return str(grid.input_row)
    return str(grid.input_col)
