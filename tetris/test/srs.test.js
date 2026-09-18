import test from "node:test";
import assert from "node:assert/strict";
import { COLS, ROWS, PIECE_TYPES, createEmptyBoard, enumeratePlacements } from "../public/engine.js";
import {
  SRS_SHAPES,
  placementScore,
  reachablePlacements,
  replayPath,
  srsCells,
  tryRotate,
} from "../public/srs.js";

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

test("every SRS state has four cells inside its box", () => {
  for (const type of PIECE_TYPES) {
    const box = type === "I" ? 4 : 3;
    for (let s = 0; s < 4; s++) {
      const cells = srsCells(type, s);
      assert.equal(cells.length, 4);
      for (const [r, c] of cells) assert.ok(r >= 0 && r < box && c >= 0 && c < box, `${type}${s}`);
    }
  }
  assert.equal(Object.keys(SRS_SHAPES).length, 7);
});

test("on an empty board the reachable set contains every hard-drop landing", () => {
  for (const type of PIECE_TYPES) {
    const board = createEmptyBoard();
    const drops = new Set(enumeratePlacements(board, type).map((c) => cellsKey(c.cells)));
    const reach = new Set(reachablePlacements(board, type).map((c) => cellsKey(c.cells)));
    for (const k of drops) assert.ok(reach.has(k), `${type} missing hard-drop landing ${k}`);
  }
});

test("candidates lock on support, inside the board, with a replayable path", () => {
  const board = boardFrom([
    "....X.....",
    "XX..XX..XX",
    "XXX.XXX.XX",
  ]);
  for (const type of PIECE_TYPES) {
    for (const cand of reachablePlacements(board, type)) {
      assert.equal(cand.cells.length, 4);
      let supported = false;
      for (const [r, c] of cand.cells) {
        assert.ok(r >= 0 && r < ROWS && c >= 0 && c < COLS);
        assert.equal(board[r][c], 0, "lands on an empty cell");
        const below = r + 1;
        if (below >= ROWS || (board[below][c] !== 0 && !cand.cells.some(([rr, cc]) => rr === below && cc === c))) supported = true;
      }
      assert.ok(supported, `${type} ${cand.id} floats`);
      const frames = replayPath(board, type, cand.path);
      const last = frames[frames.length - 1];
      const end = srsCells(type, last.state).map(([r, c]) => [last.row + r, last.col + c]);
      assert.equal(cellsKey(end), cellsKey(cand.cells), `${type} ${cand.id} path ends elsewhere`);
    }
  }
});

test("a T can spin into a classic T-spin double slot that a hard drop cannot reach", () => {
  // Pillars at columns 2 and 5 (row 17) make the slot at columns 3-5, rows 18-19 unreachable
  // by dropping: the T comes down upright beside the left pillar and spins in with a kick.
  const board = boardFrom([
    "..X..X....",
    "XXX...XXXX",
    "XXXX.XXXXX",
  ]);
  const cands = reachablePlacements(board, "T");
  const tsd = cands.filter((c) => c.tspin === "full" && c.linesCleared === 2);
  assert.equal(tsd.length, 1, "exactly one T-spin double");
  assert.equal(tsd[0].score, 1200);
  assert.ok(tsd[0].path.some((m) => m === "CW" || m === "CCW"), "reached by rotating");
  assert.equal(tsd[0].path[tsd[0].path.length - 1] === "D", false, "last move is the spin");
  assert.equal(cellsKey(tsd[0].cells), cellsKey([[18, 3], [18, 4], [18, 5], [19, 4]]));

  const drops = new Set(enumeratePlacements(board, "T").map((c) => cellsKey(c.cells)));
  assert.ok(!drops.has(cellsKey(tsd[0].cells)), "hard-drop enumeration cannot see the slot");
});

test("a T dropped flat into an open slot is not a T-spin", () => {
  const board = boardFrom([
    "XXX...XXXX",
    "XXXX.XXXXX",
  ]);
  const cands = reachablePlacements(board, "T");
  const slot = cands.find((c) => cellsKey(c.cells) === cellsKey([[18, 3], [18, 4], [18, 5], [19, 4]]));
  assert.ok(slot);
  assert.equal(slot.tspin, null);
  assert.equal(slot.linesCleared, 2);
  assert.equal(slot.score, 300);
});

test("kicks let an I piece rotate against a wall", () => {
  const board = createEmptyBoard();
  // Upright I hugging the left wall: state 1 keeps column 2 of the box, so the box sits at col -2.
  const r = tryRotate(board, "I", 1, 5, -2, 1);
  assert.ok(r, "rotation succeeds via a kick");
  assert.equal(r.state, 2);
  assert.ok(r.col >= 0);
});

test("placement scoring follows the guideline table", () => {
  assert.deepEqual([0, 1, 2, 3, 4].map((n) => placementScore(n, null)), [0, 100, 300, 500, 800]);
  assert.deepEqual([0, 1, 2, 3].map((n) => placementScore(n, "full")), [400, 800, 1200, 1600]);
  assert.deepEqual([0, 1, 2].map((n) => placementScore(n, "mini")), [100, 200, 400]);
});

test("a piece that cannot spawn yields no candidates", () => {
  const board = createEmptyBoard();
  for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) board[r][c] = "X";
  assert.deepEqual(reachablePlacements(board, "T"), []);
});
