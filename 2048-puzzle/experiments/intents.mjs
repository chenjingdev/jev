// Does Jev add anything when it sets the *temperament* instead of picking the slide?
//
// Three intent neurons, each a Noul on the current grid: merge (cash in merges now), corner (protect
// the largest tile's corner and the order toward it), room (free cells before anything else). The
// engine then scores every legal slide as  Σ intent_weight × criterion(slide)  and plays the best.
// Jev never sees the candidates; it only says how urgent each intent is. Compared against the same
// engine with fixed or random weights, so the difference is exactly what Jev's judgement adds.
//
//   jev      weights = Jev's three noul values
//   equal    weights = 1, 1, 1 (no Jev)
//   random   weights drawn at random each move (no Jev)
//   merge / corner / room   a single intent alone (weights 1, 0, 0 etc.)
//
//   op run --env-file=.env.tpl -- node experiments/intents.mjs [games=5] [variants=jev,equal,random,merge,corner,room]
//   writes experiments/intents.json

import { readFileSync, writeFileSync } from "node:fs";
import { TypeSafeClient, noul } from "@typesafe-ai/sdk";
import { boardRows, candidates, facts, isGameOver, makeRng, maxTile, move, newGame, spawn } from "../public/engine.js";
import { SCENE } from "../questions.js";

const GAMES = Number(process.argv[2] ?? 5);
const VARIANTS = (process.argv[3] ?? "jev,equal,random,merge,corner,room").split(",");
const MAX_MOVES = 3000;
const USD_PER_TOKEN = 42 / 1e9;
let client;
const jev = () => (client ??= new TypeSafeClient({ defaultModel: "jev-latest", timeout: 20000, retry: { maxRetries: 2 } }));

export const INTENTS = {
  merge: {
    text:
      SCENE +
      "You are the MERGE neuron of this player. Is this the moment to cash in: take the merges that are on offer now, even if it costs some order in the grid? Weigh how crowded the grid is, how many equal neighbours `facts.pairs` reports, and whether waiting would set up something bigger.",
    labels: { true: "Yes: merge now.", false: "No: merging can wait." },
  },
  corner: {
    text:
      SCENE +
      "You are the CORNER neuron of this player. Should this slide serve structure above everything else: keep the largest tile in its corner and the tiles leading to it ordered from large to small, even if it merges nothing? Weigh whether the largest tile is already in a corner (`facts.maxCorner`), how many lines are ordered (`facts.monotone` of 8), and how much a scattered grid would cost later.",
    labels: { true: "Yes: protect the corner and the order.", false: "No: structure is fine, play for something else." },
  },
  room: {
    text:
      SCENE +
      "You are the ROOM neuron of this player. Is the grid crowded enough that freeing cells matters more than anything else right now? Weigh `facts.empty`, how many merges are still available, and whether the next random tile could leave no move.",
    labels: { true: "Yes: make room first.", false: "No: there is room to spare." },
  },
};

// criteria in 0..1 for one candidate, relative to the board it came from
function criteria(before, cand, all) {
  const fa = facts(cand.result.board);
  const maxMerges = Math.max(1, ...all.map((c) => c.result.merged.length));
  return {
    merge: cand.result.merged.length / maxMerges,
    corner: ((fa.maxCorner ? 1 : 0) + fa.monotone / 8) / 2,
    room: fa.empty / 16,
  };
}

async function weightsFromJev(board, score) {
  const state = { board: boardRows(board), score, facts: facts(board) };
  const questions = {};
  for (const [k, v] of Object.entries(INTENTS)) questions[k] = noul(v.text, v.labels);
  const t0 = Date.now();
  const r = await jev().systemOne({ state, questions });
  const w = {};
  for (const k of Object.keys(INTENTS)) w[k] = r.answers[k].noul;
  return { w, usage: r.usage, latency: Date.now() - t0 };
}

async function play(variant, seed) {
  const rand = makeRng(seed);
  const wrand = makeRng(seed * 7 + 1);
  let board = newGame(rand);
  let score = 0;
  let moves = 0;
  let tokens = 0;
  let latency = 0;
  let calls = 0;
  const fired = { merge: 0, corner: 0, room: 0 };
  const lead = { merge: 0, corner: 0, room: 0 }; // which intent had the top weight
  while (!isGameOver(board) && moves < MAX_MOVES) {
    const cands = candidates(board);
    let w;
    if (variant === "jev") {
      const a = await weightsFromJev(board, score);
      w = a.w;
      tokens += a.usage.input_tokens + a.usage.output_tokens;
      latency += a.latency;
      calls++;
      for (const k in w) if (w[k] >= 0.5) fired[k]++;
      lead[Object.keys(w).sort((x, y) => w[y] - w[x])[0]]++;
    } else if (variant === "equal") w = { merge: 1, corner: 1, room: 1 };
    else if (variant === "random") w = { merge: wrand(), corner: wrand(), room: wrand() };
    else w = { merge: 0, corner: 0, room: 0, [variant]: 1 };
    let best = null;
    let bestScore = -Infinity;
    for (const c of cands) {
      const cr = criteria(board, c, cands);
      const s = w.merge * cr.merge + w.corner * cr.corner + w.room * cr.room;
      if (s > bestScore) {
        bestScore = s;
        best = c;
      }
    }
    const r = move(board, best.dir);
    score += r.gained;
    board = spawn(r.board, rand).board;
    moves++;
  }
  return { variant, seed, max: maxTile(board), moves, score, tokens, calls, latencyAvg: calls ? Math.round(latency / calls) : 0, fired, lead };
}

const runs = [];
for (const v of VARIANTS) for (let g = 0; g < GAMES; g++) runs.push(play(v, 1000 + g));
const results = await Promise.all(runs);

const summary = {};
for (const v of VARIANTS) {
  const rs = results.filter((r) => r.variant === v);
  const maxes = rs.map((r) => r.max);
  summary[v] = {
    games: rs.length,
    maxTiles: maxes,
    maxMedian: [...maxes].sort((a, b) => a - b)[Math.floor(maxes.length / 2)],
    movesAvg: Math.round(rs.reduce((s, r) => s + r.moves, 0) / rs.length),
    scoreAvg: Math.round(rs.reduce((s, r) => s + r.score, 0) / rs.length),
    costUsd: Math.round(rs.reduce((s, r) => s + r.tokens, 0) * USD_PER_TOKEN * 1000) / 1000,
  };
  if (v === "jev") {
    const total = rs.reduce((s, r) => s + r.calls, 0);
    const sum = (key) => Object.fromEntries(Object.keys(INTENTS).map((k) => [k, Math.round((rs.reduce((s, r) => s + r[key][k], 0) / total) * 100) / 100]));
    summary[v].firedShare = sum("fired");
    summary[v].leadShare = sum("lead");
    summary[v].latencyAvg = Math.round(rs.reduce((s, r) => s + r.latencyAvg, 0) / rs.length);
  }
  console.log(v, JSON.stringify(summary[v]));
}
const out = new URL("./intents.json", import.meta.url);
let prev = { summary: {}, games: [] };
try {
  prev = JSON.parse(readFileSync(out, "utf8"));
} catch {}
prev.summary = { ...prev.summary, ...summary };
prev.games = [...prev.games.filter((g) => !VARIANTS.includes(g.variant)), ...results];
writeFileSync(out, JSON.stringify(prev, null, 2));
