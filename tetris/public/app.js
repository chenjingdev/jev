// app.js — canvas renderer, game loop and control panel.
// The code enumerates every legal landing for each piece and asks Jev which one to use;
// the answer's probability distribution is painted on the board as a ghost heatmap.

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

// Cell sizes are recomputed from the viewport (see applySizes) so the board fits a phone.
let CELL = 30;
let NEXT_S = 12; // preview cell size
let NEXT_W = 96;
let NEXT_H = 56;
const GHOST_MS = 800; // how long the probability heatmap sits before the piece moves
const STEP_MS = 90; // one shift or rotation in the replayed path
const DROP_TOTAL_MS = 260; // a run of soft-drop steps is compressed into about this long
const FLASH_MS = 240;
const TOP_N = 5;
const USD_PER_TOKEN = 42 / 1e9; // $42 per billion tokens
const MAX_GHOST_ALPHA = 0.55;
const MIN_GHOST_ALPHA = 0.14; // labelled ghosts never fade below this
const THINKING_ALPHA = 0.18;
const GHOST_LABEL_MIN_P = 0.03; // ghosts below this probability get no percentage label
const NARROW_PX = 900; // must match the @media breakpoint in index.html

// No instruction UI: Jev is asked to play well. The server still accepts an instruction
// field, so the string stays in the payload for the log and the Jev-facing contract.
const INSTRUCTION = "";
const COL_GAP = 24; // must match `main { gap }` in index.html

const PHASE_TEXT = {
  idle: ["대기", "시작하는 중…"],
  thinking: ["Jev에게 묻는 중…", "모든 착지 위치를 한 번에 제시"],
  ghost: ["확률 분포", "밝을수록 Jev가 선호하는 자리"],
  moving: ["이동 중", "회전 → 수평 이동 → 하드드롭"],
  clearing: ["줄 제거", ""],
  waiting: ["대기", "다음 조각까지"],
  paused: ["일시정지", "재개를 누르세요"],
  over: ["게임 오버", "새 게임을 눌러 다시 시작"],
};

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

const boardCanvas = $("board");
const bctx = boardCanvas.getContext("2d");
const nextCanvas = $("next");
const nctx = nextCanvas.getContext("2d");

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
  if (vw <= NARROW_PX) return Math.max(8, Math.min(30, Math.floor((vw - 32) / COLS)));
  const byHeight = Math.floor((vh - 176) / ROWS); // header + caption card + paddings
  const byWidth = Math.floor((vw - 48 - 90) / ROWS); // board + panel ≈ ROWS cells + caption wide
  return Math.max(8, Math.min(44, byHeight, byWidth));
}
// Side panel width = board column height − board width − gap, so the board column and the
// panel together form a square. Measured after layout because the caption card's height
// depends on font metrics.
function sidePanelWidth() {
  const col = document.querySelector(".col-board");
  const colH = col ? col.getBoundingClientRect().height : ROWS * CELL;
  return Math.max(240, Math.round(colH - COLS * CELL - COL_GAP));
}

function applySizes() {
  CELL = cellSizeForViewport();
  NEXT_S = Math.max(6, Math.round(CELL * 0.4));
  NEXT_W = NEXT_S * 8;
  NEXT_H = Math.round((NEXT_S * 14) / 3);
  sizeCanvas(boardCanvas, bctx, COLS * CELL, ROWS * CELL);
  sizeCanvas(nextCanvas, nctx, NEXT_W, NEXT_H);
  document.documentElement.style.setProperty("--side-w", sidePanelWidth() + "px");
  // Pin the panel to the board column's height (not the viewport's) so the two stay a square
  // on tall screens too; the candidate list absorbs the difference.
  const col = document.querySelector(".col-board");
  if (col) document.documentElement.style.setProperty("--col-h", Math.round(col.getBoundingClientRect().height) + "px");
}
applySizes();

// ---------------------------------------------------------------- game state

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
  summaries: new Map(),
  decision: null,
  chosen: null,
  ghosts: [],
  anim: null,
  flashRows: [],
  stats: {
    pieces: 0,
    lines: 0,
    score: 0,
    lastLatency: null,
    latencySum: 0,
    latencyCount: 0,
    tokensIn: 0,
    tokensOut: 0,
    confidence: null,
    tspins: 0,
  },
  sessionCost: 0,
  log: [],
};
window.__jev = G; // read by the browser smoke test

function refillQueue() {
  while (G.queue.length < 8) G.queue.push(...shuffledBag());
}

// ---------------------------------------------------------------- rendering

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
    // A white outline keeps a ghost readable as "not yet placed" even at high alpha.
    ctx.globalAlpha = Math.min(1, alpha + 0.3);
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 2;
    ctx.strokeRect(x + 2, y + 2, CELL - 4, CELL - 4);
  } else {
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

function drawSettled(ctx) {
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const v = G.board[r][c];
      if (v !== 0) drawCell(ctx, r, c, PIECE_COLORS[v] ?? "#8892a6");
    }
  }
}

function drawSrsPiece(ctx, type, state, row, col, alpha = 1) {
  const color = PIECE_COLORS[type];
  for (const [r, c] of srsCells(type, state)) {
    if (row + r >= 0) drawCell(ctx, row + r, col + c, color, alpha);
  }
}

function drawNext() {
  nctx.clearRect(0, 0, NEXT_W, NEXT_H);
  if (!G.nextType) return;
  const type = G.nextType;
  const { height, width } = pieceSize(type, 0);
  const s = NEXT_S;
  const ox = (NEXT_W - width * s) / 2;
  const oy = (NEXT_H - height * s) / 2;
  nctx.fillStyle = PIECE_COLORS[type];
  for (const [r, c] of pieceCells(type, 0)) {
    nctx.fillRect(ox + c * s + 1, oy + r * s + 1, s - 2, s - 2);
  }
}

function draw(now) {
  drawGrid(bctx);

  if (G.phase === "thinking") {
    // Every legal landing, barely visible: "Jev is looking at all of these".
    for (const cand of G.candidates) {
      for (const [r, c] of cand.cells) {
        drawCell(bctx, r, c, PIECE_COLORS[G.pieceType], THINKING_ALPHA, "wire");
      }
    }
  }

  let ghostFade = 0;
  if (G.phase === "ghost") ghostFade = 1;
  else if (G.phase === "moving" && G.anim) {
    ghostFade = clamp(1 - (now - G.anim.t0) / 220, 0, 1);
  }
  if (ghostFade > 0) {
    for (const g of G.ghosts) {
      for (const [r, c] of g.cells) {
        drawCell(bctx, r, c, PIECE_COLORS[G.pieceType], g.alpha * ghostFade, "ghost");
      }
    }
  }

  drawSettled(bctx);

  // Percentage on each ghost so the distribution reads at a glance (and in a screenshot).
  if (ghostFade > 0) {
    bctx.font = `700 ${Math.round(CELL * 0.42)}px "SF Mono", Menlo, monospace`;
    bctx.textAlign = "center";
    bctx.textBaseline = "middle";
    for (const g of G.ghosts) {
      if (g.p < GHOST_LABEL_MIN_P) continue;
      const cy = (g.cells.reduce((a, c) => a + c[0], 0) / g.cells.length + 0.5) * CELL;
      const cx = (g.cells.reduce((a, c) => a + c[1], 0) / g.cells.length + 0.5) * CELL;
      const label = Math.round(g.p * 100) + "%";
      bctx.globalAlpha = ghostFade;
      bctx.lineWidth = 3;
      bctx.strokeStyle = "rgba(0,0,0,.85)";
      bctx.strokeText(label, cx, cy);
      bctx.fillStyle = "#ffffff";
      bctx.fillText(label, cx, cy);
      bctx.globalAlpha = 1;
    }
  }

  if (G.phase === "thinking" && G.pieceType) {
    const sp = srsSpawn(G.pieceType);
    drawSrsPiece(bctx, G.pieceType, 0, sp.row, sp.col, 0.9);
  }

  if (G.phase === "moving" && G.anim) {
    // Step through the path the search found: every shift, spin (with its kick) and drop.
    const a = G.anim;
    const el = now - a.t0;
    let i = 0;
    while (i < a.times.length - 1 && a.times[i + 1] <= el) i++;
    const f = a.frames[i];
    drawSrsPiece(bctx, a.type, f.state, f.row, f.col);
  }

  if (G.phase === "clearing" && G.flashRows.length) {
    const on = Math.floor(now / 60) % 2 === 0;
    bctx.globalAlpha = on ? 0.85 : 0.35;
    bctx.fillStyle = "#ffffff";
    for (const r of G.flashRows) bctx.fillRect(0, r * CELL, COLS * CELL, CELL);
    bctx.globalAlpha = 1;
  }

  drawNext();
}

function frame(now) {
  draw(now);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// Re-measure on resize / rotation (debounced) and repaint immediately.
let resizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    applySizes();
    draw(performance.now());
  }, 100);
});

// ---------------------------------------------------------------- panel

function setDot(kind) {
  $("dot").className = "dot" + (kind ? " " + kind : "");
}

function setPhase(phase, note) {
  G.phase = phase;
  const key = G.over ? "over" : G.paused && phase !== "thinking" ? "paused" : phase;
  const [name, def] = PHASE_TEXT[key] ?? PHASE_TEXT.idle;
  $("phaseName").textContent = name;
  $("phaseNote").textContent = note ?? def;
  $("status").textContent = name;
}

function fmtCost(usd) {
  if (usd === 0) return "$0";
  if (usd < 0.01) return "$" + usd.toFixed(5);
  return "$" + usd.toFixed(4);
}

function renderStats() {
  const s = G.stats;
  $("stPieces").textContent = s.pieces;
  $("stLines").textContent = s.lines;
  $("stScore").textContent = s.score.toLocaleString("en-US");
  $("stTspins").textContent = s.tspins;
  $("stAvg").innerHTML =
    s.latencyCount === 0
      ? "–"
      : Math.round(s.latencySum / s.latencyCount) + "<small>ms</small>";
  $("stConf").textContent = s.confidence == null ? "–" : s.confidence.toFixed(2);
  const tokens = s.tokensIn + s.tokensOut;
  $("stTok").textContent = tokens.toLocaleString("en-US");
  $("stCost").textContent = fmtCost(tokens * USD_PER_TOKEN);
  $("stCostAll").textContent = fmtCost(G.sessionCost + tokens * USD_PER_TOKEN);
}

// What Jev reads for each option. Measured in experiments/judge.mjs: with only geometry and
// the ASCII result board Jev ranks placements no better than chance (rho ≈ 0, confidence
// ~0.3) and games die in ~17 pieces; with the engine's height/holes/bumpiness numbers it
// tracks a strong heuristic (rho 0.41, best move in its top 3 88% of the time). So the
// numbers stay: they are Jev's retina, not a hint.
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
  return parts.join("; ");
}

// Short Korean label for the panel. Display only; placementSummary() is what Jev reads.
function candidateLabel(type, cand) {
  const cols = cand.cells.map((c) => c[1]);
  const lo = Math.min(...cols) + 1;
  const hi = Math.max(...cols) + 1;
  const parts = [`${type} 회전 ${cand.rot}`, lo === hi ? `${lo}열` : `${lo}–${hi}열`];
  if (cand.tspin) parts.push(cand.tspin === "full" ? "T스핀" : "미니 T스핀");
  if (cand.linesCleared > 0) parts.push(`${cand.linesCleared}줄 제거`);
  return parts.join(" · ");
}

function renderCandidates(decision, chosenId) {
  const host = $("cands");
  if (!decision) {
    host.innerHTML = '<div class="empty">첫 조각을 기다리는 중…</div>';
    return;
  }
  const top = Object.entries(decision.probabilities)
    .sort((a, b) => b[1] - a[1])
    .slice(0, TOP_N);
  host.innerHTML = "";
  for (const [id, p] of top) {
    const el = document.createElement("div");
    el.className = "cand" + (id === chosenId ? " sel" : "");
    const pct = (p * 100).toFixed(1) + "%";
    const bar = Math.max(1, p * 100).toFixed(1);
    el.innerHTML =
      '<div class="row1"><span class="pct"></span>' +
      '<span class="bar"><i style="width:' + bar + '%"></i></span></div>' +
      '<div class="sum"></div>';
    el.querySelector(".pct").textContent = pct;
    const cand = G.candidates.find((c) => c.id === id);
    el.querySelector(".sum").textContent = cand ? candidateLabel(G.pieceType, cand) : id;
    el.title = G.summaries.get(id) ?? id; // full English summary, exactly as sent to Jev
    host.appendChild(el);
  }
}

let toastTimer = null;
function showToast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
}
function hideToast() {
  $("toast").classList.remove("show");
}

// ---------------------------------------------------------------- controls

function setPaused(paused) {
  G.paused = paused;
  $("btnPause").textContent = paused ? "재개" : "일시정지";
  if (!paused) hideToast();
  setDot(paused ? null : "live");
  setPhase(G.phase);
}

function gameOver() {
  G.over = true;
  setPhase("over");
  setDot("err");
  $("goRes").textContent =
    `조각 ${G.stats.pieces} · 줄 ${G.stats.lines} · 점수 ${G.stats.score.toLocaleString("en-US")}`;
  $("gameover").classList.remove("hidden");
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
  G.candidates = [];
  G.summaries = new Map();
  G.decision = null;
  G.ghosts = [];
  G.anim = null;
  G.flashRows = [];
  G.stats = {
    pieces: 0,
    lines: 0,
    score: 0,
    lastLatency: null,
    latencySum: 0,
    latencyCount: 0,
    tokensIn: 0,
    tokensOut: 0,
    confidence: null,
    tspins: 0,
  };
  G.log = [];
  $("gameover").classList.add("hidden");
  $("btnPause").textContent = "일시정지";
  hideToast();
  renderStats();
  renderCandidates(null);
  setDot("live");
  setPhase("idle");
  runGame(G.gen);
}

// ---------------------------------------------------------------- game loop

async function waitWhilePaused(gen) {
  while (G.gen === gen && G.paused && !G.over) await sleep(80);
}

async function askJev(gen, payload) {
  while (G.gen === gen) {
    try {
      const res = await fetch("/api/decide", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error ? `${res.status} ${body.error}` : `HTTP ${res.status}`);
      }
      const data = await res.json();
      hideToast();
      return data;
    } catch (err) {
      showToast("서버 오류: " + err.message + " — 자동 일시정지. 재개를 누르면 다시 시도합니다.");
      setDot("err");
      setPaused(true);
      await waitWhilePaused(gen);
      if (G.gen !== gen) return null;
    }
  }
  return null;
}

async function playPiece(gen) {
  refillQueue();
  const type = G.queue.shift();
  refillQueue();
  G.pieceType = type;
  G.nextType = G.queue[0];

  const candidates = reachablePlacements(G.board, type);
  if (candidates.length === 0) {
    gameOver();
    return false;
  }
  G.candidates = candidates;
  G.summaries = new Map(candidates.map((c) => [c.id, placementSummary(type, c, G.board)]));
  G.ghosts = [];

  setDot("busy");
  setPhase("thinking", `후보 ${candidates.length}개 · Jev에게 Choice 질문 1개`);

  const instruction = INSTRUCTION;
  const decision = await askJev(gen, {
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
  s.lastLatency = decision.latencyMs;
  s.latencySum += decision.latencyMs;
  s.latencyCount++;
  s.tokensIn += decision.usage?.input_tokens ?? 0;
  s.tokensOut += decision.usage?.output_tokens ?? 0;
  s.confidence = decision.confidence;
  renderStats();
  renderCandidates(decision, chosen.id);
  setDot("live");

  // Ghost heatmap: top 5 candidates, alpha proportional to probability.
  const top = Object.entries(decision.probabilities ?? {})
    .filter(([id]) => byId.has(id))
    .sort((a, b) => b[1] - a[1])
    .slice(0, TOP_N);
  const maxP = top.length ? top[0][1] : 1;
  G.ghosts = top.map(([id, p]) => ({
    cells: byId.get(id).cells,
    p,
    alpha:
      p >= GHOST_LABEL_MIN_P
        ? Math.max(MIN_GHOST_ALPHA, MAX_GHOST_ALPHA * (maxP > 0 ? p / maxP : 0))
        : MAX_GHOST_ALPHA * (maxP > 0 ? p / maxP : 0),
  }));

  setPhase("ghost", `후보 ${candidates.length}개 중 ${chosen.id} 선택 · 확신도 ${decision.confidence.toFixed(2)}`);
  await sleep(GHOST_MS);
  if (G.gen !== gen) return false;

  // Animate by replaying the move path from spawn; consecutive drops are compressed.
  const frames = replayPath(G.board, type, chosen.path);
  const times = [0];
  const drops = chosen.path.filter((m) => m === "D").length;
  const dropMs = drops ? Math.min(STEP_MS, DROP_TOTAL_MS / drops) : 0;
  for (let i = 1; i < frames.length; i++) {
    times.push(times[i - 1] + (frames[i].move === "D" ? dropMs : STEP_MS));
  }
  G.anim = { type, frames, times, t0: performance.now() };
  setPhase("moving", chosen.tspin ? "스핀 진입!" : undefined);
  await sleep(times[times.length - 1] + 120);
  if (G.gen !== gen) return false;
  G.anim = null;

  // Lock the piece where it landed, flash any completed rows, then take the cleared board.
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

  s.pieces++;
  s.lines += chosen.linesCleared;
  s.score += chosen.score;
  if (chosen.tspin) s.tspins++;
  G.log.push({
    piece: type,
    instruction,
    choiceId: chosen.id,
    latencyMs: decision.latencyMs,
    inputTokens: decision.usage?.input_tokens ?? 0,
    outputTokens: decision.usage?.output_tokens ?? 0,
    cols: chosen.cells.map((c) => c[1]),
    linesCleared: chosen.linesCleared,
    tspin: chosen.tspin,
    confidence: decision.confidence,
  });
  renderStats();

  const wait = Number($("speed").value);
  setPhase("waiting", wait ? `${wait}ms 후 다음 조각` : "");
  if (wait > 0) await sleep(wait);
  return G.gen === gen;
}

async function runGame(gen) {
  refillQueue();
  G.nextType = G.queue[0];
  while (G.gen === gen && !G.over) {
    await waitWhilePaused(gen);
    if (G.gen !== gen || G.over) break;
    const ok = await playPiece(gen);
    if (!ok) break;
  }
}

// ---------------------------------------------------------------- wiring

$("btnPause").addEventListener("click", () => setPaused(!G.paused));
$("btnNew").addEventListener("click", newGame);
$("btnNew2").addEventListener("click", newGame);
$("speed").addEventListener("input", () => {
  $("speedVal").textContent = $("speed").value + "ms";
});

renderStats();
renderCandidates(null);
setDot("live");
newGame();
