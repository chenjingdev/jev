import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  ALT_OPTION_TEXT,
  APPETITE_TEXT,
  ARBITRATE_TEXT,
  HOLD_TEXT,
  KNOWN_INTENTS,
  MOTOR_PRE,
  MOTOR_TEXT,
  PROPOSAL_OPTION_TEXT,
  SCENE,
  SENSE_TEXT,
  STAY_TEXT,
  VETO_TEXT,
  buildArbitrate,
  buildMotor,
  buildSense,
  directiveOf,
  instructionsOf,
  runQuestions,
  substitute,
  validateArbitrate,
  validateMotor,
  validateSense,
} from "../server/questions.js";

const SPEC = readFileSync(new URL("../docs/neurons-spec.md", import.meta.url), "utf8");

// ---------------------------------------------------------------------------
// Fixtures shaped like the section-5 example bodies, with real 21-line boards.

const EMPTY_ROW = "..........";
const BOARD = ["0123456789", ...Array(19).fill(EMPTY_ROW), "XXXXXXXXX."].join("\n");
const clone = (v) => JSON.parse(JSON.stringify(v));

const RECENT = [{ piece: "S", columns: [3, 4, 5], lines: 0, tspin: null, ledBy: "build", vetoed: false }];
const GAME = { pieces: 21, lines: 6, score: 1300, tspins: 1 };
const FACTS = { maxHeight: 9, holes: 2, bumpiness: 7, wellColumn: 9, wellDepth: 4, rowsNearlyFull: 1, piecesSinceClear: 3 };

const senseBody = () => ({
  boardAscii: BOARD,
  surface: [0, 0, 3, 4, 4, 5, 5, 6, 7, 2],
  facts: clone(FACTS),
  pieceType: "T",
  nextType: "I",
  queue: ["I", "O", "S", "Z", "L"],
  tspinAvailableNow: false,
  recent: clone(RECENT),
  game: clone(GAME),
  memory: { previousIntent: "build", hold: 0.5 },
});

const candidate = (n) => ({ id: `c${n}`, summary: `T piece, rotation 0; candidate ${n}`, boardAfterAscii: BOARD });

const motorBody = () => ({
  intent: {
    leading: "build",
    activations: { survive: 0.02, clean: 0.31, build: 0.92, cash: 0.61, spin: 0.0 },
    appetite: 1.8,
    appetiteWord: "moderate",
    fired: ["build", "cash"],
    forced: false,
    stayed: true,
  },
  boardAscii: BOARD,
  surface: [0, 0, 3, 4, 4, 5, 5, 6, 7, 2],
  facts: clone(FACTS),
  pieceType: "T",
  nextType: "I",
  queue: ["I", "O", "S", "Z", "L"],
  tspinAvailableNow: false,
  candidates: [candidate(0), candidate(1), candidate(7)],
});

const EFFECTS_C7 =
  "T piece, rotation 1 (nub pointing right); lands at columns 6-7, rows 15-17; clears no lines; keeps the well open; no new hole; peak higher; leaves a T-spin slot";

const arbitrateBody = () => ({
  pieceType: "T",
  nextType: "I",
  queue: ["I", "O", "S", "Z", "L"],
  intent: { leading: "build", fired: ["build", "cash"], forced: false, appetite: 1.8, appetiteWord: "moderate" },
  recent: clone(RECENT),
  game: clone(GAME),
  memory: { previousIntent: "build", hold: 0.5 },
  proposals: [
    { id: "c7", backedBy: ["build", "default"], alt: false, effects: EFFECTS_C7 },
    { id: "c1", backedBy: ["cash"], alt: false, effects: "T piece, rotation 0 (flat side down); clears 1 line; fills the well; no new hole; peak lower; no T-spin slot" },
  ],
});

// ---------------------------------------------------------------------------
// Texts are frozen: every constant must appear verbatim in the spec.

test("section 2 texts are copied verbatim from the spec", () => {
  const inSpec = (text, what) => assert.ok(SPEC.includes(text), `${what} differs from the spec`);
  inSpec(SCENE, "SCENE");
  inSpec(MOTOR_PRE, "MOTOR_PRE");
  for (const i of KNOWN_INTENTS) {
    inSpec(SENSE_TEXT[i].instructions.slice(SCENE.length), `sense ${i}`);
    inSpec(SENSE_TEXT[i].true, `sense ${i} true`);
    inSpec(SENSE_TEXT[i].false, `sense ${i} false`);
    inSpec(MOTOR_TEXT[i].slice(0, -MOTOR_PRE.length), `motor ${i}`);
  }
  inSpec(MOTOR_TEXT.default.slice(0, -MOTOR_PRE.length), "motor default");
  inSpec(APPETITE_TEXT.instructions.slice(SCENE.length), "appetite");
  APPETITE_TEXT.rubric.forEach((r, k) => inSpec(r, `appetite rubric ${k}`));
  inSpec(STAY_TEXT.instructions.slice(SCENE.length), "stay");
  inSpec(STAY_TEXT.true, "stay true");
  inSpec(STAY_TEXT.false, "stay false");
  inSpec(ARBITRATE_TEXT, "arbitrate");
  inSpec(PROPOSAL_OPTION_TEXT, "proposal option");
  inSpec(ALT_OPTION_TEXT, "alt option");
  inSpec(VETO_TEXT.instructions, "veto");
  inSpec(VETO_TEXT.true, "veto true");
  inSpec(VETO_TEXT.false, "veto false");
  inSpec(HOLD_TEXT.instructions, "hold");
  HOLD_TEXT.rubric.forEach((r, k) => inSpec(r, `hold rubric ${k}`));
});

// ---------------------------------------------------------------------------
// Validation

test("section 5 example bodies validate", () => {
  assert.equal(validateSense(senseBody()), null);
  assert.equal(validateMotor(motorBody()), null);
  assert.equal(validateArbitrate(arbitrateBody()), null);
});

test("validateSense rejects missing, mistyped and out-of-range fields", () => {
  const mutate = (fn) => {
    const b = senseBody();
    fn(b);
    return validateSense(b);
  };
  assert.equal(typeof validateSense(null), "string");
  assert.equal(typeof validateSense([]), "string");
  assert.equal(typeof mutate((b) => delete b.boardAscii), "string");
  assert.equal(typeof mutate((b) => (b.boardAscii = "0123456789\n..........")), "string");
  assert.equal(typeof mutate((b) => (b.surface = [1, 2, 3])), "string");
  assert.equal(typeof mutate((b) => (b.surface[3] = 1.5)), "string");
  assert.equal(typeof mutate((b) => delete b.facts.holes), "string");
  assert.equal(typeof mutate((b) => (b.facts.maxHeight = "9")), "string");
  assert.equal(mutate((b) => (b.facts.wellColumn = null)), null, "wellColumn may be null");
  assert.equal(typeof mutate((b) => (b.facts.wellDepth = null)), "string");
  assert.equal(typeof mutate((b) => (b.pieceType = "X")), "string");
  assert.equal(typeof mutate((b) => (b.nextType = "t")), "string");
  assert.equal(typeof mutate((b) => (b.queue = [])), "string");
  assert.equal(typeof mutate((b) => (b.queue = ["I", "O", "S", "Z", "L", "J"])), "string");
  assert.equal(typeof mutate((b) => (b.queue = ["I", "Q"])), "string");
  assert.equal(typeof mutate((b) => (b.tspinAvailableNow = "no")), "string");
  assert.equal(typeof mutate((b) => (b.recent = Array(7).fill(RECENT[0]))), "string");
  assert.equal(typeof mutate((b) => (b.recent[0].tspin = "half")), "string");
  assert.equal(typeof mutate((b) => (b.recent[0].vetoed = 0)), "string");
  assert.equal(typeof mutate((b) => (b.recent[0].columns = "345")), "string");
  assert.equal(typeof mutate((b) => delete b.game.tspins), "string");
  assert.equal(typeof mutate((b) => (b.memory.previousIntent = "flatten")), "string");
  assert.equal(typeof mutate((b) => (b.memory.hold = 1.2)), "string");
  assert.equal(typeof mutate((b) => delete b.memory), "string");
  assert.equal(mutate((b) => (b.memory = { previousIntent: null, hold: 0 })), null);
});

test("validateMotor rejects bad intents and candidate lists", () => {
  const mutate = (fn) => {
    const b = motorBody();
    fn(b);
    return validateMotor(b);
  };
  assert.equal(typeof mutate((b) => delete b.intent), "string");
  assert.equal(typeof mutate((b) => (b.intent.fired = ["survive", "clean", "build", "cash"])), "string", "fired 4");
  assert.equal(typeof mutate((b) => (b.intent.fired = [])), "string");
  assert.equal(typeof mutate((b) => (b.intent.fired = ["build", "build"])), "string");
  assert.equal(typeof mutate((b) => (b.intent.fired = ["build", "flatten"])), "string");
  assert.equal(typeof mutate((b) => (b.intent.leading = "habit")), "string");
  assert.equal(typeof mutate((b) => delete b.intent.activations.spin), "string");
  assert.equal(typeof mutate((b) => (b.intent.activations.build = 1.2)), "string");
  assert.equal(typeof mutate((b) => (b.intent.appetite = 3.5)), "string");
  assert.equal(typeof mutate((b) => (b.intent.appetiteWord = "brave")), "string");
  assert.equal(typeof mutate((b) => (b.intent.forced = "no")), "string");
  assert.equal(typeof mutate((b) => (b.intent.stayed = 1)), "string");
  assert.equal(typeof mutate((b) => (b.candidates = [])), "string");
  assert.equal(typeof mutate((b) => (b.candidates = Array.from({ length: 256 }, (_, n) => candidate(n)))), "string", "256 candidates");
  assert.equal(mutate((b) => (b.candidates = Array.from({ length: 255 }, (_, n) => candidate(n)))), null, "255 candidates");
  assert.equal(typeof mutate((b) => (b.candidates = [candidate(1), candidate(1)])), "string", "duplicate ids");
  assert.equal(typeof mutate((b) => delete b.candidates[0].boardAfterAscii), "string");
  assert.equal(typeof mutate((b) => (b.candidates[0].summary = 3)), "string");
  assert.equal(typeof mutate((b) => (b.pieceType = "P")), "string");
  assert.equal(typeof mutate((b) => delete b.surface), "string");
  assert.equal(typeof mutate((b) => delete b.facts), "string");
});

test("validateArbitrate rejects bad proposals and leading outside fired", () => {
  const mutate = (fn) => {
    const b = arbitrateBody();
    fn(b);
    return validateArbitrate(b);
  };
  assert.equal(typeof mutate((b) => (b.proposals = b.proposals.slice(0, 1))), "string", "1 proposal");
  assert.equal(
    typeof mutate((b) => (b.proposals = [0, 1, 2, 3, 4].map((n) => ({ id: `c${n}`, backedBy: ["cash"], alt: false, effects: "x" })))),
    "string",
    "5 proposals",
  );
  assert.equal(typeof mutate((b) => (b.proposals[1].id = "c7")), "string", "duplicate ids");
  assert.equal(typeof mutate((b) => (b.proposals[0].backedBy = [])), "string");
  assert.equal(typeof mutate((b) => (b.proposals[0].backedBy = ["habit"])), "string");
  assert.equal(mutate((b) => (b.proposals[0].backedBy = ["default"])), null, "default is a legal backer");
  assert.equal(typeof mutate((b) => (b.proposals[0].alt = "yes")), "string");
  assert.equal(typeof mutate((b) => delete b.proposals[0].effects), "string");
  assert.equal(typeof mutate((b) => (b.intent.leading = "spin")), "string", "leading not in fired");
  assert.equal(typeof mutate((b) => (b.intent.fired = ["build", "cash", "spin", "clean"])), "string");
  assert.equal(typeof mutate((b) => (b.intent.forced = undefined)), "string");
  assert.equal(typeof mutate((b) => (b.pieceType = "V")), "string");
  assert.equal(typeof mutate((b) => delete b.queue), "string");
  assert.equal(typeof mutate((b) => delete b.recent), "string");
  assert.equal(typeof mutate((b) => delete b.game), "string");
  assert.equal(typeof mutate((b) => (b.memory.hold = -0.1)), "string");
  assert.equal(mutate((b) => (b.directive = "whatever")), null, "a client-sent directive is ignored, not rejected");
});

// ---------------------------------------------------------------------------
// Builders

test("buildSense state matches the section-3 R1 shape exactly", () => {
  const { state } = buildSense(senseBody());
  assert.deepEqual(state, {
    board: BOARD,
    surface: [0, 0, 3, 4, 4, 5, 5, 6, 7, 2],
    facts: { max_height: 9, holes: 2, bumpiness: 7, well_column: 9, well_depth: 4, rows_nearly_full: 1, pieces_since_clear: 3 },
    now: "T",
    next: "I",
    queue: ["I", "O", "S", "Z", "L"],
    tspin_available_now: false,
    recent: [{ piece: "S", columns: [3, 4, 5], lines: 0, tspin: null, led_by: "build", vetoed: false }],
    game: { pieces: 21, lines: 6, score: 1300, tspins: 1 },
    memory: { previous_intent: "build", hold: 0.5 },
  });
  assert.deepEqual(Object.keys(state), ["board", "surface", "facts", "now", "next", "queue", "tspin_available_now", "recent", "game", "memory"]);
});

test("buildSense asks stay only when a plan is carried over", () => {
  const withPlan = buildSense(senseBody());
  assert.deepEqual(Object.keys(withPlan.questions), ["survive", "clean", "build", "cash", "spin", "appetite", "stay"]);
  assert.equal(withPlan.questions.stay.type, "noul");
  assert.equal(withPlan.questions.appetite.type, "score");
  assert.equal(withPlan.questions.appetite.criteria.length, 4);
  assert.equal(withPlan.questions.survive.instructions, SCENE + SENSE_TEXT.survive.instructions.slice(SCENE.length));
  assert.deepEqual(withPlan.questions.survive.criteria, { true: SENSE_TEXT.survive.true, false: SENSE_TEXT.survive.false });

  const noIntent = senseBody();
  noIntent.memory = { previousIntent: null, hold: 0.8 };
  assert.ok(!("stay" in buildSense(noIntent).questions), "no previous intent → no stay");

  const dropped = senseBody();
  dropped.memory = { previousIntent: "build", hold: 0 };
  assert.ok(!("stay" in buildSense(dropped).questions), "hold 0 → no stay");
});

test("buildMotor makes motor_<fired> + motor_default with one shared criteria map", () => {
  const { state, questions } = buildMotor(motorBody());
  assert.deepEqual(Object.keys(questions), ["motor_build", "motor_cash", "motor_default"]);
  for (const q of Object.values(questions)) assert.equal(q.type, "choice");
  const expected = { c0: candidate(0).summary, c1: candidate(1).summary, c7: candidate(7).summary };
  assert.deepEqual(questions.motor_build.criteria, expected);
  assert.deepEqual(questions.motor_cash.criteria, expected);
  assert.deepEqual(questions.motor_default.criteria, expected);

  const text = questions.motor_build.instructions;
  assert.ok(text.includes("activated you at 0.92 "), "activation substituted with two decimals");
  assert.ok(text.includes("1.8 of 3 (moderate)"), "appetite and word substituted");
  assert.ok(!text.includes("{"), "no token left behind");
  assert.ok(text.endsWith(MOTOR_PRE));
  assert.ok(questions.motor_cash.instructions.includes("activated you at 0.61 "));
  assert.ok(questions.motor_default.instructions.startsWith("Choose the placement a strong Tetris player would make"));
  assert.ok(!questions.motor_default.instructions.includes("`intent`"), "habit never reads intent");

  assert.deepEqual(Object.keys(state), ["intent", "board", "surface", "facts", "now", "next", "queue", "tspin_available_now", "candidates"]);
  assert.deepEqual(state.intent, {
    leading: "build",
    activations: { survive: 0.02, clean: 0.31, build: 0.92, cash: 0.61, spin: 0.0 },
    appetite: 1.8,
    appetite_word: "moderate",
    fired: ["build", "cash"],
    forced: false,
    stayed: true,
  });
  assert.deepEqual(state.candidates.c7, { summary: candidate(7).summary, board_after: BOARD });
});

test("buildMotor writes 'forced by height' for a forced survive neuron", () => {
  const body = motorBody();
  body.intent.fired = ["survive", "build"];
  body.intent.forced = true;
  body.intent.activations.survive = 0.1;
  const { questions } = buildMotor(body);
  assert.deepEqual(Object.keys(questions), ["motor_survive", "motor_build", "motor_default"]);
  assert.ok(questions.motor_survive.instructions.includes("activated you at forced by height for this piece"));
  assert.ok(questions.motor_build.instructions.includes("activated you at 0.92 "), "only survive is forced");
});

test("directiveOf joins phrases in fired order and marks a forced survive", () => {
  assert.equal(directiveOf(["build", "cash"], false), "keep the well open and stack cleanly beside it and take the clear now");
  assert.equal(directiveOf(["survive"], true), "bring the danger down first (forced by height)");
  assert.equal(directiveOf(["survive"], false), "bring the danger down first");
  assert.equal(directiveOf(["cash", "spin", "clean"], true), "take the clear now and play for the T-spin and repair the surface");
  assert.throws(() => directiveOf([], false));
  assert.throws(() => directiveOf(["flatten"], false));
});

test("buildArbitrate makes arbitrate + veto per proposal + hold on a blind state", () => {
  const body = arbitrateBody();
  body.directive = "IGNORED BY THE SERVER";
  const { state, questions } = buildArbitrate(body);
  assert.deepEqual(Object.keys(questions), ["arbitrate", "veto_c7", "veto_c1", "hold"]);
  assert.equal(questions.arbitrate.type, "choice");
  assert.equal(questions.veto_c7.type, "noul");
  assert.equal(questions.hold.type, "score");
  assert.equal(questions.hold.criteria.length, 3);

  const directive = directiveOf(["build", "cash"], false);
  assert.equal(state.intent.directive, directive);
  assert.ok(!JSON.stringify(state).includes("IGNORED"), "client directive is ignored");
  assert.deepEqual(Object.keys(state), ["now", "next", "queue", "intent", "recent", "game", "memory", "proposals"]);
  assert.deepEqual(Object.keys(state.intent), ["leading", "fired", "forced", "appetite", "appetite_word", "directive"]);
  for (const key of ["board", "surface", "facts", "candidates", "activations", "stayed"]) {
    assert.ok(!JSON.stringify(state).includes(`"${key}"`), `R3 state must not contain ${key}`);
  }
  assert.deepEqual(state.proposals.c7, { backed_by: ["build", "default"], alt: false, effects: EFFECTS_C7 });

  assert.equal(questions.arbitrate.criteria.c7, `BUILD and HABIT proposed this: ${EFFECTS_C7}`);
  assert.ok(questions.arbitrate.criteria.c1.startsWith("CASH proposed this: "));
  assert.ok(questions.arbitrate.instructions.includes(`asked this piece to ${directive}, with a moderate appetite for risk (1.8 of 3)`));
  assert.ok(questions.veto_c7.instructions.includes("Consider `proposals.c7`, one of the moves"));
  assert.ok(questions.veto_c1.instructions.includes("Consider `proposals.c1`, one of the moves"));
  assert.ok(questions.veto_c7.instructions.includes(`asked this piece to ${directive}, with a moderate appetite`));
  assert.ok(questions.hold.instructions.includes(`the same plan (${directive}) or start fresh`));
  for (const q of Object.values(questions)) {
    assert.ok(!q.instructions.includes("{"), "no token left in instructions");
    for (const c of Object.values(q.criteria)) assert.ok(!c.includes("{"), "no token left in criteria");
  }
});

test("buildArbitrate describes an ALT proposal as the leading neuron's second thought", () => {
  const body = arbitrateBody();
  body.proposals[1] = { id: "c3", backedBy: ["build"], alt: true, effects: "T piece, rotation 2 (flat side up); clears no lines; no well; adds a hole; peak unchanged; no T-spin slot" };
  const { questions } = buildArbitrate(body);
  assert.equal(questions.arbitrate.criteria.c3, `Second thought of the BUILD neuron: ${body.proposals[1].effects}`);
  assert.deepEqual(Object.keys(questions), ["arbitrate", "veto_c7", "veto_c3", "hold"]);
});

test("instructionsOf echoes exactly the text of each question", () => {
  const { questions } = buildArbitrate(arbitrateBody());
  const instr = instructionsOf(questions);
  assert.deepEqual(Object.keys(instr), ["arbitrate", "veto_c7", "veto_c1", "hold"]);
  assert.equal(instr.veto_c7, questions.veto_c7.instructions);
});

// ---------------------------------------------------------------------------
// Backtick keys: every `identifier` the texts mention must exist in that request's state.
// A name Jev cannot find is silent theater, so this must fail loudly.

function collectKeys(value, out = new Set()) {
  if (Array.isArray(value)) value.forEach((v) => collectKeys(v, out));
  else if (value && typeof value === "object") {
    for (const [k, v] of Object.entries(value)) {
      out.add(k);
      collectKeys(v, out);
    }
  }
  return out;
}

function backtickIdentifiers(text) {
  const found = [];
  for (const m of text.matchAll(/`([A-Za-z_][A-Za-z0-9_]*)(?:\.[^`]*)?`/g)) found.push(m[1]);
  return found;
}

function allTexts(questions) {
  const texts = [];
  for (const q of Object.values(questions)) {
    texts.push(q.instructions);
    for (const c of Object.values(q.criteria ?? {})) if (typeof c === "string") texts.push(c);
  }
  return texts;
}

for (const [name, build, body] of [
  ["sense", buildSense, senseBody()],
  ["motor", buildMotor, motorBody()],
  ["arbitrate", buildArbitrate, arbitrateBody()],
]) {
  test(`every backtick identifier in the ${name} texts is a key in the ${name} state`, () => {
    const { state, questions } = build(body);
    const keys = collectKeys(state);
    let seen = 0;
    for (const text of allTexts(questions)) {
      for (const id of backtickIdentifiers(text)) {
        seen++;
        assert.ok(keys.has(id), `\`${id}\` is mentioned but missing from the ${name} state`);
      }
    }
    assert.ok(seen > 0, "the texts mention at least one state key");
  });
}

test("backtick scan catches a stale identifier (self-check of the checker)", () => {
  assert.deepEqual(backtickIdentifiers("see `memory.previous_intent`, `now` and `proposals.c7`; '.' is not one"), ["memory", "now", "proposals"]);
  assert.ok(!collectKeys(buildArbitrate(arbitrateBody()).state).has("board"));
});

// ---------------------------------------------------------------------------
// substitute

test("substitute replaces known tokens and throws on any left behind", () => {
  assert.equal(substitute("a {x} b {y_z}", { x: 1, y_z: "two" }), "a 1 b two");
  assert.throws(() => substitute("a {x} b {missing}", { x: 1 }), /missing/);
  assert.throws(() => substitute("{activation}", {}), /activation/);
  assert.equal(substitute("no tokens", {}), "no tokens");
});

// ---------------------------------------------------------------------------
// Fan-out

function stubClient(calls) {
  return {
    async systemOne(req) {
      calls.push(req);
      const answers = Object.fromEntries(
        Object.entries(req.questions).map(([name, q]) => [
          name,
          q.type === "noul"
            ? { type: "noul", noul: 0.4 }
            : q.type === "score"
              ? { type: "score", score: 1, confidence: 0.5, legend: {}, probabilities: {} }
              : { type: "choice", choice: Object.keys(q.criteria)[0], confidence: 0.5, probabilities: {} },
        ]),
      );
      return { model: "jev-stub", answers, usage: { input_tokens: 100, output_tokens: 3 } };
    },
  };
}

test("runQuestions bundles every question into one call by default", async () => {
  const calls = [];
  const { state, questions } = buildMotor(motorBody());
  const result = await runQuestions(stubClient(calls), "jev-latest", state, questions, false);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].model, "jev-latest");
  assert.deepEqual(Object.keys(calls[0].questions), ["motor_build", "motor_cash", "motor_default"]);
  assert.deepEqual(result.usage, { input_tokens: 100, output_tokens: 3 });
});

test("runQuestions with fanout calls systemOne once per question with the same state and sums usage", async () => {
  const calls = [];
  const { state, questions } = buildMotor(motorBody());
  const result = await runQuestions(stubClient(calls), "jev-latest", state, questions, true);
  assert.equal(calls.length, 3);
  for (const call of calls) {
    assert.equal(call.state, state, "every fan-out call carries the same state");
    assert.equal(Object.keys(call.questions).length, 1);
  }
  assert.deepEqual(calls.map((c) => Object.keys(c.questions)[0]), ["motor_build", "motor_cash", "motor_default"]);
  assert.deepEqual(Object.keys(result.answers), ["motor_build", "motor_cash", "motor_default"]);
  assert.equal(result.answers.motor_build.type, "choice");
  assert.deepEqual(result.usage, { input_tokens: 300, output_tokens: 9 });
  assert.equal(result.model, "jev-stub");
});

test("runQuestions with fanout rejects when any single call fails", async () => {
  const client = {
    calls: 0,
    async systemOne(req) {
      if (++this.calls === 2) throw new Error("boom");
      const [name] = Object.keys(req.questions);
      return { model: "m", answers: { [name]: { type: "noul", noul: 0.1 } }, usage: { input_tokens: 1, output_tokens: 1 } };
    },
  };
  const { state, questions } = buildSense(senseBody());
  await assert.rejects(runQuestions(client, "m", state, questions, true), /boom/);
});
