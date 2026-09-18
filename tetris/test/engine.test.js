import test from "node:test";
import assert from "node:assert/strict";
import {
  COLS,
  ROWS,
  PIECE_TYPES,
  ROTATIONS,
  boardToAscii,
  candidateSummary,
  clearLines,
  columnHeights,
  computeMetrics,
  createEmptyBoard,
  enumeratePlacements,
  lineScore,
  rotationLabel,
  shuffledBag,
} from "../public/engine.js";

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

test("unique rotation counts collapse duplicate shapes", () => {
  assert.equal(ROTATIONS.O.length, 1);
  assert.equal(ROTATIONS.I.length, 2);
  assert.equal(ROTATIONS.S.length, 2);
  assert.equal(ROTATIONS.Z.length, 2);
  assert.equal(ROTATIONS.T.length, 4);
  assert.equal(ROTATIONS.L.length, 4);
  assert.equal(ROTATIONS.J.length, 4);
});

test("candidate counts on an empty board", () => {
  const board = createEmptyBoard();
  const counts = Object.fromEntries(
    PIECE_TYPES.map((t) => [t, enumeratePlacements(board, t).length]),
  );
  assert.deepEqual(counts, { O: 9, I: 17, S: 17, Z: 17, T: 34, L: 34, J: 34 });
});

test("every candidate is well formed and lands inside the board", () => {
  const board = createEmptyBoard();
  for (const type of PIECE_TYPES) {
    const cands = enumeratePlacements(board, type);
    const ids = new Set(cands.map((c) => c.id));
    assert.equal(ids.size, cands.length, type + " ids must be unique");
    for (const c of cands) {
      assert.equal(c.cells.length, 4);
      for (const [r, col] of c.cells) {
        assert.ok(r >= 0 && r < ROWS, "row in range");
        assert.ok(col >= 0 && col < COLS, "col in range");
      }
      assert.equal(c.boardAfter.length, ROWS);
      assert.equal(c.boardAfter[0].length, COLS);
      assert.ok(typeof c.metrics.holes === "number");
    }
    // On an empty board every piece rests on the floor.
    for (const c of cands) {
      const maxRow = Math.max(...c.cells.map((x) => x[0]));
      assert.equal(maxRow, ROWS - 1, type + " must hard-drop to the floor");
    }
  }
});

test("a piece that completes the bottom row clears it and the stack drops one row", () => {
  // Bottom row filled except column 9; nothing else on the board.
  const board = boardFrom(["XXXXXXXXX."]);

  // Upright I in column 9 fills rows 16-19 of that column, completing row 19.
  const cand = enumeratePlacements(board, "I").find((c) => c.col === 9 && c.rot === 1);
  assert.ok(cand, "upright I in column 9 must be a candidate");

  assert.equal(cand.linesCleared, 1);
  assert.deepEqual(
    cand.cells,
    [[16, 9], [17, 9], [18, 9], [19, 9]],
    "the piece occupies four rows before the clear",
  );

  // Top row of the resulting board is empty.
  assert.ok(cand.boardAfter[0].every((v) => v === 0));

  // The piece stood 4 tall before the clear; afterwards the stack is 3 tall: one row less.
  const heightBeforeClear = 4;
  assert.equal(cand.metrics.maxHeight, heightBeforeClear - 1);
  assert.deepEqual(columnHeights(cand.boardAfter), [0, 0, 0, 0, 0, 0, 0, 0, 0, 3]);
  assert.equal(cand.metrics.holes, 0);
});

test("holes, bumpiness and wells match hand-computed values", () => {
  //            col: 0123456789
  const board = boardFrom([
    "X.X.......", // row 17
    "XX........", // row 18
    "XXX.......", // row 19  -> col3 stays empty here
  ]);
  // col0 filled rows 17,18,19          -> height 3
  // col1 filled rows 18,19             -> height 2
  // col2 filled rows 17 and 19, 18 gap -> height 3, one hole
  // col3..col9 empty                   -> height 0
  const m = computeMetrics(board);
  assert.deepEqual(m.heights, [3, 2, 3, 0, 0, 0, 0, 0, 0, 0]);
  assert.equal(m.maxHeight, 3);
  assert.equal(m.aggregateHeight, 8);
  assert.equal(m.holes, 1, "only the gap under col2's top cell counts");
  // |3-2| + |2-3| + |3-0| + 0*6 = 1 + 1 + 3 = 5
  assert.equal(m.bumpiness, 5);
  // col1 sits 1 below both neighbours; that is the deepest well.
  assert.equal(m.wellCol, 1);
  assert.equal(m.wellDepth, 1);
});

test("holes are counted per column under any filled cell", () => {
  const board = boardFrom([
    "X.........", // row 16
    "..........", // row 17  -> hole under col0
    "..........", // row 18  -> hole under col0
    "X........X", // row 19
  ]);
  const m = computeMetrics(board);
  assert.equal(m.holes, 2);
  assert.deepEqual(m.heights, [4, 0, 0, 0, 0, 0, 0, 0, 0, 1]);
  assert.equal(m.bumpiness, 4 + 0 + 0 + 0 + 0 + 0 + 0 + 0 + 1);
});

test("boardToAscii renders a header plus 20 rows, each 10 wide", () => {
  const board = boardFrom(["T.........", "TTT......."]);
  const lines = boardToAscii(board).split("\n");
  assert.equal(lines.length, 21);
  for (const line of lines) assert.equal(line.length, 10);
  assert.equal(lines[0], "0123456789");
  assert.equal(lines[1], "..........");
  assert.equal(lines[19], "T.........");
  assert.equal(lines[20], "TTT.......");
});

test("clearLines removes only full rows and refills from the top", () => {
  const board = boardFrom(["XXXXXXXXX.", "XXXXXXXXXX", "XXXXXXXXXX"]);
  const { board: after, linesCleared } = clearLines(board);
  assert.equal(linesCleared, 2);
  assert.equal(after.length, ROWS);
  assert.ok(after[0].every((v) => v === 0));
  assert.deepEqual(columnHeights(after), [1, 1, 1, 1, 1, 1, 1, 1, 1, 0]);
});

test("line scoring follows 100/300/500/800", () => {
  assert.deepEqual([0, 1, 2, 3, 4].map(lineScore), [0, 100, 300, 500, 800]);
});

test("candidateSummary reads as one sentence with before/after deltas", () => {
  const board = createEmptyBoard();
  const cand = enumeratePlacements(board, "T").find((c) => c.rot === 2 && c.col === 3);
  const summary = candidateSummary("T", cand, board);
  assert.equal(
    summary,
    "T piece, rotation 2 (flat side up), lands at columns 3-5, rows 18-19; clears no lines; " +
      "after: max height 2 (+2), holes 2 (+2), bumpiness 4, aggregate height 6",
  );
  assert.equal(rotationLabel("T", 2), "flat side up");
});

test("candidateSummary reports a cleared line and a single column", () => {
  const board = boardFrom(["XXXXXXXXX."]);
  const cand = enumeratePlacements(board, "I").find((c) => c.col === 9 && c.rot === 1);
  const summary = candidateSummary("I", cand, board);
  assert.match(summary, /^I piece, rotation 1 \(upright, 4 tall\), lands at column 9, rows 16-19; clears 1 line;/);
  assert.match(summary, /holes 0/);
});

test("a piece is skipped when it would stick out over the ceiling", () => {
  // Every column is full to the ceiling except column 0, an open 20-deep shaft.
  const board = createEmptyBoard();
  for (let r = 0; r < ROWS; r++) for (let c = 1; c < COLS; c++) board[r][c] = "X";
  // The flat I is 4 wide and always overlaps a full column, so it has no landing at all.
  // The upright I is 1 wide and drops cleanly down the shaft.
  const cands = enumeratePlacements(board, "I");
  assert.deepEqual(
    cands.map((c) => [c.rot, c.col]),
    [[1, 0]],
    "the flat I cannot fit anywhere and only the shaft accepts the upright I",
  );
});

test("a full board yields no candidates", () => {
  const board = createEmptyBoard();
  for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) board[r][c] = "X";
  for (const t of PIECE_TYPES) assert.deepEqual(enumeratePlacements(board, t), []);
});

test("enumeratePlacements does not mutate the board it is given", () => {
  const board = boardFrom(["XXXXXXXXX."]);
  const snapshot = JSON.stringify(board);
  enumeratePlacements(board, "T");
  assert.equal(JSON.stringify(board), snapshot);
});

test("shuffledBag returns each piece exactly once", () => {
  for (let i = 0; i < 50; i++) {
    const bag = shuffledBag();
    assert.equal(bag.length, 7);
    assert.deepEqual(bag.slice().sort(), PIECE_TYPES.slice().sort());
  }
});
