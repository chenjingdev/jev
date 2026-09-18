import test from "node:test";
import assert from "node:assert/strict";
import { COLS, ROWS, createEmptyBoard } from "../public/engine.js";
import { reachablePlacements } from "../public/srs.js";
import {
  BRAINSTEM_HEIGHT,
  COUNTUP_MS,
  FADE_MS,
  FIELD_ALPHA,
  FIELD_ALPHA_AFTER,
  FIRE_P,
  FORK_GAP,
  GHOST_LABEL_MIN_P,
  GHOST_MS,
  HARD_VETO,
  HUES,
  INTENTS,
  KNOWN_INTENTS,
  LABELS_KO,
  MAX_FIRED,
  MAX_GHOST_ALPHA,
  MIN_GHOST_ALPHA,
  NEARLY_FULL,
  RING_INSET_PX,
  THINKING_ALPHA,
  WIRE_HOLD_MS,
  W_DEFAULT,
  appetiteWord,
  arbitrateProposals,
  candidateSummaryV2,
  combine,
  depthAt,
  effects,
  facts,
  fallbackCombine,
  gate,
  ghostsFrom,
  hasTSlot,
  proposalsFrom,
  wellPhrase,
} from "../public/neurons.js";

/** Build a board from an ASCII sketch of its bottom rows ('.' empty, any letter filled). */
function boardFrom(bottomRows) {
  const board = createEmptyBoard();
  const offset = ROWS - bottomRows.length;
  bottomRows.forEach((line, i) => {
    assert.equal(line.length, COLS, "sketch row must be 10 wide");
    for (let c = 0; c < COLS; c++) board[offset + i][c] = line[c] === "." ? 0 : line[c];
  });
  return board;
}

const cellsKey = (cells) => cells.map(([r, c]) => r + ":" + c).sort().join(",");
const findCells = (cands, cells) => cands.find((c) => cellsKey(c.cells) === cellsKey(cells));

const LOW = { survive: 0.1, clean: 0.1, build: 0.1, cash: 0.1, spin: 0.1, stay: null };
const FLAT_FACTS = { maxHeight: 3, holes: 0, bumpiness: 0, wellColumn: null, wellDepth: 0, rowsNearlyFull: 0, piecesSinceClear: 0 };
const NO_MEMORY = { previousIntent: null, hold: 0 };

// Synthetic candidates for the arithmetic stages: only id, cells and metrics.maxHeight matter.
function fakeCandidates(n, maxHeights = []) {
  return Array.from({ length: n }, (_, i) => ({
    id: "c" + i,
    cells: [[19, i], [18, i], [17, i], [16, i]],
    metrics: { maxHeight: maxHeights[i] ?? 5 },
    linesCleared: 0,
    tspin: null,
  }));
}
const answer = (probabilities) => {
  const choice = Object.entries(probabilities).sort((a, b) => b[1] - a[1])[0][0];
  return { choice, confidence: probabilities[choice], probabilities };
};
const intentOf = (fired, activations, extra = {}) => ({
  leading: fired[0],
  activations: { survive: 0, clean: 0, build: 0, cash: 0, spin: 0, ...activations },
  appetite: 1.8,
  appetiteWord: "moderate",
  fired,
  forced: false,
  stayed: false,
  ...extra,
});
const sum = (obj) => Object.values(obj).reduce((a, b) => a + b, 0);

// ---------------------------------------------------------------- constants

test("Appendix B constants and the palette are exported verbatim", () => {
  assert.deepEqual([...INTENTS], ["survive", "clean", "build", "cash", "spin"]);
  assert.deepEqual([...KNOWN_INTENTS], [...INTENTS]);
  assert.equal(FIRE_P, 0.5);
  assert.equal(MAX_FIRED, 3);
  assert.equal(BRAINSTEM_HEIGHT, 14);
  assert.equal(HARD_VETO, 0.65);
  assert.equal(W_DEFAULT, 0.5);
  assert.equal(FORK_GAP, 0.15);
  assert.equal(NEARLY_FULL, 8);
  assert.equal(GHOST_MS, 450);
  assert.equal(WIRE_HOLD_MS, 350);
  assert.equal(COUNTUP_MS, 200);
  assert.equal(FADE_MS, 220);
  assert.equal(MAX_GHOST_ALPHA, 0.55);
  assert.equal(MIN_GHOST_ALPHA, 0.14);
  assert.equal(GHOST_LABEL_MIN_P, 0.03);
  assert.equal(THINKING_ALPHA, 0.18);
  assert.deepEqual([...FIELD_ALPHA], [0.22, 0.12]);
  assert.equal(FIELD_ALPHA_AFTER, 0.06);
  assert.deepEqual([...RING_INSET_PX], [3, 6, 9]);
  assert.deepEqual(
    { ...HUES },
    { survive: "#ff4d6d", clean: "#2ee6d6", build: "#7c8cff", cash: "#ffd166", spin: "#f472b6", default: "#9aa3b8", veto: "#f87171", forced: "#fb923c" },
  );
  assert.equal(LABELS_KO.survive, "생존");
  assert.equal(LABELS_KO.clean, "정리");
  assert.equal(LABELS_KO.build, "빌드");
  assert.equal(LABELS_KO.cash, "현금");
  assert.equal(LABELS_KO.spin, "스핀");
  assert.equal(LABELS_KO.default, "습관");
});

// ---------------------------------------------------------------- percepts

test("facts: exactly the seven contract keys, rowsNearlyFull and wellColumn null below depth 2", () => {
  const board = boardFrom([
    ".........X", // 1 filled
    "XXXXXXXX..", // 8 filled → nearly full
    "XXXXXXXXX.", // 9 filled → nearly full
  ]);
  const f = facts(board, 4);
  assert.deepEqual(Object.keys(f).sort(), ["bumpiness", "holes", "maxHeight", "piecesSinceClear", "rowsNearlyFull", "wellColumn", "wellDepth"]);
  assert.equal(f.rowsNearlyFull, 2);
  assert.equal(f.piecesSinceClear, 4);
  assert.equal(f.maxHeight, 3);
  assert.equal(f.holes, 2); // (18,9) and (19,9) are empty under (17,9)

  const shallow = boardFrom(["XXXXXXXXX."]);
  assert.equal(shallow[19][9], 0);
  assert.equal(facts(shallow).wellDepth, 1);
  assert.equal(facts(shallow).wellColumn, null);

  const deep = boardFrom(["XXXXXXXXX.", "XXXXXXXXX.", "XXXXXXXXX."]);
  assert.equal(facts(deep).wellDepth, 3);
  assert.equal(facts(deep).wellColumn, 9);
  assert.equal(facts(createEmptyBoard()).rowsNearlyFull, 0);
});

test("depthAt: edges see an infinitely tall wall on the outside", () => {
  const heights = [0, 4, 4, 2, 4, 4, 4, 4, 4, 0];
  assert.equal(depthAt(heights, 0), 4);
  assert.equal(depthAt(heights, 9), 4);
  assert.equal(depthAt(heights, 3), 2);
  assert.equal(depthAt(heights, 1), -4); // min(0, 4) - 4: taller than its lower neighbour
});

// Three boards: a well kept open, a well filled, and no well at all.
const WELL_BOARD = boardFrom([
  "XXXXXXXXX.",
  "XXXXXXXXX.",
  ".XXXXXXXX.", // a hole at column 0 keeps the rows from clearing
  "XXXXXXXXX.",
]);

test("candidateSummaryV2 says when a placement keeps the well open", () => {
  const cands = reachablePlacements(WELL_BOARD, "O");
  const o = findCells(cands, [[14, 0], [14, 1], [15, 0], [15, 1]]);
  assert.ok(o, "O on the left edge");
  const s = candidateSummaryV2("O", o, WELL_BOARD);
  assert.ok(s.startsWith("O piece, rotation 0 (2x2 square); lands at columns 0-1, rows 14-15; clears no lines; after: max height 6 (+2), holes 1, "), s);
  assert.ok(s.includes("; keeps the well at column 9 open (depth 4)"), s);
  assert.ok(s.endsWith("; leaves a T-spin slot: no; top of piece 14 rows below the ceiling"), s);
  assert.equal(wellPhrase(facts(WELL_BOARD), o), "; keeps the well at column 9 open (depth 4)");
  const e = effects("O", o, WELL_BOARD);
  assert.equal(e, "O piece, rotation 0 (2x2 square); lands at columns 0-1, rows 14-15; clears no lines; keeps the well open; no new hole; peak higher; no T-spin slot");
});

test("candidateSummaryV2 says when a placement fills the well", () => {
  const cands = reachablePlacements(WELL_BOARD, "I");
  const i = cands.find((c) => c.cells.every(([, col]) => col === 9));
  assert.ok(i, "upright I in the well");
  assert.equal(i.linesCleared, 3); // row 17 keeps its hole
  const s = candidateSummaryV2("I", i, WELL_BOARD);
  assert.ok(s.includes("; clears 3 lines; after: "), s);
  assert.ok(s.includes("; fills the well at column 9"), s);
  assert.ok(s.includes("; top of piece 16 rows below the ceiling"), s);
  const e = effects("I", i, WELL_BOARD);
  assert.ok(e.includes("; clears 3 lines; fills the well; "), e);
  assert.ok(e.endsWith("; peak lower; no T-spin slot"), e);
});

test("candidateSummaryV2 says nothing about a well when there is none", () => {
  const board = createEmptyBoard();
  const cands = reachablePlacements(board, "I");
  const flat = cands.find((c) => c.rot === 0 && c.cells[0][1] === 0);
  assert.ok(flat);
  const s = candidateSummaryV2("I", flat, board);
  assert.equal(
    s,
    "I piece, rotation 0 (flat, 4 wide); lands at columns 0-3, row 19; clears no lines; after: max height 1 (+1), holes 0, bumpiness 1, aggregate height 4; leaves a T-spin slot: no; top of piece 19 rows below the ceiling",
  );
  assert.ok(!s.includes("well"));
  assert.equal(wellPhrase(facts(board), flat), "");
  const e = effects("I", flat, board);
  assert.equal(e, "I piece, rotation 0 (flat, 4 wide); lands at columns 0-3, row 19; clears no lines; no well; no new hole; peak higher; no T-spin slot");
});

test("T-spin slot detection: yes when a T-spin double is reachable afterwards, no otherwise", () => {
  const slotBoard = boardFrom([
    "..X..X....",
    "XXX...XXXX",
    "XXXX.XXXXX",
  ]);
  assert.equal(hasTSlot(slotBoard), true);
  assert.equal(hasTSlot(createEmptyBoard()), false);

  const o = reachablePlacements(slotBoard, "O").find((c) => c.cells.every(([, col]) => col >= 8));
  assert.ok(o, "O dropped at columns 8-9 leaves the slot alone");
  assert.ok(candidateSummaryV2("O", o, slotBoard).includes("; leaves a T-spin slot: yes; "));
  assert.ok(effects("O", o, slotBoard).endsWith("; leaves a T-spin slot"));

  // Taking the spin itself: the slot is gone afterwards and the summary carries the T-spin clause.
  const tsd = reachablePlacements(slotBoard, "T").find((c) => c.tspin === "full" && c.linesCleared === 2);
  assert.ok(tsd);
  const s = candidateSummaryV2("T", tsd, slotBoard);
  assert.ok(s.includes("; placed with a T-spin; clears 2 lines; after: "), s);
  assert.ok(s.includes("; leaves a T-spin slot: no; "), s);
  const e = effects("T", tsd, slotBoard);
  assert.ok(e.includes("; placed with a T-spin; clears 2 lines; "), e);
  assert.ok(e.includes("; uncovers a hole; peak lower; no T-spin slot"), e);
});

test("effects carries no numeric metrics and names added holes", () => {
  const board = boardFrom([
    "XXXXXXXX..",
    "XXXXXXXX..",
  ]);
  const cands = reachablePlacements(board, "O");
  for (const cand of cands) {
    const e = effects("O", cand, board);
    assert.ok(!e.includes("max height"), e);
    assert.ok(!e.includes("bumpiness"), e);
    assert.ok(!e.includes("aggregate"), e);
    assert.ok(!e.includes("holes "), e);
    assert.ok(!/depth \d/.test(e), e);
  }
  // O resting on the ledge at columns 7-8 roofs two cells of the pit: two holes.
  const roof = findCells(cands, [[16, 7], [16, 8], [17, 7], [17, 8]]);
  assert.ok(roof);
  assert.ok(effects("O", roof, board).includes("; adds 2 holes; "), effects("O", roof, board));
  assert.ok(candidateSummaryV2("O", roof, board).includes("holes 2 (+2)"));
  // An upright T (nub right) standing on the left edge roofs the cell under its nub: one hole.
  const t = findCells(reachablePlacements(board, "T"), [[15, 0], [16, 0], [16, 1], [17, 0]]);
  assert.ok(t);
  assert.ok(effects("T", t, board).includes("; adds a hole; "), effects("T", t, board));
});

test("appetiteWord boundaries", () => {
  assert.equal(appetiteWord(0), "none");
  assert.equal(appetiteWord(0.4), "none");
  assert.equal(appetiteWord(0.5), "low");
  assert.equal(appetiteWord(1.4), "low");
  assert.equal(appetiteWord(1.5), "moderate");
  assert.equal(appetiteWord(2.4), "moderate");
  assert.equal(appetiteWord(2.5), "bold");
  assert.equal(appetiteWord(3), "bold");
});

// ---------------------------------------------------------------- gate

test("gate (a): two neurons at or above 0.5 both fire, ordered by activation", () => {
  const intent = gate({ ...LOW, cash: 0.61, build: 0.92 }, 1.8, FLAT_FACTS, NO_MEMORY);
  assert.deepEqual(intent.fired, ["build", "cash"]);
  assert.equal(intent.leading, "build");
  assert.equal(intent.forced, false);
  assert.equal(intent.stayed, false);
  assert.equal(intent.appetite, 1.8);
  assert.equal(intent.appetiteWord, "moderate");
  assert.deepEqual(Object.keys(intent).sort(), ["activations", "appetite", "appetiteWord", "fired", "forced", "leading", "stayed"]);
  assert.deepEqual(intent.activations, { survive: 0.1, clean: 0.1, build: 0.92, cash: 0.61, spin: 0.1 });
});

test("gate (b): nothing above the threshold fires the argmax alone", () => {
  const intent = gate({ ...LOW, clean: 0.3 }, 0.2, FLAT_FACTS, NO_MEMORY);
  assert.deepEqual(intent.fired, ["clean"]);
  assert.equal(intent.leading, "clean");
});

test("gate (c): four above the threshold are trimmed to three, the leader survives", () => {
  const intent = gate({ survive: 0.1, clean: 0.9, build: 0.8, cash: 0.7, spin: 0.6, stay: null }, 2, FLAT_FACTS, NO_MEMORY);
  assert.deepEqual(intent.fired, ["clean", "build", "cash"]);
  assert.equal(intent.leading, "clean");
  assert.equal(intent.fired.length, MAX_FIRED);
});

test("gate (d): the brainstem forces survive at height 14 and trimming keeps it and the leader", () => {
  const facts14 = { ...FLAT_FACTS, maxHeight: 14 };
  const intent = gate({ survive: 0.1, clean: 0.9, build: 0.8, cash: 0.7, spin: 0.6, stay: null }, 2, facts14, NO_MEMORY);
  assert.equal(intent.forced, true);
  assert.equal(intent.fired.length, 3);
  assert.ok(intent.fired.includes("survive"));
  assert.ok(intent.fired.includes("clean"));
  assert.deepEqual(intent.fired, ["clean", "build", "survive"]);
  assert.equal(intent.leading, "clean");
  // Not forced when survive already fires on its own.
  const own = gate({ ...LOW, survive: 0.7 }, 0, facts14, NO_MEMORY);
  assert.equal(own.forced, false);
  assert.deepEqual(own.fired, ["survive"]);
  // Not forced below the threshold height.
  assert.equal(gate({ ...LOW, clean: 0.6 }, 0, { ...FLAT_FACTS, maxHeight: 13 }, NO_MEMORY).forced, false);
});

test("gate (e): a held plan re-enters through stay", () => {
  const intent = gate({ ...LOW, build: 0.3, cash: 0.8, stay: 0.9 }, 1, FLAT_FACTS, { previousIntent: "build", hold: 0.8 });
  assert.ok(intent.activations.build >= 0.72, String(intent.activations.build));
  assert.equal(intent.stayed, true);
  assert.ok(intent.fired.includes("build"));
  assert.deepEqual(intent.fired, ["cash", "build"]);
  // The boost never lowers an activation that was already higher.
  const higher = gate({ ...LOW, build: 0.95, stay: 0.9 }, 1, FLAT_FACTS, { previousIntent: "build", hold: 0.8 });
  assert.equal(higher.activations.build, 0.95);
  assert.equal(higher.stayed, true);
});

test("gate (f): no previous intent means stay is ignored", () => {
  const intent = gate({ ...LOW, clean: 0.6, stay: 0.95 }, 1, FLAT_FACTS, { previousIntent: null, hold: 1 });
  assert.equal(intent.stayed, false);
  assert.deepEqual(intent.fired, ["clean"]);
  assert.deepEqual(intent.activations, { survive: 0.1, clean: 0.6, build: 0.1, cash: 0.1, spin: 0.1 });
});

test("gate (g): ties go to the previous intent, else to INTENTS order", () => {
  const tied = { ...LOW, build: 0.6, cash: 0.6 };
  assert.equal(gate(tied, 1, FLAT_FACTS, { previousIntent: "cash", hold: 0 }).leading, "cash");
  assert.deepEqual(gate(tied, 1, FLAT_FACTS, { previousIntent: "cash", hold: 0 }).fired, ["build", "cash"]);
  assert.equal(gate(tied, 1, FLAT_FACTS, NO_MEMORY).leading, "build");
  assert.equal(gate(tied, 1, FLAT_FACTS, { previousIntent: "spin", hold: 0 }).leading, "build");
});

test("gate (h): hold 0 means the stay answer changes nothing", () => {
  const intent = gate({ ...LOW, build: 0.2, clean: 0.7, stay: 0.99 }, 1, FLAT_FACTS, { previousIntent: "build", hold: 0 });
  assert.equal(intent.stayed, false);
  assert.equal(intent.activations.build, 0.2);
  assert.deepEqual(intent.fired, ["clean"]);
  // Below the threshold, stay does not count either.
  const weak = gate({ ...LOW, build: 0.2, clean: 0.7, stay: 0.4 }, 1, FLAT_FACTS, { previousIntent: "build", hold: 1 });
  assert.equal(weak.stayed, false);
});

test("gate (i): appetite is rounded to one decimal and the word follows the rounded value", () => {
  const at = (v) => gate(LOW, v, FLAT_FACTS, NO_MEMORY);
  assert.equal(at(0.5).appetiteWord, "low");
  assert.equal(at(0.49).appetiteWord, "low"); // rounds to 0.5
  assert.equal(at(0.44).appetiteWord, "none");
  assert.equal(at(1.5).appetiteWord, "moderate");
  assert.equal(at(1.46).appetiteWord, "moderate");
  assert.equal(at(1.44).appetiteWord, "low");
  assert.equal(at(2.5).appetiteWord, "bold");
  assert.equal(at(2.44).appetiteWord, "moderate");
  assert.equal(at(1.84).appetite, 1.8);
  assert.equal(at({ value: 2.7, confidence: 0.5 }).appetite, 2.7);
});

// ---------------------------------------------------------------- proposalsFrom

test("proposalsFrom: agreeing neurons yield one proposal plus the leader's second thought", () => {
  const cands = fakeCandidates(4);
  const intent = intentOf(["build", "cash"], { build: 0.92, cash: 0.61 });
  const motor = {
    build: answer({ c0: 0.1, c1: 0.7, c2: 0.2, c3: 0 }),
    cash: answer({ c0: 0.2, c1: 0.6, c2: 0.2, c3: 0 }),
    default: answer({ c0: 0.05, c1: 0.8, c2: 0.15, c3: 0 }),
  };
  const r = proposalsFrom(motor, intent, cands);
  assert.equal(r.proposals.length, 2);
  assert.equal(r.proposals[0].id, "c1");
  assert.deepEqual(r.proposals[0].backers, ["build", "cash", "default"]);
  assert.equal(r.proposals[0].alt, false);
  assert.equal(r.proposals[1].id, "c2");
  assert.deepEqual(r.proposals[1].backers, ["build"]);
  assert.equal(r.proposals[1].alt, true);
  assert.equal(r.proposals[1].cand, cands[2]);
  assert.ok(Math.abs(r.proposals[0].E - (0.92 * 0.7 + 0.61 * 0.6 + 0.5 * 0.8)) < 1e-9);
  assert.ok(Math.abs(r.proposals[1].E - 0.92 * 0.2) < 1e-9);
  assert.deepEqual(r.proposals[0].m, { build: 0.7, cash: 0.6, default: 0.8 });
  assert.deepEqual(r.picks, { build: "c1", cash: "c1", default: "c1" });
  assert.deepEqual(r.confidence, { build: 0.7, cash: 0.6, default: 0.8 });
  assert.equal(r.disagreement, false);
  assert.equal(r.fork, false);
});

test("proposalsFrom: differing argmaxes need no ALT; the habit alone can back a spot", () => {
  const cands = fakeCandidates(4);
  const intent = intentOf(["build", "cash"], { build: 0.7, cash: 0.62 });
  const motor = {
    build: answer({ c0: 0.1, c1: 0.7, c2: 0.2 }),
    cash: answer({ c0: 0.55, c1: 0.3, c2: 0.15 }),
    default: answer({ c0: 0.1, c1: 0.1, c2: 0.1, c3: 0.7 }),
  };
  const r = proposalsFrom(motor, intent, cands);
  assert.deepEqual(r.proposals.map((p) => p.id), ["c1", "c0", "c3"]);
  assert.deepEqual(r.proposals.map((p) => p.backers), [["build"], ["cash"], ["default"]]);
  assert.ok(r.proposals.every((p) => p.alt === false));
  assert.ok(Math.abs(r.proposals[2].E - 0.5 * 0.7) < 1e-9);
  assert.equal(r.disagreement, true);
  assert.equal(r.fork, true); // 0.70 - 0.62 < 0.15 and their picks differ
  // The motor field: each fired neuron's 2nd and 3rd picks that are not proposals.
  const buildField = r.motorField.filter((f) => f.neuron === "build");
  assert.deepEqual(buildField.map((f) => [f.id, f.rank]), [["c2", 2]]); // c0 (rank 3) is a proposal
  const cashField = r.motorField.filter((f) => f.neuron === "cash");
  assert.deepEqual(cashField.map((f) => [f.id, f.rank]), [["c2", 3]]);
  assert.ok(r.motorField.every((f) => f.cand && f.p > 0));
});

test("proposalsFrom: fork needs both a close race and differing picks", () => {
  const cands = fakeCandidates(3);
  const motor = { build: answer({ c0: 0.9 }), cash: answer({ c1: 0.9 }), default: answer({ c0: 0.9 }) };
  assert.equal(proposalsFrom(motor, intentOf(["build", "cash"], { build: 0.9, cash: 0.6 }), cands).fork, false);
  const same = { build: answer({ c0: 0.9 }), cash: answer({ c0: 0.9 }), default: answer({ c1: 0.9 }) };
  assert.equal(proposalsFrom(same, intentOf(["build", "cash"], { build: 0.7, cash: 0.65 }), cands).fork, false);
  assert.equal(proposalsFrom(same, intentOf(["build", "cash"], { build: 0.7, cash: 0.65 }), cands).disagreement, false);
});

test("proposalsFrom: unknown ids are ignored, argmax ties go to the lowest candidate index", () => {
  const cands = fakeCandidates(12);
  const intent = intentOf(["spin"], { spin: 0.8 });
  const motor = {
    spin: answer({ zzz: 0.9, c11: 0.4, c2: 0.4 }),
    default: answer({ nope: 1 }),
  };
  const r = proposalsFrom(motor, intent, cands);
  assert.equal(r.picks.spin, "c2"); // tie with c11 → lower index, not string order
  assert.equal(r.picks.default, "c0"); // a flat distribution → first candidate
  assert.ok(!r.proposals.some((p) => p.id === "zzz" || p.id === "nope"));
  assert.equal(r.P.spin.zzz, undefined);
  assert.equal(r.P.spin.c11, 0.4);
  assert.deepEqual(r.proposals.map((p) => p.id), ["c2", "c0"]);
  assert.ok(r.proposals.every((p) => !p.alt));
});

test("proposalsFrom: a fired neuron without a motor answer is skipped; a known choice rescues a flat distribution", () => {
  const cands = fakeCandidates(3);
  const intent = intentOf(["build", "cash"], { build: 0.9, cash: 0.6 });
  const motor = { build: { choice: "c2", confidence: 0, probabilities: {} }, default: answer({ c0: 1 }) };
  const r = proposalsFrom(motor, intent, cands);
  assert.deepEqual(r.picks, { build: "c2", default: "c0" });
  assert.deepEqual(r.proposals.map((p) => p.id), ["c2", "c0"]);
  assert.equal(r.disagreement, false);
});

test("arbitrateProposals shapes the 5.3 request body", () => {
  const cands = fakeCandidates(3);
  const r = proposalsFrom({ build: answer({ c0: 0.9, c1: 0.1 }), default: answer({ c0: 0.9, c1: 0.1 }) }, intentOf(["build"], { build: 0.9 }), cands);
  const body = arbitrateProposals(r, { c0: "E0", c1: "E1" });
  assert.deepEqual(body, [
    { id: "c0", backedBy: ["build", "default"], alt: false, effects: "E0" },
    { id: "c1", backedBy: ["build"], alt: true, effects: "E1" },
  ]);
  assert.deepEqual(arbitrateProposals(r, new Map([["c0", "M0"]]))[0].effects, "M0");
});

// ---------------------------------------------------------------- combine

// Two fired neurons disagreeing, the habit siding with the leader: proposals c1 (build+default), c0 (cash).
function twoWay(maxHeights) {
  const cands = fakeCandidates(4, maxHeights);
  const intent = intentOf(["build", "cash"], { build: 0.92, cash: 0.61 });
  const motor = {
    build: answer({ c0: 0.1, c1: 0.7, c2: 0.2 }),
    cash: answer({ c0: 0.55, c1: 0.3, c2: 0.15 }),
    default: answer({ c0: 0.2, c1: 0.8 }),
  };
  return { cands, intent, props: proposalsFrom(motor, intent, cands) };
}
const HOLD = { value: 1.4, confidence: 0.6, probabilities: { 0: 0.1, 1: 0.4, 2: 0.5 } };

test("combine: a hard veto zeroes a proposal and the rest is normalised", () => {
  const { cands, intent, props } = twoWay();
  const arb = { choice: "c0", confidence: 0.6, probabilities: { c0: 0.6, c1: 0.4 } };
  const r = combine(arb, { c0: 0.7, c1: 0.12 }, HOLD, props, intent, cands);
  assert.equal(r.final.c0, 0);
  assert.equal(r.final.c1, 1);
  assert.deepEqual(r.hardVetoed, ["c0"]);
  assert.equal(r.allVetoed, false);
  assert.equal(r.chosenId, "c1");
  assert.equal(r.chosen, cands[1]);
  assert.equal(r.vetoedTop, true); // the arbiter's first choice was the vetoed one
  assert.equal(r.ledBy, "build");
  assert.equal(r.override, false);
  assert.equal(r.changed, false); // the habit also picked c1
  assert.equal(r.fallback, false);
  assert.deepEqual(r.memoryNext, { previousIntent: "build", hold: 0.7 });
  assert.equal(r.proposals, props.proposals);
  assert.equal(r.disagreement, true);
  assert.deepEqual(r.A, { c1: 0.4, c0: 0.6 });
  assert.deepEqual(r.V, { c1: 0.12, c0: 0.7 });
});

test("combine: soft vetoes scale, the sum is 1, below 0.65 nothing is zeroed", () => {
  const { cands, intent, props } = twoWay();
  const arb = { choice: "c1", confidence: 0.7, probabilities: { c1: 0.7, c0: 0.3 } };
  const r = combine(arb, { c1: 0.5, c0: 0.64 }, HOLD, props, intent, cands);
  assert.deepEqual(r.hardVetoed, []);
  assert.ok(Math.abs(sum(r.final) - 1) < 1e-9);
  const rawC1 = 0.7 * 0.5;
  const rawC0 = 0.3 * 0.36;
  assert.ok(Math.abs(r.final.c1 - rawC1 / (rawC1 + rawC0)) < 1e-9);
  assert.ok(r.final.c0 > 0);
  assert.equal(r.chosenId, "c1");
  assert.equal(r.vetoedTop, false);
});

test("combine: when the coach stops everything, the raw distribution is played", () => {
  const { cands, intent, props } = twoWay();
  const arb = { choice: "c0", confidence: 0.55, probabilities: { c0: 0.55, c1: 0.45 } };
  const r = combine(arb, { c0: 0.9, c1: 0.7 }, HOLD, props, intent, cands);
  assert.equal(r.allVetoed, true);
  assert.deepEqual(r.hardVetoed.sort(), ["c0", "c1"]);
  assert.ok(Math.abs(sum(r.final) - 1) < 1e-9);
  const rawC0 = 0.55 * 0.1;
  const rawC1 = 0.45 * 0.3;
  assert.ok(Math.abs(r.final.c1 - rawC1 / (rawC0 + rawC1)) < 1e-9);
  assert.equal(r.chosenId, "c1"); // less vetoed wins on raw
  assert.equal(r.vetoedTop, true);
});

test("combine: an arbiter with no mass falls back to uniform, ties resolve by E then max height then index", () => {
  // Equal final → larger E wins (c1: build+cash+default backing vs c0: cash alone).
  const { cands, intent, props } = twoWay();
  const flat = { choice: "c0", confidence: 0.5, probabilities: { c0: 0.5, c1: 0.5 } };
  const r = combine(flat, {}, HOLD, props, intent, cands);
  assert.equal(r.chosenId, "c1");
  assert.ok(Math.abs(r.final.c0 - 0.5) < 1e-9);

  // Zero arbiter → uniform and the same tie chain.
  const zero = { choice: "c0", confidence: 0, probabilities: {} };
  const u = combine(zero, {}, HOLD, props, intent, cands);
  assert.deepEqual(u.final, { c1: 0.5, c0: 0.5 });
  assert.equal(u.chosenId, "c1");

  // Equal E → lower max height after.
  const c2 = fakeCandidates(3, [9, 4, 6]);
  const i2 = intentOf(["build", "cash"], { build: 0.6, cash: 0.6 });
  const m2 = { build: answer({ c0: 0.5, c1: 0.3, c2: 0.2 }), cash: answer({ c1: 0.5, c0: 0.3 }), default: answer({ c2: 0.9 }) };
  const p2 = proposalsFrom(m2, i2, c2);
  assert.ok(Math.abs(p2.proposals[0].E - p2.proposals[1].E) < 1e-9);
  const t2 = combine({ choice: "c0", confidence: 0.5, probabilities: { c0: 0.5, c1: 0.5, c2: 0 } }, {}, HOLD, p2, i2, c2);
  assert.equal(t2.chosenId, "c1"); // maxHeight 4 < 9

  // Equal E and equal max height → lower candidate index.
  const c3 = fakeCandidates(3, [5, 5, 5]);
  const p3 = proposalsFrom(m2, i2, c3);
  const t3 = combine({ choice: "c1", confidence: 0.5, probabilities: { c0: 0.5, c1: 0.5 } }, {}, HOLD, p3, i2, c3);
  assert.equal(t3.chosenId, "c0");
});

test("combine: override is false for an ALT win, true for a weaker backer, true for the habit alone", () => {
  const cands = fakeCandidates(4);
  // ALT case: everyone agrees on c1; the leader's second thought c2 wins.
  const agree = intentOf(["build", "cash"], { build: 0.92, cash: 0.61 });
  const pa = proposalsFrom(
    { build: answer({ c1: 0.7, c2: 0.3 }), cash: answer({ c1: 0.6, c0: 0.4 }), default: answer({ c1: 0.8, c3: 0.2 }) },
    agree,
    cands,
  );
  assert.equal(pa.proposals[1].alt, true);
  const ra = combine({ choice: "c2", confidence: 0.8, probabilities: { c1: 0.2, c2: 0.8 } }, {}, HOLD, pa, agree, cands);
  assert.equal(ra.chosenId, "c2");
  assert.equal(ra.override, false);
  assert.equal(ra.ledBy, "build");
  assert.equal(ra.changed, true); // the habit picked c1
  assert.deepEqual(ra.memoryNext, { previousIntent: "build", hold: 0.7 });

  // Weaker backer wins: cash's c0 beats build's c1.
  const { intent, props } = twoWay();
  const rw = combine({ choice: "c0", confidence: 0.7, probabilities: { c0: 0.7, c1: 0.3 } }, {}, HOLD, props, intent, cands);
  assert.equal(rw.chosenId, "c0");
  assert.equal(rw.override, true);
  assert.equal(rw.ledBy, "cash");
  assert.equal(rw.changed, true);
  assert.deepEqual(rw.memoryNext, { previousIntent: "cash", hold: 0.7 });

  // The habit alone wins: override, ledBy default, memory cleared, not changed.
  const pd = proposalsFrom(
    { build: answer({ c1: 0.7, c2: 0.3 }), cash: answer({ c0: 0.6, c1: 0.4 }), default: answer({ c3: 0.9, c1: 0.1 }) },
    intent,
    cands,
  );
  const rd = combine({ choice: "c3", confidence: 0.9, probabilities: { c3: 0.9, c1: 0.05, c0: 0.05 } }, {}, { value: 2 }, pd, intent, cands);
  assert.equal(rd.chosenId, "c3");
  assert.equal(rd.override, true);
  assert.equal(rd.ledBy, "default");
  assert.equal(rd.changed, false);
  assert.deepEqual(rd.memoryNext, { previousIntent: null, hold: 1 });
});

test("combine: a shared backer wins as the strongest fired backer, hold accepts a bare number or null", () => {
  const cands = fakeCandidates(3);
  const intent = intentOf(["build", "cash"], { build: 0.7, cash: 0.9 }, { leading: "cash" });
  const props = proposalsFrom({ build: answer({ c0: 0.8 }), cash: answer({ c0: 0.6 }), default: answer({ c1: 0.9 }) }, intent, cands);
  const r = combine({ choice: "c0", confidence: 0.9, probabilities: { c0: 0.9, c1: 0.1 } }, {}, 1, props, intent, cands);
  assert.equal(r.ledBy, "cash");
  assert.equal(r.override, false);
  assert.deepEqual(r.memoryNext, { previousIntent: "cash", hold: 0.5 });
  assert.deepEqual(combine({ probabilities: { c0: 1 } }, {}, null, props, intent, cands).memoryNext, { previousIntent: "cash", hold: 0 });
  assert.equal(combine({ probabilities: { c0: 1 } }, { c0: { value: 0.7 } }, null, props, intent, cands).hardVetoed[0], "c0");
});

// ---------------------------------------------------------------- fallbackCombine

test("fallbackCombine: argmax E wins, ledBy is fallback, final is E normalised", () => {
  const { cands, props } = twoWay();
  const r = fallbackCombine(props, cands);
  assert.equal(r.ledBy, "fallback");
  assert.equal(r.chosenId, "c1");
  assert.equal(r.chosen, cands[1]);
  assert.equal(r.fallback, true);
  const E1 = props.proposals.find((p) => p.id === "c1").E;
  const E0 = props.proposals.find((p) => p.id === "c0").E;
  assert.ok(Math.abs(r.final.c1 - E1 / (E1 + E0)) < 1e-9);
  assert.ok(Math.abs(sum(r.final) - 1) < 1e-9);
  assert.deepEqual(r.memoryNext, { previousIntent: null, hold: 0 });
  assert.deepEqual(r.hardVetoed, []);
  assert.equal(r.allVetoed, false);
  assert.equal(r.override, false);
  assert.equal(r.vetoedTop, false);
  assert.equal(r.changed, false);
  assert.equal(r.proposals, props.proposals);
});

// ---------------------------------------------------------------- ghostsFrom

test("ghostsFrom: colour, alpha, label, rings, vetoed and chosen flags; field ghosts have no label", () => {
  const { cands, intent, props } = twoWay();
  const arb = { choice: "c1", confidence: 0.61, probabilities: { c1: 0.61, c0: 0.39 } };
  const r = combine(arb, { c1: 0.1, c0: 0.7 }, HOLD, props, intent, cands);
  const ghosts = ghostsFrom(r);
  const g1 = ghosts.find((g) => g.id === "c1");
  const g0 = ghosts.find((g) => g.id === "c0");
  assert.ok(g1 && g0);

  assert.equal(g1.color, HUES.build);
  assert.equal(g1.chosen, true);
  assert.equal(g1.vetoed, false);
  assert.equal(g1.p, 1);
  assert.equal(g1.alpha, MAX_GHOST_ALPHA);
  assert.equal(g1.label, "100%");
  assert.equal(g1.tag, "빌드·습관 · 선택");
  assert.deepEqual(g1.rings, [HUES.build, HUES.default]);
  assert.equal(g1.cells, cands[1].cells);
  assert.equal(g1.dashed, false);
  assert.equal(g1.faint, false);

  assert.equal(g0.vetoed, true);
  assert.equal(g0.chosen, false);
  assert.equal(g0.alpha, 0.1);
  assert.equal(g0.label, "0%");
  assert.equal(g0.tag, "VETO");
  assert.equal(g0.color, HUES.cash);
  assert.deepEqual(g0.rings, []);

  // Motor field: build's and cash's c2 (rank 3), faint, unlabelled, in the neuron's hue.
  const field = ghosts.filter((g) => g.faint);
  assert.ok(field.length >= 1);
  for (const f of field) {
    assert.equal(f.label, null);
    assert.equal(f.tag, null);
    assert.equal(f.alpha, FIELD_ALPHA_AFTER);
    assert.deepEqual(f.rings, []);
    assert.equal(f.chosen, false);
    assert.equal(f.vetoed, false);
    assert.ok([HUES.build, HUES.cash].includes(f.color));
  }
  const inflight = ghostsFrom(r, FIELD_ALPHA).filter((g) => g.faint);
  assert.deepEqual(inflight.map((g) => [g.color, g.alpha]), [[HUES.build, 0.22], [HUES.cash, 0.12]]); // build's rank 2, cash's rank 3
});

test("ghostsFrom: alpha follows the current heatmap formula, ALT ghosts are dashed in the leader hue", () => {
  const cands = fakeCandidates(4);
  const intent = intentOf(["spin"], { spin: 0.8 });
  const props = proposalsFrom({ spin: answer({ c0: 0.6, c1: 0.4 }), default: answer({ c0: 0.9, c1: 0.1 }) }, intent, cands);
  const arb = { choice: "c0", confidence: 0.8, probabilities: { c0: 0.8, c1: 0.2 } };
  const r = combine(arb, { c0: 0, c1: 0 }, HOLD, props, intent, cands);
  const [g0, g1] = ghostsFrom(r);
  assert.equal(g0.alpha, MAX_GHOST_ALPHA);
  assert.ok(Math.abs(g1.alpha - Math.max(MIN_GHOST_ALPHA, MAX_GHOST_ALPHA * 0.25)) < 1e-9);
  assert.equal(g1.label, "20%");
  assert.equal(g1.dashed, true);
  assert.equal(g1.alt, true);
  assert.equal(g1.color, HUES.spin);
  assert.equal(g1.tag, "스핀");
  assert.deepEqual(g1.rings, [HUES.spin]);
  assert.equal(g0.tag, "스핀·습관 · 선택");

  // A tiny probability drops below the labelled floor.
  const r2 = combine({ choice: "c0", confidence: 0.99, probabilities: { c0: 0.99, c1: 0.01 } }, {}, HOLD, props, intent, cands);
  const tiny = ghostsFrom(r2).find((g) => g.id === "c1");
  assert.ok(tiny.alpha < MIN_GHOST_ALPHA);
  assert.equal(tiny.label, "1%");
});

test("ghostsFrom: the fallback verdict carries a FALLBACK pill instead of labels", () => {
  const { cands, props } = twoWay();
  const ghosts = ghostsFrom(fallbackCombine(props, cands)).filter((g) => !g.faint);
  assert.ok(ghosts.every((g) => g.label === null));
  assert.equal(ghosts.find((g) => g.chosen).tag, "FALLBACK · 선택");
  assert.equal(ghosts.find((g) => !g.chosen).tag, "FALLBACK");
});
