// srs.js — Super Rotation System: four rotation states per piece, wall/floor kicks, and a
// breadth-first search over every position a piece can actually reach by moving, rotating and
// soft-dropping from spawn. That is what makes spins, tucks and T-spins placements at all:
// a hard-drop enumeration (engine.js enumeratePlacements) cannot see a slot you rotate into.
//
// Pure like engine.js; imported unchanged by the browser and by the Node tests.

import { COLS, ROWS, cloneBoard, clearLines, computeMetrics } from "./engine.js";

// Cells per rotation state (0 = spawn, 1 = clockwise, 2 = 180, 3 = counter-clockwise), as
// [row, col] inside the piece's bounding box: 3x3 for T/S/Z/J/L, 4x4 for I, guideline O in 3x3.
export const SRS_SHAPES = {
  T: [
    [[0, 1], [1, 0], [1, 1], [1, 2]],
    [[0, 1], [1, 1], [1, 2], [2, 1]],
    [[1, 0], [1, 1], [1, 2], [2, 1]],
    [[0, 1], [1, 0], [1, 1], [2, 1]],
  ],
  J: [
    [[0, 0], [1, 0], [1, 1], [1, 2]],
    [[0, 1], [0, 2], [1, 1], [2, 1]],
    [[1, 0], [1, 1], [1, 2], [2, 2]],
    [[0, 1], [1, 1], [2, 0], [2, 1]],
  ],
  L: [
    [[0, 2], [1, 0], [1, 1], [1, 2]],
    [[0, 1], [1, 1], [2, 1], [2, 2]],
    [[1, 0], [1, 1], [1, 2], [2, 0]],
    [[0, 0], [0, 1], [1, 1], [2, 1]],
  ],
  S: [
    [[0, 1], [0, 2], [1, 0], [1, 1]],
    [[0, 1], [1, 1], [1, 2], [2, 2]],
    [[1, 1], [1, 2], [2, 0], [2, 1]],
    [[0, 0], [1, 0], [1, 1], [2, 1]],
  ],
  Z: [
    [[0, 0], [0, 1], [1, 1], [1, 2]],
    [[0, 2], [1, 1], [1, 2], [2, 1]],
    [[1, 0], [1, 1], [2, 1], [2, 2]],
    [[0, 1], [1, 0], [1, 1], [2, 0]],
  ],
  I: [
    [[1, 0], [1, 1], [1, 2], [1, 3]],
    [[0, 2], [1, 2], [2, 2], [3, 2]],
    [[2, 0], [2, 1], [2, 2], [2, 3]],
    [[0, 1], [1, 1], [2, 1], [3, 1]],
  ],
  O: [
    [[0, 1], [0, 2], [1, 1], [1, 2]],
    [[0, 1], [0, 2], [1, 1], [1, 2]],
    [[0, 1], [0, 2], [1, 1], [1, 2]],
    [[0, 1], [0, 2], [1, 1], [1, 2]],
  ],
};

// Kick offsets as [dx, dy] with dy pointing UP (guideline convention); applied as col += dx,
// row -= dy. Keyed by "from>to" state.
const KICKS_JLSTZ = {
  "0>1": [[0, 0], [-1, 0], [-1, 1], [0, -2], [-1, -2]],
  "1>0": [[0, 0], [1, 0], [1, -1], [0, 2], [1, 2]],
  "1>2": [[0, 0], [1, 0], [1, -1], [0, 2], [1, 2]],
  "2>1": [[0, 0], [-1, 0], [-1, 1], [0, -2], [-1, -2]],
  "2>3": [[0, 0], [1, 0], [1, 1], [0, -2], [1, -2]],
  "3>2": [[0, 0], [-1, 0], [-1, -1], [0, 2], [-1, 2]],
  "3>0": [[0, 0], [-1, 0], [-1, -1], [0, 2], [-1, 2]],
  "0>3": [[0, 0], [1, 0], [1, 1], [0, -2], [1, -2]],
};
const KICKS_I = {
  "0>1": [[0, 0], [-2, 0], [1, 0], [-2, -1], [1, 2]],
  "1>0": [[0, 0], [2, 0], [-1, 0], [2, 1], [-1, -2]],
  "1>2": [[0, 0], [-1, 0], [2, 0], [-1, 2], [2, -1]],
  "2>1": [[0, 0], [1, 0], [-2, 0], [1, -2], [-2, 1]],
  "2>3": [[0, 0], [2, 0], [-1, 0], [2, 1], [-1, -2]],
  "3>2": [[0, 0], [-2, 0], [1, 0], [-2, -1], [1, 2]],
  "3>0": [[0, 0], [1, 0], [-2, 0], [1, -2], [-2, 1]],
  "0>3": [[0, 0], [-1, 0], [2, 0], [-1, 2], [2, -1]],
};
const KICKS_O = { "0>1": [[0, 0]], "1>0": [[0, 0]], "1>2": [[0, 0]], "2>1": [[0, 0]],
  "2>3": [[0, 0]], "3>2": [[0, 0]], "3>0": [[0, 0]], "0>3": [[0, 0]] };

function kicksFor(type) {
  if (type === "I") return KICKS_I;
  if (type === "O") return KICKS_O;
  return KICKS_JLSTZ;
}

/** Bounding-box cells of a piece in an SRS rotation state (0..3). */
export function srsCells(type, state) {
  const shapes = SRS_SHAPES[type];
  if (!shapes) throw new Error("unknown piece type: " + type);
  return shapes[((state % 4) + 4) % 4];
}

/** Spawn position of the bounding box: horizontally centred, top rows just inside the board. */
export function srsSpawn(type) {
  return type === "I" ? { row: -1, col: 3 } : { row: 0, col: 3 };
}

function fits(board, type, state, row, col) {
  for (const [r, c] of srsCells(type, state)) {
    const rr = row + r;
    const cc = col + c;
    if (cc < 0 || cc >= COLS || rr >= ROWS) return false;
    if (rr < 0) continue; // above the ceiling is free
    if (board[rr][cc] !== 0) return false;
  }
  return true;
}

/**
 * Try to rotate a piece with SRS kicks. Returns the new box position and the kick index used,
 * or null when every kick collides.
 */
export function tryRotate(board, type, state, row, col, dir) {
  const to = (((state + dir) % 4) + 4) % 4;
  const table = kicksFor(type)[state + ">" + to];
  for (let i = 0; i < table.length; i++) {
    const [dx, dy] = table[i];
    const nr = row - dy;
    const nc = col + dx;
    if (fits(board, type, to, nr, nc)) return { state: to, row: nr, col: nc, kick: i };
  }
  return null;
}

function filledOrWall(board, r, c) {
  if (r < 0) return false; // open sky above the board does not count as a wall
  if (r >= ROWS || c < 0 || c >= COLS) return true;
  return board[r][c] !== 0;
}

/**
 * Three-corner T-spin test. Only meaningful when the piece is a T that locked right after a
 * rotation. Returns "full", "mini" or null.
 */
export function tspinKind(board, state, row, col, kick) {
  const corners = [
    [row, col], [row, col + 2], [row + 2, col + 2], [row + 2, col], // TL, TR, BR, BL
  ];
  const filled = corners.map(([r, c]) => filledOrWall(board, r, c));
  if (filled.filter(Boolean).length < 3) return null;
  // The two corners the flat side faces are the "front" corners: state 0 faces up, and so on.
  const front = [[0, 1], [1, 2], [2, 3], [3, 0]][state];
  const isFull = (filled[front[0]] && filled[front[1]]) || kick === 4;
  return isFull ? "full" : "mini";
}

/** Guideline scoring including T-spins. */
export function placementScore(linesCleared, tspin) {
  if (tspin === "full") return [400, 800, 1200, 1600][linesCleared] ?? 0;
  if (tspin === "mini") return [100, 200, 400, 400][linesCleared] ?? 0;
  return [0, 100, 300, 500, 800][linesCleared] ?? 0;
}

const MOVES = ["L", "R", "CW", "CCW", "D"];

/**
 * Every placement a piece can reach from spawn by shifting, rotating (with kicks) and
 * soft-dropping, deduplicated by the cells it ends on. Each candidate carries the move path
 * from spawn (for animation), its SRS state, and whether it locks as a T-spin.
 *
 * Returns [] when the piece cannot even spawn — that is game over.
 */
export function reachablePlacements(board, type) {
  const spawn = srsSpawn(type);
  if (!fits(board, type, 0, spawn.row, spawn.col)) return [];

  // BFS over (state, row, col, lastWasRotation). The rotation flag is part of the node so a
  // slot reachable both by dropping and by spinning keeps the spin path (that is the T-spin).
  const key = (s, r, c, rot) => ((s * 64 + (r + 8)) * 16 + c) * 2 + rot;
  const start = { state: 0, row: spawn.row, col: spawn.col, rot: 0, kick: -1, prev: null, move: null };
  const seen = new Map([[key(0, spawn.row, spawn.col, 0), start]]);
  const queue = [start];
  const lockable = [];

  for (let qi = 0; qi < queue.length; qi++) {
    const node = queue[qi];
    if (!fits(board, type, node.state, node.row + 1, node.col)) lockable.push(node);
    for (const move of MOVES) {
      let next = null;
      if (move === "L" || move === "R") {
        const nc = node.col + (move === "L" ? -1 : 1);
        if (fits(board, type, node.state, node.row, nc)) {
          next = { state: node.state, row: node.row, col: nc, rot: 0, kick: -1 };
        }
      } else if (move === "D") {
        if (fits(board, type, node.state, node.row + 1, node.col)) {
          next = { state: node.state, row: node.row + 1, col: node.col, rot: 0, kick: -1 };
        }
      } else {
        const r = tryRotate(board, type, node.state, node.row, node.col, move === "CW" ? 1 : -1);
        if (r) next = { state: r.state, row: r.row, col: r.col, rot: 1, kick: r.kick };
      }
      if (!next) continue;
      const k = key(next.state, next.row, next.col, next.rot);
      if (seen.has(k)) continue;
      next.prev = node;
      next.move = move;
      seen.set(k, next);
      queue.push(next);
    }
  }

  // Dedupe by final cells; prefer a T-spin lock, otherwise the first (shortest) path found.
  const byCells = new Map();
  for (const node of lockable) {
    const cells = srsCells(type, node.state).map(([r, c]) => [node.row + r, node.col + c]);
    if (cells.some(([r]) => r < 0)) continue; // would lock sticking out over the ceiling
    const tspin = type === "T" && node.rot ? tspinKind(board, node.state, node.row, node.col, node.kick) : null;
    const ck = cells.map(([r, c]) => r + ":" + c).sort().join(",");
    const existing = byCells.get(ck);
    if (existing && (existing.tspin || !tspin)) continue;
    byCells.set(ck, { node, cells, tspin });
  }

  const out = [];
  for (const { node, cells, tspin } of byCells.values()) {
    const placed = cloneBoard(board);
    for (const [r, c] of cells) placed[r][c] = type;
    const { board: boardAfter, linesCleared } = clearLines(placed);
    const path = [];
    for (let n = node; n.prev; n = n.prev) path.push(n.move);
    path.reverse();
    out.push({
      id: "c" + out.length,
      rot: node.state,
      row: node.row,
      col: node.col,
      cells: cells.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]),
      path,
      tspin,
      boardAfter,
      linesCleared,
      score: placementScore(linesCleared, tspin),
      metrics: computeMetrics(boardAfter),
    });
  }
  // Stable order: by state, then column, then row — matches the hard-drop enumeration's feel.
  out.sort((a, b) => a.rot - b.rot || a.col - b.col || a.row - b.row);
  out.forEach((c, i) => (c.id = "c" + i));
  return out;
}

/**
 * Replay a move path from spawn, returning every intermediate box position. Used by the
 * renderer to animate exactly the moves the search found (including kicks).
 */
export function replayPath(board, type, path) {
  const spawn = srsSpawn(type);
  let cur = { state: 0, row: spawn.row, col: spawn.col };
  const frames = [{ ...cur, move: null }];
  for (const move of path) {
    if (move === "L" || move === "R") {
      cur = { ...cur, col: cur.col + (move === "L" ? -1 : 1) };
    } else if (move === "D") {
      cur = { ...cur, row: cur.row + 1 };
    } else {
      const r = tryRotate(board, type, cur.state, cur.row, cur.col, move === "CW" ? 1 : -1);
      if (!r) throw new Error("path replays into a blocked rotation");
      cur = { state: r.state, row: r.row, col: r.col };
    }
    frames.push({ ...cur, move });
  }
  return frames;
}
