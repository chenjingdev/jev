// questions.js — the exact words Jev reads, plus the request validator and builder. Kept apart
// from server.js so the measurement script and the tests can import them without a server.

import { choice, noul } from "@typesafe-ai/sdk";

export const DIRS = ["up", "down", "left", "right"];

export const SCENE =
  "A game of 2048 is in progress. `board` shows the 4×4 grid as four rows of four cells, top row " +
  "first, '.' for an empty cell. A slide pushes every tile toward one wall; two equal tiles that " +
  "touch along the way merge into their sum, and afterwards a new 2 or 4 appears in a random empty " +
  "cell. The game ends when no slide changes the grid. `facts` holds what the engine measured about " +
  "the grid now: empty cells, the largest tile and whether it sits in a corner, how many of the 8 " +
  "rows and columns are ordered, roughness (how different neighbouring tiles are), and how many " +
  "equal neighbours could still merge. `candidates` lists every legal slide: `board_after` is the " +
  "grid after that slide and before the new tile, and `summary` is what the engine measured about it. ";

export const MOVE_TEXT =
  SCENE +
  "Choose the slide a strong 2048 player would make: keep the largest tile in one corner and the " +
  "tiles leading to it ordered from large to small, merge when it keeps that order, keep empty cells " +
  "free, and avoid a slide that pulls the largest tile out of its corner or scatters large tiles " +
  "across the grid. Each option key is a direction and its description is that candidate's summary.";

// The same question with no strategy in it: the measurement's control for "is the play in the
// prompt or in the model".
export const MOVE_TEXT_PLAIN =
  SCENE + "Choose the best slide for this position. Each option key is a direction and its description is that candidate's summary.";

// Only what a person sees: the rules, the grid, four directions. No candidates in the state.
export const RULES =
  "A game of 2048 is in progress. `board` shows the 4×4 grid as four rows of four cells, top row " +
  "first, '.' for an empty cell. A slide pushes every tile toward one wall; two equal tiles that " +
  "touch along the way merge into their sum, and afterwards a new 2 or 4 appears in a random empty " +
  "cell. The game ends when no slide changes the grid. ";
export const MOVE_TEXT_EYES = RULES + "Choose the best slide for this position. The options are the directions that would change the grid.";

export const DANGER_TEXT =
  SCENE +
  "Is this grid close to locking up: few empty cells, few equal neighbours left to merge, large " +
  "tiles scattered so that an unlucky new tile within the next few slides could end the game?";

export const DANGER_LABELS = {
  true: "Yes: the grid is nearly stuck and the next few tiles decide the game.",
  false: "No: there is room to keep merging.",
};

export function validateMove(body) {
  if (!body || typeof body !== "object") return "body must be a JSON object";
  if (!Array.isArray(body.rows) || body.rows.length !== 4 || !body.rows.every((r) => typeof r === "string")) {
    return "rows must be four strings";
  }
  if (!body.facts || typeof body.facts !== "object") return "facts must be an object";
  if (!Array.isArray(body.candidates) || body.candidates.length === 0) return "candidates must be a non-empty array";
  for (const c of body.candidates) {
    if (!c || !DIRS.includes(c.dir)) return "each candidate needs a dir of up/down/left/right";
    if (typeof c.summary !== "string" || !Array.isArray(c.rows)) return "each candidate needs a summary and rows";
  }
  return null;
}

export const DANGER_TEXT_EYES =
  RULES + "Is this grid close to locking up, so that an unlucky new tile within the next few slides could end the game?";

export function buildMove(body) {
  if (body.mode === "eyes") {
    // what a person sees: the grid, nothing the engine computed
    const state = { board: body.rows, score: body.score ?? 0 };
    const criteria = Object.fromEntries(body.candidates.map((c) => [c.dir, `slide ${c.dir}`]));
    return { state, questions: { move: choice(MOVE_TEXT_EYES, criteria), danger: noul(DANGER_TEXT_EYES, DANGER_LABELS) } };
  }
  const state = {
    board: body.rows,
    score: body.score ?? 0,
    facts: body.facts,
    candidates: Object.fromEntries(body.candidates.map((c) => [c.dir, { summary: c.summary, board_after: c.rows }])),
  };
  const criteria = Object.fromEntries(body.candidates.map((c) => [c.dir, c.summary]));
  const questions = {
    move: choice(MOVE_TEXT, criteria),
    danger: noul(DANGER_TEXT, DANGER_LABELS),
  };
  return { state, questions };
}
