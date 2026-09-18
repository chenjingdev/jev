// Can Jev judge a Tetris stack from the ASCII board alone, with no engine metrics in the prompt?
//
// Plays N pieces with a simple heuristic to reach mid-game boards, then for each board asks Jev
// three ways and compares against the engine's heuristic ranking of the candidates:
//   A) one Choice over all candidates, geometry-only summaries + board_after (the current game)
//   B) one Score question per candidate in one request ("rate this resulting stack"), no metrics
//   C) one Choice over all candidates, summaries that include the engine metrics (the old game)
// Prints Spearman rank correlation with the heuristic and whether the heuristic's best is in
// Jev's top 3, per variant.
//
//   op run --env-file=.env.tpl -- node experiments/judge.mjs [boards=6]

import { choice, score, TypeSafeClient } from "@typesafe-ai/sdk";
import { boardToAscii, candidateSummary, createEmptyBoard, rotationLabel, shuffledBag } from "../public/engine.js";
import { reachablePlacements } from "../public/srs.js";

const N_BOARDS = Number(process.argv[2] ?? 6);
const client = new TypeSafeClient({ defaultModel: "jev-latest", timeout: 20000 });

// Classic Dellacherie-style linear heuristic: the "truth" we compare Jev against.
function heuristic(c) {
  const m = c.metrics;
  return -0.51 * m.aggregateHeight + 0.76 * c.linesCleared - 0.36 * m.holes - 0.18 * m.bumpiness;
}

function geometrySummary(type, c) {
  const rows = c.cells.map((x) => x[0]);
  const cols = c.cells.map((x) => x[1]);
  const span = (v, one, many) => (Math.min(...v) === Math.max(...v) ? `${one} ${v[0]}` : `${many} ${Math.min(...v)}-${Math.max(...v)}`);
  return `${type} piece, rotation ${c.rot} (${rotationLabel(type, c.rot)}); lands at ${span(cols, "column", "columns")}, ${span(rows, "row", "rows")}; ` +
    (c.linesCleared ? `clears ${c.linesCleared} line(s)` : "clears no lines");
}

function spearman(a, b) {
  const rank = (v) => {
    const idx = v.map((x, i) => [x, i]).sort((p, q) => q[0] - p[0]);
    const r = new Array(v.length);
    idx.forEach(([, i], k) => (r[i] = k));
    return r;
  };
  const ra = rank(a);
  const rb = rank(b);
  const n = a.length;
  const d2 = ra.reduce((s, x, i) => s + (x - rb[i]) ** 2, 0);
  return 1 - (6 * d2) / (n * (n * n - 1));
}

const RUBRIC = [
  "Terrible stack: many buried holes, tall and jagged, close to topping out.",
  "Poor stack: several holes or a tall uneven surface that will be hard to clean up.",
  "Okay stack: a hole or two, moderate height, surface mostly usable.",
  "Good stack: no new holes, low and fairly flat, easy to keep clearing lines.",
  "Excellent stack: flat, low, no holes, well set up for the next pieces.",
];

async function judge(board, type, cands) {
  const boardNow = boardToAscii(board);
  const results = {};

  // A: geometry-only choice
  {
    const state = {
      board_now: boardNow, current_piece: type,
      candidates: Object.fromEntries(cands.map((c) => [c.id, { summary: geometrySummary(type, c), board_after: boardToAscii(c.boardAfter) }])),
    };
    const r = await client.systemOne({ state, questions: { pick: choice(
      "Choose the placement a strong Tetris player would make: clear lines, avoid creating holes, keep the stack low and flat. Judge each option by its resulting board in `candidates`.",
      Object.fromEntries(cands.map((c) => [c.id, geometrySummary(type, c)]))) } });
    results.A = { probs: cands.map((c) => r.answers.pick.probabilities[c.id]), conf: r.answers.pick.confidence, tokens: r.usage.input_tokens };
  }
  // B: per-candidate score
  {
    const state = { current_piece: type, candidates: Object.fromEntries(cands.map((c) => [c.id, boardToAscii(c.boardAfter)])) };
    const questions = Object.fromEntries(cands.map((c) => [c.id, score(`Rate the Tetris stack shown in candidates.${c.id} (rows top to bottom, '.' empty). A strong player wants it low, flat and without buried holes.`, RUBRIC)]));
    const r = await client.systemOne({ state, questions });
    results.B = { probs: cands.map((c) => r.answers[c.id].score), conf: null, tokens: r.usage.input_tokens };
  }
  // C: metric summaries (old game)
  {
    const state = {
      board_now: boardNow, current_piece: type,
      candidates: Object.fromEntries(cands.map((c) => [c.id, { summary: candidateSummary(type, c, board), board_after: boardToAscii(c.boardAfter) }])),
    };
    const r = await client.systemOne({ state, questions: { pick: choice(
      "Choose the placement a strong Tetris player would make: clear lines, avoid creating holes, keep the stack low and flat.",
      Object.fromEntries(cands.map((c) => [c.id, candidateSummary(type, c, board)]))) } });
    results.C = { probs: cands.map((c) => r.answers.pick.probabilities[c.id]), conf: r.answers.pick.confidence, tokens: r.usage.input_tokens };
  }
  return results;
}

// Reach mid-game boards by playing the heuristic with some noise.
let board = createEmptyBoard();
let queue = shuffledBag();
const agg = { A: [], B: [], C: [] };
let boardsJudged = 0;
for (let piece = 0; boardsJudged < N_BOARDS && piece < 200; piece++) {
  if (queue.length < 2) queue.push(...shuffledBag());
  const type = queue.shift();
  const cands = reachablePlacements(board, type);
  if (!cands.length) { board = createEmptyBoard(); continue; }
  const h = cands.map(heuristic);
  if (piece >= 6 && piece % 3 === 0 && cands.length >= 8) {
    const res = await judge(board, type, cands);
    const best = h.indexOf(Math.max(...h));
    for (const k of ["A", "B", "C"]) {
      const p = res[k].probs;
      const top3 = p.map((x, i) => [x, i]).sort((a, b) => b[0] - a[0]).slice(0, 3).map((x) => x[1]);
      const rho = spearman(p, h);
      agg[k].push({ rho, hit: top3.includes(best), conf: res[k].conf, tokens: res[k].tokens });
      console.log(`board ${boardsJudged} piece ${type} cands ${cands.length} ${k}: rho=${rho.toFixed(2)} bestInTop3=${top3.includes(best)} conf=${res[k].conf?.toFixed(2) ?? "-"} tokens=${res[k].tokens}`);
    }
    boardsJudged++;
  }
  // play on: heuristic best, occasionally a random move to make messy boards
  const pick = Math.random() < 0.25 ? cands[Math.floor(Math.random() * cands.length)] : cands[h.indexOf(Math.max(...h))];
  board = pick.boardAfter;
}

console.log("\nvariant  mean rho  best-in-top3  mean conf  mean tokens");
for (const k of ["A", "B", "C"]) {
  const v = agg[k];
  const mean = (f) => v.reduce((s, x) => s + f(x), 0) / v.length;
  console.log(`${k}        ${mean((x) => x.rho).toFixed(2)}      ${(mean((x) => (x.hit ? 1 : 0)) * 100).toFixed(0)}%          ${v[0].conf == null ? "-" : mean((x) => x.conf).toFixed(2)}       ${mean((x) => x.tokens).toFixed(0)}`);
}
