// neurons.js — pure functions of the Jev Neurons pipeline (docs/neurons-spec.md, section 4).
// Percepts the engine computes (facts, candidate summaries, effects), the gate that turns R1
// answers into an intent, the proposal set built from R2 answers, the final distribution built
// from R3 answers, and the ghost list the canvas draws. No DOM, no fetch, no module state:
// the browser (app.js) and the Node tests import this file unchanged.
//
// Naming: everything crossing into an API body (5절) is camelCase; the snake_case in the spec's
// pseudocode is notation, and the server does the camel→snake mapping.

import { COLS, ROWS, computeMetrics, rotationLabel } from "./engine.js";
import { reachablePlacements } from "./srs.js";

// ---------------------------------------------------------------- frozen palette and labels

/** Intent order: the tie-break and sort order everywhere. */
export const INTENTS = Object.freeze(["survive", "clean", "build", "cash", "spin"]);
/** Same list under the name the API contract uses (copied, never shared, per 5절). */
export const KNOWN_INTENTS = INTENTS;

export const HUES = Object.freeze({
  survive: "#ff4d6d",
  clean: "#2ee6d6",
  build: "#7c8cff",
  cash: "#ffd166",
  spin: "#f472b6",
  default: "#9aa3b8", // the habit neuron: grey, never an intent
  veto: "#f87171", // red ring, hatch and VETO pill (same as --warn)
  forced: "#fb923c", // orange: brainstem forcing is an engine rule, not a Jev answer
});

export const LABELS_KO = Object.freeze({
  survive: "생존",
  clean: "정리",
  build: "빌드",
  cash: "현금",
  spin: "스핀",
  default: "습관",
  veto: "거부",
  forced: "강제",
});

// ---------------------------------------------------------------- Appendix B constants (frozen)

export const FIRE_P = 0.5;
export const MAX_FIRED = 3;
export const BRAINSTEM_HEIGHT = 14;
export const HARD_VETO = 0.65;
export const W_DEFAULT = 0.5;
export const FORK_GAP = 0.15;
export const NEARLY_FULL = 8;
export const GHOST_MS = 450;
export const WIRE_HOLD_MS = 350;
export const COUNTUP_MS = 200;
export const FADE_MS = 220;
export const MAX_GHOST_ALPHA = 0.55;
export const MIN_GHOST_ALPHA = 0.14;
export const GHOST_LABEL_MIN_P = 0.03;
export const THINKING_ALPHA = 0.18;
/** Motor-field ghost alphas for the 2nd and 3rd pick of a fired neuron, while R3 is in flight. */
export const FIELD_ALPHA = Object.freeze([0.22, 0.12]);
/** Motor-field ghost alpha once the verdict is on screen. */
export const FIELD_ALPHA_AFTER = 0.06;
export const RING_INSET_PX = Object.freeze([3, 6, 9]);
/** Alpha of a hard-vetoed ghost (4.5). */
export const VETO_GHOST_ALPHA = 0.1;

// ---------------------------------------------------------------- small helpers

const round1 = (v) => Math.round(v * 10) / 10;
const round2 = (v) => Math.round(v * 100) / 100;
const num = (v, fallback = 0) => (typeof v === "number" && Number.isFinite(v) ? v : fallback);
const intentRank = (i) => (INTENTS.includes(i) ? INTENTS.indexOf(i) : INTENTS.length);

// Sort intents by activation descending, ties in INTENTS order.
function byActivationDesc(a) {
  return (x, y) => a[y] - a[x] || intentRank(x) - intentRank(y);
}

function span(values, one, many) {
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  return lo === hi ? `${one} ${lo}` : `${many} ${lo}-${hi}`;
}

function clearsClause(cand) {
  const n = cand.linesCleared;
  return n === 0 ? "clears no lines" : `clears ${n} line${n === 1 ? "" : "s"}`;
}

function tspinClause(cand) {
  if (!cand.tspin) return null;
  return cand.tspin === "full" ? "placed with a T-spin" : "placed with a mini T-spin";
}

// ---------------------------------------------------------------- 4.1 percepts (engine)

/**
 * The engine's measurement of a board, in exactly the 7 keys of the 5.1 request body.
 *   board: 20x10 array of 0 | piece letter; piecesSinceClear: number kept by the game state.
 * Returns {maxHeight, holes, bumpiness, wellColumn, wellDepth, rowsNearlyFull, piecesSinceClear};
 * wellColumn is null when the deepest well is shallower than 2.
 */
export function facts(board, piecesSinceClear = 0) {
  const m = computeMetrics(board);
  let rowsNearlyFull = 0;
  for (let r = 0; r < ROWS; r++) {
    let filled = 0;
    for (let c = 0; c < COLS; c++) if (board[r][c] !== 0) filled++;
    if (filled >= NEARLY_FULL) rowsNearlyFull++;
  }
  return {
    maxHeight: m.maxHeight,
    holes: m.holes,
    bumpiness: m.bumpiness,
    wellColumn: m.wellDepth >= 2 ? m.wellCol : null,
    wellDepth: m.wellDepth,
    rowsNearlyFull,
    piecesSinceClear: num(piecesSinceClear),
  };
}

/** Depth of column c relative to its lower neighbour; the board edge counts as infinitely tall. */
export function depthAt(heights, c) {
  const left = c === 0 ? Infinity : heights[c - 1];
  const right = c === COLS - 1 ? Infinity : heights[c + 1];
  return Math.min(left, right) - heights[c];
}

/**
 * What a placement does to the deepest well of the board before it.
 *   before: computeMetrics(boardBefore) or facts(boardBefore) (both shapes accepted);
 *   cand: a candidate from reachablePlacements (needs cand.metrics.heights).
 * "" when there was no well (depth < 2) to keep or fill.
 */
export function wellPhrase(before, cand) {
  if (num(before.wellDepth) < 2) return "";
  const w = before.wellColumn ?? before.wellCol;
  if (w === null || w === undefined || w < 0) return "";
  const depth = depthAt(cand.metrics.heights, w);
  return depth >= 2 ? `; keeps the well at column ${w} open (depth ${depth})` : `; fills the well at column ${w}`;
}

/** Whether a T could lock as a full T-spin that clears at least one line on this board. */
export function hasTSlot(boardAfter) {
  return reachablePlacements(boardAfter, "T").some((c) => c.tspin === "full" && c.linesCleared >= 1);
}

// The first part of the summary is the string app.js sent as `placementSummary` before neurons
// existed; measured in experiments/judge.mjs, the numbers are what let Jev track a heuristic
// at all (rho 0.41 vs ≈ 0 without them). They stay, and the V2 clauses are appended after.
function placementSummary(type, cand, before) {
  const after = cand.metrics;
  const delta = (a, b) => (a === b ? "" : a > b ? ` (+${a - b})` : ` (${a - b})`);
  const rows = cand.cells.map((c) => c[0]);
  const cols = cand.cells.map((c) => c[1]);
  const parts = [
    `${type} piece, rotation ${cand.rot} (${rotationLabel(type, cand.rot)})`,
    `lands at ${span(cols, "column", "columns")}, ${span(rows, "row", "rows")}`,
  ];
  const ts = tspinClause(cand);
  if (ts) parts.push(ts);
  parts.push(clearsClause(cand));
  parts.push(
    `after: max height ${after.maxHeight}${delta(after.maxHeight, before.maxHeight)}, holes ${after.holes}${delta(after.holes, before.holes)}, ` +
      `bumpiness ${after.bumpiness}, aggregate height ${after.aggregateHeight}`,
  );
  return parts.join("; ");
}

/**
 * The option description every motor neuron reads for a candidate (R2 criteria).
 *   type: piece letter; cand: reachablePlacements entry; boardBefore: the board it lands on.
 */
export function candidateSummaryV2(type, cand, boardBefore) {
  const before = computeMetrics(boardBefore);
  const top = Math.min(...cand.cells.map((c) => c[0]));
  return (
    placementSummary(type, cand, before) +
    wellPhrase(before, cand) +
    `; leaves a T-spin slot: ${hasTSlot(cand.boardAfter) ? "yes" : "no"}` +
    `; top of piece ${top} rows below the ceiling`
  );
}

/**
 * The qualitative description of a proposal the arbiter and the coach read (R3). No numeric
 * metrics: the arbiter must not be able to compute "lowest stack" from it (Appendix A-10).
 * Same arguments as candidateSummaryV2.
 */
export function effects(type, cand, boardBefore) {
  const before = computeMetrics(boardBefore);
  const after = cand.metrics;
  const rows = cand.cells.map((c) => c[0]);
  const cols = cand.cells.map((c) => c[1]);
  const parts = [
    `${type} piece, rotation ${cand.rot} (${rotationLabel(type, cand.rot)})`,
    `lands at ${span(cols, "column", "columns")}, ${span(rows, "row", "rows")}`,
  ];
  const ts = tspinClause(cand);
  if (ts) parts.push(ts);
  parts.push(clearsClause(cand));

  if (before.wellDepth < 2) parts.push("no well");
  else parts.push(depthAt(after.heights, before.wellCol) >= 2 ? "keeps the well open" : "fills the well");

  const dh = after.holes - before.holes;
  if (dh === 1) parts.push("adds a hole");
  else if (dh > 1) parts.push(`adds ${dh} holes`);
  else if (dh < 0) parts.push("uncovers a hole");
  else parts.push("no new hole");

  const dp = after.maxHeight - before.maxHeight;
  parts.push(dp > 0 ? "peak higher" : dp < 0 ? "peak lower" : "peak unchanged");

  parts.push(hasTSlot(cand.boardAfter) ? "leaves a T-spin slot" : "no T-spin slot");
  return parts.join("; ");
}

/** none | low | moderate | bold for an appetite score in 0..3. */
export function appetiteWord(a) {
  if (a < 0.5) return "none";
  if (a < 1.5) return "low";
  if (a < 2.5) return "moderate";
  return "bold";
}

// ---------------------------------------------------------------- 4.2 gate: R1 answers → intent

/**
 * Turn the sense answers into the intent object of the 5.2 request body.
 *   sense:    {survive, clean, build, cash, spin, stay} — noul probabilities, stay null or absent
 *             when the server skipped the question.
 *   appetite: the score's expected value (number), or the whole {value, ...} answer object.
 *   facts:    the object from facts() (reads maxHeight).
 *   memory:   {previousIntent: intent|null, hold: 0..1} carried over from the previous piece.
 * Returns {leading, activations, appetite, appetiteWord, fired, forced, stayed} — exactly the
 * keys the server validates, so app.js can put it in the R2 body as is.
 */
export function gate(sense, appetite, facts, memory) {
  const mem = memory ?? {};
  const prev = mem.previousIntent ?? mem.previous_intent ?? null;
  const hold = num(mem.hold);
  const stay = typeof sense?.stay === "number" ? sense.stay : null;

  const a = {};
  for (const i of INTENTS) a[i] = round2(num(sense?.[i]));

  // The recursion link: a plan the last verdict asked to hold re-enters through `stay`, at most
  // as strongly as the hold that asked for it.
  let stayed = false;
  if (prev !== null && INTENTS.includes(prev) && hold > 0 && stay !== null && stay >= FIRE_P) {
    a[prev] = round2(Math.max(a[prev], stay * hold));
    stayed = true;
  }

  const top = Math.max(...INTENTS.map((i) => a[i]));
  const tied = INTENTS.filter((i) => a[i] === top);
  const leading = prev !== null && tied.includes(prev) ? prev : tied[0];

  const firedSet = new Set(INTENTS.filter((i) => a[i] >= FIRE_P));
  firedSet.add(leading);
  if (stayed) firedSet.add(prev);

  const maxHeight = num(facts?.maxHeight ?? facts?.max_height);
  const forced = maxHeight >= BRAINSTEM_HEIGHT && !firedSet.has("survive");
  if (forced) firedSet.add("survive");

  const fired = [...firedSet].sort(byActivationDesc(a));
  // Trim the weakest, but never the leader nor a survive the brainstem forced in.
  while (fired.length > MAX_FIRED) {
    let victim = -1;
    for (let k = fired.length - 1; k >= 0; k--) {
      const i = fired[k];
      if (i === leading || (forced && i === "survive")) continue;
      victim = k;
      break;
    }
    if (victim < 0) break;
    fired.splice(victim, 1);
  }

  // A missing appetite (the question deleted by gate (c)/(d)) reads as a neutral temperament
  // rather than "dead safe", so the motor texts do not all collapse to refusing everything.
  const rawAppetite = typeof appetite === "number" ? appetite : appetite?.value;
  const app = round1(num(rawAppetite, 1.5));

  return {
    leading,
    activations: a,
    appetite: app,
    appetiteWord: appetiteWord(app),
    fired,
    forced,
    stayed,
  };
}

// ---------------------------------------------------------------- 4.3 proposalsFrom: R2 answers → Π

// Probabilities restricted to the ids we actually enumerated; unknown ids are ignored, missing
// known ids are 0. Argmax ties go to the lowest candidate index (array position, not id string).
function knownProbabilities(answer, candidates) {
  const probs = answer?.probabilities ?? {};
  const P = {};
  for (const c of candidates) P[c.id] = num(probs[c.id]);
  return P;
}

function argmaxOver(P, candidates, exclude = new Set()) {
  let best = null;
  for (const c of candidates) {
    if (exclude.has(c.id)) continue;
    if (best === null || P[c.id] > P[best]) best = c.id;
  }
  return best;
}

/**
 * Build the proposal set from the motor answers.
 *   motor:      {survive|clean|build|cash|spin|default: {choice, confidence, probabilities}},
 *               keyed WITHOUT the motor_ prefix (5.2 response `motor`); a fired intent with no
 *               entry is skipped.
 *   intent:     the object gate() returned.
 *   candidates: the array from reachablePlacements (ids, cells, metrics, ...).
 * Returns an object, not a bare array — combine(), fallbackCombine() and ghostsFrom() need all
 * of it:
 *   proposals:    [{id, cand, backers, alt, E, m: {backer: P_backer(id)}}] in first-backer order
 *                 (fired by activation desc, then default, then ALT)
 *   picks:        {neuron: candidateId} — each motor neuron's argmax (π_i), default included
 *   P:            {neuron: {candidateId: p}} — each neuron's distribution over known ids
 *   confidence:   {neuron: m_i} — P_i(π_i)
 *   disagreement: the fired neurons' argmaxes are not all the same
 *   fork:         top two activations within FORK_GAP and their argmaxes differ
 *   motorField:   [{neuron, id, cand, p, rank}] — a fired neuron's 2nd/3rd pick outside Π
 *   leading, fired, activations: copied from intent for the later stages
 */
export function proposalsFrom(motor, intent, candidates) {
  const fired = (intent?.fired ?? []).filter((i) => INTENTS.includes(i));
  const a = intent?.activations ?? {};
  const leading = intent?.leading ?? fired[0] ?? null;
  const byId = new Map(candidates.map((c) => [c.id, c]));

  const neurons = [...fired.slice().sort(byActivationDesc(a)), "default"];
  const P = {};
  const picks = {};
  const confidence = {};
  for (const n of neurons) {
    const answer = motor?.[n];
    if (!answer) continue;
    P[n] = knownProbabilities(answer, candidates);
    let pick = argmaxOver(P[n], candidates);
    // Defensive: a flat/empty distribution but a known `choice` still names a pick.
    if (pick !== null && P[n][pick] === 0 && byId.has(answer.choice)) pick = answer.choice;
    if (pick === null) continue;
    picks[n] = pick;
    confidence[n] = P[n][pick];
  }

  const proposals = [];
  const proposalById = new Map();
  for (const n of neurons) {
    const pick = picks[n];
    if (pick === undefined) continue;
    let prop = proposalById.get(pick);
    if (!prop) {
      prop = { id: pick, cand: byId.get(pick), backers: [], alt: false, E: 0, m: {} };
      proposalById.set(pick, prop);
      proposals.push(prop);
    }
    prop.backers.push(n);
    prop.m[n] = P[n][pick];
  }

  // The arbiter needs something to choose between: when every neuron agrees, the leader's
  // second thought joins, backed by the leader so that its win never counts as an override.
  if (proposals.length < 2 && leading !== null && P[leading]) {
    const alt = argmaxOver(P[leading], candidates, new Set(proposalById.keys()));
    if (alt !== null) {
      const prop = { id: alt, cand: byId.get(alt), backers: [leading], alt: true, E: 0, m: { [leading]: P[leading][alt] } };
      proposalById.set(alt, prop);
      proposals.push(prop);
    }
  }

  const weight = (n) => (n === "default" ? W_DEFAULT : num(a[n]));
  for (const prop of proposals) {
    prop.E = prop.backers.reduce((sum, n) => sum + weight(n) * num(prop.m[n]), 0);
  }

  const firedPicks = new Set(fired.filter((i) => picks[i] !== undefined).map((i) => picks[i]));
  const disagreement = firedPicks.size > 1;

  const ranked = fired.slice().sort(byActivationDesc(a));
  const fork =
    ranked.length >= 2 &&
    picks[ranked[0]] !== undefined &&
    picks[ranked[1]] !== undefined &&
    num(a[ranked[0]]) - num(a[ranked[1]]) < FORK_GAP &&
    picks[ranked[0]] !== picks[ranked[1]];

  const motorField = [];
  for (const n of ranked) {
    if (!P[n]) continue;
    const order = candidates
      .map((c, index) => ({ id: c.id, p: P[n][c.id], index }))
      .sort((x, y) => y.p - x.p || x.index - y.index);
    for (let rank = 2; rank <= 3 && rank - 1 < order.length; rank++) {
      const entry = order[rank - 1];
      if (entry.p <= 0 || proposalById.has(entry.id)) continue;
      motorField.push({ neuron: n, id: entry.id, cand: byId.get(entry.id), p: entry.p, rank });
    }
  }

  return { proposals, picks, P, confidence, disagreement, fork, motorField, leading, fired, activations: a };
}

/**
 * The `proposals` array of the 5.3 request body, built from a proposalsFrom() result and the
 * effects strings: effectsById is {candidateId: effects(...)} (or a Map).
 */
export function arbitrateProposals(result, effectsById) {
  const lookup = effectsById instanceof Map ? (id) => effectsById.get(id) : (id) => effectsById?.[id];
  return result.proposals.map((p) => ({ id: p.id, backedBy: p.backers.slice(), alt: p.alt, effects: lookup(p.id) ?? "" }));
}

// ---------------------------------------------------------------- 4.4 combine: R3 answers → verdict

const candIndexOf = (cand, candidates) => {
  const k = candidates ? candidates.indexOf(cand) : -1;
  return k < 0 ? Number.MAX_SAFE_INTEGER : k;
};

// The tie chain of 4.4: larger E, then lower max height after, then lower candidate index.
function tieBreak(candidates) {
  return (x, y) =>
    y.E - x.E ||
    num(x.cand?.metrics?.maxHeight, Infinity) - num(y.cand?.metrics?.maxHeight, Infinity) ||
    candIndexOf(x.cand, candidates) - candIndexOf(y.cand, candidates);
}

function pickBest(proposals, scoreOf, candidates) {
  const tie = tieBreak(candidates);
  let best = null;
  for (const p of proposals) {
    if (best === null) best = p;
    else {
      const d = scoreOf(p) - scoreOf(best);
      if (d > 0 || (d === 0 && tie(p, best) < 0)) best = p;
    }
  }
  return best;
}

function normalise(values, ids) {
  const sum = ids.reduce((s, id) => s + values[id], 0);
  const out = {};
  for (const id of ids) out[id] = sum > 0 ? values[id] / sum : 1 / ids.length;
  return out;
}

// ledBy: the strongest fired backer of the chosen proposal, else the habit. ALT proposals are
// backed by the leader alone, so the rule yields the leader for them without a special case.
function ledByOf(prop, fired, a) {
  const firedBackers = prop.backers.filter((n) => fired.includes(n)).sort(byActivationDesc(a));
  return firedBackers[0] ?? "default";
}

/**
 * Fold the verdict answers into the final distribution and the chosen placement.
 *   arb:        {choice, confidence, probabilities: {proposalId: p}} — the arbitrate answer
 *   veto:       {proposalId: p} — the coach's noul per proposal (a {value} object is accepted too)
 *   hold:       {value, ...} score answer, or a number 0..2, or null
 *   proposals:  the object returned by proposalsFrom()
 *   intent:     the object gate() returned
 *   candidates: the array from reachablePlacements (only for the index tie-break)
 * Returns {final, chosen, chosenId, ledBy, override, changed, fork, vetoedTop, hardVetoed,
 *          allVetoed, memoryNext, proposals, disagreement, motorField, A, V, raw, arbTop,
 *          hold, leading, fired, fallback: false}. `final` is {proposalId: p} summing to 1;
 * candidates outside Π are simply absent (read as 0).
 */
export function combine(arb, veto, hold, proposals, intent, candidates) {
  const props = proposals.proposals;
  const ids = props.map((p) => p.id);
  const fired = intent?.fired ?? proposals.fired ?? [];
  const a = intent?.activations ?? proposals.activations ?? {};
  const leading = intent?.leading ?? proposals.leading ?? null;

  const A = {};
  const V = {};
  const raw = {};
  for (const id of ids) {
    A[id] = num(arb?.probabilities?.[id]);
    const v = veto?.[id];
    V[id] = num(typeof v === "number" ? v : v?.value ?? v?.p);
    raw[id] = A[id] * (1 - V[id]);
  }

  // The veto is the only path to a zero: the arbiter never sees it, the coach never sees the
  // arbiter, so the product is where the two meet.
  const hardVetoed = ids.filter((id) => V[id] >= HARD_VETO);
  const hardSet = new Set(hardVetoed);
  let final = {};
  for (const id of ids) final[id] = hardSet.has(id) ? 0 : raw[id];
  let allVetoed = false;
  if (ids.every((id) => final[id] === 0)) {
    // The coach stopped every move: sigh, and play the least-vetoed one.
    final = { ...raw };
    allVetoed = true;
  }
  final = normalise(final, ids); // still all zero (A all zero) → uniform

  const chosen = pickBest(props, (p) => final[p.id], candidates);
  const arbTop = pickBest(props, (p) => A[p.id], candidates);
  const ledBy = ledByOf(chosen, fired, a);
  const defaultPick = proposals.picks?.default ?? props.find((p) => p.backers.includes("default"))?.id ?? null;
  const holdValue = num(typeof hold === "number" ? hold : hold?.value);

  return {
    final,
    chosen: chosen.cand,
    chosenId: chosen.id,
    ledBy,
    override: leading !== null && !chosen.backers.includes(leading),
    changed: defaultPick !== null && chosen.id !== defaultPick,
    fork: proposals.fork,
    vetoedTop: arbTop !== null && hardSet.has(arbTop.id),
    hardVetoed,
    allVetoed,
    memoryNext: { previousIntent: INTENTS.includes(ledBy) ? ledBy : null, hold: holdValue / 2 },
    proposals: props,
    disagreement: proposals.disagreement,
    motorField: proposals.motorField,
    A,
    V,
    raw,
    arbTop: arbTop?.id ?? null,
    hold: holdValue,
    leading,
    fired,
    fallback: false,
  };
}

/**
 * The R3-failed path (5.4): no arbiter, no coach. The proposal with the largest E wins,
 * `final` is E normalised, nothing carries over to the next piece. Same shape as combine()
 * so ghostsFrom() and the panel code read it unchanged; `ledBy` is "fallback".
 *   proposals: the object returned by proposalsFrom(); candidates optional (index tie-break).
 */
export function fallbackCombine(proposals, candidates) {
  const props = proposals.proposals;
  const ids = props.map((p) => p.id);
  const E = {};
  for (const p of props) E[p.id] = num(p.E);
  const final = normalise(E, ids);
  const chosen = pickBest(props, (p) => E[p.id], candidates);
  const defaultPick = proposals.picks?.default ?? props.find((p) => p.backers.includes("default"))?.id ?? null;
  const zero = Object.fromEntries(ids.map((id) => [id, 0]));
  return {
    final,
    chosen: chosen.cand,
    chosenId: chosen.id,
    ledBy: "fallback",
    override: false,
    changed: defaultPick !== null && chosen.id !== defaultPick,
    fork: proposals.fork,
    vetoedTop: false,
    hardVetoed: [],
    allVetoed: false,
    memoryNext: { previousIntent: null, hold: 0 },
    proposals: props,
    disagreement: proposals.disagreement,
    motorField: proposals.motorField,
    A: { ...zero },
    V: { ...zero },
    raw: { ...E },
    arbTop: null,
    hold: 0,
    leading: proposals.leading ?? null,
    fired: proposals.fired ?? [],
    fallback: true,
  };
}

// ---------------------------------------------------------------- 4.5 ghosts

/**
 * The ghost list the canvas draws after the verdict (or after the fallback).
 *   result: the object from combine() or fallbackCombine().
 *   fieldAlpha: alpha for the motor-field ghosts; FIELD_ALPHA_AFTER (0.06) once the verdict is
 *               in, or FIELD_ALPHA ([0.22, 0.12] by rank) while it is still in flight.
 * Each entry: {id, cells, p, alpha, color, tag, rings, vetoed, chosen, faint, dashed, label,
 *              alt, backers}. Proposals come first in proposal order, then the faint field
 * ghosts (no label, no pill, no rings). The label is always the returned probability: it reads
 * "0%" for a hard-vetoed ghost except in the allVetoed case, where the raw values are what is
 * actually played and the vetoed flag alone marks the coach's objection.
 */
export function ghostsFrom(result, fieldAlpha = FIELD_ALPHA_AFTER) {
  const final = result.final ?? {};
  const hardSet = new Set(result.hardVetoed ?? []);
  const maxP = Math.max(0, ...result.proposals.map((p) => num(final[p.id])));
  const ghosts = [];

  for (const prop of result.proposals) {
    const p = num(final[prop.id]);
    const vetoed = hardSet.has(prop.id);
    const chosen = prop.id === result.chosenId;
    const scaled = MAX_GHOST_ALPHA * (maxP > 0 ? p / maxP : 0);
    let alpha = p >= GHOST_LABEL_MIN_P ? Math.max(MIN_GHOST_ALPHA, scaled) : scaled;
    if (vetoed) alpha = VETO_GHOST_ALPHA;

    const lead = prop.alt ? result.leading ?? prop.backers[0] : prop.backers[0];
    let tag = vetoed ? "VETO" : prop.backers.map((n) => LABELS_KO[n] ?? n).join("·");
    if (result.fallback) tag = "FALLBACK";
    if (chosen) tag += " · 선택";

    ghosts.push({
      id: prop.id,
      cells: prop.cand?.cells ?? [],
      p,
      alpha,
      color: HUES[lead] ?? HUES.default,
      tag,
      rings: vetoed ? [] : prop.backers.map((n) => HUES[n] ?? HUES.default),
      vetoed,
      chosen,
      faint: false,
      dashed: !!prop.alt,
      label: result.fallback ? null : Math.round(100 * p) + "%",
      alt: !!prop.alt,
      backers: prop.backers.slice(),
    });
  }

  for (const f of result.motorField ?? []) {
    const alpha = Array.isArray(fieldAlpha) ? fieldAlpha[Math.min(f.rank - 2, fieldAlpha.length - 1)] : fieldAlpha;
    ghosts.push({
      id: f.id,
      cells: f.cand?.cells ?? [],
      p: f.p,
      alpha: num(alpha, FIELD_ALPHA_AFTER),
      color: HUES[f.neuron] ?? HUES.default,
      tag: null,
      rings: [],
      vetoed: false,
      chosen: false,
      faint: true,
      dashed: false,
      label: null,
      alt: false,
      backers: [f.neuron],
    });
  }

  return ghosts;
}
