// How far does Jev get in 2048, and does it need the engine's numbers?
//
// Plays whole games three ways and prints the largest tile, moves and score per game:
//   random        a random legal slide (the floor)
//   board         Jev sees the grid and each slide's grid-after, but no measured numbers
//   metrics       Jev sees the grid, `facts` and the full summaries (what the game sends)
//   plain-board   like board, but the instruction carries no strategy ("choose the best slide")
//   plain-metrics like metrics, with the same strategy-free instruction
//   bare          strategy-free instruction, no numbers at all: options are just "slide up" etc.
//                 and the state holds only the grid and each slide's grid-after
//   eyes          what a person sees: the current grid only, options "slide up" etc. No grid-after.
// Also records Jev's `danger` answer against the moves that were actually left, to see whether
// the gauge means anything.
//
//   op run --env-file=.env.tpl -- node experiments/judge.mjs [games=4] [variants=random,board,metrics]
//   writes experiments/results.json

import { readFileSync, writeFileSync } from "node:fs";
import { TypeSafeClient, choice, noul } from "@typesafe-ai/sdk";
import { boardRows, candidates, facts, isGameOver, makeRng, maxTile, move, newGame, spawn } from "../public/engine.js";
import { DANGER_LABELS, DANGER_TEXT, MOVE_TEXT, MOVE_TEXT_EYES, MOVE_TEXT_PLAIN } from "../questions.js";

const GAMES = Number(process.argv[2] ?? 4);
const VARIANTS = (process.argv[3] ?? "random,board,metrics").split(",");
const MAX_MOVES = 3000;
const USD_PER_TOKEN = 42 / 1e9;
let client; // created on first use so the random variant runs without a key
const jev = () => (client ??= new TypeSafeClient({ defaultModel: "jev-latest", timeout: 20000, retry: { maxRetries: 2 } }));

async function askJev(board, score, withMetrics, plain, bare = false, eyes = false) {
  const cands = candidates(board, withMetrics);
  if (cands.length === 1) return { dir: cands[0].dir, danger: null, usage: null, latency: 0 };
  const state = { board: boardRows(board), score };
  if (withMetrics) state.facts = facts(board);
  if (!eyes) state.candidates = Object.fromEntries(cands.map((c) => [c.dir, bare ? { board_after: c.rows } : { summary: c.summary, board_after: c.rows }]));
  const criteria = Object.fromEntries(cands.map((c) => [c.dir, bare ? `slide ${c.dir}` : c.summary]));
  const t0 = Date.now();
  const r = await jev().systemOne({
    state,
    questions: { move: choice(eyes ? MOVE_TEXT_EYES : plain ? MOVE_TEXT_PLAIN : MOVE_TEXT, criteria), danger: noul(DANGER_TEXT, DANGER_LABELS) },
  });
  return { dir: r.answers.move.choice, danger: r.answers.danger.noul, usage: r.usage, latency: Date.now() - t0 };
}

async function play(variant, seed) {
  const rand = makeRng(seed);
  let board = newGame(rand);
  let score = 0;
  let moves = 0;
  let tokens = 0;
  let latency = 0;
  let calls = 0;
  const dangers = [];
  while (!isGameOver(board) && moves < MAX_MOVES) {
    let dir;
    if (variant === "random") {
      const cands = candidates(board);
      dir = cands[Math.floor(rand() * cands.length)].dir;
    } else {
      const a = await askJev(board, score, variant.endsWith("metrics"), variant.startsWith("plain") || variant === "bare" || variant === "eyes", variant === "bare" || variant === "eyes", variant === "eyes");
      dir = a.dir;
      if (a.usage) {
        tokens += a.usage.input_tokens + a.usage.output_tokens;
        latency += a.latency;
        calls++;
        dangers.push({ move: moves, danger: a.danger });
      }
    }
    const r = move(board, dir);
    if (!r.changed) throw new Error(`illegal move ${dir} chosen`);
    score += r.gained;
    board = spawn(r.board, rand).board;
    moves++;
  }
  // danger vs how many moves were actually left
  for (const d of dangers) d.left = moves - d.move;
  return { variant, seed, max: maxTile(board), moves, score, tokens, calls, latencyAvg: calls ? Math.round(latency / calls) : 0, dangers };
}

const runs = [];
for (const v of VARIANTS) for (let g = 0; g < GAMES; g++) runs.push(play(v, 1000 + g));
const results = await Promise.all(runs);

const summary = {};
for (const v of VARIANTS) {
  const rs = results.filter((r) => r.variant === v);
  const maxes = rs.map((r) => r.max);
  const cost = rs.reduce((s, r) => s + r.tokens, 0) * USD_PER_TOKEN;
  summary[v] = {
    games: rs.length,
    maxTiles: maxes,
    maxMedian: [...maxes].sort((a, b) => a - b)[Math.floor(maxes.length / 2)],
    movesAvg: Math.round(rs.reduce((s, r) => s + r.moves, 0) / rs.length),
    scoreAvg: Math.round(rs.reduce((s, r) => s + r.score, 0) / rs.length),
    latencyAvg: Math.round(rs.reduce((s, r) => s + r.latencyAvg, 0) / rs.length),
    tokensPerMove: rs.reduce((s, r) => s + r.calls, 0) ? Math.round(rs.reduce((s, r) => s + r.tokens, 0) / rs.reduce((s, r) => s + r.calls, 0)) : 0,
    costUsd: Math.round(cost * 1000) / 1000,
  };
  if (v !== "random") {
    const all = rs.flatMap((r) => r.dangers);
    const bucket = (lo, hi) => {
      const xs = all.filter((d) => d.left >= lo && d.left < hi).map((d) => d.danger);
      return xs.length ? Math.round((xs.reduce((s, x) => s + x, 0) / xs.length) * 100) / 100 : null;
    };
    summary[v].dangerByMovesLeft = { "0-10": bucket(0, 10), "10-30": bucket(10, 30), "30-100": bucket(30, 100), "100+": bucket(100, 1e9) };
  }
  console.log(v, JSON.stringify(summary[v]));
}
// merge into results.json so variants can be run separately
const out = new URL("./results.json", import.meta.url);
let prev = { summary: {}, games: [] };
try { prev = JSON.parse(readFileSync(out, "utf8")); } catch {}
prev.summary = { ...prev.summary, ...summary };
prev.games = [...prev.games.filter((g) => !VARIANTS.includes(g.variant)), ...results.map(({ dangers, ...r }) => r)];
writeFileSync(out, JSON.stringify(prev, null, 2));
