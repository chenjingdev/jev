// engine.js — pure, stateless Tetris engine.
// Imported unchanged by the browser (public/app.js) and by Node (test/engine.test.js).
// No module-level mutable state; every exported function is a pure function of its arguments.

export const ROWS = 20;
export const COLS = 10;

/** Piece letters, also used as the fill value inside a board cell. */
export const PIECE_TYPES = ["I", "O", "T", "S", "Z", "J", "L"];

/** Canonical colors, shared by the renderer so engine and UI never disagree. */
export const PIECE_COLORS = {
  I: "#22d3ee",
  O: "#facc15",
  T: "#c084fc",
  S: "#4ade80",
  Z: "#f87171",
  J: "#60a5fa",
  L: "#fb923c",
};

// Spawn orientation of each piece, as [row, col] cells normalized to a 0-based bounding box.
//
//   I  XXXX      O  XX      T  .X.      S  .XX      Z  XX.      J  X..      L  ..X
//                   XX         XXX         XX.         .XX         XXX         XXX
const SPAWN_SHAPES = {
  I: [[0, 0], [0, 1], [0, 2], [0, 3]],
  O: [[0, 0], [0, 1], [1, 0], [1, 1]],
  T: [[0, 1], [1, 0], [1, 1], [1, 2]],
  S: [[0, 1], [0, 2], [1, 0], [1, 1]],
  Z: [[0, 0], [0, 1], [1, 1], [1, 2]],
  J: [[0, 0], [1, 0], [1, 1], [1, 2]],
  L: [[0, 2], [1, 0], [1, 1], [1, 2]],
};

// Short English description per unique rotation, in the same order as ROTATIONS below
// (each entry is the shape reached after N clockwise quarter turns from spawn).
const ROTATION_LABELS = {
  I: ["flat, 4 wide", "upright, 4 tall"],
  O: ["2x2 square"],
  T: ["flat side down", "nub pointing right", "flat side up", "nub pointing left"],
  S: ["flat, top row shifted right", "upright, right column shifted down"],
  Z: ["flat, top row shifted left", "upright, left column shifted down"],
  J: [
    "flat bottom, corner up-left",
    "upright, hook at top-right",
    "flat top, corner down-right",
    "upright, foot at bottom-left",
  ],
  L: [
    "flat bottom, corner up-right",
    "upright, foot at bottom-right",
    "flat top, corner down-left",
    "upright, hook at top-left",
  ],
};

function normalizeCells(cells) {
  const minRow = Math.min(...cells.map((c) => c[0]));
  const minCol = Math.min(...cells.map((c) => c[1]));
  return cells
    .map(([r, c]) => [r - minRow, c - minCol])
    .sort((a, b) => a[0] - b[0] || a[1] - b[1]);
}

function rotateCellsCW(cells) {
  const maxRow = Math.max(...cells.map((c) => c[0]));
  return normalizeCells(cells.map(([r, c]) => [c, maxRow - r]));
}

function cellsKey(cells) {
  return cells.map(([r, c]) => r + ":" + c).join(",");
}

function buildRotations(spawn) {
  const out = [];
  const seen = new Set();
  let cur = normalizeCells(spawn);
  for (let i = 0; i < 4; i++) {
    const key = cellsKey(cur);
    if (seen.has(key)) break;
    seen.add(key);
    out.push(cur);
    cur = rotateCellsCW(cur);
  }
  return out;
}

/** ROTATIONS[type] = array of unique rotation shapes; duplicates collapsed (O:1, I/S/Z:2, T/J/L:4). */
export const ROTATIONS = Object.freeze(
  Object.fromEntries(PIECE_TYPES.map((t) => [t, Object.freeze(buildRotations(SPAWN_SHAPES[t]))])),
);

/** Cells of one rotation of a piece, normalized to a 0-based bounding box. */
export function pieceCells(type, rot) {
  const rots = ROTATIONS[type];
  if (!rots) throw new Error("unknown piece type: " + type);
  return rots[((rot % rots.length) + rots.length) % rots.length];
}

/** Number of distinct rotations for a piece. */
export function rotationCount(type) {
  return ROTATIONS[type].length;
}

/** Short English description of a rotation, e.g. "flat side up". */
export function rotationLabel(type, rot) {
  const labels = ROTATION_LABELS[type];
  return labels[((rot % labels.length) + labels.length) % labels.length];
}

/** Bounding box of a rotation as { height, width }. */
export function pieceSize(type, rot) {
  const cells = pieceCells(type, rot);
  return {
    height: Math.max(...cells.map((c) => c[0])) + 1,
    width: Math.max(...cells.map((c) => c[1])) + 1,
  };
}

export function createEmptyBoard() {
  return Array.from({ length: ROWS }, () => new Array(COLS).fill(0));
}

export function cloneBoard(board) {
  return board.map((row) => row.slice());
}

/** Column heights: ROWS - (index of the topmost filled cell), 0 for an empty column. */
export function columnHeights(board) {
  const heights = new Array(COLS).fill(0);
  for (let c = 0; c < COLS; c++) {
    for (let r = 0; r < ROWS; r++) {
      if (board[r][c] !== 0) {
        heights[c] = ROWS - r;
        break;
      }
    }
  }
  return heights;
}

/**
 * Board statistics used both in candidate summaries and in the UI.
 * holes: empty cells with at least one filled cell above them in the same column.
 * bumpiness: sum of |height difference| over adjacent column pairs.
 * wellDepth/wellCol: deepest column relative to its neighbours (edges see only one neighbour).
 */
export function computeMetrics(board) {
  const heights = columnHeights(board);
  let holes = 0;
  for (let c = 0; c < COLS; c++) {
    let seenFilled = false;
    for (let r = 0; r < ROWS; r++) {
      if (board[r][c] !== 0) seenFilled = true;
      else if (seenFilled) holes++;
    }
  }
  let bumpiness = 0;
  for (let c = 0; c < COLS - 1; c++) bumpiness += Math.abs(heights[c] - heights[c + 1]);

  let wellDepth = 0;
  let wellCol = -1;
  for (let c = 0; c < COLS; c++) {
    const left = c === 0 ? Infinity : heights[c - 1];
    const right = c === COLS - 1 ? Infinity : heights[c + 1];
    const depth = Math.min(left, right) - heights[c];
    if (depth > wellDepth) {
      wellDepth = depth;
      wellCol = c;
    }
  }

  return {
    heights,
    maxHeight: Math.max(...heights),
    aggregateHeight: heights.reduce((a, b) => a + b, 0),
    holes,
    bumpiness,
    wellDepth,
    wellCol,
  };
}

/** Remove full rows, returning a new board and how many rows went. */
export function clearLines(board) {
  const kept = board.filter((row) => row.some((v) => v === 0));
  const linesCleared = ROWS - kept.length;
  const fresh = Array.from({ length: linesCleared }, () => new Array(COLS).fill(0));
  return { board: fresh.concat(kept), linesCleared };
}

/** Standard single/double/triple/tetris scoring. */
export function lineScore(linesCleared) {
  return [0, 100, 300, 500, 800][linesCleared] ?? 0;
}

function collides(board, cells, top, col) {
  for (const [r, c] of cells) {
    const row = top + r;
    const column = col + c;
    if (column < 0 || column >= COLS) return true;
    if (row >= ROWS) return true;
    if (row < 0) continue; // above the ceiling is free space
    if (board[row][column] !== 0) return true;
  }
  return false;
}

/**
 * Row at which the piece comes to rest when hard-dropped from above the board,
 * or null when it cannot rest inside the board at all. A negative result means
 * the piece would stick out over the ceiling.
 */
export function dropRow(board, type, rot, col) {
  const cells = pieceCells(type, rot);
  const { height } = pieceSize(type, rot);
  let landing = null;
  for (let top = -height; top + height <= ROWS; top++) {
    if (collides(board, cells, top, col)) break;
    landing = top;
  }
  return landing;
}

/**
 * Every legal hard-drop landing for a piece on a board: each unique rotation crossed
 * with every column the rotation fits into. Candidates that would leave part of the
 * piece above the ceiling are dropped.
 */
export function enumeratePlacements(board, pieceType) {
  const out = [];
  const rots = ROTATIONS[pieceType];
  for (let rot = 0; rot < rots.length; rot++) {
    const cells = rots[rot];
    const { width } = pieceSize(pieceType, rot);
    for (let col = 0; col + width <= COLS; col++) {
      const top = dropRow(board, pieceType, rot, col);
      if (top === null || top < 0) continue; // no room, or overflows the ceiling
      const placed = cloneBoard(board);
      const absolute = [];
      for (const [r, c] of cells) {
        absolute.push([top + r, col + c]);
        placed[top + r][col + c] = pieceType;
      }
      const { board: boardAfter, linesCleared } = clearLines(placed);
      out.push({
        id: "c" + out.length,
        rot,
        col,
        cells: absolute,
        boardAfter,
        linesCleared,
        metrics: computeMetrics(boardAfter),
      });
    }
  }
  return out;
}

/** 21 lines: a `0123456789` column header, then 20 rows of 10 characters. */
export function boardToAscii(board) {
  const header = "0123456789";
  const rows = board.map((row) => row.map((v) => (v === 0 ? "." : v)).join(""));
  return [header, ...rows].join("\n");
}

function delta(after, before) {
  const d = after - before;
  if (d === 0) return "";
  return d > 0 ? " (+" + d + ")" : " (" + d + ")";
}

function span(values, singular, plural) {
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  return lo === hi ? singular + " " + lo : plural + " " + lo + "-" + hi;
}

/** One human-readable sentence describing what a candidate placement does. */
export function candidateSummary(pieceType, cand, boardBefore) {
  const before = computeMetrics(boardBefore);
  const after = cand.metrics;
  const rows = cand.cells.map((c) => c[0]);
  const cols = cand.cells.map((c) => c[1]);
  const clears =
    cand.linesCleared === 0
      ? "clears no lines"
      : "clears " + cand.linesCleared + (cand.linesCleared === 1 ? " line" : " lines");
  return (
    pieceType +
    " piece, rotation " +
    cand.rot +
    " (" +
    rotationLabel(pieceType, cand.rot) +
    "), lands at " +
    span(cols, "column", "columns") +
    ", " +
    span(rows, "row", "rows") +
    "; " +
    clears +
    "; after: max height " +
    after.maxHeight +
    delta(after.maxHeight, before.maxHeight) +
    ", holes " +
    after.holes +
    delta(after.holes, before.holes) +
    ", bumpiness " +
    after.bumpiness +
    ", aggregate height " +
    after.aggregateHeight
  );
}

/** One shuffled 7-bag. Pure: the caller supplies the randomness. */
export function shuffledBag(random = Math.random) {
  const bag = PIECE_TYPES.slice();
  for (let i = bag.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [bag[i], bag[j]] = [bag[j], bag[i]];
  }
  return bag;
}

/** Column a piece spawns in: horizontally centred for its spawn rotation. */
export function spawnColumn(type) {
  return Math.floor((COLS - pieceSize(type, 0).width) / 2);
}
