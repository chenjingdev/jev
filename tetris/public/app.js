// app.js — canvas renderer, game loop and control panel.
// Every piece runs the Jev Neurons pipeline of docs/neurons-spec.md: the engine looks (R0), the
// intent neurons fire (R1 /api/sense), the motor neurons propose placements (R2 /api/motor),
// and the arbiter, the coach and the hold neuron judge the proposals at once (R3
// /api/arbitrate). Everything bright on the board is a returned probability; the only thing
// animated before an answer arrives means "a request is out". With the neuron toggle off the
// original single-Choice path (/api/decide) plays instead, unchanged.

import {
  COLS,
  ROWS,
  PIECE_COLORS,
  boardToAscii,
  computeMetrics,
  createEmptyBoard,
  pieceCells,
  pieceSize,
  rotationLabel,
  shuffledBag,
} from "./engine.js";
import { reachablePlacements, replayPath, srsCells, srsSpawn } from "./srs.js";
import {
  COUNTUP_MS,
  FADE_MS,
  FIELD_ALPHA,
  FIELD_ALPHA_AFTER,
  GHOST_LABEL_MIN_P,
  GHOST_MS,
  HUES,
  INTENTS,
  LABELS_KO,
  MAX_GHOST_ALPHA,
  MIN_GHOST_ALPHA,
  RING_INSET_PX,
  THINKING_ALPHA,
  WIRE_HOLD_MS,
  arbitrateProposals,
  candidateSummaryV2,
  combine,
  effects,
  facts as factsOf,
  fallbackCombine,
  gate,
  ghostsFrom,
  proposalsFrom,
} from "./neurons.js";

// The cortex panel (cortex.js) is loaded dynamically: the game must keep playing when that file
// is missing or throws mid-edit, so a failed import degrades to no-op renderers and every call
// into it goes through safe().
const cortexModule = await import("./cortex.js").catch((err) => {
  console.warn("cortex.js unavailable, panel disabled:", err.message);
  return null;
});
const noop = () => null;
const initCortex = cortexModule?.initCortex ?? noop;
const renderCortex = cortexModule?.renderCortex ?? noop;
const neuronAnchor = cortexModule?.neuronAnchor ?? noop;
const setInflight = cortexModule?.setInflight ?? noop;
function safe(fn, ...args) {
  try {
    return fn(...args);
  } catch (err) {
    console.warn("cortex:", err);
    return null;
  }
}

// Cell sizes are recomputed from the viewport (see applySizes) so the board fits a phone.
let CELL = 30;
let QS = 14; // next-queue cell size
let QUEUE_W = 70;
const QUEUE_N = 5; // pieces shown; Jev reads the same five
const DECIDE_GHOST_MS = 800; // single-Choice path: how long its heatmap sits before the move
const STEP_MS = 90; // one shift or rotation in the replayed path
const DROP_TOTAL_MS = 260; // a run of soft-drop steps is compressed into about this long
const FLASH_MS = 240;
const SCANLINE_MS = 200; // the white line that sweeps the board at spawn
const CROSSFADE_MS = 200; // wires → filled ghosts at the verdict
const WIRE_STAGGER_MS = 80; // proposal wires appear one after another in fired order
const DIM_ALPHA = 0.7; // settled stack while the cortex is thinking
const TOP_N = 5; // single-Choice path: ghosts and rows shown
const MAX_CANDS = 80; // above this the API hit its max-token error (136 candidates observed)
const USD_PER_TOKEN = 42 / 1e9; // $42 per billion tokens
const NARROW_PX = 900; // must match the @media breakpoint in index.html
const COL_GAP = 24; // must match `main { gap }` in index.html
const SVG_NS = "http://www.w3.org/2000/svg";
const MONO = '"SFMono-Regular", "SF Mono", Menlo, Consolas, monospace';

// No instruction UI: Jev is asked to play well. The server still accepts an instruction
// field, so the string stays in the payload for the log and the Jev-facing contract.
const INSTRUCTION = "";

// Phase keys name the request in flight; the Korean name is the layer that just answered
// (R1 arrives → '연합' while R2 is out, R2 arrives → '운동' while R3 is out).
const PHASE_TEXT = {
  idle: ["대기", "시작하는 중…"],
  sense: ["감각", "뉴런에 자극 전달 중…"],
  motor: ["연합", "의도 발화 → 운동 뉴런에 전달 중…"],
  arbitrate: ["운동", "제안 → 중재와 코치가 동시에 심사 중…"],
  verdict: ["판정", ""],
  single: ["외길", "착지 가능한 자리가 하나뿐 · Jev 없이 배치"],
  thinking: ["Jev에게 묻는 중…", "모든 착지 위치를 한 번에 제시"],
  ghost: ["확률 분포", "밝을수록 Jev가 선호하는 자리"],
  moving: ["이동", "회전 → 수평 이동 → 하드드롭"],
  clearing: ["줄 제거", ""],
  waiting: ["대기", "다음 조각까지"],
  paused: ["일시정지", "재개를 누르세요"],
  over: ["게임 오버", "새 게임을 눌러 다시 시작"],
};
// Phases whose text stays put when the game auto-pauses on a failed request.
const REQUEST_PHASES = new Set(["thinking", "sense", "motor", "arbitrate"]);
// Phases during which the settled stack is dimmed and the spawned piece hovers at the top.
const CORTEX_PHASES = new Set(["sense", "motor", "arbitrate", "verdict", "single", "thinking", "ghost"]);

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const setText = (id, text) => {
  const el = $(id);
  if (el) el.textContent = text;
};
const setHTML = (id, html) => {
  const el = $(id);
  if (el) el.innerHTML = html;
};
const lab = (n) => LABELS_KO[n] ?? n;
// ".92" — the spec's two-decimal probability without the leading zero.
const fmtP = (p) => (p >= 1 ? "1.00" : (p ?? 0).toFixed(2).replace(/^0/, ""));

const boardCanvas = $("board");
const bctx = boardCanvas.getContext("2d");
const queueCanvas = $("queue");
const qctx = queueCanvas ? queueCanvas.getContext("2d") : null;

function sizeCanvas(canvas, ctx, cssW, cssH) {
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(cssW * dpr);
  canvas.height = Math.round(cssH * dpr);
  canvas.style.width = cssW + "px";
  canvas.style.height = cssH + "px";
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
// Phone: min(30, floor((viewport - 32px gutters) / COLS)). Desktop: the board is the star,
// so it takes the viewport height minus header/caption chrome, capped at 44px per cell.
// The floor keeps a tiny board drawable either way.
function cellSizeForViewport() {
  const vw = window.innerWidth || document.documentElement.clientWidth || 0;
  const vh = window.innerHeight || document.documentElement.clientHeight || 0;
  // The queue strip beside the board is QUEUE_CELLS cells wide plus its gap.
  if (vw <= NARROW_PX) return Math.max(8, Math.min(30, Math.floor((vw - 32 - 12) / (COLS + QUEUE_CELLS))));
  const byHeight = Math.floor((vh - 104) / ROWS); // header + paddings; nothing sits under the board now
  const byWidth = Math.floor((vw - 48 - 24 - 24) / ((COLS + QUEUE_CELLS) * 2)); // two equal halves + gaps
  return Math.max(8, Math.min(44, byHeight, byWidth));
}
const QUEUE_CELLS = 2.4; // strip width in board cells
// The panel is exactly as wide as the board row (board + queue strip): two equal halves.
// Its height is pinned to the board column (--col-h) so the two read as one block.
function sidePanelWidth() {
  return Math.max(240, COLS * CELL + 12 + QUEUE_W);
}

function applySizes() {
  CELL = cellSizeForViewport();
  QS = Math.max(6, Math.round(CELL * 0.5));
  QUEUE_W = Math.round(CELL * QUEUE_CELLS);
  sizeCanvas(boardCanvas, bctx, COLS * CELL, ROWS * CELL);
  if (queueCanvas) sizeCanvas(queueCanvas, qctx, QUEUE_W, ROWS * CELL);
  document.documentElement.style.setProperty("--side-w", sidePanelWidth() + "px");
  // Pin the panel to the board column's height (not the viewport's) so the two stay a square
  // on tall screens too; the cortex card absorbs the difference.
  const col = document.querySelector(".col-board");
  if (col) document.documentElement.style.setProperty("--col-h", Math.round(col.getBoundingClientRect().height) + "px");
}
applySizes();

// ---------------------------------------------------------------- game state

function freshStats() {
  return {
    pieces: 0,
    lines: 0,
    score: 0,
    tspins: 0,
    calls: 0,
    r1Sum: 0,
    r2Sum: 0,
    r3Sum: 0,
    r1Count: 0,
    r2Count: 0,
    r3Count: 0,
    lastLatency: null,
    latencySum: 0, // total request time per piece (r1 + r2 + r3, or the single decide call)
    latencyCount: 0, // pieces that asked Jev at all
    tokensIn: 0,
    tokensOut: 0,
    confidence: null,
    disagreements: 0,
    overrides: 0,
    vetoes: 0, // pieces on which the coach hard-vetoed at least one proposal
    changed: 0,
    forced: 0,
    fallbacks: 0,
  };
}

const G = {
  gen: 0,
  board: createEmptyBoard(),
  queue: [],
  phase: "idle",
  paused: false,
  over: false,
  pieceType: null,
  nextType: null,
  candidates: [],
  dropped: 0, // candidates cut by the MAX_CANDS cap on this piece
  summaries: new Map(), // id → candidateSummaryV2 (exactly what the motor neurons read)
  effects: new Map(), // id → effects (exactly what the arbiter and coach read)
  decision: null, // single-Choice path answer
  chosen: null,
  ghosts: [],
  wires: [],
  fieldGhosts: [],
  anim: null,
  flashRows: [],
  surface: null,
  facts: null,
  sense: null,
  appetite: null,
  intent: null,
  motor: null,
  proposals: null,
  verdict: null,
  instructions: {},
  memory: { previousIntent: null, hold: 0 },
  recent: [],
  piecesSinceClear: 0,
  timeline: [],
  cortex: { phase: "idle", t0: 0, tR1: 0, tR2: 0, tR3: 0 },
  spawnT0: 0,
  opts: { neurons: true, prefetch: false },
  stats: freshStats(),
  sessionCost: 0,
  log: [],
};
window.__jev = G; // read by the browser smoke test

function refillQueue() {
  while (G.queue.length < 8) G.queue.push(...shuffledBag());
}

// ---------------------------------------------------------------- canvas primitives

function drawCell(ctx, rowF, colF, color, alpha = 1, mode = "solid") {
  const x = colF * CELL;
  const y = rowF * CELL;
  if (mode === "wire") {
    ctx.globalAlpha = Math.min(1, alpha * 2.4);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    ctx.strokeRect(x + 1.5, y + 1.5, CELL - 3, CELL - 3);
    ctx.globalAlpha = 1;
    return;
  }
  ctx.globalAlpha = alpha;
  ctx.fillStyle = color;
  ctx.fillRect(x + 1, y + 1, CELL - 2, CELL - 2);
  if (mode === "ghost") {
    // A white outline keeps a ghost readable as "not yet placed" even at high alpha, and
    // separates the intent hues from the piece palette they were chosen against.
    ctx.globalAlpha = Math.min(1, alpha + 0.3);
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 2;
    ctx.strokeRect(x + 2, y + 2, CELL - 4, CELL - 4);
  } else if (mode === "solid") {
    ctx.globalAlpha = alpha * 0.32;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(x + 1, y + 1, CELL - 2, 3);
  }
  ctx.globalAlpha = 1;
}

function drawGrid(ctx) {
  ctx.fillStyle = "#080a0e";
  ctx.fillRect(0, 0, COLS * CELL, ROWS * CELL);
  ctx.strokeStyle = "#151926";
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let c = 1; c < COLS; c++) {
    ctx.moveTo(c * CELL + 0.5, 0);
    ctx.lineTo(c * CELL + 0.5, ROWS * CELL);
  }
  for (let r = 1; r < ROWS; r++) {
    ctx.moveTo(0, r * CELL + 0.5);
    ctx.lineTo(COLS * CELL, r * CELL + 0.5);
  }
  ctx.stroke();
}

function drawSettled(ctx, alpha) {
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const v = G.board[r][c];
      if (v !== 0) drawCell(ctx, r, c, PIECE_COLORS[v] ?? "#8892a6", alpha);
    }
  }
}

function drawSrsPiece(ctx, type, state, row, col, alpha = 1) {
  const color = PIECE_COLORS[type];
  for (const [r, c] of srsCells(type, state)) {
    if (row + r >= 0) drawCell(ctx, row + r, col + c, color, alpha);
  }
}

function centroid(cells) {
  const cy = (cells.reduce((a, c) => a + c[0], 0) / cells.length + 0.5) * CELL;
  const cx = (cells.reduce((a, c) => a + c[1], 0) / cells.length + 0.5) * CELL;
  return { cx, cy };
}

function bbox(cells) {
  const rows = cells.map((c) => c[0]);
  const cols = cells.map((c) => c[1]);
  return {
    x: Math.min(...cols) * CELL,
    y: Math.min(...rows) * CELL,
    w: (Math.max(...cols) - Math.min(...cols) + 1) * CELL,
    h: (Math.max(...rows) - Math.min(...rows) + 1) * CELL,
  };
}

// Outline of a set of cells inset by d px, as line segments. Edges shared by two cells of the
// set are interior and skipped. Each end of a boundary edge is shortened at a convex corner,
// left alone on a straight run and extended at a concave corner, so the inset outlines of
// neighbouring cells meet without gaps; that is what makes the concentric rings read as one
// ring around the whole piece rather than four boxes.
const SIDES = [
  { n: [-1, 0], t: [0, 1], p0: [0, 0] }, // top: left → right
  { n: [0, 1], t: [1, 0], p0: [0, 1] }, // right: top → bottom
  { n: [1, 0], t: [0, -1], p0: [1, 1] }, // bottom: right → left
  { n: [0, -1], t: [-1, 0], p0: [1, 0] }, // left: bottom → top
];
function outlineSegments(cells, d) {
  const set = new Set(cells.map(([r, c]) => r + ":" + c));
  const has = (r, c) => set.has(r + ":" + c);
  const segs = [];
  for (const [r, c] of cells) {
    for (const { n, t, p0 } of SIDES) {
      if (has(r + n[0], c + n[1])) continue;
      const shift = (dir) => {
        const along = has(r + dir * t[0], c + dir * t[1]);
        const diag = has(r + dir * t[0] + n[0], c + dir * t[1] + n[1]);
        if (!along) return -dir * d; // convex: pull the end in
        return diag ? dir * d : 0; // concave: push it out; straight: leave it
      };
      const s0 = shift(-1);
      const s1 = shift(1);
      const x0 = (c + p0[1]) * CELL;
      const y0 = (r + p0[0]) * CELL;
      const x1 = x0 + t[1] * CELL;
      const y1 = y0 + t[0] * CELL;
      segs.push([
        x0 + t[1] * s0 - n[1] * d,
        y0 + t[0] * s0 - n[0] * d,
        x1 + t[1] * s1 - n[1] * d,
        y1 + t[0] * s1 - n[0] * d,
      ]);
    }
  }
  return segs;
}

function strokeOutline(ctx, cells, inset, color, width, { alpha = 1, dash = null, glow = 0 } = {}) {
  const segs = outlineSegments(cells, inset);
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineCap = "square";
  if (dash) ctx.setLineDash(dash);
  if (glow) {
    ctx.shadowColor = color;
    ctx.shadowBlur = glow;
  }
  ctx.beginPath();
  for (const [x0, y0, x1, y1] of segs) {
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
  }
  ctx.stroke();
  ctx.restore();
}

function hatchCells(ctx, cells, color, alpha) {
  const b = bbox(cells);
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.beginPath();
  for (const [r, c] of cells) ctx.rect(c * CELL + 1, r * CELL + 1, CELL - 2, CELL - 2);
  ctx.clip();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (let x = b.x - b.h; x < b.x + b.w; x += 6) {
    ctx.moveTo(x, b.y + b.h);
    ctx.lineTo(x + b.h, b.y);
  }
  ctx.stroke();
  ctx.restore();
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

// The pill above a ghost: its backers' names (and ' · 선택', or VETO). Sits just above the
// piece's bounding box, or inside it when the piece touches the ceiling.
function drawPill(ctx, text, cx, topY, bg, alpha) {
  const fontPx = Math.max(9, Math.round(CELL * 0.32));
  ctx.font = `700 ${fontPx}px ${MONO}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const h = fontPx + 6;
  const w = Math.ceil(ctx.measureText(text).width) + 12;
  const x = clamp(cx - w / 2, 2, COLS * CELL - w - 2);
  const y = topY - h - 3 < 2 ? topY + 3 : topY - h - 3;
  ctx.save();
  ctx.globalAlpha = alpha;
  roundRect(ctx, x, y, w, h, 4);
  ctx.fillStyle = bg;
  ctx.fill();
  ctx.fillStyle = "#ffffff";
  ctx.fillText(text, x + w / 2, y + h / 2 + 0.5);
  ctx.restore();
}

function drawLabel(ctx, text, cx, cy, alpha) {
  ctx.save();
  ctx.font = `700 ${Math.round(CELL * 0.42)}px ${MONO}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.globalAlpha = alpha;
  ctx.lineWidth = 3;
  ctx.strokeStyle = "rgba(0,0,0,.85)";
  ctx.strokeText(text, cx, cy);
  ctx.fillStyle = "#ffffff";
  ctx.fillText(text, cx, cy);
  ctx.restore();
}

// ---------------------------------------------------------------- board drawing

// The next five pieces, top to bottom, in the strip beside the board. The first is drawn a
// touch larger and brighter; it is the piece Jev will be asked about next.
function drawQueue() {
  if (!qctx) return;
  const H = ROWS * CELL;
  qctx.clearRect(0, 0, QUEUE_W, H);
  const pieces = G.queue.slice(0, QUEUE_N);
  if (!pieces.length) return;
  const top = 26; // below the "다음" label
  const slot = (H - top - 8) / QUEUE_N;
  pieces.forEach((type, i) => {
    const s = i === 0 ? QS * 1.15 : QS;
    const { height, width } = pieceSize(type, 0);
    const ox = (QUEUE_W - width * s) / 2;
    const oy = top + slot * i + (slot - height * s) / 2;
    qctx.globalAlpha = i === 0 ? 1 : 0.55;
    qctx.fillStyle = PIECE_COLORS[type];
    for (const [r, c] of pieceCells(type, 0)) {
      qctx.fillRect(ox + c * s + 1, oy + r * s + 1, s - 2, s - 2);
    }
    if (i === 0) {
      qctx.globalAlpha = 0.32;
      qctx.fillStyle = "#ffffff";
      for (const [r, c] of pieceCells(type, 0)) qctx.fillRect(ox + c * s + 1, oy + r * s + 1, s - 2, 3);
    }
  });
  qctx.globalAlpha = 1;
}

// R2 arrived: each motor neuron's argmax as a wire outline in its hue, width 2k when k backers
// share the cells. Pills name the backers. The habit's own pick is a grey dashed outline.
function drawWires(ctx, now, alpha) {
  for (const w of G.wires) {
    if (now < w.appearAt) continue;
    const k = w.backers.length;
    const dash = w.dashed ? [5, 4] : null;
    strokeOutline(ctx, w.cells, k, w.color, 2 * k, { alpha, dash, glow: 6 * k });
  }
}

function drawWirePills(ctx, now, alpha) {
  for (const w of G.wires) {
    if (now < w.appearAt || !w.cells.length) continue;
    const b = bbox(w.cells);
    drawPill(ctx, w.tag, b.x + b.w / 2, b.y, w.color, alpha);
  }
}

function drawGhostFills(ctx, fade) {
  for (const g of G.ghosts) {
    const mode = g.faint ? "flat" : "ghost";
    for (const [r, c] of g.cells) drawCell(ctx, r, c, g.color, g.alpha * fade, mode);
  }
}

// Rings, veto marks, the chosen outline, pills and % labels: drawn over the stack so they stay
// legible whatever sits next to the ghost.
function drawGhostDecor(ctx, now, fade, countup) {
  for (const g of G.ghosts) {
    if (g.faint || !g.cells.length) continue;
    if (g.vetoed) {
      const b = bbox(g.cells);
      hatchCells(ctx, g.cells, HUES.veto, fade * 0.9);
      ctx.save();
      ctx.globalAlpha = fade;
      ctx.strokeStyle = HUES.veto;
      ctx.lineWidth = 2;
      ctx.strokeRect(b.x + 1, b.y + 1, b.w - 2, b.h - 2);
      ctx.restore();
    } else {
      g.rings.forEach((hue, i) => {
        const inset = RING_INSET_PX[Math.min(i, RING_INSET_PX.length - 1)];
        strokeOutline(ctx, g.cells, inset, hue, 1.5, { alpha: fade * 0.95 });
      });
      if (g.dashed) strokeOutline(ctx, g.cells, 1, "#ffffff", 1.5, { alpha: fade, dash: [4, 3] });
    }
    if (g.chosen) {
      const pulse = 0.7 + 0.3 * Math.sin(now / 260);
      strokeOutline(ctx, g.cells, 1.5, "#ffffff", 3, { alpha: fade * pulse, glow: 8 });
    }
  }
  for (const g of G.ghosts) {
    if (g.faint || !g.cells.length) continue;
    const b = bbox(g.cells);
    if (g.tag) drawPill(ctx, g.tag, b.x + b.w / 2, b.y, g.vetoed ? HUES.veto : g.color, fade);
    if (g.label != null && (g.vetoed || g.p >= GHOST_LABEL_MIN_P)) {
      const { cx, cy } = centroid(g.cells);
      const text = countup < 1 ? Math.round(100 * g.p * countup) + "%" : g.label;
      drawLabel(ctx, text, cx, cy, fade);
    }
  }
}

function drawForkPill(ctx, alpha) {
  const intent = G.intent;
  const ranked = intent ? intent.fired.slice(0, 2) : [];
  const a = HUES[ranked[0]] ?? HUES.default;
  const b = HUES[ranked[1]] ?? HUES.default;
  const fontPx = Math.max(9, Math.round(CELL * 0.32));
  ctx.save();
  ctx.font = `700 ${fontPx}px ${MONO}`;
  const w = Math.ceil(ctx.measureText("FORK").width) + 12;
  const h = fontPx + 6;
  const x = COLS * CELL - w - 4;
  const y = 4;
  ctx.globalAlpha = alpha;
  roundRect(ctx, x, y, w, h, 4);
  ctx.clip();
  ctx.fillStyle = a;
  ctx.fillRect(x, y, w / 2, h);
  ctx.fillStyle = b;
  ctx.fillRect(x + w / 2, y, w / 2, h);
  ctx.fillStyle = "#ffffff";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("FORK", x + w / 2, y + h / 2 + 0.5);
  ctx.restore();
}

function draw(now) {
  drawGrid(bctx);
  const phase = G.phase;
  const inCortex = CORTEX_PHASES.has(phase);

  if (phase === "sense" || phase === "motor" || phase === "thinking") {
    // Every legal landing, barely visible: "Jev is looking at all of these".
    for (const cand of G.candidates) {
      for (const [r, c] of cand.cells) {
        drawCell(bctx, r, c, PIECE_COLORS[G.pieceType], THINKING_ALPHA, "wire");
      }
    }
  }

  // Wires stay solid while R3 is out, then cross-fade into the filled ghosts at the verdict.
  let wireAlpha = 0;
  if (phase === "arbitrate") wireAlpha = 1;
  else if (phase === "verdict") wireAlpha = 1 - clamp((now - G.cortex.tR3) / CROSSFADE_MS, 0, 1);

  let ghostFade = 0;
  let countup = 1;
  if (phase === "verdict") {
    ghostFade = clamp((now - G.cortex.tR3) / CROSSFADE_MS, 0, 1);
    countup = clamp((now - G.cortex.tR3) / COUNTUP_MS, 0, 1);
  } else if (phase === "ghost") ghostFade = 1;
  else if (phase === "moving" && G.anim) ghostFade = clamp(1 - (now - G.anim.t0) / FADE_MS, 0, 1);

  if (phase === "arbitrate") {
    for (const g of G.fieldGhosts) for (const [r, c] of g.cells) drawCell(bctx, r, c, g.color, g.alpha, "flat");
  }
  if (wireAlpha > 0) drawWires(bctx, now, wireAlpha);
  if (ghostFade > 0) drawGhostFills(bctx, ghostFade);

  drawSettled(bctx, inCortex ? DIM_ALPHA : 1);

  // Wire pills vanish the moment the verdict lands: the ghost pills take their place, and two
  // sets of labels over the same cells during the crossfade just collide.
  if (wireAlpha > 0 && phase !== "verdict") drawWirePills(bctx, now, wireAlpha);
  if (ghostFade > 0) drawGhostDecor(bctx, now, ghostFade, countup);
  if (ghostFade > 0 && G.verdict?.fork) drawForkPill(bctx, ghostFade);

  // The piece about to be played hovers at the top of the board through every cortex phase.
  // Its true spawn rows sit above the ceiling, so it is shown clamped to row 0.
  if (inCortex && G.pieceType) {
    const sp = srsSpawn(G.pieceType);
    const minRow = Math.min(...srsCells(G.pieceType, 0).map((c) => c[0])) + sp.row;
    drawSrsPiece(bctx, G.pieceType, 0, sp.row - Math.min(0, minRow), sp.col, 0.9);
  }

  if (G.spawnT0 && now - G.spawnT0 < SCANLINE_MS) {
    const y = ((now - G.spawnT0) / SCANLINE_MS) * ROWS * CELL;
    bctx.save();
    bctx.globalAlpha = 0.85;
    bctx.fillStyle = "#ffffff";
    bctx.fillRect(0, y, COLS * CELL, 1);
    bctx.globalAlpha = 0.12;
    bctx.fillRect(0, y - 14, COLS * CELL, 14);
    bctx.restore();
  }

  if (phase === "moving" && G.anim) {
    // Step through the path the search found: every shift, spin (with its kick) and drop.
    const a = G.anim;
    const el = now - a.t0;
    let i = 0;
    while (i < a.times.length - 1 && a.times[i + 1] <= el) i++;
    const f = a.frames[i];
    drawSrsPiece(bctx, a.type, f.state, f.row, f.col);
    if (a.ring) {
      const cells = srsCells(a.type, f.state)
        .map(([r, c]) => [f.row + r, f.col + c])
        .filter(([r]) => r >= 0);
      if (cells.length) strokeOutline(bctx, cells, 1, a.ring, 2, { glow: 6 });
    }
  }

  if (phase === "clearing" && G.flashRows.length) {
    const on = Math.floor(now / 60) % 2 === 0;
    bctx.globalAlpha = on ? 0.85 : 0.35;
    bctx.fillStyle = "#ffffff";
    for (const r of G.flashRows) bctx.fillRect(0, r * CELL, COLS * CELL, CELL);
    bctx.globalAlpha = 1;
  }

  drawQueue();
}

function frame(now) {
  draw(now);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// Re-measure on resize / rotation (debounced), repaint and re-anchor the synapse lines.
let resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    applySizes();
    draw(performance.now());
    if (G.phase === "arbitrate" || G.phase === "verdict") drawSynapses(false);
  }, 100);
});
// The side panel scrolls on short viewports, which moves the circles the lines point at.
let scrollTimer = null;
document.querySelector(".col-side")?.addEventListener("scroll", () => {
  clearTimeout(scrollTimer);
  scrollTimer = setTimeout(() => {
    if (G.phase === "arbitrate" || G.phase === "verdict") drawSynapses(false);
  }, 60);
});

// ---------------------------------------------------------------- synapses overlay

// Lines from each proposal on the board to the neuron circles that proposed it. The overlay
// covers <main>; both ends are measured in viewport coordinates and shifted into the SVG's own
// box, with the viewBox pinned to its pixel size so one unit is one CSS pixel whatever the
// stylesheet says. Skipped on phones, where the panel stacks below the board.
// Board→neuron lines were dropped: they read as decoration and hid the layer order. The
// cortex card now animates the request sequence itself; ghosts keep their backer pills.
const SYNAPSES = false;
const LAYER_HOLD_MS = 280; // minimum time a lit band stays before the next one; requests overlap it

function drawSynapses(animate) {
  if (!SYNAPSES) return;
  const svg = $("synapses");
  if (!svg) return;
  if (window.innerWidth <= NARROW_PX) {
    svg.replaceChildren();
    return;
  }
  const items = G.ghosts.length ? G.ghosts.filter((g) => !g.faint) : G.wires;
  if (!items.length) {
    svg.replaceChildren();
    return;
  }
  const sRect = svg.getBoundingClientRect();
  const cRect = boardCanvas.getBoundingClientRect();
  if (!sRect.width || !cRect.width) return;
  svg.setAttribute("viewBox", `0 0 ${sRect.width} ${sRect.height}`);
  svg.setAttribute("preserveAspectRatio", "none");
  const sx = cRect.width / (COLS * CELL);
  const sy = cRect.height / (ROWS * CELL);
  const frag = document.createDocumentFragment();
  for (const g of items) {
    if (!g.cells.length) continue;
    const { cx, cy } = centroid(g.cells);
    const x1 = cRect.left + cx * sx - sRect.left;
    const y1 = cRect.top + cy * sy - sRect.top;
    g.backers.forEach((backer, i) => {
      const anchor = safe(neuronAnchor, backer);
      if (!anchor || typeof anchor.x !== "number") return;
      const line = document.createElementNS(SVG_NS, "line");
      const x2 = anchor.x - sRect.left;
      const y2 = anchor.y - sRect.top;
      line.setAttribute("x1", x1.toFixed(1));
      line.setAttribute("y1", y1.toFixed(1));
      line.setAttribute("x2", x2.toFixed(1));
      line.setAttribute("y2", y2.toFixed(1));
      line.setAttribute("stroke", g.vetoed ? HUES.veto : HUES[backer] ?? HUES.default);
      line.setAttribute("stroke-width", i === 0 ? "1.6" : "0.8");
      line.setAttribute("stroke-opacity", g.vetoed ? "0.9" : "0.75");
      line.setAttribute("stroke-linecap", "round");
      if (g.vetoed) {
        line.style.strokeDasharray = "5 4";
      } else if (animate) {
        // Draw-on: the dash offset runs from the full length to zero over 180ms.
        const len = Math.hypot(x2 - x1, y2 - y1);
        line.style.strokeDasharray = `${len}`;
        line.style.strokeDashoffset = `${len}`;
        line.style.transition = "stroke-dashoffset 180ms ease-out";
        requestAnimationFrame(() => requestAnimationFrame(() => (line.style.strokeDashoffset = "0")));
      }
      frag.appendChild(line);
    });
  }
  svg.replaceChildren(frag);
  svg.style.transition = "";
  svg.style.opacity = "1";
}

function fadeSynapses() {
  const svg = $("synapses");
  if (!svg) return;
  svg.style.transition = `opacity ${FADE_MS}ms ease-out`;
  svg.style.opacity = "0";
}

function clearSynapses() {
  const svg = $("synapses");
  if (!svg) return;
  svg.replaceChildren();
  svg.style.transition = "";
  svg.style.opacity = "1";
}

// ---------------------------------------------------------------- panel

function setDot(kind) {
  const dot = $("dot");
  if (dot) dot.className = "dot" + (kind ? " " + kind : "");
}

function setPhase(phase, note) {
  G.phase = phase;
  const key = G.over ? "over" : G.paused && !REQUEST_PHASES.has(phase) ? "paused" : phase;
  const [name, def] = PHASE_TEXT[key] ?? PHASE_TEXT.idle;
  setText("phaseName", name);
  setText("phaseNote", note ?? def);
  setText("status", name);
}

function setLead(hue) {
  const wrap = document.querySelector(".board-wrap");
  if (!wrap) return;
  if (hue) wrap.style.setProperty("--lead", hue);
  else wrap.style.removeProperty("--lead");
}

function fmtCost(usd) {
  if (usd === 0) return "$0";
  if (usd < 0.01) return "$" + usd.toFixed(5);
  return "$" + usd.toFixed(4);
}

// The hero label ("평균 응답 · 조각당 호출 N회") follows the neuron toggle: #stAvgLabel when
// index.html gives it an id, else the .k sibling of #stAvg.
function setHeroLabel() {
  const k = $("stAvgLabel") ?? $("stAvg")?.parentElement?.querySelector(".k");
  if (k) k.textContent = `평균 응답 · 조각당 호출 ${G.opts.neurons ? 3 : 1}회`;
}

function renderStats() {
  const s = G.stats;
  setText("stPieces", s.pieces);
  setText("stLines", s.lines);
  setText("stScore", s.score.toLocaleString("en-US"));
  setText("stTspins", s.tspins);
  setHTML("stAvg", s.latencyCount === 0 ? "–" : Math.round(s.latencySum / s.latencyCount) + "<small>ms</small>");
  setText("stConf", s.confidence == null ? "–" : s.confidence.toFixed(2));
  const mean = (sum, n) => (n ? String(Math.round(sum / n)) : "–");
  setText("stR1", mean(s.r1Sum, s.r1Count));
  setText("stR2", mean(s.r2Sum, s.r2Count));
  setText("stR3", mean(s.r3Sum, s.r3Count));
  setText("stDisagree", s.disagreements);
  setText("stOverride", s.overrides);
  setText("stVeto", s.vetoes);
  setText("stChanged", s.changed);
  const tokens = s.tokensIn + s.tokensOut;
  setText("stTok", tokens.toLocaleString("en-US"));
  setText("stCost", fmtCost(tokens * USD_PER_TOKEN));
  setText("stCostAll", fmtCost(G.sessionCost + tokens * USD_PER_TOKEN));
}

function addUsage(res, stage) {
  const s = G.stats;
  const ms = Number(res?.latencyMs) || 0;
  s.calls++;
  s[stage + "Sum"] += ms;
  s[stage + "Count"]++;
  s.tokensIn += res?.usage?.input_tokens ?? 0;
  s.tokensOut += res?.usage?.output_tokens ?? 0;
  return ms;
}

// What the single-Choice path sends per option; this is the string measured in
// experiments/judge.mjs (rho 0.41 against a strong heuristic with the numbers, ≈ 0 without),
// kept byte-for-byte so the neurons-off toggle really is the old game.
function placementSummary(type, cand, boardBefore) {
  const before = computeMetrics(boardBefore);
  const after = cand.metrics;
  const delta = (a, b) => (a === b ? "" : a > b ? ` (+${a - b})` : ` (${a - b})`);
  const rows = cand.cells.map((c) => c[0]);
  const cols = cand.cells.map((c) => c[1]);
  const span = (v, one, many) => {
    const lo = Math.min(...v);
    const hi = Math.max(...v);
    return lo === hi ? `${one} ${lo}` : `${many} ${lo}-${hi}`;
  };
  const parts = [
    `${type} piece, rotation ${cand.rot} (${rotationLabel(type, cand.rot)})`,
    `lands at ${span(cols, "column", "columns")}, ${span(rows, "row", "rows")}`,
  ];
  if (cand.tspin) parts.push(cand.tspin === "full" ? "placed with a T-spin" : "placed with a mini T-spin");
  parts.push(cand.linesCleared === 0 ? "clears no lines" : `clears ${cand.linesCleared} line${cand.linesCleared === 1 ? "" : "s"}`);
  parts.push(
    `after: max height ${after.maxHeight}${delta(after.maxHeight, before.maxHeight)}, holes ${after.holes}${delta(after.holes, before.holes)}, ` +
      `bumpiness ${after.bumpiness}, aggregate height ${after.aggregateHeight}`,
  );
  return parts.join(" ; ").replace(/ ; /g, "; ");
}

// Short Korean label for the panel. Display only; the summary is what Jev reads.
function candidateLabel(type, cand) {
  if (!cand) return "";
  const cols = cand.cells.map((c) => c[1]);
  const lo = Math.min(...cols) + 1;
  const hi = Math.max(...cols) + 1;
  const parts = [`${type} 회전 ${cand.rot}`, lo === hi ? `${lo}열` : `${lo}–${hi}열`];
  if (cand.tspin) parts.push(cand.tspin === "full" ? "T스핀" : "미니 T스핀");
  if (cand.linesCleared > 0) parts.push(`${cand.linesCleared}줄 제거`);
  return parts.join(" · ");
}

function tagSpan(text, kind) {
  const el = document.createElement("span");
  el.className = "tag" + (kind ? " " + kind : "");
  el.textContent = text;
  return el;
}

function emptyRow() {
  const el = document.createElement("div");
  el.className = "empty";
  el.textContent = "첫 조각을 기다리는 중…";
  return el;
}

// 6.4: one row per proposal, sorted by final probability. Class names are the hooks index.html
// styles (.prop .row1 .dot .name .pct .tag .bars .bar); only hues and widths are inline.
function renderProps() {
  const host = $("props");
  if (!host) return;
  host.replaceChildren();
  const v = G.verdict;
  const props = G.proposals;
  if (!v || !props) {
    host.appendChild(emptyRow());
    return;
  }
  const neurons = Object.keys(props.P);
  const sorted = v.proposals.slice().sort((a, b) => (v.final[b.id] ?? 0) - (v.final[a.id] ?? 0));
  for (const p of sorted) {
    const chosen = p.id === v.chosenId;
    const vetoed = v.hardVetoed.includes(p.id);
    const hue = HUES[p.alt ? v.leading : p.backers[0]] ?? HUES.default;
    const row = document.createElement("div");
    row.className = "prop" + (chosen ? " sel" : "") + (vetoed ? " veto" : "");
    if (chosen) row.style.borderColor = hue;
    // The exact texts Jev read for this candidate: the motor summary and the arbiter's effects.
    row.title = `${G.summaries.get(p.id) ?? p.id}\n\n${G.effects.get(p.id) ?? ""}`;

    const head = document.createElement("div");
    head.className = "row1";
    const dot = document.createElement("span");
    dot.className = "dot";
    dot.style.background = hue;
    const name = document.createElement("span");
    name.className = "name mono";
    name.textContent = `${p.id} · ${candidateLabel(G.pieceType, p.cand)}`;
    head.append(dot, name);
    if (chosen) head.appendChild(tagSpan("선택", ""));
    if (vetoed) head.appendChild(tagSpan("VETO", "veto"));
    if (p.alt) head.appendChild(tagSpan("ALT", "alt"));
    if (v.fallback && chosen) head.appendChild(tagSpan("FALLBACK", ""));
    const pct = document.createElement("b");
    pct.className = "pct";
    pct.textContent = Math.round(100 * (v.final[p.id] ?? 0)) + "%";
    head.appendChild(pct);

    const bars = document.createElement("div");
    bars.className = "bars";
    for (const n of neurons) {
      const nh = HUES[n] ?? HUES.default;
      const bar = document.createElement("span");
      bar.className = "bar";
      const l = document.createElement("span");
      l.style.color = nh;
      l.textContent = lab(n);
      const track = document.createElement("b");
      const fill = document.createElement("i");
      fill.style.width = Math.max(1, Math.round(100 * (props.P[n]?.[p.id] ?? 0))) + "%";
      fill.style.background = nh;
      track.appendChild(fill);
      bar.append(l, track);
      bars.appendChild(bar);
    }
    row.append(head, bars);
    host.appendChild(row);
  }
}

// Single-Choice path: the old top-5 list, in the same card and the same row classes.
function renderDecideRows(decision, chosenId) {
  const host = $("props");
  if (!host) return;
  host.replaceChildren();
  if (!decision) {
    host.appendChild(emptyRow());
    return;
  }
  const top = Object.entries(decision.probabilities ?? {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, TOP_N);
  const hue = PIECE_COLORS[G.pieceType] ?? "#c084fc";
  for (const [id, p] of top) {
    const sel = id === chosenId;
    const row = document.createElement("div");
    row.className = "prop" + (sel ? " sel" : "");
    if (sel) row.style.borderColor = hue;
    const cand = G.candidates.find((c) => c.id === id);
    row.title = G.summaries.get(id) ?? id; // full English summary, exactly as sent to Jev
    const head = document.createElement("div");
    head.className = "row1";
    const pct = document.createElement("b");
    pct.className = "pct";
    pct.textContent = (p * 100).toFixed(1) + "%";
    const bar = document.createElement("span");
    bar.className = "bar";
    bar.style.cssText = "flex:1;display:flex;align-items:center";
    const track = document.createElement("b");
    track.style.cssText = "flex:1;height:6px;background:#0e1118;border-radius:3px;overflow:hidden";
    const fill = document.createElement("i");
    fill.style.cssText = `display:block;height:100%;width:${Math.max(1, p * 100).toFixed(1)}%;background:${hue};border-radius:3px`;
    track.appendChild(fill);
    bar.appendChild(track);
    head.append(pct, bar);
    const sum = document.createElement("div");
    sum.className = "name";
    sum.style.color = sel ? "var(--text)" : "var(--muted)";
    sum.textContent = cand ? candidateLabel(G.pieceType, cand) : id;
    row.append(head, sum);
    host.appendChild(row);
  }
}

let toastTimer = null; // set only for a timed toast (the R3 fallback notice)
function showToast(msg, ms = 0) {
  const t = $("toast");
  if (!t) return;
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = ms > 0 ? setTimeout(hideToast, ms) : null;
}
function hideToast() {
  clearTimeout(toastTimer);
  toastTimer = null;
  $("toast")?.classList.remove("show");
}

// ---------------------------------------------------------------- cortex view

// One line of the whole piece, as far as it has got:
//   빌드 .92 · 현금 .61 · 선호 1.8 → 빌드 c7 .71 / 현금 c1 .55 / 습관 c7 .80 → 중재 c7 .71 · 거부 c1 .70 → c7 61%
function thoughtLine() {
  const intent = G.intent;
  if (!intent) return "";
  const parts = [];
  const acts = intent.fired.map((i) => `${lab(i)} ${fmtP(intent.activations[i])}`);
  parts.push([...acts, `선호 ${intent.appetite.toFixed(1)}`].join(" · "));
  const props = G.proposals;
  if (props) {
    const neurons = [...intent.fired, "default"].filter((n) => props.picks[n] !== undefined);
    parts.push(neurons.map((n) => `${lab(n)} ${props.picks[n]} ${fmtP(props.confidence[n])}`).join(" / "));
  }
  const v = G.verdict;
  if (v) {
    if (v.fallback) {
      parts.push("중재 실패", `${v.chosenId} FALLBACK`);
    } else {
      const arb = v.arbTop ? [`중재 ${v.arbTop} ${fmtP(v.A[v.arbTop])}`] : [];
      const vetoes = v.hardVetoed.map((id) => `거부 ${id} ${fmtP(v.V[id])}`);
      parts.push([...arb, ...vetoes].join(" · "));
      parts.push(`${v.chosenId} ${Math.round(100 * (v.final[v.chosenId] ?? 0))}%`);
    }
  }
  return parts.join(" → ");
}

// The intent that leads a proposal, for the panel texts: first backer, or the leader for an ALT.
function leaderOf(v, id) {
  const p = v.proposals.find((x) => x.id === id);
  if (!p) return "";
  return lab(p.alt ? v.leading : p.backers[0]);
}

// 6.3 row 3. The arbiter and the coach judge at once, so the wording never says the coach
// stopped the arbiter's pick: a vetoed top reads as "arbiter's first → coach veto → chosen".
function verdictLineOf() {
  const v = G.verdict;
  if (!v) return "";
  if (v.fallback) return `중재 실패 → E 최대 ${v.chosenId} (FALLBACK)`;
  if (v.vetoedTop) return `중재 1위 ${v.arbTop} → 코치 거부 → ${v.chosenId} 선택`;
  if (v.ledBy === "default") return `습관이 이김 (${lab(v.leading)} → 습관)`;
  if (v.override) return `중재가 우선순위를 뒤집음 (${lab(v.leading)} → ${lab(v.ledBy)})`;
  const coach = v.hardVetoed.length ? v.hardVetoed.map((id) => `${leaderOf(v, id)} ${id} 거부`).join(" · ") : "거부 없음";
  return `중재: ${leaderOf(v, v.arbTop)} ${v.arbTop} 승 · 코치: ${coach}`;
}

function buildView(phase) {
  const props = G.proposals;
  const v = G.verdict;
  return {
    phase,
    surface: G.surface,
    facts: G.facts,
    queue: G.queue.slice(0, 5),
    sense: G.sense,
    appetite: G.appetite,
    intent: G.intent,
    instructions: Object.keys(G.instructions).length ? G.instructions : null,
    proposals: props
      ? props.proposals.map((p) => ({
          id: p.id,
          backers: p.backers.slice(),
          alt: p.alt,
          label: candidateLabel(G.pieceType, p.cand),
          probs: Object.fromEntries(Object.keys(props.P).map((n) => [n, props.P[n][p.id] ?? 0])),
          E: p.E,
        }))
      : null,
    verdict: v,
    hold: v ? v.hold : null, // raw score 0..2; timeline entries carry the memory scale (0..1)
    timeline: G.timeline.slice(-40),
    thought: thoughtLine(),
    verdictLine: verdictLineOf(),
    fork: !!v?.fork,
    // Extras beyond the frozen interface, harmless to a renderer that ignores them.
    memory: G.memory,
    pieceType: G.pieceType,
  };
}

function showCortex(phase, inflight) {
  G.cortex.phase = phase;
  safe(renderCortex, buildView(phase));
  safe(setInflight, inflight);
}

// ---------------------------------------------------------------- controls

function setPaused(paused) {
  G.paused = paused;
  setText("btnPause", paused ? "재개" : "일시정지");
  if (!paused) hideToast();
  setDot(paused ? null : "live");
  setPhase(G.phase);
}

function gameOver() {
  G.over = true;
  setPhase("over");
  setDot("err");
  showCortex("idle", null);
  setText("goRes", `조각 ${G.stats.pieces} · 줄 ${G.stats.lines} · 점수 ${G.stats.score.toLocaleString("en-US")}`);
  $("gameover")?.classList.remove("hidden");
}

function resetPieceState() {
  G.candidates = [];
  G.dropped = 0;
  G.summaries = new Map();
  G.effects = new Map();
  G.decision = null;
  G.chosen = null;
  G.ghosts = [];
  G.wires = [];
  G.fieldGhosts = [];
  G.anim = null;
  G.flashRows = [];
  G.sense = null;
  G.appetite = null;
  G.intent = null;
  G.motor = null;
  G.proposals = null;
  G.verdict = null;
  G.instructions = {};
}

function newGame() {
  G.sessionCost += (G.stats.tokensIn + G.stats.tokensOut) * USD_PER_TOKEN;
  G.gen++;
  G.board = createEmptyBoard();
  G.queue = [];
  refillQueue();
  G.over = false;
  G.paused = false;
  G.pieceType = null;
  G.nextType = G.queue[0];
  resetPieceState();
  G.surface = null;
  G.facts = null;
  G.memory = { previousIntent: null, hold: 0 };
  G.recent = [];
  G.piecesSinceClear = 0;
  G.timeline = [];
  G.cortex = { phase: "idle", t0: 0, tR1: 0, tR2: 0, tR3: 0 };
  G.spawnT0 = 0;
  G.stats = freshStats();
  G.log = [];
  $("gameover")?.classList.add("hidden");
  setText("btnPause", "일시정지");
  hideToast();
  setLead(null);
  clearSynapses();
  renderStats();
  renderProps();
  setDot("live");
  setPhase("idle");
  showCortex("idle", null);
  runGame(G.gen);
}

// ---------------------------------------------------------------- requests

async function waitWhilePaused(gen) {
  while (G.gen === gen && G.paused && !G.over) await sleep(80);
}

async function postJson(path, payload) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error ? `${res.status} ${body.error}` : `HTTP ${res.status}`);
  }
  return res.json();
}

// R1, R2 and the single-Choice call: a failure pauses the game with a toast, and resuming
// retries the same request. Returns null once the game has moved on (new game).
async function askJev(gen, path, payload) {
  while (G.gen === gen) {
    try {
      const data = await postJson(path, payload);
      if (!toastTimer) hideToast(); // a timed fallback notice runs its 3 s out
      return data;
    } catch (err) {
      showToast(`서버 오류 (${path}): ${err.message} — 자동 일시정지. 재개를 누르면 다시 시도합니다.`);
      setDot("err");
      setPaused(true);
      await waitWhilePaused(gen);
      if (G.gen !== gen) return null;
    }
  }
  return null;
}

// ---------------------------------------------------------------- percepts (R0)

// Above MAX_CANDS the bundled R2 request overran the API's token limit (seen at 136
// candidates), so the weakest placements by a Dellacherie-style score are dropped before
// anything is sent. Ids are kept as reachablePlacements assigned them; the log records the cut.
function capCandidates(cands) {
  if (cands.length <= MAX_CANDS) return { kept: cands, dropped: 0 };
  const score = (c) =>
    -0.51 * c.metrics.aggregateHeight +
    0.76 * c.linesCleared -
    0.36 * c.metrics.holes -
    0.18 * c.metrics.bumpiness +
    (c.tspin === "full" ? 1 : 0);
  const kept = cands
    .map((c, i) => ({ c, i, s: score(c) }))
    .sort((a, b) => b.s - a.s || a.i - b.i)
    .slice(0, MAX_CANDS)
    .sort((a, b) => a.i - b.i)
    .map((x) => x.c);
  return { kept, dropped: cands.length - MAX_CANDS };
}

// Summaries and effects run a T-spin search per candidate (≈ 1.3 ms each), so they are computed
// in slices between animation frames while R1 is already in flight; R1 does not need them.
async function computePercepts(gen, type, cands) {
  for (let i = 0; i < cands.length; i += 8) {
    for (const c of cands.slice(i, i + 8)) {
      G.summaries.set(c.id, candidateSummaryV2(type, c, G.board));
      G.effects.set(c.id, effects(type, c, G.board));
    }
    if (G.gen !== gen) return;
    await sleep(0);
  }
}

const uniqueColumns = (cells) => [...new Set(cells.map((c) => c[1]))].sort((a, b) => a - b);

function gameSnapshot() {
  const s = G.stats;
  return { pieces: s.pieces, lines: s.lines, score: s.score, tspins: s.tspins };
}

// ---------------------------------------------------------------- the move itself

// Replay the move path from spawn; consecutive drops are compressed. Hold times are keyed on the
// departing pose: a pose entered by a drop is held for the compressed drop step, and every
// shift or rotation pose for a full STEP_MS, so a spin stays visible even when a soft drop
// follows it at once.
async function animateMove(gen, type, chosen, ring) {
  const frames = replayPath(G.board, type, chosen.path);
  const times = [0];
  const drops = chosen.path.filter((m) => m === "D").length;
  const dropMs = drops ? Math.min(STEP_MS, DROP_TOTAL_MS / drops) : 0;
  for (let i = 1; i < frames.length; i++) {
    times.push(times[i - 1] + (frames[i - 1].move === "D" ? dropMs : STEP_MS));
  }
  G.anim = { type, frames, times, t0: performance.now(), ring };
  await sleep(times[times.length - 1] + 120);
  if (G.gen !== gen) return false;
  G.anim = null;
  return true;
}

// Lock the piece where it landed, flash any completed rows, then take the cleared board.
async function lockPiece(gen, type, chosen) {
  for (const [r, c] of chosen.cells) G.board[r][c] = type;
  if (chosen.linesCleared > 0) {
    G.flashRows = [];
    for (let r = 0; r < ROWS; r++) if (G.board[r].every((v) => v !== 0)) G.flashRows.push(r);
    setPhase("clearing", chosen.tspin ? `T-SPIN ${["", "SINGLE", "DOUBLE", "TRIPLE"][chosen.linesCleared]}!` : `${chosen.linesCleared}줄!`);
    await sleep(FLASH_MS);
    if (G.gen !== gen) return false;
    G.flashRows = [];
  }
  G.board = chosen.boardAfter.map((row) => row.slice());
  const s = G.stats;
  s.pieces++;
  s.lines += chosen.linesCleared;
  s.score += chosen.score;
  if (chosen.tspin) s.tspins++;
  G.piecesSinceClear = chosen.linesCleared > 0 ? 0 : G.piecesSinceClear + 1;
  return true;
}

function pushRecent(type, chosen, ledBy, vetoed) {
  G.recent.push({
    piece: type,
    columns: uniqueColumns(chosen.cells),
    lines: chosen.linesCleared,
    tspin: chosen.tspin ?? null,
    ledBy,
    vetoed,
  });
  if (G.recent.length > 6) G.recent.splice(0, G.recent.length - 6);
}

async function waitAfterLock(gen) {
  const wait = Number($("speed")?.value ?? 0);
  setPhase("waiting", wait ? `${wait}ms 후 다음 조각` : "");
  if (wait > 0) await sleep(wait);
  return G.gen === gen;
}

// ---------------------------------------------------------------- game loop: neurons

async function playPiece(gen) {
  refillQueue();
  const type = G.queue.shift();
  refillQueue();
  G.pieceType = type;
  G.nextType = G.queue[0];
  resetPieceState();
  G.spawnT0 = performance.now();

  const all = reachablePlacements(G.board, type);
  if (all.length === 0) {
    gameOver();
    return false;
  }
  G.surface = computeMetrics(G.board).heights;
  G.facts = factsOf(G.board, G.piecesSinceClear);

  if (!G.opts.neurons) return playPieceDecide(gen, type, all);

  const { kept, dropped } = capCandidates(all);
  G.candidates = kept;
  G.dropped = dropped;

  if (kept.length === 1) return playSingle(gen, type, kept[0]);

  const s = G.stats;
  const byId = new Map(kept.map((c) => [c.id, c]));
  const queue = G.queue.slice(0, 5);
  const boardAscii = boardToAscii(G.board);
  // "A T-spin is on the table right now": some reachable placement of this piece is a full
  // T-spin that clears. The same test hasTSlot applies to the boards after each candidate.
  const tspinAvailableNow = type === "T" && kept.some((c) => c.tspin === "full" && c.linesCleared >= 1);
  const recent = G.recent.slice(-6);
  const game = gameSnapshot();
  const memory = { ...G.memory };
  const stayAsked = memory.previousIntent !== null && memory.hold > 0;

  // ---- R1: sense. Fired before the percepts are summarised; it does not read them.
  G.cortex.t0 = G.spawnT0;
  setDot("busy");
  setPhase("sense", `감각: 뉴런 ${6 + (stayAsked ? 1 : 0)}개에 자극 전달 중…` + (dropped ? ` · 후보 ${all.length}개 중 ${MAX_CANDS}개만 전달` : ""));
  showCortex("sense", "sense");
  const r1Promise = askJev(gen, "/api/sense", {
    boardAscii,
    surface: G.surface,
    facts: G.facts,
    pieceType: type,
    nextType: G.nextType,
    queue,
    tspinAvailableNow,
    recent,
    game,
    memory,
  });
  await computePercepts(gen, type, kept);
  const r1 = await r1Promise;
  if (!r1 || G.gen !== gen) return false;
  G.cortex.tR1 = performance.now();
  const r1Ms = addUsage(r1, "r1");
  G.sense = r1.sense;
  G.appetite = r1.appetite?.value ?? null;
  Object.assign(G.instructions, r1.instructions ?? {});
  const intent = gate(r1.sense, r1.appetite, G.facts, memory);
  G.intent = intent;
  if (intent.forced) s.forced++;
  setLead(HUES[intent.leading]);

  // ---- R2: motor.
  const firedText = intent.fired.map((i) => `${lab(i)} ${fmtP(intent.activations[i])}`).join(" · ");
  setPhase(
    "motor",
    `${firedText} 발화 · 위험 선호 ${intent.appetite.toFixed(1)}/3` + (intent.forced ? " · 생존 강제" : "") + (intent.stayed ? " · 계획 유지" : ""),
  );
  showCortex("motor", "motor");
  const [r2] = await Promise.all([askJev(gen, "/api/motor", {
    intent,
    boardAscii,
    surface: G.surface,
    facts: G.facts,
    pieceType: type,
    nextType: G.nextType,
    queue,
    tspinAvailableNow,
    candidates: kept.map((c) => ({ id: c.id, summary: G.summaries.get(c.id), boardAfterAscii: boardToAscii(c.boardAfter) })),
  }), sleep(LAYER_HOLD_MS)]); // the request rides inside the band's minimum display time
  if (!r2 || G.gen !== gen) return false;
  G.cortex.tR2 = performance.now();
  const r2Ms = addUsage(r2, "r2");
  G.motor = r2.motor;
  Object.assign(G.instructions, r2.instructions ?? {});
  const props = proposalsFrom(r2.motor, intent, kept);
  G.proposals = props;
  if (props.disagreement) s.disagreements++;

  // Wires on the board, staggered in proposal order (fired by activation, then the habit).
  G.wires = props.proposals.map((p, k) => {
    const lead = p.alt ? intent.leading : p.backers[0];
    const habitOnly = p.backers.length === 1 && p.backers[0] === "default";
    return {
      id: p.id,
      cells: p.cand?.cells ?? [],
      backers: p.backers.slice(),
      color: HUES[lead] ?? HUES.default,
      tag: p.alt ? `${lab(intent.leading)}·ALT` : p.backers.map(lab).join("·"),
      dashed: habitOnly,
      vetoed: false,
      appearAt: G.cortex.tR2 + WIRE_STAGGER_MS * k,
    };
  });
  const propIds = new Set(props.proposals.map((p) => p.id));
  G.fieldGhosts = props.motorField
    .filter((f) => !propIds.has(f.id))
    .map((f) => ({ cells: f.cand?.cells ?? [], color: HUES[f.neuron] ?? HUES.default, alpha: FIELD_ALPHA[Math.min(f.rank - 2, FIELD_ALPHA.length - 1)] }));
  const picksText = [...intent.fired, "default"]
    .filter((n) => props.picks[n] !== undefined)
    .map((n) => `${lab(n)} ${props.picks[n]}`)
    .join(" · ");
  setPhase("arbitrate", `${picksText} → 제안 ${props.proposals.length}개`);
  showCortex("arbitrate", "arbitrate");

  // ---- R3: arbitrate, coach and hold in one request. The wires hold at least WIRE_HOLD_MS.
  const r3Promise = postJson("/api/arbitrate", {
    pieceType: type,
    nextType: G.nextType,
    queue,
    intent: { leading: intent.leading, fired: intent.fired, forced: intent.forced, appetite: intent.appetite, appetiteWord: intent.appetiteWord },
    recent,
    game,
    memory,
    proposals: arbitrateProposals(props, G.effects),
  });
  const [r3Outcome] = await Promise.all([r3Promise.then((data) => ({ data }), (err) => ({ err })), sleep(WIRE_HOLD_MS)]);
  if (G.gen !== gen) return false;

  let verdict;
  let r3 = null;
  let r3Ms = 0;
  if (r3Outcome.data) {
    r3 = r3Outcome.data;
    r3Ms = addUsage(r3, "r3");
    Object.assign(G.instructions, r3.instructions ?? {});
    verdict = combine(r3.arbitrate, r3.veto, r3.hold, props, intent, kept);
  } else {
    // 5.4: no pause. The largest E plays, nothing carries over, and the counter says so.
    verdict = fallbackCombine(props, kept);
    s.fallbacks++;
    showToast(`중재 요청 실패: ${r3Outcome.err?.message ?? "?"} — 제안 중 E 최대를 둡니다 (FALLBACK)`, 3000);
  }
  G.verdict = verdict;
  G.cortex.tR3 = performance.now();
  G.ghosts = ghostsFrom(verdict, FIELD_ALPHA_AFTER);
  const chosen = byId.get(verdict.chosenId) ?? verdict.chosen ?? kept[0];
  G.chosen = chosen;
  if (verdict.override) s.overrides++;
  if (verdict.hardVetoed.length) s.vetoes++;
  if (verdict.changed) s.changed++;
  s.confidence = verdict.final[verdict.chosenId] ?? null;
  s.lastLatency = r1Ms + r2Ms + r3Ms;
  s.latencySum += s.lastLatency;
  s.latencyCount++;
  G.timeline.push({
    ledBy: verdict.ledBy,
    vetoed: verdict.hardVetoed.length > 0,
    hold: verdict.memoryNext.hold, // memory scale 0..1: the lock glyph threshold of 2.3
    chosenId: verdict.chosenId,
    piece: type,
  });
  if (G.timeline.length > 40) G.timeline.splice(0, G.timeline.length - 40);

  const pct = Math.round(100 * (verdict.final[verdict.chosenId] ?? 0));
  const vetoText = verdict.hardVetoed.map((id) => ` · ${leaderOf(verdict, id)} ${id} 거부`).join("");
  setPhase(
    "verdict",
    verdict.fallback ? `중재 실패 · E 최대 ${verdict.chosenId} FALLBACK` : `${lab(verdict.ledBy)} ${verdict.chosenId} ${pct}% 선택${vetoText}`,
  );
  showCortex("verdict", null);
  drawSynapses(false);
  renderProps();
  renderStats();
  setDot("live");
  await sleep(GHOST_MS);
  if (G.gen !== gen) return false;

  // ---- move, lock, remember.
  setPhase("moving", chosen.tspin ? "스핀 진입!" : verdict.fallback ? "FALLBACK" : `${lab(verdict.ledBy)}가 이끎`);
  showCortex("moving", null);
  fadeSynapses();
  if (!(await animateMove(gen, type, chosen, HUES[verdict.ledBy] ?? HUES.default))) return false;
  if (!(await lockPiece(gen, type, chosen))) return false;

  const chosenVetoed = verdict.hardVetoed.includes(verdict.chosenId);
  G.memory = { ...verdict.memoryNext };
  pushRecent(type, chosen, verdict.ledBy, chosenVetoed);
  G.log.push({
    piece: type,
    mode: "neurons",
    intent,
    directive: r3?.directive ?? null,
    motorPicks: props.picks,
    proposals: props.proposals.map((p) => ({ id: p.id, backers: p.backers.slice(), alt: p.alt, E: p.E })),
    arbitrate: r3?.arbitrate ?? null,
    veto: r3?.veto ?? null,
    hold: r3?.hold ?? null,
    final: verdict.final,
    chosen: verdict.chosenId,
    ledBy: verdict.ledBy,
    override: verdict.override,
    changed: verdict.changed,
    fork: verdict.fork,
    vetoedTop: verdict.vetoedTop,
    fallback: verdict.fallback,
    latency: { r1: r1Ms, r2: r2Ms, r3: r3Ms },
    tokens: {
      input: (r1.usage?.input_tokens ?? 0) + (r2.usage?.input_tokens ?? 0) + (r3?.usage?.input_tokens ?? 0),
      output: (r1.usage?.output_tokens ?? 0) + (r2.usage?.output_tokens ?? 0) + (r3?.usage?.output_tokens ?? 0),
    },
    cols: chosen.cells.map((c) => c[1]),
    linesCleared: chosen.linesCleared,
    tspin: chosen.tspin,
    candidates: all.length,
    dropped,
  });
  renderStats();
  return waitAfterLock(gen);
}

// One reachable placement: no question to ask. Every layer stays dark and the piece just goes.
async function playSingle(gen, type, chosen) {
  G.chosen = chosen;
  setDot("live");
  setPhase("single");
  showCortex("single", null);
  setLead(null);
  await sleep(SCANLINE_MS);
  if (G.gen !== gen) return false;
  setPhase("moving", "외길");
  showCortex("moving", null);
  if (!(await animateMove(gen, type, chosen, null))) return false;
  if (!(await lockPiece(gen, type, chosen))) return false;
  pushRecent(type, chosen, null, false);
  G.log.push({
    piece: type,
    mode: "single",
    intent: null,
    directive: null,
    chosen: chosen.id,
    ledBy: null,
    latency: { r1: 0, r2: 0, r3: 0 },
    tokens: { input: 0, output: 0 },
    cols: chosen.cells.map((c) => c[1]),
    linesCleared: chosen.linesCleared,
    tspin: chosen.tspin,
    candidates: 1,
    dropped: 0,
  });
  renderStats();
  return waitAfterLock(gen);
}

// ---------------------------------------------------------------- game loop: single Choice

// The pre-neuron game, kept as the baseline behind the toggle: one Choice over every candidate,
// its distribution painted as the heatmap. Nothing here reads the neuron state, and a piece
// played this way drops the carried plan so switching the neurons back on starts fresh.
async function playPieceDecide(gen, type, candidates) {
  G.candidates = candidates;
  G.summaries = new Map(candidates.map((c) => [c.id, placementSummary(type, c, G.board)]));
  G.memory = { previousIntent: null, hold: 0 };
  showCortex("idle", null);
  setLead(null);

  setDot("busy");
  setPhase("thinking", `후보 ${candidates.length}개 · Jev에게 Choice 질문 1개`);

  const instruction = INSTRUCTION;
  const decision = await askJev(gen, "/api/decide", {
    instruction,
    boardAscii: boardToAscii(G.board),
    pieceType: type,
    nextType: G.nextType,
    candidates: candidates.map((c) => ({
      id: c.id,
      summary: G.summaries.get(c.id),
      boardAfterAscii: boardToAscii(c.boardAfter),
    })),
  });
  if (!decision || G.gen !== gen) return false;

  const byId = new Map(candidates.map((c) => [c.id, c]));
  let chosen = byId.get(decision.choice);
  if (!chosen) {
    // Defensive: fall back to the highest-probability id we actually know.
    const best = Object.entries(decision.probabilities ?? {})
      .filter(([id]) => byId.has(id))
      .sort((a, b) => b[1] - a[1])[0];
    chosen = best ? byId.get(best[0]) : candidates[0];
  }
  G.decision = decision;
  G.chosen = chosen;

  const s = G.stats;
  const ms = addUsage(decision, "r1");
  s.lastLatency = ms;
  s.latencySum += ms;
  s.latencyCount++;
  s.confidence = decision.confidence;
  renderStats();
  renderDecideRows(decision, chosen.id);
  setDot("live");

  // Ghost heatmap: top 5 candidates, alpha proportional to probability.
  const top = Object.entries(decision.probabilities ?? {})
    .filter(([id]) => byId.has(id))
    .sort((a, b) => b[1] - a[1])
    .slice(0, TOP_N);
  const maxP = top.length ? top[0][1] : 1;
  G.ghosts = top.map(([id, p]) => ({
    id,
    cells: byId.get(id).cells,
    p,
    alpha: p >= GHOST_LABEL_MIN_P ? Math.max(MIN_GHOST_ALPHA, MAX_GHOST_ALPHA * (maxP > 0 ? p / maxP : 0)) : MAX_GHOST_ALPHA * (maxP > 0 ? p / maxP : 0),
    color: PIECE_COLORS[type],
    tag: null,
    rings: [],
    vetoed: false,
    chosen: id === chosen.id,
    faint: false,
    dashed: false,
    label: Math.round(p * 100) + "%",
    backers: [],
  }));

  setPhase("ghost", `후보 ${candidates.length}개 중 ${chosen.id} 선택 · 확신도 ${(decision.confidence ?? 0).toFixed(2)}`);
  await sleep(DECIDE_GHOST_MS);
  if (G.gen !== gen) return false;

  setPhase("moving", chosen.tspin ? "스핀 진입!" : undefined);
  if (!(await animateMove(gen, type, chosen, null))) return false;
  if (!(await lockPiece(gen, type, chosen))) return false;

  pushRecent(type, chosen, null, false);
  G.log.push({
    piece: type,
    mode: "decide",
    instruction,
    choiceId: chosen.id,
    chosen: chosen.id,
    latencyMs: decision.latencyMs,
    latency: { r1: ms, r2: 0, r3: 0 },
    inputTokens: decision.usage?.input_tokens ?? 0,
    outputTokens: decision.usage?.output_tokens ?? 0,
    cols: chosen.cells.map((c) => c[1]),
    linesCleared: chosen.linesCleared,
    tspin: chosen.tspin,
    confidence: decision.confidence,
  });
  renderStats();
  return waitAfterLock(gen);
}

async function runGame(gen) {
  refillQueue();
  G.nextType = G.queue[0];
  while (G.gen === gen && !G.over) {
    await waitWhilePaused(gen);
    if (G.gen !== gen || G.over) break;
    let ok = false;
    try {
      ok = await playPiece(gen);
    } catch (err) {
      // A bug in one piece must not freeze the page: report it and pause, like a failed request.
      console.error("playPiece failed:", err);
      showToast("내부 오류: " + err.message + " — 자동 일시정지. 재개를 누르면 다음 조각부터 계속합니다.");
      setDot("err");
      G.anim = null;
      setPaused(true);
      await waitWhilePaused(gen);
      ok = G.gen === gen && !G.over;
    }
    if (!ok) break;
  }
}

// ---------------------------------------------------------------- wiring

$("btnPause")?.addEventListener("click", () => setPaused(!G.paused));
$("btnNew")?.addEventListener("click", newGame);
$("btnNew2")?.addEventListener("click", newGame);
$("speed")?.addEventListener("input", () => setText("speedVal", $("speed").value + "ms"));
if ($("speed")) setText("speedVal", $("speed").value + "ms");
// G.opts is the source of truth (the smoke test flips it directly); the checkboxes feed it.
$("optNeurons")?.addEventListener("change", () => {
  G.opts.neurons = $("optNeurons").checked;
  setHeroLabel();
});
if ($("optNeurons")) G.opts.neurons = $("optNeurons").checked;

// Recording mode hides the controls, the token fine print and the header status; keys keep
// the game drivable. Default on, ?clean=0 or the C key turns it off.
function setClean(on) {
  document.body.classList.toggle("clean", on);
  try { localStorage.setItem("jev-clean", on ? "1" : "0"); } catch {}
  applySizes();
}
{
  let clean = true;
  try { clean = localStorage.getItem("jev-clean") !== "0"; } catch {}
  const q = new URLSearchParams(location.search).get("clean");
  if (q !== null) clean = q !== "0";
  setClean(clean);
}
window.addEventListener("keydown", (e) => {
  if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
  if (e.code === "Space") { e.preventDefault(); setPaused(!G.paused); }
  else if (e.key === "n" || e.key === "N") newGame();
  else if (e.key === "c" || e.key === "C") setClean(!document.body.classList.contains("clean"));
});

safe(initCortex);
setHeroLabel();
renderStats();
renderProps();
setDot("live");
newGame();
