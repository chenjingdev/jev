// engine.js — pure 2048 on a 4×4 board. Shared by the browser, the tests and the headless
// measurement script, so nothing here touches the DOM.
//
// A board is a flat array of 16 numbers, row-major, 0 for empty. A move slides every line
// toward one wall and merges equal neighbours once (the classic rules). `move` also returns
// where every tile went so the page can animate it, and `facts`/`summarize` turn a board into
// the numbers and the sentence that Jev reads — Jev never sees the picture.

export const N = 4;
export const DIRS = ["up", "down", "left", "right"];

export function emptyBoard() {
  return new Array(N * N).fill(0);
}

// mulberry32: a seed makes a game reproducible (`?seed=`), which the recordings rely on.
export function makeRng(seed) {
  let a = seed >>> 0;
  return function rand() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Spawns a 2 (90%) or a 4 (10%) on a random empty cell. Returns null on a full board.
export function spawn(board, rand) {
  const empties = [];
  for (let i = 0; i < board.length; i++) if (board[i] === 0) empties.push(i);
  if (empties.length === 0) return null;
  const index = empties[Math.floor(rand() * empties.length)];
  const value = rand() < 0.9 ? 2 : 4;
  const next = board.slice();
  next[index] = value;
  return { board: next, index, value };
}

// The 4 lines of a direction, each listed from the wall the tiles slide toward.
export function linesOf(dir) {
  const lines = [];
  for (let k = 0; k < N; k++) {
    const line = [];
    for (let j = 0; j < N; j++) {
      if (dir === "left") line.push(k * N + j);
      else if (dir === "right") line.push(k * N + (N - 1 - j));
      else if (dir === "up") line.push(j * N + k);
      else line.push((N - 1 - j) * N + k);
    }
    lines.push(line);
  }
  return lines;
}

// Slides one line of values toward index 0. Returns the new values plus, for each output
// slot, the input slots that landed there (one, or two when they merged).
export function slideLine(values) {
  const out = [];
  const sources = [];
  let gained = 0;
  let pending = -1; // index into `out` of a tile that may still merge
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (v === 0) continue;
    if (pending >= 0 && out[pending] === v) {
      out[pending] = v * 2;
      sources[pending].push(i);
      gained += v * 2;
      pending = -1;
    } else {
      out.push(v);
      sources.push([i]);
      pending = out.length - 1;
    }
  }
  while (out.length < values.length) out.push(0);
  return { values: out, sources, gained };
}

// Applies a move without spawning. `moved` lists every tile with where it came from and where
// it stopped; `merged` lists the cells where two tiles became one.
export function move(board, dir) {
  const next = emptyBoard();
  const moved = [];
  const merged = [];
  let gained = 0;
  let changed = false;
  for (const line of linesOf(dir)) {
    const { values, sources, gained: g } = slideLine(line.map((i) => board[i]));
    gained += g;
    for (let j = 0; j < N; j++) {
      const to = line[j];
      next[to] = values[j];
      if (values[j] !== board[to]) changed = true;
      if (!sources[j]) continue;
      for (const s of sources[j]) moved.push({ from: line[s], to, value: board[line[s]] });
      if (sources[j].length === 2) merged.push({ at: to, value: values[j] });
    }
  }
  return { board: next, gained, moved, merged, changed };
}

export function legalMoves(board) {
  return DIRS.filter((d) => move(board, d).changed);
}

export function maxTile(board) {
  return Math.max(0, ...board);
}

const log2 = (v) => (v > 0 ? Math.log2(v) : 0);

function isMonotone(vals) {
  const v = vals.filter((x) => x > 0);
  if (v.length < 2) return true;
  let inc = true;
  let dec = true;
  for (let i = 1; i < v.length; i++) {
    if (v[i] < v[i - 1]) inc = false;
    if (v[i] > v[i - 1]) dec = false;
  }
  return inc || dec;
}

// What the engine measures about a board. These are the numbers Jev reads; tetris showed that
// the ASCII alone is not enough for it to rank positions.
export function facts(board) {
  let empty = 0;
  let max = 0;
  let maxAt = -1;
  for (let i = 0; i < board.length; i++) {
    if (board[i] === 0) empty++;
    else if (board[i] > max) {
      max = board[i];
      maxAt = i;
    }
  }
  const r = Math.floor(maxAt / N);
  const c = maxAt % N;
  const corners = { 0: "top-left", [N - 1]: "top-right", [(N - 1) * N]: "bottom-left", [N * N - 1]: "bottom-right" };
  const maxCorner = maxAt >= 0 && corners[maxAt] ? corners[maxAt] : null;
  const maxOnEdge = maxAt >= 0 && (r === 0 || r === N - 1 || c === 0 || c === N - 1);

  let monotone = 0;
  for (let k = 0; k < N; k++) {
    if (isMonotone(board.slice(k * N, k * N + N))) monotone++;
    if (isMonotone([0, 1, 2, 3].map((j) => board[j * N + k]))) monotone++;
  }

  // Smoothness: how different neighbouring tiles are, in doublings. 0 is perfectly smooth.
  let rough = 0;
  let pairs = 0;
  for (let i = 0; i < N; i++) {
    for (let j = 0; j < N; j++) {
      const v = board[i * N + j];
      if (v === 0) continue;
      const right = j + 1 < N ? board[i * N + j + 1] : 0;
      const down = i + 1 < N ? board[(i + 1) * N + j] : 0;
      if (right) {
        rough += Math.abs(log2(v) - log2(right));
        if (right === v) pairs++;
      }
      if (down) {
        rough += Math.abs(log2(v) - log2(down));
        if (down === v) pairs++;
      }
    }
  }

  return {
    empty,
    max,
    maxCorner,
    maxOnEdge,
    monotone, // of 8 lines
    rough: Math.round(rough * 10) / 10,
    pairs, // adjacent equal pairs still on the board
    legal: legalMoves(board).length,
  };
}

// The board as four strings of four words — one token per cell, which is what Jev can index.
export function boardRows(board) {
  const rows = [];
  for (let r = 0; r < N; r++) {
    rows.push(
      board
        .slice(r * N, r * N + N)
        .map((v) => (v === 0 ? "." : String(v)))
        .join(" "),
    );
  }
  return rows;
}

// One sentence per candidate move, built from the engine's numbers. `withMetrics=false` keeps
// only the geometry (what merged, what moved) for the measurement script's comparison.
export function summarize(dir, before, result, withMetrics = true) {
  const fb = facts(before);
  const fa = facts(result.board);
  const parts = [`slide ${dir.toUpperCase()}`];
  if (result.merged.length) {
    const list = result.merged.map((m) => `${m.value / 2}+${m.value / 2}`).join(", ");
    parts.push(`merges ${result.merged.length} pair${result.merged.length > 1 ? "s" : ""} (${list}) for +${result.gained}`);
  } else parts.push("merges nothing");
  if (!withMetrics) return parts.join("; ") + ".";
  parts.push(`empty cells ${fb.empty} → ${fa.empty} before the new tile`);
  const where = fa.maxCorner ? `in the ${fa.maxCorner} corner` : fa.maxOnEdge ? "on an edge, not in a corner" : "away from the edges";
  const same = fb.maxCorner && fb.maxCorner === fa.maxCorner;
  parts.push(`largest tile ${fa.max} ${same ? "stays" : "ends up"} ${where}`);
  parts.push(`${fa.monotone} of 8 lines ordered (was ${fb.monotone})`);
  parts.push(`roughness ${fa.rough} (was ${fb.rough})`);
  parts.push(`${fa.pairs} mergeable pair${fa.pairs === 1 ? "" : "s"} left`);
  return parts.join("; ") + ".";
}

// Every legal move with its result and sentence: the candidate list Jev chooses from.
export function candidates(board, withMetrics = true) {
  const out = [];
  for (const dir of DIRS) {
    const result = move(board, dir);
    if (!result.changed) continue;
    out.push({ dir, result, summary: summarize(dir, board, result, withMetrics), rows: boardRows(result.board) });
  }
  return out;
}

export function isGameOver(board) {
  return legalMoves(board).length === 0;
}

export function newGame(rand) {
  let board = emptyBoard();
  board = spawn(board, rand).board;
  board = spawn(board, rand).board;
  return board;
}
