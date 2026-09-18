// cortex.js — the cortex panel: the SVG of docs/neurons-spec.md 6.3, the timeline of 6.3,
// and the two text lines below it. Built once by initCortex(); renderCortex(view) only sets
// attributes and classes on the elements that already exist, so a frame never rebuilds DOM.
// Every light here is a number that came back from Jev (or an engine fact); the only thing
// that moves without an answer is the dashed "request in flight" flow that setInflight() turns
// on, and it is styled as a request, not as an answer.
//
// The view object (built by app.js) is the single input; every field may be null or missing
// and the panel then draws that layer in its idle state.

import { HUES, INTENTS, LABELS_KO } from "./neurons.js";

const NS = "http://www.w3.org/2000/svg";

// Row 1 geometry (6.3): five intent circles, then the habit circle.
const CIRCLE_X = { survive: 45, clean: 105, build: 165, cash: 225, spin: 285, default: 335 };
const CIRCLE_Y = 117;
const R_IDLE = 13;
const R_HABIT = 10;
// Row 2: proposal chips.
const CHIP_Y = 196;
const CHIP_W = 88;
const CHIP_H = 40;
const chipX = (k) => 12 + 96 * k;
// Row 3: verdict bars.
const BAR_Y0 = 300;
const BAR_STEP = 20;
const BAR_H = 14;
const BAR_X = 56;
const BAR_W = 244;
// Recurrent nodes on the left edge.
const STAY = { x: 18, y: 117, r: 7 };
const HOLD = { x: 18, y: 354, r: 7 };
// Appetite gauge.
const GAUGE = { x: 372, y: 92, w: 12, h: 55 };
// The three layers as bands: y range of each, and the header baseline inside it. The piece's
// phase (data-phase on the svg) dims the bands that have not run yet, so the eye reads the
// request order top to bottom instead of one flat panel.
const BANDS = {
  sense: { y: 50, h: 110, label: "R1 감각층" },
  motor: { y: 172, h: 76, label: "R2 운동층" },
  verdict: { y: 260, h: 122, label: "R3 판정층" },
};
const VIEW_H = 390;

const MAX_CHIPS = 4;
const TIMELINE_N = 40;

const COLORS = {
  text: "#e6e9f2",
  muted: "#7d859c",
  dim: "#3d4456",
  panel: "#171b25",
  well: "#0e1118",
  line: "#232838",
  bar: "#5a637a",
  white: "#ffffff",
  ok: "#4ade80",
  amber: "#fbbf24",
};

// Styles live inside the SVG so the module is self-contained (the demo page needs nothing
// else), but an inline SVG's <style> applies to the whole document, hence the #cortex prefix.
const STYLE = `
#cortex { font-family: -apple-system, "Pretendard", "Apple SD Gothic Neo", system-ui, "Segoe UI", sans-serif; }
#cortex .mono { font-family: "SFMono-Regular", "SF Mono", Menlo, Consolas, monospace; font-variant-numeric: tabular-nums; }
#cortex .neuron .body { transition: fill-opacity .15s ease, r .15s ease, filter .15s ease, stroke .15s ease; }
#cortex .gauge .fill { transition: height .15s ease, y .15s ease, fill .15s ease; }
#cortex .node .fill { transition: height .15s ease, y .15s ease; }
#cortex .node .body { transition: fill-opacity .15s ease, filter .15s ease; }
#cortex .bar .A { transition: width .15s ease; }
#cortex .bar .V { transition: width .15s ease, x .15s ease; }
#cortex .sline { stroke: ${COLORS.dim}; stroke-width: 1; stroke-opacity: 0; stroke-dasharray: 4 4; }
#cortex .mline { fill: none; stroke-linecap: round; transition: stroke-opacity .15s ease; }
#cortex .mline.pending { stroke-dasharray: 4 4; stroke-opacity: .35; }
#cortex .rec { fill: none; stroke: ${COLORS.dim}; stroke-width: 1; stroke-dasharray: 3 3; transition: stroke .15s ease; }
#cortex .rec.lit { stroke-width: 1.5; animation: cx-flow .9s linear infinite; }
#cortex .arrow { transition: opacity .15s ease; }
#cortex .hidden { display: none; }
#cortex .band { transition: opacity .25s ease; }
#cortex .band .frame { fill: ${COLORS.panel}; fill-opacity: .35; stroke: ${COLORS.line}; stroke-width: 1; }
#cortex .band .head { font-size: 10px; font-weight: 700; fill: ${COLORS.muted}; letter-spacing: .08em; }
#cortex .band .count { font-size: 9.5px; fill: ${COLORS.text}; }
#cortex[data-phase="sense"] .band-motor, #cortex[data-phase="sense"] .band-verdict { opacity: .22; }
#cortex[data-phase="motor"] .band-verdict { opacity: .22; }
#cortex[data-phase="verdict"] .band-sense, #cortex[data-phase="moving"] .band-sense { opacity: .55; }
#cortex[data-phase="moving"] .band-motor { opacity: .7; }
#cortex[data-phase="idle"] .band, #cortex[data-phase="single"] .band { opacity: .35; }
#cortex .hop { fill: ${COLORS.dim}; transition: fill .2s ease; }
#cortex .hop-text { font-size: 8px; fill: ${COLORS.muted}; opacity: 0; transition: opacity .2s ease; }
#cortex.inflight-motor .hop-1, #cortex.inflight-arbitrate .hop-2 { fill: ${COLORS.white}; animation: cx-pulse .5s ease-in-out infinite alternate; }
#cortex.inflight-motor .hop-text-1, #cortex.inflight-arbitrate .hop-text-2 { opacity: 1; }
#cortex.inflight-sense .sline { stroke-opacity: .8; animation: cx-flow .5s linear infinite; }
#cortex.inflight-motor .mline.pending { stroke-opacity: .8; animation: cx-flow .5s linear infinite; }
#cortex.inflight-arbitrate .arrow { animation: cx-pulse .7s ease-in-out infinite alternate; }
@keyframes cx-flow { to { stroke-dashoffset: -16; } }
@keyframes cx-pulse { from { opacity: .35; } to { opacity: 1; } }
`;

const el = {
  svg: null,
  bars0: [],
  facts1: null,
  facts2: null,
  queue: null,
  slines: {},
  neurons: {},
  habit: null,
  gauge: null,
  stay: null,
  hold: null,
  rec: null,
  mlines: {},
  chips: [],
  bars: [],
  arrows: [],
  timeline: null,
  timelineCells: [],
  thought: null,
  verdictLine: null,
};
let built = false;
// The previous piece's ledBy, read from the timeline before this piece's verdict lands; the
// STAY node and the stayed lock need it, and gate() does not carry it forward.
let prevLedMemo = null;

// ---------------------------------------------------------------- small helpers

function make(tag, attrs = {}, parent = null) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined) continue;
    node.setAttribute(k, String(v));
  }
  if (parent) parent.appendChild(node);
  return node;
}

function text(parent, x, y, attrs = {}, content = "") {
  const t = make("text", { x, y, ...attrs }, parent);
  t.textContent = content;
  return t;
}

function setTitle(node, str) {
  let t = node.querySelector(":scope > title");
  if (!t) t = make("title", {}, node);
  if (node.firstChild !== t) node.insertBefore(t, node.firstChild);
  t.textContent = str ?? "";
}

function setText(node, str) {
  const s = str ?? "";
  if (node.textContent !== s) node.textContent = s;
}

function show(node, on) {
  node.classList.toggle("hidden", !on);
}

const isNum = (v) => typeof v === "number" && Number.isFinite(v);
const clamp01 = (v) => Math.max(0, Math.min(1, v));

/** ".92" style probability text: leading zero dropped, two decimals. */
function fmtP(p) {
  if (!isNum(p)) return "";
  if (p >= 0.995) return "1.0";
  return p.toFixed(2).replace(/^0/, "");
}

function hueOf(name) {
  return HUES[name] ?? HUES.default;
}

function labelOf(name) {
  return LABELS_KO[name] ?? name ?? "";
}

/** Instruction text for a question name, or an honest placeholder: nothing here is invented. */
function instruction(view, name) {
  const t = view?.instructions?.[name];
  return typeof t === "string" && t ? t : `${name} · 지시문 없음 (아직 전송 전)`;
}

// Fit a <text> into maxW viewBox units by truncating with an ellipsis. getComputedTextLength
// is 0 when the SVG is not rendered (display:none); then the full string stays.
function fitText(node, str, maxW) {
  setText(node, str);
  if (typeof node.getComputedTextLength !== "function") return;
  let w = node.getComputedTextLength();
  if (!w || w <= maxW) return;
  let s = str;
  while (s.length > 1 && w > maxW) {
    s = s.slice(0, -1);
    node.textContent = s + "…";
    w = node.getComputedTextLength();
  }
}

// Split "a · b · c" over two <text> lines at the separators, as many parts on the first line
// as fit; whatever is left is truncated on the second.
function fitTwoLines(first, second, str, maxW) {
  const parts = String(str ?? "").split(" · ");
  const canMeasure = typeof first.getComputedTextLength === "function";
  let n = parts.length;
  if (canMeasure) {
    setText(first, parts.join(" · "));
    if (!first.getComputedTextLength()) n = parts.length; // not rendered: no measurement possible
    else {
      while (n > 1) {
        setText(first, parts.slice(0, n).join(" · "));
        if (first.getComputedTextLength() <= maxW) break;
        n--;
      }
    }
  }
  fitText(first, parts.slice(0, n).join(" · "), maxW);
  fitText(second, parts.slice(n).join(" · "), maxW);
}

// ---------------------------------------------------------------- build

function buildBands(svg) {
  el.bands = {};
  for (const [key, b] of Object.entries(BANDS)) {
    const g = make("g", { class: `band band-${key}` }, svg);
    make("rect", { class: "frame", x: 4, y: b.y, width: 392, height: b.h, rx: 8 }, g);
    text(g, 12, b.y + 13, { class: "head" }, b.label);
    const count = text(g, 388, b.y + 13, { class: "count mono", "text-anchor": "end" }, "");
    el.bands[key] = { g, count };
  }
  // Hop arrows in the gaps between bands: lit only while that request is in flight.
  const hop = (n, y) => {
    make("polygon", { class: `hop hop-${n}`, points: `${200 - 6},${y} ${200 + 6},${y} 200,${y + 7}` }, svg);
    el[`hop${n}`] = text(svg, 212, y + 7, { class: `hop-text hop-text-${n}` }, "");
  };
  hop(1, BANDS.sense.y + BANDS.sense.h + 2);
  hop(2, BANDS.motor.y + BANDS.motor.h + 2);
}

function buildRow0(svg) {
  const g = make("g", { class: "row0" }, svg);
  for (let c = 0; c < 10; c++) {
    el.bars0.push(make("rect", { x: 12 + 12 * c, y: 40, width: 9, height: 0, fill: COLORS.bar, rx: 1 }, g));
  }
  // Baseline under the bars, so an empty board still shows where the surface is.
  make("line", { x1: 12, y1: 40.5, x2: 129, y2: 40.5, stroke: COLORS.line, "stroke-width": 1 }, g);
  const tx = 138;
  el.facts1 = text(g, tx, 17, { "font-size": 10, fill: COLORS.text, class: "mono" }, "높이 – · 구멍 – · 굴곡 –");
  el.facts2 = text(g, tx, 29, { "font-size": 10, fill: COLORS.text, class: "mono" }, "우물 – · 꽉찬 줄 –");
  el.queue = text(g, tx, 41, { "font-size": 10, fill: COLORS.muted, class: "mono" }, "큐 –");
  // Request-1 flow: the retina row down to each intent circle, visible only while in flight.
  for (const i of INTENTS) {
    el.slines[i] = make("line", { class: "sline", x1: CIRCLE_X[i], y1: BANDS.sense.y + 18, x2: CIRCLE_X[i], y2: CIRCLE_Y - R_IDLE - 1 }, g);
  }
}

function buildLock(parent) {
  const g = make("g", { class: "lock hidden" }, parent);
  make("path", { d: "M-2.6,0 V-2.6 A2.6,2.6 0 0 1 2.6,-2.6 V0", fill: "none", stroke: COLORS.white, "stroke-width": 1.3 }, g);
  make("rect", { x: -4, y: 0, width: 8, height: 5.5, rx: 1, fill: COLORS.white }, g);
  return g;
}

function buildNeuron(svg, name) {
  const x = CIRCLE_X[name];
  const g = make("g", { class: "neuron", "data-neuron": name }, svg);
  setTitle(g, "");
  const body = make("circle", { class: "body", cx: x, cy: CIRCLE_Y, r: R_IDLE, fill: hueOf(name), "fill-opacity": 0.12, stroke: "none" }, g);
  const value = text(g, x, CIRCLE_Y + 3.4, { class: "mono", "font-size": 9, fill: COLORS.white, "text-anchor": "middle" }, "");
  const label = text(g, x, CIRCLE_Y + 27, { "font-size": 10, fill: COLORS.muted, "text-anchor": "middle" }, labelOf(name));
  const forced = text(g, x, CIRCLE_Y - 21, { class: "hidden", "font-size": 9, "font-weight": 700, fill: HUES.forced, "text-anchor": "middle" }, LABELS_KO.forced);
  const lock = buildLock(g);
  lock.setAttribute("transform", `translate(${x + 13}, ${CIRCLE_Y - 24})`);
  el.neurons[name] = { g, body, value, label, forced, lock };
}

function buildHabit(svg) {
  const x = CIRCLE_X.default;
  const g = make("g", { class: "neuron habit", "data-neuron": "default" }, svg);
  setTitle(g, "");
  const body = make("circle", { class: "body", cx: x, cy: CIRCLE_Y, r: R_HABIT, fill: HUES.default, "fill-opacity": 0.5, stroke: "none" }, g);
  const value = text(g, x, CIRCLE_Y + 3.2, { class: "mono", "font-size": 8, fill: COLORS.white, "text-anchor": "middle" }, "");
  text(g, x, 122, { "font-size": 10, fill: COLORS.muted, "text-anchor": "middle" }, LABELS_KO.default);
  el.habit = { g, body, value };
}

function buildGauge(svg) {
  const { x, y, w, h } = GAUGE;
  const g = make("g", { class: "gauge" }, svg);
  setTitle(g, "");
  make("rect", { x, y, width: w, height: h, fill: COLORS.well, stroke: COLORS.line, rx: 2 }, g);
  const fill = make("rect", { class: "fill", x: x + 1, y: y + h - 1, width: w - 2, height: 0, fill: COLORS.ok, rx: 1 }, g);
  for (let k = 1; k < 4; k++) {
    const yy = y + (h * k) / 4;
    make("line", { x1: x, y1: yy, x2: x + w, y2: yy, stroke: COLORS.line, "stroke-width": 1 }, g);
  }
  const value = text(g, x + w / 2, y - 5, { class: "mono", "font-size": 9, fill: COLORS.text, "text-anchor": "middle" }, "");
  text(g, x + w / 2, y + h + 11, { "font-size": 9, fill: COLORS.muted, "text-anchor": "middle" }, "선호");
  el.gauge = { g, fill, value };
}

function buildNode(svg, spec, label, cls) {
  const g = make("g", { class: `node ${cls}` }, svg);
  setTitle(g, "");
  const clipId = `cx-clip-${cls}`;
  const clip = make("clipPath", { id: clipId }, g);
  const clipRect = make("rect", { x: spec.x - spec.r, y: spec.y + spec.r, width: spec.r * 2, height: 0 }, clip);
  const body = make("circle", { class: "body", cx: spec.x, cy: spec.y, r: spec.r, fill: HUES.default, "fill-opacity": 0.1, stroke: COLORS.dim, "stroke-width": 1 }, g);
  const fill = make("circle", { class: "fillc", cx: spec.x, cy: spec.y, r: spec.r, fill: HUES.default, "clip-path": `url(#${clipId})` }, g);
  const value = text(g, spec.x, spec.y + 2.8, { class: "mono", "font-size": 7, fill: COLORS.white, "text-anchor": "middle" }, "");
  text(g, spec.x, spec.y + spec.r + 9, { "font-size": 8, fill: COLORS.muted, "text-anchor": "middle" }, label);
  return { g, body, fill, clipRect, value, spec };
}

function buildMotorLines(svg) {
  const g = make("g", { class: "mlines" }, svg);
  for (const n of [...INTENTS, "default"]) {
    el.mlines[n] = make("path", { class: "mline hidden", "data-neuron": n, d: "" }, g);
  }
}

function buildChips(svg) {
  const g = make("g", { class: "chips" }, svg);
  for (let k = 0; k < MAX_CHIPS; k++) {
    const x = chipX(k);
    const cg = make("g", { class: "chip hidden", "data-k": k }, g);
    setTitle(cg, "");
    const box = make("rect", { x, y: CHIP_Y, width: CHIP_W, height: CHIP_H, rx: 6, fill: COLORS.panel, stroke: HUES.default, "stroke-width": 1 }, cg);
    const swatch = make("rect", { x: x + 7, y: CHIP_Y + 8, width: 10, height: 10, rx: 2, fill: HUES.default }, cg);
    const top = text(cg, x + 21, CHIP_Y + 16, { class: "mono", "font-size": 10, fill: COLORS.text }, "");
    const alt = text(cg, x + CHIP_W - 5, CHIP_Y + 16, { class: "hidden", "font-size": 7, "font-weight": 700, fill: COLORS.muted, "text-anchor": "end" }, "ALT");
    // The Korean candidate label rarely fits one line at this width, so it gets two.
    const label = text(cg, x + 7, CHIP_Y + 27, { "font-size": 8.5, fill: COLORS.muted }, "");
    const label2 = text(cg, x + 7, CHIP_Y + 36.5, { "font-size": 8.5, fill: COLORS.muted }, "");
    el.chips.push({ g: cg, box, swatch, top, alt, label, label2, x });
  }
}

function buildArrows(svg) {
  const g = make("g", { class: "row3head" }, svg);
  const one = (x, label) => {
    const ag = make("g", { class: "arrow" }, g);
    const ty = BAR_Y0 - 15;
    text(ag, x, ty, { "font-size": 10, "font-weight": 700, fill: COLORS.text, "text-anchor": "middle" }, label);
    make("line", { x1: x, y1: ty + 3, x2: x, y2: ty + 10, stroke: COLORS.muted, "stroke-width": 1 }, ag);
    make("polygon", { points: `${x - 3},${ty + 10} ${x + 3},${ty + 10} ${x},${ty + 14}`, fill: COLORS.muted }, ag);
    return ag;
  };
  // Two arrows side by side: the arbiter and the coach judge in the same request, never one
  // after the other (Appendix A-4), and the picture must say so.
  el.arrows = [one(150, "중재"), one(270, "코치")];
  text(g, 210, BAR_Y0 - 15, { "font-size": 8, fill: COLORS.muted, "text-anchor": "middle" }, "동시에");
}

function buildBars(svg) {
  const g = make("g", { class: "bars" }, svg);
  for (let k = 0; k < MAX_CHIPS; k++) {
    const y = BAR_Y0 + BAR_STEP * k;
    const bg = make("g", { class: "bar hidden", "data-k": k }, g);
    setTitle(bg, "");
    const chosen = make("rect", { class: "hidden", x: 40, y: y - 1, width: 3, height: BAR_H + 2, fill: COLORS.white }, bg);
    const swatch = make("rect", { x: 45, y: y + 3, width: 8, height: 8, rx: 2, fill: HUES.default }, bg);
    const well = make("rect", { x: BAR_X, y, width: BAR_W, height: BAR_H, rx: 2, fill: COLORS.well, stroke: "none" }, bg);
    const A = make("rect", { class: "A", x: BAR_X, y, width: 0, height: BAR_H, rx: 2, fill: HUES.default }, bg);
    const V = make("rect", { class: "V", x: BAR_X + BAR_W, y, width: 0, height: BAR_H, rx: 2, fill: HUES.veto, "fill-opacity": 0.55 }, bg);
    setTitle(V, "");
    const id = text(bg, BAR_X + 4, y + 10.5, { class: "mono", "font-size": 9, fill: COLORS.white }, "");
    const pct = text(bg, 306, y + 11, { class: "mono", "font-size": 10, "font-weight": 700, fill: COLORS.text }, "");
    const vetoBox = make("rect", { class: "hidden", x: 336, y: y + 1.5, width: 27, height: 11, rx: 2, fill: HUES.veto }, bg);
    const vetoText = text(bg, 349.5, y + 10, { class: "hidden", "font-size": 7.5, "font-weight": 800, fill: COLORS.white, "text-anchor": "middle" }, "VETO");
    const sel = text(bg, 366, y + 10.5, { class: "hidden", "font-size": 9, "font-weight": 700, fill: COLORS.white }, "선택");
    el.bars.push({ g: bg, chosen, swatch, well, A, V, id, pct, vetoBox, vetoText, sel, y });
  }
}

function buildTimeline() {
  const host = document.getElementById("timeline");
  if (!host) return;
  el.timeline = host;
  host.textContent = "";
  el.timelineCells = [];
  for (let k = 0; k < TIMELINE_N; k++) {
    const i = document.createElement("i");
    i.className = "empty";
    host.appendChild(i);
    el.timelineCells.push(i);
  }
}

/** Build the SVG contents once and prepare the text lines. Safe to call again: a no-op. */
export function initCortex() {
  if (built) return;
  const svg = document.getElementById("cortex");
  if (!svg) return;
  built = true;
  el.svg = svg;
  svg.textContent = "";
  const style = make("style", {}, svg);
  style.textContent = STYLE;

  buildBands(svg);
  buildRow0(svg);
  // The recurrent link: HOLD (this verdict) climbs the left edge into STAY (the next R1).
  el.rec = make("path", {
    class: "rec",
    d: `M${HOLD.x},${HOLD.y - HOLD.r} L${HOLD.x},${HOLD.y - HOLD.r - 5} L6,${HOLD.y - HOLD.r - 5} L6,${STAY.y} L${STAY.x - STAY.r},${STAY.y}`,
  }, svg);
  el.stay = buildNode(svg, STAY, "계획", "stay");
  buildMotorLines(svg);
  for (const i of INTENTS) buildNeuron(svg, i);
  buildHabit(svg);
  buildGauge(svg);
  buildChips(svg);
  buildArrows(svg);
  buildBars(svg);
  el.hold = buildNode(svg, HOLD, "유지", "hold");

  buildTimeline();
  el.thought = document.getElementById("thought");
  el.verdictLine = document.getElementById("verdictLine");
  if (el.thought) el.thought.textContent = "";
  if (el.verdictLine) el.verdictLine.textContent = "";
}

// ---------------------------------------------------------------- derived values

// Band headers carry counts so a piece with one fired neuron still reads as three stages:
// "5 evaluated → 1 fired", "2 proposals", "arbiter + 2 coaches + hold".
function renderBands(view) {
  if (!el.bands) return;
  const sensed = view.sense ? INTENTS.filter((i) => typeof view.sense[i] === "number").length : 0;
  const fired = view.intent?.fired?.length ?? 0;
  const props = view.proposals?.length ?? 0;
  const forced = view.intent?.forced ? " · 강제" : "";
  const stayed = view.intent?.stayed ? " · 유지" : "";
  setText(el.bands.sense.count, sensed ? `뉴런 ${sensed + 1}개 평가 → ${fired}개 발화${forced}${stayed}` : "");
  setText(el.bands.motor.count, props ? `운동 뉴런 ${fired + 1}개 → 제안 ${props}개` : fired ? `운동 뉴런 ${fired + 1}개` : "");
  setText(el.bands.verdict.count, props ? `중재 1 + 코치 ${props} + 유지 1` : "");
  if (el.hop1) setText(el.hop1, fired ? `발화 ${fired}개 → 운동 질문 ${fired + 1}개` : "");
  if (el.hop2) setText(el.hop2, props ? `제안 ${props}개 → 판정 질문 ${props + 2}개` : "");
}

function activationOf(view, name) {
  const a = view.intent?.activations?.[name];
  if (isNum(a)) return a;
  const s = view.sense?.[name];
  return isNum(s) ? s : null;
}

function firedSet(view) {
  return new Set(Array.isArray(view.intent?.fired) ? view.intent.fired : []);
}

/** Which intent led the previous piece (for the STAY node and the lock glyph). */
function previousLed(view) {
  const tl = Array.isArray(view.timeline) ? view.timeline : [];
  if (!view.verdict) {
    prevLedMemo = tl.length ? tl[tl.length - 1]?.ledBy ?? null : null;
    return prevLedMemo;
  }
  if (prevLedMemo) return prevLedMemo;
  return tl.length >= 2 ? tl[tl.length - 2]?.ledBy ?? null : null;
}

function topTwoIntents(view) {
  return INTENTS.map((i) => [i, activationOf(view, i) ?? 0])
    .sort((p, q) => q[1] - p[1])
    .slice(0, 2)
    .map((p) => p[0]);
}

function proposalsOf(view) {
  return Array.isArray(view.proposals) ? view.proposals.slice(0, MAX_CHIPS) : null;
}

const backerP = (prop, n) => {
  const p = prop.probs?.[n] ?? prop.m?.[n];
  return isNum(p) ? p : null;
};

// ---------------------------------------------------------------- render: rows

function renderRow0(view) {
  const surface = Array.isArray(view.surface) ? view.surface : [];
  for (let c = 0; c < 10; c++) {
    const h = clamp01((isNum(surface[c]) ? surface[c] : 0) / 20) * 28;
    el.bars0[c].setAttribute("height", h.toFixed(1));
    el.bars0[c].setAttribute("y", (40 - h).toFixed(1));
  }
  const f = view.facts;
  const n = (v) => (isNum(v) ? String(v) : "–");
  if (f) {
    const well = isNum(f.wellColumn) ? `우물 ${f.wellColumn + 1}열 −${n(f.wellDepth)}` : "우물 없음";
    setText(el.facts1, `높이 ${n(f.maxHeight)} · 구멍 ${n(f.holes)} · 굴곡 ${n(f.bumpiness)}`);
    setText(el.facts2, `${well} · 꽉찬 줄 ${n(f.rowsNearlyFull)}`);
  } else {
    setText(el.facts1, "높이 – · 구멍 – · 굴곡 –");
    setText(el.facts2, "우물 – · 꽉찬 줄 –");
  }
  const q = Array.isArray(view.queue) ? view.queue.join(" ") : "";
  setText(el.queue, q ? `큐 ${q}` : "큐 –");
}

function renderNeurons(view) {
  const fired = firedSet(view);
  const forced = !!view.intent?.forced;
  const stayed = !!view.intent?.stayed;
  const prev = previousLed(view);
  const lockOn = stayed ? (INTENTS.includes(prev) ? prev : view.intent?.leading ?? null) : null;
  const dark = view.phase === "idle" || view.phase === "single" || view.phase === "sense";

  for (const i of INTENTS) {
    const node = el.neurons[i];
    const hue = hueOf(i);
    const a = dark ? null : activationOf(view, i);
    const isFired = !dark && fired.has(i);
    const isForced = isFired && forced && i === "survive";
    if (a === null) {
      node.body.setAttribute("fill-opacity", dark && view.phase === "sense" ? "0.06" : "0.12");
      node.body.setAttribute("r", String(R_IDLE));
      node.body.style.filter = "none";
      setText(node.value, "");
    } else {
      node.body.setAttribute("fill-opacity", (0.15 + 0.85 * clamp01(a)).toFixed(3));
      node.body.setAttribute("r", (R_IDLE + 6 * clamp01(a)).toFixed(2));
      node.body.style.filter = `drop-shadow(0 0 ${(4 + 10 * clamp01(a)).toFixed(1)}px ${hue})`;
      setText(node.value, fmtP(a));
    }
    node.body.setAttribute("stroke", isForced ? HUES.forced : isFired ? COLORS.white : "none");
    node.body.setAttribute("stroke-width", isForced ? "2" : "1.5");
    node.label.setAttribute("fill", isFired ? COLORS.text : COLORS.muted);
    node.label.setAttribute("font-weight", isFired ? "700" : "400");
    show(node.forced, isForced);
    show(node.lock, lockOn === i);
    setTitle(node.g, instruction(view, i));
  }

  // The habit neuron is tonic: always on, always grey, never an intent.
  const m = view.proposals ? (view.proposals.find((p) => p.backers?.includes("default")) ?? null) : null;
  setText(el.habit.value, dark ? "" : m ? fmtP(backerP(m, "default")) : "");
  setTitle(el.habit.g, instruction(view, "motor_default"));

  // Appetite gauge: green → amber → red as the temperament grows bolder.
  const app = dark ? null : isNum(view.appetite) ? view.appetite : isNum(view.intent?.appetite) ? view.intent.appetite : null;
  const { y, h } = GAUGE;
  const fh = app === null ? 0 : clamp01(app / 3) * (h - 2);
  el.gauge.fill.setAttribute("height", fh.toFixed(1));
  el.gauge.fill.setAttribute("y", (y + h - 1 - fh).toFixed(1));
  el.gauge.fill.setAttribute("fill", app === null ? COLORS.ok : app < 1 ? COLORS.ok : app < 2 ? COLORS.amber : HUES.veto);
  setText(el.gauge.value, app === null ? "" : app.toFixed(1));
  setTitle(el.gauge.g, instruction(view, "appetite"));

  // STAY: lit in the previous piece's colour when the plan re-entered.
  const stay = dark ? null : isNum(view.sense?.stay) ? view.sense.stay : null;
  const stayHue = hueOf(INTENTS.includes(prev) ? prev : "default");
  renderNode(el.stay, stay === null ? 0 : stay, stayHue, stay !== null && stay >= 0.5);
  setText(el.stay.value, stay === null ? "" : fmtP(stay));
  setTitle(el.stay.g, view.sense && view.sense.stay === null && view.phase !== "idle" ? "stay · 이번 조각은 질문 생략 (이전 계획 없음)" : instruction(view, "stay"));
}

function renderNode(node, frac, hue, lit) {
  const { x, y, r } = node.spec;
  const fh = clamp01(frac) * r * 2;
  node.clipRect.setAttribute("y", (y + r - fh).toFixed(2));
  node.clipRect.setAttribute("height", fh.toFixed(2));
  node.fill.setAttribute("fill", hue);
  node.fill.setAttribute("fill-opacity", lit ? "0.9" : "0.45");
  node.body.setAttribute("stroke", lit ? hue : COLORS.dim);
  node.body.style.filter = lit ? `drop-shadow(0 0 6px ${hue})` : "none";
}

// One line per motor neuron, from its circle to the chip holding its argmax. Several neurons
// on the same chip end at the same point, which is where the lines merge.
function setMotorLine(neuron, chipIndex, a, pending) {
  const line = el.mlines[neuron];
  const x0 = CIRCLE_X[neuron];
  const r = neuron === "default" ? R_HABIT : R_IDLE + 6 * clamp01(a ?? 0);
  const y0 = CIRCLE_Y + r + 1;
  const x1 = chipX(chipIndex) + CHIP_W / 2;
  const y1 = CHIP_Y - 1;
  // Straight down past the label, then an S-sweep in the gap between labels and chips: long
  // sweeps flatten into a bus that other neurons' lines join before the chip.
  const ys = CIRCLE_Y + 33;
  const ye = CHIP_Y - 4;
  line.setAttribute("d", `M${x0},${y0.toFixed(1)} L${x0},${ys} C${x0},${ys + 18} ${x1},${ye - 18} ${x1},${ye} L${x1},${y1}`);
  line.setAttribute("stroke", hueOf(neuron));
  line.setAttribute("stroke-width", neuron === "default" ? "1.5" : (1 + 3 * clamp01(a ?? 0)).toFixed(2));
  line.setAttribute("stroke-opacity", pending ? "0.35" : "0.85");
  line.classList.toggle("pending", pending);
  show(line, true);
}

function renderChips(view) {
  const props = proposalsOf(view);
  const intent = view.intent;
  for (const n of [...INTENTS, "default"]) show(el.mlines[n], false);
  const used = new Set();

  if (props && props.length) {
    props.forEach((prop, k) => {
      const chip = el.chips[k];
      const backers = Array.isArray(prop.backers) && prop.backers.length ? prop.backers : ["default"];
      const lead = backers[0];
      const hue = hueOf(lead);
      const habitOnly = backers.every((b) => b === "default");
      chip.box.setAttribute("stroke", habitOnly ? HUES.default : hue);
      chip.box.setAttribute("stroke-dasharray", prop.alt ? "3 2" : "none");
      chip.box.setAttribute("stroke-width", "1");
      chip.swatch.setAttribute("fill", habitOnly ? HUES.default : hue);
      const m = backerP(prop, lead);
      setText(chip.top, m === null ? prop.id ?? "" : `${prop.id} · ${fmtP(m)}`);
      show(chip.alt, !!prop.alt);
      chip.label.setAttribute("fill", habitOnly ? COLORS.muted : COLORS.text);
      const titles = backers.map((b) => instruction(view, `motor_${b}`));
      setTitle(chip.g, titles.join("\n\n"));
      chip.label2.setAttribute("fill", habitOnly ? COLORS.muted : COLORS.text);
      show(chip.g, true); // before measuring: a hidden <text> measures as 0
      fitTwoLines(chip.label, chip.label2, prop.label ?? "", CHIP_W - 14);
      used.add(k);
      for (const b of backers) {
        if (!el.mlines[b]) continue;
        const a = b === "default" ? null : activationOf(view, b);
        setMotorLine(b, k, a, false);
      }
    });
  } else if (intent && (view.phase === "motor" || view.phase === "arbitrate")) {
    // R2 in flight: an empty chip per fired neuron plus one for the habit, so the request
    // flow has somewhere to go; nothing on them pretends to be an answer.
    const order = [...(Array.isArray(intent.fired) ? intent.fired : []), "default"].slice(0, MAX_CHIPS);
    order.forEach((n, k) => {
      const chip = el.chips[k];
      chip.box.setAttribute("stroke", hueOf(n));
      chip.box.setAttribute("stroke-dasharray", "3 2");
      chip.swatch.setAttribute("fill", hueOf(n));
      setText(chip.top, "…");
      show(chip.alt, false);
      chip.label.setAttribute("fill", COLORS.muted);
      setText(chip.label, `${labelOf(n)} 제안 대기`);
      setText(chip.label2, "");
      setTitle(chip.g, instruction(view, `motor_${n}`));
      show(chip.g, true);
      used.add(k);
      setMotorLine(n, k, n === "default" ? null : activationOf(view, n), true);
    });
  }
  for (let k = 0; k < MAX_CHIPS; k++) if (!used.has(k)) show(el.chips[k].g, false);
}

function renderBars(view) {
  const props = proposalsOf(view);
  const verdict = view.verdict;
  const showBars = props && props.length && (verdict || view.phase === "arbitrate" || view.phase === "verdict" || view.phase === "moving");
  const hard = new Set(Array.isArray(verdict?.hardVetoed) ? verdict.hardVetoed : []);
  let used = 0;

  if (showBars) {
    props.forEach((prop, k) => {
      const bar = el.bars[k];
      const lead = Array.isArray(prop.backers) && prop.backers.length ? prop.backers[0] : "default";
      const hue = hueOf(lead);
      bar.swatch.setAttribute("fill", hue);
      bar.A.setAttribute("fill", hue);
      const A = verdict ? clamp01(verdict.A?.[prop.id] ?? 0) : 0;
      const V = verdict ? clamp01(verdict.V?.[prop.id] ?? 0) : 0;
      bar.A.setAttribute("width", (BAR_W * A).toFixed(1));
      bar.V.setAttribute("width", (BAR_W * V).toFixed(1));
      bar.V.setAttribute("x", (BAR_X + BAR_W - BAR_W * V).toFixed(1));
      setText(bar.id, prop.id ?? "");
      const p = verdict?.final?.[prop.id];
      setText(bar.pct, verdict ? (verdict.fallback ? "E" : `${Math.round(100 * (isNum(p) ? p : 0))}%`) : "");
      const vetoed = hard.has(prop.id);
      show(bar.vetoBox, vetoed);
      show(bar.vetoText, vetoed);
      const chosen = !!verdict && verdict.chosenId === prop.id;
      show(bar.chosen, chosen);
      show(bar.sel, chosen);
      bar.sel.setAttribute("x", vetoed ? "366" : "336");
      bar.well.setAttribute("stroke", chosen ? COLORS.white : "none");
      bar.well.setAttribute("stroke-width", "1");
      setTitle(bar.g, instruction(view, "arbitrate"));
      setTitle(bar.V, instruction(view, `veto_${prop.id}`));
      show(bar.g, true);
      used++;
    });
  }
  for (let k = used; k < MAX_CHIPS; k++) show(el.bars[k].g, false);
  for (const a of el.arrows) a.setAttribute("opacity", showBars ? "1" : "0.35");

  // HOLD: how strongly this verdict asked the next piece to keep the plan (0..2 → 0..1).
  const holdRaw = isNum(view.hold) ? view.hold : isNum(verdict?.hold) ? verdict.hold : null;
  const holdFrac = holdRaw === null ? 0 : clamp01(holdRaw / 2);
  const holdHue = hueOf(INTENTS.includes(verdict?.ledBy) ? verdict.ledBy : "default");
  renderNode(el.hold, holdFrac, holdHue, holdFrac >= 0.5);
  setText(el.hold.value, holdRaw === null ? "" : holdRaw.toFixed(1));
  setTitle(el.hold.g, instruction(view, "hold"));
  el.rec.classList.toggle("lit", holdFrac >= 0.5);
  el.rec.setAttribute("stroke", holdFrac >= 0.5 ? holdHue : COLORS.dim);
}

// ---------------------------------------------------------------- render: HTML parts

function renderTimeline(view) {
  if (!el.timelineCells.length) return;
  const tl = Array.isArray(view.timeline) ? view.timeline.slice(-TIMELINE_N) : [];
  const offset = TIMELINE_N - tl.length; // newest square always sits at the right edge
  for (let k = 0; k < TIMELINE_N; k++) {
    const cell = el.timelineCells[k];
    const entry = k >= offset ? tl[k - offset] : null;
    if (!entry) {
      cell.className = "empty";
      cell.style.background = "";
      cell.title = "";
      continue;
    }
    const led = entry.ledBy;
    const bg = led === "fallback" ? "#000" : hueOf(led);
    cell.className = (entry.vetoed ? "veto " : "") + (isNum(entry.hold) && entry.hold >= 0.5 ? "hold" : "");
    cell.style.background = bg;
    const parts = [led === "fallback" ? "FALLBACK" : labelOf(led)];
    if (entry.vetoed) parts.push("거부 있음");
    if (isNum(entry.hold) && entry.hold >= 0.5) parts.push("계획 유지");
    cell.title = parts.join(" · ");
  }
}

function composeThought(view) {
  const intent = view.intent;
  const props = proposalsOf(view);
  const verdict = view.verdict;
  const parts = [];
  if (intent) {
    const fired = Array.isArray(intent.fired) ? intent.fired : [];
    const seg = fired.map((i) => `${labelOf(i)} ${fmtP(activationOf(view, i))}`);
    const app = isNum(view.appetite) ? view.appetite : intent.appetite;
    if (isNum(app)) seg.push(`선호 ${app.toFixed(1)}`);
    parts.push(seg.join(" · "));
  }
  if (props && props.length) {
    // One entry per motor neuron in firing order, the habit last: "빌드 c7 .71 / 현금 c1 .55 / 습관 c7 .80".
    const order = [...(Array.isArray(intent?.fired) ? intent.fired : []), "default"];
    const seg = [];
    for (const n of order) {
      const p = props.find((q) => Array.isArray(q.backers) && q.backers.includes(n) && !q.alt) ?? props.find((q) => q.backers?.includes(n));
      if (!p) continue;
      const m = backerP(p, n);
      seg.push(`${labelOf(n)} ${p.id} ${m === null ? "" : fmtP(m)}`.trim());
    }
    parts.push(seg.join(" / "));
  }
  if (verdict && props) {
    if (verdict.fallback) {
      parts.push("R3 실패 → E 최대");
    } else {
      const seg = [];
      if (verdict.arbTop) seg.push(`중재 ${verdict.arbTop} ${fmtP(verdict.A?.[verdict.arbTop])}`);
      const hard = Array.isArray(verdict.hardVetoed) ? verdict.hardVetoed : [];
      if (hard.length) seg.push(hard.map((id) => `거부 ${id} ${fmtP(verdict.V?.[id])}`).join(" · "));
      parts.push(seg.join(" · "));
    }
    if (verdict.chosenId) {
      const p = verdict.final?.[verdict.chosenId];
      parts.push(`${verdict.chosenId} ${isNum(p) ? Math.round(100 * p) + "%" : "선택"}`);
    }
  }
  return parts.filter(Boolean).join(" → ");
}

// The verdict sentence of 6.3, used only when app.js did not supply one.
function composeVerdictLine(view) {
  const verdict = view.verdict;
  const props = proposalsOf(view);
  if (!verdict || !props) return { text: "", hue: null };
  const byId = new Map(props.map((p) => [p.id, p]));
  const leadOf = (id) => {
    const b = byId.get(id)?.backers;
    return Array.isArray(b) && b.length ? b[0] : "default";
  };
  const leading = verdict.leading ?? view.intent?.leading ?? null;
  const ledBy = verdict.ledBy ?? "default";
  if (verdict.fallback) return { text: `FALLBACK · E 최대 ${verdict.chosenId} 선택`, hue: null };
  if (verdict.vetoedTop && verdict.arbTop) {
    return { text: `중재 1위 ${verdict.arbTop} → 코치 거부 → ${verdict.chosenId} 선택`, hue: null };
  }
  if (verdict.override && leading) {
    if (ledBy === "default") return { text: `습관이 이김 (${labelOf(leading)} → 습관)`, hue: null };
    return { text: `중재가 우선순위를 뒤집음 (${labelOf(leading)} → ${labelOf(ledBy)})`, hue: hueOf(ledBy) };
  }
  const hard = Array.isArray(verdict.hardVetoed) ? verdict.hardVetoed : [];
  const top = verdict.arbTop ?? verdict.chosenId;
  const coach = hard.length ? hard.map((id) => `${labelOf(leadOf(id))} ${id} 거부`).join(" · ") : "거부 없음";
  return { text: `중재: ${labelOf(leadOf(top))} ${top} 승 · 코치: ${coach}`, hue: null };
}

function renderTexts(view) {
  const dark = view.phase === "idle" || view.phase === "single";
  if (el.thought) {
    const t = typeof view.thought === "string" ? view.thought : dark ? "" : composeThought(view);
    setText(el.thought, t);
  }
  if (el.verdictLine) {
    const host = el.verdictLine;
    const own = typeof view.verdictLine === "string" ? { text: view.verdictLine, hue: null } : composeVerdictLine(view);
    if (own.hue === null && verdictHue(view)) own.hue = verdictHue(view);
    host.textContent = "";
    host.style.color = own.hue ?? "";
    if (view.fork && !dark) {
      const [h1, h2] = topTwoIntents(view).map(hueOf);
      const tag = document.createElement("span");
      tag.className = "cx-fork";
      tag.textContent = "FORK";
      tag.style.background = `linear-gradient(90deg, ${h1} 0 50%, ${h2} 50% 100%)`;
      host.appendChild(tag);
      host.appendChild(document.createTextNode(" "));
    }
    host.appendChild(document.createTextNode(dark ? "" : own.text));
  }
}

// An override line is painted in the winner's hue (6.3); everything else stays neutral.
function verdictHue(view) {
  const v = view.verdict;
  if (!v || v.fallback || v.vetoedTop || !v.override) return null;
  return INTENTS.includes(v.ledBy) ? hueOf(v.ledBy) : null;
}

// ---------------------------------------------------------------- public API

/**
 * Full re-render from a view object; idempotent, and every field may be null/undefined.
 *   view.phase: idle | sense | motor | arbitrate | verdict | moving | single
 */
export function renderCortex(view) {
  if (!built) initCortex();
  if (!built) return;
  const v = view && typeof view === "object" ? view : {};
  if (v.phase === "idle" && !v.timeline?.length) prevLedMemo = null; // new game
  el.svg.setAttribute("data-phase", v.phase ?? "idle");
  renderBands(v);
  renderRow0(v);
  renderNeurons(v);
  renderChips(v);
  renderBars(v);
  renderTimeline(v);
  renderTexts(v);
}

/** Viewport centre of an intent's circle (survive|clean|build|cash|spin|default), or null. */
export function neuronAnchor(id) {
  const node = id === "default" ? el.habit : el.neurons[id];
  if (!node || !node.body) return null;
  const r = node.body.getBoundingClientRect();
  if (!r.width && !r.height) return null;
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
}

/** Toggle the dashed request-in-flight flow: null | 'sense' | 'motor' | 'arbitrate'. */
export function setInflight(stage) {
  if (!built) initCortex();
  if (!el.svg) return;
  for (const s of ["sense", "motor", "arbitrate"]) {
    el.svg.classList.toggle(`inflight-${s}`, stage === s);
  }
}
