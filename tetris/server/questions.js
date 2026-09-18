// server/questions.js — pure builders for the three neuron requests (docs/neurons-spec.md).
// Every text below is copied verbatim from section 2 of the spec; the spec, not this file,
// is where wording changes happen. Nothing here touches the network: `runQuestions` takes
// the client as an argument so tests can hand it a stub.

import { choice, noul, score } from "@typesafe-ai/sdk";

export const KNOWN_INTENTS = ["survive", "clean", "build", "cash", "spin"];
export const PIECES = ["I", "O", "T", "S", "Z", "J", "L"];
export const APPETITE_WORDS = ["none", "low", "moderate", "bold"];
export const BACKERS = [...KNOWN_INTENTS, "default"];
export const MAX_FIRED = 3;
export const MAX_CANDIDATES = 255;
export const MAX_PROPOSALS = 4;
export const MAX_RECENT = 6;
export const BOARD_LINES = 21;

// ---------------------------------------------------------------------------
// 2.1 Request 1 — sense / association layer

export const SCENE =
  "A game of Tetris is in progress. `board` shows the stack, rows top to bottom, '.' for empty and letters for locked pieces. `surface` lists the ten column heights from left to right. `facts` holds what the engine measured: the peak height, holes (empty cells with something above them), bumpiness, the deepest well and its depth, how many rows are nearly full, and how many pieces have passed since the last line clear. `now` is the piece about to be played, `next` the one after it, and `queue` the five pieces coming next in order. `recent` lists the last moves with the goal that led each one. `memory` holds the plan carried over from the previous piece. ";

export const SENSE_TEXT = {
  survive: {
    instructions:
      SCENE +
      "You are the SURVIVE neuron of this player. Should THIS piece serve survival above everything else: bring the stack down or away from the spawn columns, even if it clears nothing and leaves an ugly surface? Say yes only when continuing to stack or to set something up would be reckless here. A tall stack with a clean surface and friendly pieces in `queue` can still be safe; a lower stack can be in trouble when the pieces in `queue` do not fit it, or when the last moves in `recent` have been going badly.",
    true: "Yes: reduce the danger first, whatever it costs.",
    false: "No: there is room to play for something better than safety.",
  },
  clean: {
    instructions:
      SCENE +
      "You are the CLEAN neuron of this player. Should this piece be spent on repairing the stack: filling the pits and ledges that are already there, uncovering a buried hole, levelling a cliff between neighbouring columns, even if it clears nothing and sets up nothing? Weigh how much the damage in `board` will cost over the next pieces in `queue` against what those pieces could do if the surface were left alone. A hole the next clear will remove is not worth a piece; a hole under a tall column is.",
    true: "Yes: pay this piece to fix the surface now.",
    false: "No: the damage can wait, or is not worth a piece.",
  },
  build: {
    instructions:
      SCENE +
      "You are the BUILD neuron of this player. Is this the moment to keep one deep well open at an edge and stack cleanly beside it, holding out for a four-line clear? Consider whether an I is in `queue` and how far away it is, how tall the columns beside the well already are, how clean the well is, and how much height the player can afford to carry while waiting.",
    true: "Yes: keep the well open and invest in the stack beside it.",
    false: "No: waiting for the I is not worth it right now.",
  },
  cash: {
    instructions:
      SCENE +
      "You are the CASH neuron of this player. Should this piece cash in: take a line clear that is on offer now, even a single, even at the price of a rougher surface, instead of keeping those rows for a bigger clear later? Weigh what `queue` brings, how long it has been since the last clear (`facts`), and whether waiting would pay more than it risks.",
    true: "Yes: take the clear now.",
    false: "No: keep the rows for a bigger payout.",
  },
  spin: {
    instructions:
      SCENE +
      "You are the SPIN neuron of this player. Is a T-spin worth playing for on this piece: taking one now when `tspin_available_now` is true, or shaping an overhang slot for a T that is coming in `queue`? Say yes only when the reward justifies the awkward surface and the roof hole a slot costs, and when a T will arrive before the slot is buried.",
    true: "Yes: play for the T-spin.",
    false: "No: a spin is not worth it here.",
  },
};

export const APPETITE_TEXT = {
  instructions:
    SCENE +
    "How much risk should this player accept on this piece? This is temperament, not arithmetic: a bold player accepts a temporary hole or a taller stack for a bigger payoff; a cautious one refuses it. Read the stack, what is still coming in `queue`, how the last moves in `recent` went, and how long it has been since a line clear.",
  rubric: [
    "None. Play it dead safe: refuse any placement that adds a hole or height, whatever it promises.",
    "Low. Accept a small compromise, a bump or one row of height, only when it clearly pays back within a piece or two.",
    "Moderate. Accept a hole or a tall column when a real setup is within reach with the pieces still in `queue`.",
    "Bold. Go for the big clear or the spin even if a miss leaves the board ugly.",
  ],
};

export const STAY_TEXT = {
  instructions:
    SCENE +
    "The previous piece was led by the `memory.previous_intent` goal, and the last verdict asked to hold that plan with strength `memory.hold` (0 drop, 1 keep). Looking at the stack, `now` and `queue`, is that plan still the right one to continue with this piece, or has something changed: a danger appeared, a clear opened up, the slot is gone, or the I has arrived?",
  true: "Yes: continue the plan so the previous pieces' work pays off.",
  false: "No: start fresh with this piece.",
};

// ---------------------------------------------------------------------------
// 2.2 Request 2 — motor layer

export const MOTOR_PRE =
  " `candidates` describes every placement the piece `now` can reach: each entry's `summary` says where it lands and what the engine measured afterwards, and `board_after` shows the resulting stack. `board`, `surface` and `facts` describe the stack before the move; `queue` lists the next five pieces. Each option key below is a candidate id and its description is that candidate's summary.";

export const MOTOR_TEXT = {
  survive:
    "You are the SURVIVE neuron of this player. The appraisal in `intent` activated you at {activation} for this piece and set the risk appetite at {appetite} of 3 ({appetite_word}). Choose the placement a player whose one goal right now is getting the stack down and away from the top would make, staying inside that appetite. Judge what each placement does to the danger of topping out over the next few pieces, not just the tallest column: where the stack will sit under the spawn columns, whether the pieces in `queue` will still have somewhere to go, and whether a hole taken now is cheaper than the height it saves. With a bold appetite you may leave a hole to buy height; with none, accept only the safest placement that keeps the surface honest." +
    MOTOR_PRE,
  clean:
    "You are the CLEAN neuron of this player. The appraisal in `intent` activated you at {activation} for this piece and set the risk appetite at {appetite} of 3 ({appetite_word}). Choose the placement a player whose one goal right now is repairing the surface would make, staying inside that appetite. Judge whether the placement mends what is already wrong: fills a pit or a ledge, brings a row closer to clearing, stops burying an old hole, and covers nothing that would become a new hole. A placement that looks tidy but delays uncovering an old hole is not clean. With a low appetite refuse any new hole; with a bolder one a hole may be taken if it uncovers a bigger mess sooner." +
    MOTOR_PRE,
  build:
    "You are the BUILD neuron of this player. The appraisal in `intent` activated you at {activation} for this piece and set the risk appetite at {appetite} of 3 ({appetite_word}). Choose the placement a player whose one goal right now is setting up a four-line clear would make, staying inside that appetite. Judge whether the placement keeps one deep well open at an edge and piles cleanly beside it so an I from `queue` will clear several lines at once. Filling the well betrays this goal; stacking tall beside it is the point. With a bold appetite stack higher and wait for the I; with a low one keep the pile modest and the well shallow." +
    MOTOR_PRE,
  cash:
    "You are the CASH neuron of this player. The appraisal in `intent` activated you at {activation} for this piece and set the risk appetite at {appetite} of 3 ({appetite_word}). Choose the placement a player whose one goal right now is taking value off the table would make, staying inside that appetite. Judge which placement takes the most now: lines cleared by this piece, a T-spin if one is offered, and how quickly another clear follows given `queue`. A clear that leaves a hole is still cash; whether that price is acceptable is the appetite's call: with none, only clear cleanly; with bold, take the biggest clear on the table." +
    MOTOR_PRE,
  spin:
    "You are the SPIN neuron of this player. The appraisal in `intent` activated you at {activation} for this piece and set the risk appetite at {appetite} of 3 ({appetite_word}). Choose the placement a player whose one goal right now is a T-spin would make, staying inside that appetite. Judge whether the placement takes a T-spin now, or leaves or creates an overhang slot a T can twist into, with the rows beside the slot filled so the spin clears lines, and whether a T will arrive from `queue` before the slot is buried. A slot a spin cannot reach is worthless. With a bold appetite you may leave the slot's roof as a temporary hole; with a low one only shape a slot that costs nothing." +
    MOTOR_PRE,
  // The habit neuron never reads `intent`: its first sentence is the measured single-Choice
  // baseline (spec 2.2; note judge.mjs variant C omits the "and" — the spec text wins here).
  default:
    "Choose the placement a strong Tetris player would make: clear lines, avoid creating holes, and keep the stack low and flat." +
    MOTOR_PRE,
};

// ---------------------------------------------------------------------------
// 2.3 Request 3 — verdict layer

export const DIRECTIVE_PHRASE = {
  survive: "bring the danger down first",
  clean: "repair the surface",
  build: "keep the well open and stack cleanly beside it",
  cash: "take the clear now",
  spin: "play for the T-spin",
};

export const ARBITRATE_TEXT =
  "Several motor neurons of the same Tetris player each proposed a placement for the piece `now`; `proposals` lists them by candidate id, with the goal that backs each one and what the engine says the move does. The appraisal asked this piece to {DIRECTIVE}, with a {appetite_word} appetite for risk ({appetite} of 3). `queue` lists the next five pieces, `recent` the last moves with the goal that led each one, and `memory` the plan carried over from the previous piece. You cannot see the board; you see only what the neurons proposed. Pick the proposal to play. The goal that was asked for does not win by right: it loses when its proposal costs too much for this appetite, and another goal, or plain habit, wins when its proposal serves the asked-for goal nearly as well at a lower price, or keeps alive a plan that `recent` and `memory` show the player has been building. Choose as a player choosing between their own competing instincts.";

export const PROPOSAL_OPTION_TEXT = "{BACKERS} proposed this: {effects}";
export const ALT_OPTION_TEXT = "Second thought of the {LEADING} neuron: {effects}";

export const VETO_TEXT = {
  instructions:
    "A coach is watching over the player's shoulder. The appraisal asked this piece to {DIRECTIVE}, with a {appetite_word} appetite for risk ({appetite} of 3). Consider `proposals.{id}`, one of the moves on the table for the piece `now`. Would the coach put a hand on the player's arm and stop this move? Stop it only for reasons a coach would state: it takes a risk the appetite does not cover, it throws away a setup that `recent` and `memory` show the player has been building, or it defeats the very goal that backs it. Do not stop a move merely for being imperfect, and do not stop it because another proposal looks better.",
  true: "Stop it: the move overreaches for this appetite, wastes a plan the player has been building, or defeats its own goal.",
  false: "Let it through: the move is consistent with its goal and the appetite, even if it is not the best possible.",
};

export const HOLD_TEXT = {
  instructions:
    "Whichever proposal is played, should the next piece keep serving the same plan ({DIRECTIVE}) or start fresh? Judge from `proposals`, `queue`, `recent` and `memory` whether this piece's plan is a down-payment that only pays off if it is followed through, such as a well kept open or a slot being shaped, or whether it finishes the job.",
  rubric: [
    "Drop: the job is done after this piece, or the plan is wrong.",
    "Lean: the plan probably still applies, but the next piece should re-judge it.",
    "Hold: the next piece should continue this plan; this piece only makes sense if it is followed through.",
  ],
};

// ---------------------------------------------------------------------------
// Text helpers

/** Joins the directive phrases in `fired` order; the client never builds this sentence. */
export function directiveOf(fired, forced) {
  if (!Array.isArray(fired) || fired.length === 0) throw new Error("directiveOf: fired is empty");
  return fired
    .map((i) => {
      const phrase = DIRECTIVE_PHRASE[i];
      if (!phrase) throw new Error(`directiveOf: unknown intent ${i}`);
      return i === "survive" && forced ? phrase + " (forced by height)" : phrase;
    })
    .join(" and ");
}

const TOKEN_RE = /\{([A-Za-z_][A-Za-z0-9_]*)\}/g;

/** Replaces `{token}` with `vars[token]`; a token the caller forgot is a silent lie, so throw. */
export function substitute(text, vars) {
  const out = text.replace(TOKEN_RE, (match, key) =>
    Object.prototype.hasOwnProperty.call(vars, key) ? String(vars[key]) : match,
  );
  const leftover = out.match(TOKEN_RE);
  if (leftover) throw new Error(`substitute: unreplaced token ${leftover[0]}`);
  return out;
}

// ---------------------------------------------------------------------------
// Validation (section 5). Each returns a problem string or null.

const isObj = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const isNum = (v) => typeof v === "number" && Number.isFinite(v);
const isPiece = (v) => typeof v === "string" && PIECES.includes(v);

function validateQueue(queue) {
  if (!Array.isArray(queue) || queue.length < 1 || queue.length > 5) {
    return "queue must be an array of 1..5 piece letters";
  }
  if (!queue.every(isPiece)) return "queue must contain only piece letters";
  return null;
}

function validateBoard(boardAscii) {
  if (typeof boardAscii !== "string") return "boardAscii must be a string";
  if (boardAscii.split("\n").length !== BOARD_LINES) return `boardAscii must have ${BOARD_LINES} lines`;
  return null;
}

function validateSurface(surface) {
  if (!Array.isArray(surface) || surface.length !== 10 || !surface.every(Number.isInteger)) {
    return "surface must be an array of 10 integers";
  }
  return null;
}

const FACT_KEYS = ["maxHeight", "holes", "bumpiness", "wellColumn", "wellDepth", "rowsNearlyFull", "piecesSinceClear"];

function validateFacts(facts) {
  if (!isObj(facts)) return "facts must be an object";
  for (const k of FACT_KEYS) {
    if (k === "wellColumn" && facts[k] === null) continue;
    if (!isNum(facts[k])) return `facts.${k} must be a number`;
  }
  return null;
}

function validateRecent(recent) {
  if (!Array.isArray(recent) || recent.length > MAX_RECENT) return `recent must be an array of at most ${MAX_RECENT} moves`;
  for (const m of recent) {
    if (!isObj(m)) return "each recent move must be an object";
    if (!isPiece(m.piece)) return "recent[].piece must be a piece letter";
    if (!Array.isArray(m.columns) || !m.columns.every(isNum)) return "recent[].columns must be a number array";
    if (!isNum(m.lines)) return "recent[].lines must be a number";
    if (!(m.tspin === null || m.tspin === "full" || m.tspin === "mini")) return 'recent[].tspin must be "full", "mini" or null';
    if (!(m.ledBy === null || typeof m.ledBy === "string")) return "recent[].ledBy must be a string or null";
    if (typeof m.vetoed !== "boolean") return "recent[].vetoed must be a boolean";
  }
  return null;
}

function validateGame(game) {
  if (!isObj(game)) return "game must be an object";
  for (const k of ["pieces", "lines", "score", "tspins"]) {
    if (!isNum(game[k])) return `game.${k} must be a number`;
  }
  return null;
}

function validateMemory(memory) {
  if (!isObj(memory)) return "memory must be an object";
  if (!(memory.previousIntent === null || KNOWN_INTENTS.includes(memory.previousIntent))) {
    return "memory.previousIntent must be a known intent or null";
  }
  if (!isNum(memory.hold) || memory.hold < 0 || memory.hold > 1) return "memory.hold must be a number in 0..1";
  return null;
}

function validateFired(fired) {
  if (!Array.isArray(fired) || fired.length < 1 || fired.length > MAX_FIRED) {
    return `intent.fired must have 1..${MAX_FIRED} intents`;
  }
  if (!fired.every((i) => KNOWN_INTENTS.includes(i))) return "intent.fired must contain only known intents";
  if (new Set(fired).size !== fired.length) return "intent.fired must not repeat an intent";
  return null;
}

function validateIntentCommon(intent) {
  if (!isObj(intent)) return "intent must be an object";
  if (!KNOWN_INTENTS.includes(intent.leading)) return "intent.leading must be a known intent";
  const fired = validateFired(intent.fired);
  if (fired) return fired;
  if (typeof intent.forced !== "boolean") return "intent.forced must be a boolean";
  if (!isNum(intent.appetite) || intent.appetite < 0 || intent.appetite > 3) return "intent.appetite must be a number in 0..3";
  if (!APPETITE_WORDS.includes(intent.appetiteWord)) return "intent.appetiteWord must be one of none, low, moderate, bold";
  return null;
}

function validateScene(body) {
  return (
    validateBoard(body.boardAscii) ??
    validateSurface(body.surface) ??
    validateFacts(body.facts) ??
    (isPiece(body.pieceType) ? null : "pieceType must be a piece letter") ??
    (isPiece(body.nextType) ? null : "nextType must be a piece letter") ??
    validateQueue(body.queue) ??
    (typeof body.tspinAvailableNow === "boolean" ? null : "tspinAvailableNow must be a boolean")
  );
}

export function validateSense(body) {
  if (!isObj(body)) return "body must be a JSON object";
  return (
    validateScene(body) ??
    validateRecent(body.recent) ??
    validateGame(body.game) ??
    validateMemory(body.memory)
  );
}

export function validateMotor(body) {
  if (!isObj(body)) return "body must be a JSON object";
  const scene = validateScene(body);
  if (scene) return scene;
  const intent = validateIntentCommon(body.intent);
  if (intent) return intent;
  const a = body.intent.activations;
  if (!isObj(a)) return "intent.activations must be an object";
  for (const i of KNOWN_INTENTS) {
    if (!isNum(a[i]) || a[i] < 0 || a[i] > 1) return `intent.activations.${i} must be a number in 0..1`;
  }
  if (typeof body.intent.stayed !== "boolean") return "intent.stayed must be a boolean";
  const cands = body.candidates;
  if (!Array.isArray(cands) || cands.length === 0) return "candidates must be a non-empty array";
  if (cands.length > MAX_CANDIDATES) return `at most ${MAX_CANDIDATES} candidates are allowed`;
  const ids = new Set();
  for (const c of cands) {
    if (!isObj(c) || typeof c.id !== "string" || typeof c.summary !== "string" || typeof c.boardAfterAscii !== "string") {
      return "each candidate needs string id, summary and boardAfterAscii";
    }
    if (ids.has(c.id)) return `duplicate candidate id ${c.id}`;
    ids.add(c.id);
  }
  return null;
}

export function validateArbitrate(body) {
  if (!isObj(body)) return "body must be a JSON object";
  const head =
    (isPiece(body.pieceType) ? null : "pieceType must be a piece letter") ??
    (isPiece(body.nextType) ? null : "nextType must be a piece letter") ??
    validateQueue(body.queue) ??
    validateIntentCommon(body.intent);
  if (head) return head;
  if (!body.intent.fired.includes(body.intent.leading)) return "intent.leading must be in intent.fired";
  const tail = validateRecent(body.recent) ?? validateGame(body.game) ?? validateMemory(body.memory);
  if (tail) return tail;
  const props = body.proposals;
  if (!Array.isArray(props) || props.length < 2 || props.length > MAX_PROPOSALS) {
    return `proposals must have 2..${MAX_PROPOSALS} entries`;
  }
  const ids = new Set();
  for (const p of props) {
    if (!isObj(p) || typeof p.id !== "string") return "each proposal needs a string id";
    if (ids.has(p.id)) return `duplicate proposal id ${p.id}`;
    ids.add(p.id);
    if (!Array.isArray(p.backedBy) || p.backedBy.length === 0 || !p.backedBy.every((b) => BACKERS.includes(b))) {
      return `proposal ${p.id}: backedBy must be a non-empty list of known intents or "default"`;
    }
    if (new Set(p.backedBy).size !== p.backedBy.length) return `proposal ${p.id}: backedBy must not repeat`;
    if (typeof p.alt !== "boolean") return `proposal ${p.id}: alt must be a boolean`;
    if (typeof p.effects !== "string") return `proposal ${p.id}: effects must be a string`;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Builders: camelCase request → snake_case state Jev reads + SDK question objects.

function snakeFacts(f) {
  return {
    max_height: f.maxHeight,
    holes: f.holes,
    bumpiness: f.bumpiness,
    well_column: f.wellColumn,
    well_depth: f.wellDepth,
    rows_nearly_full: f.rowsNearlyFull,
    pieces_since_clear: f.piecesSinceClear,
  };
}

function snakeRecent(recent) {
  return recent.map((m) => ({
    piece: m.piece,
    columns: m.columns,
    lines: m.lines,
    tspin: m.tspin,
    led_by: m.ledBy,
    vetoed: m.vetoed,
  }));
}

function snakeGame(g) {
  return { pieces: g.pieces, lines: g.lines, score: g.score, tspins: g.tspins };
}

function snakeMemory(m) {
  return { previous_intent: m.previousIntent, hold: m.hold };
}

const noulQ = (t) => noul(t.instructions, { true: t.true, false: t.false });

export function buildSense(body) {
  const state = {
    board: body.boardAscii,
    surface: body.surface,
    facts: snakeFacts(body.facts),
    now: body.pieceType,
    next: body.nextType,
    queue: body.queue,
    tspin_available_now: body.tspinAvailableNow,
    recent: snakeRecent(body.recent),
    game: snakeGame(body.game),
    memory: snakeMemory(body.memory),
  };
  const questions = {};
  for (const i of KNOWN_INTENTS) questions[i] = noulQ(SENSE_TEXT[i]);
  questions.appetite = score(APPETITE_TEXT.instructions, APPETITE_TEXT.rubric);
  // A dropped plan has nothing to continue, so the stay question is not asked at all.
  if (body.memory.previousIntent !== null && body.memory.hold > 0) questions.stay = noulQ(STAY_TEXT);
  return { state, questions };
}

export function buildMotor(body) {
  const { intent } = body;
  const state = {
    intent: {
      leading: intent.leading,
      activations: intent.activations,
      appetite: intent.appetite,
      appetite_word: intent.appetiteWord,
      fired: intent.fired,
      forced: intent.forced,
      stayed: intent.stayed,
    },
    board: body.boardAscii,
    surface: body.surface,
    facts: snakeFacts(body.facts),
    now: body.pieceType,
    next: body.nextType,
    queue: body.queue,
    tspin_available_now: body.tspinAvailableNow,
    candidates: Object.fromEntries(
      body.candidates.map((c) => [c.id, { summary: c.summary, board_after: c.boardAfterAscii }]),
    ),
  };
  // Every motor neuron reads the same option map; only the instructions differ.
  const criteria = Object.fromEntries(body.candidates.map((c) => [c.id, c.summary]));
  const vars = { appetite: intent.appetite.toFixed(1), appetite_word: intent.appetiteWord };
  const questions = {};
  for (const i of intent.fired) {
    const activation = intent.forced && i === "survive" ? "forced by height" : intent.activations[i].toFixed(2);
    questions[`motor_${i}`] = choice(substitute(MOTOR_TEXT[i], { ...vars, activation }), criteria);
  }
  questions.motor_default = choice(substitute(MOTOR_TEXT.default, {}), criteria);
  return { state, questions };
}

const backerName = (b) => (b === "default" ? "HABIT" : b.toUpperCase());

export function buildArbitrate(body) {
  const { intent } = body;
  const directive = directiveOf(intent.fired, intent.forced);
  const state = {
    now: body.pieceType,
    next: body.nextType,
    queue: body.queue,
    intent: {
      leading: intent.leading,
      fired: intent.fired,
      forced: intent.forced,
      appetite: intent.appetite,
      appetite_word: intent.appetiteWord,
      directive,
    },
    recent: snakeRecent(body.recent),
    game: snakeGame(body.game),
    memory: snakeMemory(body.memory),
    proposals: Object.fromEntries(
      body.proposals.map((p) => [p.id, { backed_by: p.backedBy, alt: p.alt, effects: p.effects }]),
    ),
  };
  const vars = {
    DIRECTIVE: directive,
    LEADING: intent.leading.toUpperCase(),
    appetite: intent.appetite.toFixed(1),
    appetite_word: intent.appetiteWord,
  };
  // Option descriptions name the backers and the qualitative effects only: no weights,
  // no confidences, no metrics (spec 2.3).
  const options = Object.fromEntries(
    body.proposals.map((p) => [
      p.id,
      p.alt
        ? substitute(ALT_OPTION_TEXT, { ...vars, effects: p.effects })
        : substitute(PROPOSAL_OPTION_TEXT, { BACKERS: p.backedBy.map(backerName).join(" and "), effects: p.effects }),
    ]),
  );
  const questions = { arbitrate: choice(substitute(ARBITRATE_TEXT, vars), options) };
  for (const p of body.proposals) {
    questions[`veto_${p.id}`] = noul(substitute(VETO_TEXT.instructions, { ...vars, id: p.id }), {
      true: substitute(VETO_TEXT.true, vars),
      false: substitute(VETO_TEXT.false, vars),
    });
  }
  questions.hold = score(
    substitute(HOLD_TEXT.instructions, vars),
    HOLD_TEXT.rubric.map((r) => substitute(r, vars)),
  );
  return { state, questions };
}

/** The instruction text actually sent per question, echoed in every response. */
export function instructionsOf(questions) {
  return Object.fromEntries(Object.entries(questions).map(([name, q]) => [name, q.instructions]));
}

// ---------------------------------------------------------------------------
// Transport: one systemOne, or one per question with the same state (JEV_FANOUT).
// The client is injected so tests can count calls without a network.

export async function runQuestions(client, model, state, questions, fanout) {
  if (!fanout) return client.systemOne({ state, model, questions });
  const names = Object.keys(questions);
  const results = await Promise.all(
    names.map((name) => client.systemOne({ state, model, questions: { [name]: questions[name] } })),
  );
  const answers = {};
  const usage = { input_tokens: 0, output_tokens: 0 };
  results.forEach((r, k) => {
    answers[names[k]] = r.answers[names[k]];
    usage.input_tokens += r.usage.input_tokens;
    usage.output_tokens += r.usage.output_tokens;
  });
  return { model: results[0].model, answers, usage };
}
