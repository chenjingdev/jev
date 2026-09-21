// app.js — the page: the board with picture tiles, the four-arrow heatmap of Jev's answer, the
// picture that assembles on the right, and the game loop that asks the server for each slide.
// The picture lives only here; the server and Jev get the grid as words and numbers.

import { DIRS, boardRows, candidates, facts, isGameOver, makeRng, maxTile, move, newGame, spawn } from "./engine.js";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const N = 4;
const PIECES = 16; // the picture is cut 4×4; pieces appear in this order, centre first
const PIECE_ORDER = [5, 6, 10, 9, 1, 2, 3, 7, 11, 15, 14, 13, 12, 8, 4, 0];
const MAX_EXP = 11; // 2^11 = 2048 shows the whole picture
const USD_PER_TOKEN = 42 / 1e9;
const SPEEDS = {
  slow: { heat: 700, slide: 170, pop: 150, label: "느림" },
  normal: { heat: 320, slide: 130, pop: 120, label: "보통" },
  fast: { heat: 120, slide: 90, pop: 80, label: "빠름" },
};
// Classic 2048 tile colours, used for the still-hidden part of each tile face.
const TILE_COLORS = ["#3a3f4b", "#eee4da", "#ede0c8", "#f2b179", "#f59563", "#f67c5f", "#f65e3b", "#edcf72", "#edcc61", "#edc850", "#edc53f", "#edc22e", "#3c3a32"];

// ---------------------------------------------------------------------------
// Picture

// How many of the 16 pieces a tile of 2^k shows. 2 shows one piece, 2048 shows them all.
export function revealCount(k) {
  if (k <= 0) return 0;
  return Math.min(PIECES, Math.round((PIECES * k) / MAX_EXP));
}

// The default picture: a drawn scene, so the page needs no image file and nothing personal.
function makeDefaultArt(size) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d");
  const sky = g.createLinearGradient(0, 0, 0, size * 0.62);
  sky.addColorStop(0, "#1b1f5c");
  sky.addColorStop(0.55, "#7a3f8f");
  sky.addColorStop(1, "#ff9a5c");
  g.fillStyle = sky;
  g.fillRect(0, 0, size, size);
  // stars
  const rand = makeRng(42);
  g.fillStyle = "rgba(255,255,255,.8)";
  for (let i = 0; i < 60; i++) {
    const x = rand() * size;
    const y = rand() * size * 0.35;
    const r = 0.6 + rand() * 1.4;
    g.beginPath();
    g.arc(x, y, r, 0, Math.PI * 2);
    g.fill();
  }
  // sun
  const sunY = size * 0.55;
  const glow = g.createRadialGradient(size * 0.62, sunY, size * 0.02, size * 0.62, sunY, size * 0.3);
  glow.addColorStop(0, "rgba(255,240,180,.9)");
  glow.addColorStop(1, "rgba(255,180,90,0)");
  g.fillStyle = glow;
  g.fillRect(0, 0, size, size);
  g.fillStyle = "#ffe08a";
  g.beginPath();
  g.arc(size * 0.62, sunY, size * 0.11, 0, Math.PI * 2);
  g.fill();
  // mountains, three layers
  const layer = (color, baseY, amp, seed) => {
    const r = makeRng(seed);
    g.fillStyle = color;
    g.beginPath();
    g.moveTo(0, size);
    g.lineTo(0, baseY);
    let x = 0;
    while (x < size) {
      const w = size * (0.08 + r() * 0.12);
      const peak = baseY - amp * (0.4 + r() * 0.6);
      g.lineTo(x + w / 2, peak);
      g.lineTo(x + w, baseY - amp * r() * 0.3);
      x += w;
    }
    g.lineTo(size, size);
    g.closePath();
    g.fill();
  };
  layer("#4a2a6a", size * 0.6, size * 0.22, 3);
  layer("#2d1b4e", size * 0.66, size * 0.16, 9);
  // sea
  const sea = g.createLinearGradient(0, size * 0.7, 0, size);
  sea.addColorStop(0, "#1e4d7a");
  sea.addColorStop(1, "#0b1e33");
  g.fillStyle = sea;
  g.fillRect(0, size * 0.7, size, size * 0.3);
  // reflection stripes
  g.fillStyle = "rgba(255,210,120,.35)";
  for (let i = 0; i < 9; i++) {
    const y = size * 0.72 + i * size * 0.028;
    const w = size * (0.05 + i * 0.012);
    g.fillRect(size * 0.62 - w / 2 + (i % 2 ? size * 0.01 : -size * 0.01), y, w, size * 0.008);
  }
  // sailboat
  const bx = size * 0.3;
  const by = size * 0.84;
  g.fillStyle = "#0a0a14";
  g.beginPath();
  g.moveTo(bx - size * 0.07, by);
  g.lineTo(bx + size * 0.07, by);
  g.lineTo(bx + size * 0.05, by + size * 0.03);
  g.lineTo(bx - size * 0.05, by + size * 0.03);
  g.closePath();
  g.fill();
  g.fillRect(bx - size * 0.004, by - size * 0.16, size * 0.008, size * 0.16);
  g.fillStyle = "#fff4dc";
  g.beginPath();
  g.moveTo(bx + size * 0.006, by - size * 0.15);
  g.lineTo(bx + size * 0.075, by - size * 0.01);
  g.lineTo(bx + size * 0.006, by - size * 0.01);
  g.closePath();
  g.fill();
  g.fillStyle = "#ffd6c2";
  g.beginPath();
  g.moveTo(bx - size * 0.006, by - size * 0.13);
  g.lineTo(bx - size * 0.05, by - size * 0.01);
  g.lineTo(bx - size * 0.006, by - size * 0.01);
  g.closePath();
  g.fill();
  return c;
}

// Crops any image to a square (cover) at `size`.
function squareOf(img, size) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const g = c.getContext("2d");
  const s = Math.min(img.width, img.height);
  g.drawImage(img, (img.width - s) / 2, (img.height - s) / 2, s, s, 0, 0, size, size);
  return c;
}

// Draws `picture` at (x, y, w) with only the first `count` pieces visible; the rest are covered
// with `cover` (a colour) at `alpha`.
function drawRevealed(g, picture, x, y, w, count, cover, alpha) {
  g.drawImage(picture, x, y, w, w);
  const pw = w / N;
  g.fillStyle = cover;
  g.globalAlpha = alpha;
  for (let i = count; i < PIECES; i++) {
    const idx = PIECE_ORDER[i];
    g.fillRect(x + (idx % N) * pw, y + Math.floor(idx / N) * pw, pw + 0.5, pw + 0.5);
  }
  g.globalAlpha = 1;
  // hairlines between pieces so the cut is visible
  g.strokeStyle = "rgba(11,13,18,.35)";
  g.lineWidth = 1;
  for (let i = 1; i < N; i++) {
    g.beginPath();
    g.moveTo(x + i * pw, y);
    g.lineTo(x + i * pw, y + w);
    g.moveTo(x, y + i * pw);
    g.lineTo(x + w, y + i * pw);
    g.stroke();
  }
}

// ---------------------------------------------------------------------------
// State

const G = {
  board: null,
  score: 0,
  moves: 0,
  over: false,
  paused: false,
  gen: 0,
  seed: 0,
  rand: null,
  best: 0, // largest tile ever reached this game
  decision: null, // the answer being executed: { dir, probabilities, danger, local }
  pending: null,
  reached2048: false,
  phase: "idle",
  stats: { calls: 0, latency: 0, tokens: 0, errors: 0 },
  log: [],
};
let speed = SPEEDS[params.get("speed")] ? params.get("speed") : "normal";
// "eyes": Jev gets only the grid, like a person looking at the screen. Default: grid + engine numbers + strategy.
let mode = params.get("mode") === "eyes" ? "eyes" : "full";
let picture = makeDefaultArt(768);
let faces = []; // per exponent: offscreen tile face
let anim = null; // { kind: "slide"|"pop", t0, ms, ... }

const boardCanvas = $("board");
const bctx = boardCanvas.getContext("2d");
const picCanvas = $("picture");
const pctx = picCanvas.getContext("2d");
const dpr = Math.max(1, Math.min(3, window.devicePixelRatio || 1));
let CELL = 96;
let GAP = 10;
let MARGIN = 44;
let BOARD_PX = 0;

function sizeCanvas(canvas, ctx, w, h) {
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  canvas.style.width = w + "px";
  canvas.style.height = h + "px";
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function layout() {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const sideW = vw > 900 ? 420 : 0;
  const avail = vw > 900 ? Math.min(vh - 52 - 24, vw - 48 - sideW - 24) : Math.min(vw - 32, 560);
  MARGIN = Math.max(34, Math.round(avail * 0.075));
  GAP = Math.max(6, Math.round(avail * 0.016));
  CELL = Math.floor((avail - 2 * MARGIN - (N + 1) * GAP) / N);
  BOARD_PX = N * CELL + (N + 1) * GAP + 2 * MARGIN;
  sizeCanvas(boardCanvas, bctx, BOARD_PX, BOARD_PX);
  document.documentElement.style.setProperty("--col-h", BOARD_PX + "px");
  document.documentElement.style.setProperty("--side-w", sideW + "px");
  const pic = 130;
  sizeCanvas(picCanvas, pctx, pic, pic);
  buildFaces();
  drawPicture();
  render();
}

function buildFaces() {
  faces = [];
  const s = CELL * dpr;
  for (let k = 0; k <= MAX_EXP + 2; k++) {
    const c = document.createElement("canvas");
    c.width = c.height = s;
    const g = c.getContext("2d");
    if (k === 0) {
      faces.push(c);
      continue;
    }
    const color = TILE_COLORS[Math.min(k, TILE_COLORS.length - 1)];
    drawRevealed(g, picture, 0, 0, s, revealCount(k), color, 0.86);
    faces.push(c);
  }
}

// ---------------------------------------------------------------------------
// Drawing

function cellXY(i) {
  return { x: MARGIN + GAP + (i % N) * (CELL + GAP), y: MARGIN + GAP + Math.floor(i / N) * (CELL + GAP) };
}

function roundRect(g, x, y, w, h, r) {
  g.beginPath();
  g.moveTo(x + r, y);
  g.arcTo(x + w, y, x + w, y + h, r);
  g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r);
  g.arcTo(x, y, x + w, y, r);
  g.closePath();
}

function drawTile(g, value, x, y, scale = 1) {
  const k = Math.round(Math.log2(value));
  const face = faces[Math.min(k, faces.length - 1)];
  const s = CELL * scale;
  const ox = x + (CELL - s) / 2;
  const oy = y + (CELL - s) / 2;
  g.save();
  roundRect(g, ox, oy, s, s, Math.max(4, CELL * 0.08));
  g.clip();
  g.drawImage(face, ox, oy, s, s);
  g.restore();
  // number pill
  const fs = Math.max(11, Math.round(CELL * (value >= 1024 ? 0.19 : 0.22)));
  g.font = `800 ${fs}px -apple-system, "Pretendard", system-ui, sans-serif`;
  const label = String(value);
  const tw = g.measureText(label).width;
  const px = ox + s * 0.07;
  const py = oy + s * 0.07;
  g.fillStyle = "rgba(11,13,18,.72)";
  roundRect(g, px, py, tw + fs * 0.7, fs * 1.35, fs * 0.35);
  g.fill();
  g.fillStyle = value >= 2048 ? "#ffd166" : "#f4f0e6";
  g.textBaseline = "middle";
  g.textAlign = "left";
  g.fillText(label, px + fs * 0.35, py + fs * 0.7);
}

function drawArrow(g, dir, prob, chosen, legal) {
  const c = BOARD_PX / 2;
  const m = MARGIN / 2;
  const pos = { up: [c, m], down: [c, BOARD_PX - m], left: [m, c], right: [BOARD_PX - m, c] }[dir];
  const rot = { up: -Math.PI / 2, down: Math.PI / 2, left: Math.PI, right: 0 }[dir];
  const size = MARGIN * 0.36;
  g.save();
  g.translate(pos[0], pos[1]);
  const a = legal ? 0.12 + 0.88 * prob : 0.05;
  g.globalAlpha = a;
  g.fillStyle = chosen ? "#c084fc" : "#e6e9f2";
  if (chosen) {
    g.shadowColor = "#c084fc";
    g.shadowBlur = 18;
  }
  g.rotate(rot);
  g.beginPath();
  g.moveTo(size, 0);
  g.lineTo(-size * 0.6, -size * 0.85);
  g.lineTo(-size * 0.2, 0);
  g.lineTo(-size * 0.6, size * 0.85);
  g.closePath();
  g.fill();
  g.restore();
  if (legal && prob != null) {
    g.save();
    g.globalAlpha = 0.35 + 0.65 * prob;
    g.fillStyle = chosen ? "#c084fc" : "#7d859c";
    g.font = `700 ${Math.max(10, Math.round(MARGIN * 0.27))}px -apple-system, system-ui, sans-serif`;
    g.textAlign = "center";
    g.textBaseline = "middle";
    const off = MARGIN * 0.62;
    const tp = { up: [c + off, m], down: [c + off, BOARD_PX - m], left: [m, c + off], right: [BOARD_PX - m, c + off] }[dir];
    g.fillText(Math.round(prob * 100) + "%", tp[0], tp[1]);
    g.restore();
  }
}

function render(now = performance.now()) {
  const g = bctx;
  g.clearRect(0, 0, BOARD_PX, BOARD_PX);
  // frame
  g.fillStyle = "#12151d";
  roundRect(g, MARGIN, MARGIN, BOARD_PX - 2 * MARGIN, BOARD_PX - 2 * MARGIN, 12);
  g.fill();
  for (let i = 0; i < N * N; i++) {
    const { x, y } = cellXY(i);
    g.fillStyle = "#1a1e2a";
    roundRect(g, x, y, CELL, CELL, Math.max(4, CELL * 0.08));
    g.fill();
  }
  const board = G.board ?? [];
  if (anim && anim.kind === "slide") {
    const t = Math.min(1, (now - anim.t0) / anim.ms);
    const e = 1 - (1 - t) * (1 - t);
    const moved = [...anim.moved].sort((a, b) => a.value - b.value);
    for (const mv of moved) {
      const a = cellXY(mv.from);
      const b = cellXY(mv.to);
      drawTile(g, mv.value, a.x + (b.x - a.x) * e, a.y + (b.y - a.y) * e);
    }
  } else {
    for (let i = 0; i < board.length; i++) {
      if (!board[i]) continue;
      let scale = 1;
      if (anim && anim.kind === "pop") {
        const t = Math.min(1, (now - anim.t0) / anim.ms);
        if (anim.merged.has(i)) scale = 1 + 0.18 * Math.sin(t * Math.PI);
        if (anim.spawn === i) scale = 0.2 + 0.8 * (1 - (1 - t) * (1 - t));
      }
      const { x, y } = cellXY(i);
      drawTile(g, board[i], x, y, scale);
    }
  }
  // arrows
  const d = G.decision;
  const legal = new Set(G.board ? candidates(G.board).map((c) => c.dir) : []);
  for (const dir of DIRS) {
    const p = d ? d.probabilities[dir] ?? 0 : null;
    drawArrow(g, dir, p, d && d.dir === dir, d ? dir in d.probabilities : legal.has(dir));
  }
}

function drawPicture() {
  const w = 130;
  pctx.clearRect(0, 0, w, w);
  const k = G.best ? Math.round(Math.log2(G.best)) : 0;
  drawRevealed(pctx, picture, 0, 0, w, revealCount(k), "#0b0d12", 0.9);
  const n = revealCount(k);
  $("pieces").textContent = n;
  $("maxTile").textContent = G.best || 0;
  if (n >= PIECES) $("need").textContent = "그림 완성";
  else {
    let need = k + 1;
    while (revealCount(need) === n) need++;
    $("need").textContent = `다음 조각은 ${2 ** need} 타일에서`;
  }
}

function frame(now) {
  if (anim) {
    render(now);
    if (now - anim.t0 >= anim.ms) {
      const done = anim.resolve;
      anim = null;
      done();
    }
  }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

function animate(spec) {
  return new Promise((resolve) => {
    anim = { ...spec, t0: performance.now(), resolve };
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------------------------------------------------------------------------
// Panel

const ARROWS = { up: "↑", down: "↓", left: "←", right: "→" };
const KO = { up: "위", down: "아래", left: "왼쪽", right: "오른쪽" };

function showDecision(dec, cands) {
  const box = $("picks");
  box.innerHTML = "";
  for (const dir of DIRS) {
    const c = cands.find((x) => x.dir === dir);
    const p = dec.probabilities[dir];
    const row = document.createElement("div");
    row.className = "pick" + (dec.dir === dir ? " chosen" : "") + (c ? "" : " illegal");
    row.innerHTML =
      `<div class="arrow">${ARROWS[dir]}</div>` +
      `<div class="bar"><i style="width:${c && p != null ? Math.round(p * 100) : 0}%"></i></div>` +
      `<div class="pct mono">${c && p != null ? Math.round(p * 100) + "%" : "–"}</div>` +
      `<div class="why">${!c ? KO[dir] + "으로는 움직일 수 없음" : mode === "eyes" ? "" : c.summary.replace(/^slide \w+; /, "").replace(/ before the new tile/, "")}</div>`;
    box.appendChild(row);
  }
  $("pickNote").textContent = dec.local ? "갈 곳이 하나라 묻지 않음" : `Jev ${dec.latencyMs}ms`;
  if (dec.danger != null) {
    $("dangerBar").style.width = Math.round(dec.danger * 100) + "%";
    $("dangerVal").textContent = dec.danger.toFixed(2);
  }
}

function showStats() {
  const s = G.stats;
  $("sMoves").textContent = G.moves;
  $("sScore").textContent = G.score;
  $("sCalls").textContent = s.calls;
  $("sLatency").textContent = s.calls ? Math.round(s.latency / s.calls) + "ms" : "–";
  $("sTokens").textContent = s.calls ? Math.round(s.tokens / s.calls) : "–";
  $("sCost").textContent = "$" + (s.tokens * USD_PER_TOKEN).toFixed(4);
}

function setStatus(text, cls) {
  $("status").textContent = text;
  $("dot").className = "dot " + (cls || "");
}

function banner(title, sub, ms) {
  $("bannerTitle").textContent = title;
  $("bannerSub").textContent = sub;
  $("banner").classList.add("show");
  if (ms) setTimeout(() => $("banner").classList.remove("show"), ms);
}

// ---------------------------------------------------------------------------
// Jev

// Replay: a saved game (seed + Jev's answer per move) plays back without calling Jev. Every
// probability shown is the one Jev gave when the game was recorded; the seed makes the spawns match.
let REPLAY = null;

async function decide(board, moveNo) {
  const cands = candidates(board);
  if (cands.length === 0) return null;
  if (cands.length === 1) {
    return { dir: cands[0].dir, probabilities: { [cands[0].dir]: 1 }, danger: null, local: true, latencyMs: 0, cands };
  }
  const saved = REPLAY?.log[moveNo];
  if (saved && cands.some((c) => c.dir === saved.dir)) {
    G.stats.calls++;
    G.stats.latency += saved.latencyMs ?? 0;
    G.stats.tokens += saved.tokens ?? 0;
    await sleep(saved.latencyMs ?? 250);
    return { dir: saved.dir, probabilities: saved.p, danger: saved.danger, local: false, latencyMs: saved.latencyMs ?? 0, cands };
  }
  const body = {
    rows: boardRows(board),
    score: G.score,
    moveNo,
    mode,
    facts: facts(board),
    candidates: cands.map((c) => ({ dir: c.dir, summary: c.summary, rows: c.rows })),
  };
  for (let attempt = 0; ; attempt++) {
    try {
      const res = await fetch("/api/move", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || res.statusText);
      G.stats.calls++;
      G.stats.latency += data.latencyMs;
      G.stats.tokens += data.usage.input_tokens + data.usage.output_tokens;
      const dir = cands.some((c) => c.dir === data.choice) ? data.choice : cands[0].dir;
      const tokens = data.usage.input_tokens + data.usage.output_tokens;
      return { dir, probabilities: data.probabilities, danger: data.danger, local: false, latencyMs: data.latencyMs, tokens, cands };
    } catch (err) {
      G.stats.errors++;
      setStatus("Jev 오류: " + err.message, "err");
      if (attempt >= 3) {
        return { dir: cands[0].dir, probabilities: { [cands[0].dir]: 1 }, danger: null, local: true, latencyMs: 0, cands, failed: true };
      }
      await sleep(1500 * (attempt + 1));
    }
  }
}

// ---------------------------------------------------------------------------
// Loop

async function run() {
  const gen = G.gen;
  while (!G.over && !G.paused && gen === G.gen) {
    G.phase = "think";
    setStatus("Jev가 고르는 중", "busy");
    const dec = await (G.pending ?? decide(G.board, G.moves));
    G.pending = null;
    if (gen !== G.gen) return;
    if (!dec) break;
    G.decision = dec;
    const S = SPEEDS[speed];
    showDecision(dec, dec.cands);
    setStatus(dec.local ? "외길" : `${KO[dec.dir]} ${Math.round((dec.probabilities[dec.dir] ?? 1) * 100)}%`, "live");
    G.phase = "heat";
    render();
    const r = move(G.board, dec.dir);
    G.score += r.gained;
    const sp = spawn(r.board, G.rand);
    const nextBoard = sp.board;
    G.log.push({ move: G.moves, dir: dec.dir, p: dec.probabilities, danger: dec.danger, latencyMs: dec.latencyMs, tokens: dec.tokens ?? 0, gained: r.gained });
    // Ask about the next grid while this slide plays: the spawn is seeded, so it is known now.
    G.pending = isGameOver(nextBoard) ? null : decide(nextBoard, G.moves + 1);
    await sleep(S.heat);
    if (gen !== G.gen) return;
    G.phase = "slide";
    await animate({ kind: "slide", ms: S.slide, moved: r.moved });
    if (gen !== G.gen) return;
    G.board = nextBoard;
    G.moves++;
    const best = maxTile(G.board);
    if (best > G.best) {
      G.best = best;
      drawPicture();
      if (best >= 2048 && !G.reached2048) {
        G.reached2048 = true;
        banner("2048", "그림 완성", 3500);
      }
    }
    G.phase = "pop";
    await animate({ kind: "pop", ms: S.pop, merged: new Set(r.merged.map((m) => m.at)), spawn: sp.index });
    showStats();
    if (isGameOver(G.board)) {
      G.over = true;
      G.phase = "over";
      setStatus("게임 끝", "");
      banner("게임 끝", `최대 타일 ${G.best} · ${G.moves}수 · ${G.score}점`);
    }
  }
  if (G.paused) setStatus("일시정지", "");
}

function start(seed) {
  G.gen++;
  G.seed = seed;
  G.rand = makeRng(seed);
  G.board = newGame(G.rand);
  G.score = 0;
  G.moves = 0;
  G.over = false;
  G.paused = false;
  G.best = maxTile(G.board);
  G.decision = null;
  G.pending = null;
  G.reached2048 = false;
  G.stats = { calls: 0, latency: 0, tokens: 0, errors: 0 };
  G.log = [];
  anim = null;
  $("banner").classList.remove("show");
  $("picks").innerHTML = "";
  $("dangerBar").style.width = "0%";
  $("dangerVal").textContent = "–";
  drawPicture();
  showStats();
  render();
  history.replaceState(null, "", "?" + new URLSearchParams({ ...Object.fromEntries(params), seed }).toString());
  run();
}

function togglePause() {
  if (G.over) return;
  G.paused = !G.paused;
  $("btnPause").textContent = G.paused ? "계속 (Space)" : "일시정지 (Space)";
  if (!G.paused) run();
}

function setClean(on) {
  document.body.classList.toggle("clean", on);
  try {
    localStorage.setItem("jev-2048-clean", on ? "1" : "0");
  } catch {}
}

function setPicture(img) {
  picture = squareOf(img, 768);
  buildFaces();
  drawPicture();
  render();
}

// ---------------------------------------------------------------------------
// Wiring

$("btnNew").onclick = () => start(Math.floor(Math.random() * 1e9));
$("btnPause").onclick = togglePause;
$("btnSpeed").onclick = () => {
  const keys = Object.keys(SPEEDS);
  speed = keys[(keys.indexOf(speed) + 1) % keys.length];
  $("btnSpeed").textContent = "속도: " + SPEEDS[speed].label;
};
$("btnClean").onclick = () => setClean(!document.body.classList.contains("clean"));
$("btnMode").onclick = () => {
  const q = new URLSearchParams(location.search);
  if (mode === "eyes") q.delete("mode");
  else q.set("mode", "eyes");
  q.delete("seed");
  location.search = q.toString();
};
function showMode() {
  $("btnMode").textContent = mode === "eyes" ? "Jev에게: 격자만 (눈 모드)" : "Jev에게: 격자 + 엔진 숫자 + 전략";
  $("modeTag").textContent = mode === "eyes" ? "눈 모드 — Jev는 격자만 본다" : "";
}
showMode();
$("file").onchange = (e) => {
  const f = e.target.files[0];
  if (f) loadFile(f);
};
function loadFile(f) {
  const img = new Image();
  img.onload = () => {
    setPicture(img);
    URL.revokeObjectURL(img.src);
  };
  img.src = URL.createObjectURL(f);
}
document.addEventListener("dragover", (e) => {
  e.preventDefault();
  document.body.classList.add("drag");
});
document.addEventListener("dragleave", () => document.body.classList.remove("drag"));
document.addEventListener("drop", (e) => {
  e.preventDefault();
  document.body.classList.remove("drag");
  const f = e.dataTransfer.files[0];
  if (f && f.type.startsWith("image/")) loadFile(f);
});
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT") return;
  if (e.code === "Space") {
    e.preventDefault();
    togglePause();
  } else if (e.key === "n" || e.key === "N") start(Math.floor(Math.random() * 1e9));
  else if (e.key === "c" || e.key === "C") setClean(!document.body.classList.contains("clean"));
});
window.addEventListener("resize", layout);
$("btnSpeed").textContent = "속도: " + SPEEDS[speed].label;

// recordings and tests read this
window.__jev = G;

let cleanPref = false;
try {
  cleanPref = localStorage.getItem("jev-2048-clean") === "1";
} catch {}
if (params.has("clean")) cleanPref = params.get("clean") !== "0";
setClean(cleanPref);

layout();
if (params.get("img")) {
  const img = new Image();
  img.onload = () => setPicture(img);
  img.src = params.get("img");
}
if (params.get("replay")) {
  // a saved game from public/replays/<name>.json: { seed, log: [{ dir, p, danger, latencyMs, tokens }] }
  const r = await fetch(`replays/${params.get("replay")}.json`);
  if (r.ok) {
    REPLAY = await r.json();
    document.querySelector("header .hook").textContent += " 녹화된 판을 재생 중: 확률은 그때 Jev가 준 값.";
    start(REPLAY.seed);
  } else {
    setStatus("리플레이 없음", "err");
  }
} else {
  start(params.has("seed") ? Number(params.get("seed")) : Math.floor(Math.random() * 1e9));
}
