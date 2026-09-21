import { test } from "node:test";
import assert from "node:assert/strict";
import {
  boardRows,
  candidates,
  facts,
  isGameOver,
  legalMoves,
  makeRng,
  move,
  newGame,
  slideLine,
  spawn,
} from "../public/engine.js";

test("slideLine merges once per pass, leftmost first", () => {
  assert.deepEqual(slideLine([2, 2, 2, 2]).values, [4, 4, 0, 0]);
  assert.deepEqual(slideLine([2, 2, 4, 0]).values, [4, 4, 0, 0]);
  assert.deepEqual(slideLine([4, 0, 4, 2]).values, [8, 2, 0, 0]);
  assert.deepEqual(slideLine([0, 0, 0, 2]).values, [2, 0, 0, 0]);
  assert.deepEqual(slideLine([2, 4, 2, 4]).values, [2, 4, 2, 4]);
  const r = slideLine([2, 2, 2, 0]);
  assert.deepEqual(r.values, [4, 2, 0, 0]);
  assert.equal(r.gained, 4);
  assert.deepEqual(r.sources, [[0, 1], [2]]);
});

test("move slides every line toward the wall and reports movement", () => {
  const b = [
    2, 0, 0, 2,
    0, 4, 0, 0,
    0, 0, 0, 0,
    8, 0, 8, 0,
  ];
  const left = move(b, "left");
  assert.deepEqual(left.board, [4, 0, 0, 0, 4, 0, 0, 0, 0, 0, 0, 0, 16, 0, 0, 0]);
  assert.equal(left.gained, 20);
  assert.equal(left.changed, true);
  assert.deepEqual(left.merged.map((m) => m.at).sort(), [0, 12]);
  assert.ok(left.moved.some((m) => m.from === 3 && m.to === 0 && m.value === 2));

  const up = move(b, "up");
  assert.deepEqual(up.board, [2, 4, 8, 2, 8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
  const down = move(b, "down");
  assert.deepEqual(down.board, [0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 0, 0, 8, 4, 8, 2]);
  const right = move(b, "right");
  assert.deepEqual(right.board, [0, 0, 0, 4, 0, 0, 0, 4, 0, 0, 0, 0, 0, 0, 0, 16]);
});

test("a move that changes nothing is not legal", () => {
  const b = [2, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
  assert.equal(move(b, "left").changed, false);
  assert.equal(move(b, "up").changed, false);
  assert.deepEqual(legalMoves(b), ["down", "right"]);
});

test("game over when no line can move or merge", () => {
  const stuck = [2, 4, 2, 4, 4, 2, 4, 2, 2, 4, 2, 4, 4, 2, 4, 2];
  assert.equal(isGameOver(stuck), true);
  const almost = stuck.slice();
  almost[15] = 4;
  assert.equal(isGameOver(almost), false);
});

test("spawn fills an empty cell with 2 or 4 and is reproducible by seed", () => {
  const rand = makeRng(7);
  const b = newGame(rand);
  assert.equal(b.filter((v) => v > 0).length, 2);
  assert.ok(b.every((v) => v === 0 || v === 2 || v === 4));
  assert.deepEqual(newGame(makeRng(7)), b);
  const full = new Array(16).fill(2);
  assert.equal(spawn(full, rand), null);
});

test("facts finds the corner and counts what Jev reads", () => {
  const b = [
    64, 32, 8, 2,
    16, 8, 4, 0,
    2, 2, 0, 0,
    0, 0, 0, 0,
  ];
  const f = facts(b);
  assert.equal(f.max, 64);
  assert.equal(f.maxCorner, "top-left");
  assert.equal(f.empty, 7);
  assert.equal(f.pairs, 1);
  assert.equal(f.monotone, 8);
  assert.equal(f.legal, 3); // up moves nothing: every column is already packed at the top
  assert.deepEqual(boardRows(b), ["64 32 8 2", "16 8 4 .", "2 2 . .", ". . . ."]);
});

test("candidates lists legal moves with a sentence each", () => {
  const b = [2, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
  const c = candidates(b);
  assert.deepEqual(c.map((x) => x.dir), ["down", "left", "right"]);
  const left = c.find((x) => x.dir === "left");
  assert.match(left.summary, /slide LEFT; merges 1 pair \(2\+2\) for \+4/);
  assert.match(left.summary, /largest tile 4 stays in the top-left corner/);
  assert.match(candidates(b, false)[0].summary, /^slide DOWN; merges nothing\.$/);
});
