import test from "node:test";
import assert from "node:assert/strict";
import { COLS, ROWS, PIECE_TYPES, createEmptyBoard, enumeratePlacements } from "../public/engine.js";
import {
  KICKS_I,
  KICKS_JLSTZ,
  KICKS_O,
  SRS_SHAPES,
  placementScore,
  reachablePlacements,
  replayPath,
  srsCells,
  srsSpawn,
  tryRotate,
  tspinKind,
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
const findCells = (cands, cells) => cands.find((c) => cellsKey(c.cells) === cellsKey(cells));

// Replay a path and report the kick index of its final move when that move is a rotation.
function lastKick(board, type, path) {
  const frames = replayPath(board, type, path);
  const last = path[path.length - 1];
  if (last !== "CW" && last !== "CCW") return -1;
  const pen = frames[frames.length - 2];
  return tryRotate(board, type, pen.state, pen.row, pen.col, last === "CW" ? 1 : -1).kick;
}

// Every candidate must rest on something, lie inside the board on empty cells, and replay from
// spawn to exactly the cells it claims. Shared by the sketch board test and the property test.
function assertSoundCandidate(board, type, cand) {
  assert.equal(cand.cells.length, 4);
  let supported = false;
  for (const [r, c] of cand.cells) {
    assert.ok(r >= 0 && r < ROWS && c >= 0 && c < COLS, `${type} ${cand.id} outside the board`);
    assert.equal(board[r][c], 0, "lands on an empty cell");
    const below = r + 1;
    if (below >= ROWS || (board[below][c] !== 0 && !cand.cells.some(([rr, cc]) => rr === below && cc === c))) supported = true;
  }
  assert.ok(supported, `${type} ${cand.id} floats`);
  const frames = replayPath(board, type, cand.path);
  const last = frames[frames.length - 1];
  const end = srsCells(type, last.state).map(([r, c]) => [last.row + r, last.col + c]);
  assert.equal(cellsKey(end), cellsKey(cand.cells), `${type} ${cand.id} path ends elsewhere`);
  assert.equal(last.state, cand.rot);
  for (const f of frames) {
    for (const [r, c] of srsCells(type, f.state)) {
      const rr = f.row + r;
      const cc = f.col + c;
      assert.ok(cc >= 0 && cc < COLS && rr < ROWS, `${type} ${cand.id} frame leaves the board`);
      if (rr >= 0) assert.equal(board[rr][cc], 0, `${type} ${cand.id} frame overlaps the stack`);
    }
  }
}

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

test("pieces spawn centred in a hidden buffer above the board", () => {
  for (const type of PIECE_TYPES) {
    const sp = srsSpawn(type);
    const cells = srsCells(type, 0).map(([r, c]) => [sp.row + r, sp.col + c]);
    // Two rows above where the pieces used to spawn (row 0 for 3x3 boxes, row -1 for the I box).
    assert.ok(cells.every(([r]) => r === -1 || r === -2), `${type} spawns in the two buffer rows`);
    const cols = [...new Set(cells.map(([, c]) => c))].sort((a, b) => a - b);
    assert.deepEqual(cols, type === "I" ? [3, 4, 5, 6] : type === "O" ? [4, 5] : [3, 4, 5]);
  }
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
    const cands = reachablePlacements(board, type);
    assert.equal(new Set(cands.map((c) => cellsKey(c.cells))).size, cands.length, "unique cell sets");
    cands.forEach((c, i) => assert.equal(c.id, "c" + i));
    for (const cand of cands) assertSoundCandidate(board, type, cand);
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

test("mirrored T-spin double: the T enters from the right with a counter-clockwise kick", () => {
  const board = boardFrom([
    "...X..X...",
    "XXX...XXXX",
    "XXXX.XXXXX",
  ]);
  const cands = reachablePlacements(board, "T");
  const c = findCells(cands, [[18, 3], [18, 4], [18, 5], [19, 4]]);
  assert.ok(c, "slot found");
  assert.equal(c.tspin, "full");
  assert.equal(c.linesCleared, 2);
  assert.equal(c.score, 1200);
  assert.equal(c.path[c.path.length - 1], "CCW");
  assert.equal(lastKick(board, "T", c.path), 2);
  assert.deepEqual(tryRotate(board, "T", 3, 16, 4, -1), { state: 2, row: 17, col: 3, kick: 2 });
  assert.ok(!findCells(enumeratePlacements(board, "T"), c.cells), "hard-drop cannot reach it");
});

test("T-spin triple: the fifth kick drops the T down the tower for three lines", () => {
  const board = boardFrom([
    "....XXXXXX",
    ".....XXXXX",
    "XXXX.XXXXX",
    "XXX..XXXXX",
    "XXXX.XXXXX",
  ]);
  const cands = reachablePlacements(board, "T");
  const c = findCells(cands, [[17, 4], [18, 3], [18, 4], [19, 4]]);
  assert.ok(c, "slot found");
  assert.equal(c.tspin, "full");
  assert.equal(c.linesCleared, 3);
  assert.equal(c.score, 1600);
  assert.equal(c.rot, 3);
  assert.equal(lastKick(board, "T", c.path), 4);
  assert.deepEqual(tryRotate(board, "T", 0, 15, 2, -1), { state: 3, row: 17, col: 3, kick: 4 });
  assert.ok(!findCells(enumeratePlacements(board, "T"), c.cells), "hard-drop cannot reach it");
});

test("mini T-spin single against the left wall", () => {
  // The T rests flat on (19,1); a clockwise turn kicks it one column left so the wall supplies
  // two corners and (19,1) the third; only one of the two front corners is filled: mini.
  const board = boardFrom([
    "..........",
    ".XXXXXXXXX",
  ]);
  const cands = reachablePlacements(board, "T");
  const c = findCells(cands, [[17, 0], [18, 0], [18, 1], [19, 0]]);
  assert.ok(c, "slot found");
  assert.equal(c.tspin, "mini");
  assert.equal(c.linesCleared, 1);
  assert.equal(c.score, 200);
  assert.equal(lastKick(board, "T", c.path), 1);
  assert.equal(tspinKind(board, 1, 17, -1, 1), "mini");
});

test("the fifth kick upgrades a mini (by corners) to a full T-spin", () => {
  // Same tower as the triple with the bottom-left corner emptied: three corners but only one of
  // them in front, so the corner rule alone says mini; the only route in is the fifth kick.
  const board = boardFrom([
    "....XXXXXX",
    ".....XXXXX",
    "XXXX.XXXXX",
    "XXX..XXXXX",
    "XXX..XXXXX",
  ]);
  assert.equal(tspinKind(board, 3, 17, 3, 1), "mini");
  assert.equal(tspinKind(board, 3, 17, 3, 4), "full");
  const cands = reachablePlacements(board, "T");
  const c = findCells(cands, [[17, 4], [18, 3], [18, 4], [19, 4]]);
  assert.ok(c, "slot found");
  assert.equal(c.tspin, "full");
  assert.equal(c.linesCleared, 2);
  assert.equal(c.score, 1200);
  assert.equal(lastKick(board, "T", c.path), 4);
});

test("T-spin kind does not depend on which route the search expands first", () => {
  // The upright T at box (17,6) is reachable both by an in-place turn (kick 0, mini by corners)
  // and by a fifth-kick turn (full). The search must report the best kind whichever it met first.
  const board = boardFrom([
    "X..X...X..",
    ".X.X......",
    "X..XX.X.X.",
    ".X.X.X....",
    "X...X.X...",
  ]);
  const target = srsCells("T", 1).map(([r, c]) => [17 + r, 6 + c]);
  const c = findCells(reachablePlacements(board, "T"), target);
  assert.ok(c, "placement found");
  assert.equal(c.tspin, "full");
  assert.equal(c.score, 400);
  assert.equal(lastKick(board, "T", c.path), 4);
  // Both kinds of arrival really exist for these cells.
  assert.equal(tspinKind(board, 1, 17, 6, 0), "mini");
  assert.deepEqual(tryRotate(board, "T", 0, 17, 6, 1), { state: 1, row: 17, col: 6, kick: 0 });
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

test("an L can tuck under an overhang that a hard drop cannot reach", () => {
  // Upright L drops to box (16,1), a clockwise kick swings its top under the (16,3)-(16,4) roof,
  // one more row down completes rows 18 and 19.
  const board = boardFrom([
    "...XXX....",
    ".....XXXXX",
    "XX...XXXXX",
    "XX.XXXXXXX",
  ]);
  const cands = reachablePlacements(board, "L");
  const c = findCells(cands, [[18, 2], [18, 3], [18, 4], [19, 2]]);
  assert.ok(c, "tuck found");
  assert.equal(c.rot, 2);
  assert.equal(c.linesCleared, 2);
  assert.equal(c.score, 300);
  assert.ok(c.path.some((m) => m === "CW" || m === "CCW"), "reached by rotating");
  assert.deepEqual(tryRotate(board, "L", 1, 16, 1, 1), { state: 2, row: 16, col: 2, kick: 1 });
  assert.ok(!findCells(enumeratePlacements(board, "L"), c.cells), "hard-drop cannot reach it");
});

test("I kicks against the walls land exactly where the guideline says", () => {
  const empty = createEmptyBoard();
  // Upright I hugging the left wall (state 1 keeps column 2 of its box, so the box sits at col -2).
  assert.deepEqual(tryRotate(empty, "I", 1, 5, -2, 1), { state: 2, row: 5, col: 0, kick: 2 });
  // Upright I hugging the right wall.
  assert.deepEqual(tryRotate(empty, "I", 1, 5, 7, 1), { state: 2, row: 5, col: 6, kick: 1 });
  // Upright I in state 3 (column 1 of its box) at the left wall, turning counter-clockwise.
  assert.deepEqual(tryRotate(empty, "I", 3, 5, -1, -1), { state: 2, row: 5, col: 0, kick: 2 });
  // Nothing in the way: the first test always applies.
  assert.deepEqual(tryRotate(empty, "I", 0, 5, 3, 1), { state: 1, row: 5, col: 3, kick: 0 });
});

test("kick tables match the guideline offset data", () => {
  // tetris.wiki "How Guideline SRS Really Works": each state has five offsets (x right, y up)
  // and kick i for from>to is offset[from][i] - offset[to][i], measured at the piece's true
  // rotation centre. The code moves the bounding box instead, so the centre's position inside
  // the box per state (fixed for 3x3 pieces, wandering for I and O) is added back.
  const OFFSETS = {
    JLSTZ: [
      [[0, 0], [0, 0], [0, 0], [0, 0], [0, 0]],
      [[0, 0], [1, 0], [1, -1], [0, 2], [1, 2]],
      [[0, 0], [0, 0], [0, 0], [0, 0], [0, 0]],
      [[0, 0], [-1, 0], [-1, -1], [0, 2], [-1, 2]],
    ],
    I: [
      [[0, 0], [-1, 0], [2, 0], [-1, 0], [2, 0]],
      [[-1, 0], [0, 0], [0, 0], [0, 1], [0, -2]],
      [[-1, 1], [1, 1], [-2, 1], [1, 0], [-2, 0]],
      [[0, 1], [0, 1], [0, 1], [0, -1], [0, 2]],
    ],
    O: [[[0, 0]], [[0, -1]], [[-1, -1]], [[-1, 0]]],
  };
  // Cells relative to the rotation centre in state 0 (x right, y up), rotated clockwise per state.
  const CENTRED = {
    T: [[-1, 0], [0, 0], [1, 0], [0, 1]],
    J: [[-1, 1], [-1, 0], [0, 0], [1, 0]],
    L: [[1, 1], [-1, 0], [0, 0], [1, 0]],
    S: [[0, 1], [1, 1], [-1, 0], [0, 0]],
    Z: [[-1, 1], [0, 1], [0, 0], [1, 0]],
    I: [[-1, 0], [0, 0], [1, 0], [2, 0]],
    O: [[0, 0], [1, 0], [0, 1], [1, 1]],
  };
  const rotateCW = (cells) => cells.map(([x, y]) => [y, -x]);
  // Where the true centre sits inside the code's box, found by matching the rotated centred cells
  // against SRS_SHAPES; this also proves each state's shape is the guideline orientation.
  function centreInBox(type, state) {
    let rel = CENTRED[type];
    for (let i = 0; i < state; i++) rel = rotateCW(rel);
    const want = cellsKey(srsCells(type, state));
    for (let cr = -2; cr <= 4; cr++) {
      for (let cc = -2; cc <= 4; cc++) {
        if (cellsKey(rel.map(([x, y]) => [cr - y, cc + x])) === want) return [cr, cc];
      }
    }
    assert.fail(`${type} state ${state} is not a guideline orientation`);
  }
  const transitions = [[0, 1], [1, 0], [1, 2], [2, 1], [2, 3], [3, 2], [3, 0], [0, 3]];
  const tables = { JLSTZ: KICKS_JLSTZ, I: KICKS_I, O: KICKS_O };
  for (const type of PIECE_TYPES) {
    const group = type === "I" ? "I" : type === "O" ? "O" : "JLSTZ";
    const off = OFFSETS[group];
    const centres = [0, 1, 2, 3].map((s) => centreInBox(type, s));
    if (group === "JLSTZ") centres.forEach((c) => assert.deepEqual(c, [1, 1], type + " centre is the middle of its box"));
    const regenerated = {};
    for (const [from, to] of transitions) {
      regenerated[from + ">" + to] = off[from].map((o, i) => {
        const kx = o[0] - off[to][i][0];
        const ky = o[1] - off[to][i][1];
        // box move = centre move minus the centre's drift inside the box (dy points up, rows down)
        return [kx - (centres[to][1] - centres[from][1]), ky + (centres[to][0] - centres[from][0])];
      });
    }
    assert.deepEqual(tables[group], regenerated, group + " kick table");
  }
});

test("placement scoring follows the guideline table", () => {
  assert.deepEqual([0, 1, 2, 3, 4].map((n) => placementScore(n, null)), [0, 100, 300, 500, 800]);
  assert.deepEqual([0, 1, 2, 3].map((n) => placementScore(n, "full")), [400, 800, 1200, 1600]);
  assert.deepEqual([0, 1, 2].map((n) => placementScore(n, "mini")), [100, 200, 400]);
});

test("a piece that cannot lock anywhere yields no candidates", () => {
  const board = createEmptyBoard();
  for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) board[r][c] = "X";
  for (const type of PIECE_TYPES) assert.deepEqual(reachablePlacements(board, type), [], type);
  // Room only in the buffer: a full row 0 blocks every descent, so the piece would lock over the
  // ceiling and that is refused.
  const roof = createEmptyBoard();
  for (let c = 0; c < COLS; c++) roof[0][c] = "X";
  for (const type of PIECE_TYPES) assert.deepEqual(reachablePlacements(roof, type), [], type + " under a roof");
});

test("the hidden buffer lets a piece slide over a full-height stack", () => {
  // Columns 0-5 reach the ceiling right under the spawn columns; the piece shifts sideways
  // through the buffer and drops into the empty right side instead of ending the game.
  const board = createEmptyBoard();
  for (let r = 0; r < ROWS; r++) for (let c = 0; c < 6; c++) board[r][c] = "X";
  for (const type of PIECE_TYPES) {
    const cands = reachablePlacements(board, type);
    assert.ok(cands.length > 0, type + " finds a landing");
    for (const c of cands) {
      assert.ok(c.cells.every(([, col]) => col >= 6), type + " lands on the open side");
      assertSoundCandidate(board, type, c);
    }
  }
  // The flat I on the floor completes row 19 against the wall.
  const floor = findCells(reachablePlacements(board, "I"), [[19, 6], [19, 7], [19, 8], [19, 9]]);
  assert.ok(floor, "flat I lands on the floor");
  assert.equal(floor.linesCleared, 1);
  // A one-wide well beside a wall of height 19 is still worth a tetris.
  const well = createEmptyBoard();
  for (let r = 1; r < ROWS; r++) for (let c = 1; c < COLS; c++) well[r][c] = "X";
  const vertical = findCells(reachablePlacements(well, "I"), [[16, 0], [17, 0], [18, 0], [19, 0]]);
  assert.ok(vertical, "upright I reaches the well bottom");
  assert.equal(vertical.linesCleared, 4);
  assert.equal(vertical.score, 800);
});

test("random boards: every candidate is sound and every hard-drop landing is reachable", () => {
  // Deterministic LCG so a failure can be reproduced by seed.
  let seed = 20260918;
  const rnd = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return seed / 0x7fffffff;
  };
  const ri = (n) => Math.floor(rnd() * n);
  function randomBoard() {
    const b = createEmptyBoard();
    const base = ri(15);
    const holeP = [0, 0.1, 0.25][ri(3)];
    for (let c = 0; c < COLS; c++) {
      const h = Math.max(0, Math.min(ROWS - 1, base + ri(7) - 3));
      for (let r = ROWS - h; r < ROWS; r++) if (rnd() > holeP) b[r][c] = "X";
    }
    // A few stray cells make overhangs, then no row may be full (the engine would have cleared it).
    for (let i = ri(6); i > 0; i--) b[ROWS - 1 - ri(ROWS - 1)][ri(COLS)] = "X";
    for (let r = 0; r < ROWS; r++) if (b[r].every((v) => v !== 0)) b[r][ri(COLS)] = 0;
    return b;
  }
  let checked = 0;
  let landings = 0;
  for (let n = 0; n < 200; n++) {
    const board = randomBoard();
    const snapshot = JSON.stringify(board);
    const maxHeight = Math.max(...board[0].map((_, c) => {
      for (let r = 0; r < ROWS; r++) if (board[r][c] !== 0) return ROWS - r;
      return 0;
    }));
    for (const type of PIECE_TYPES) {
      const cands = reachablePlacements(board, type);
      const keys = new Set(cands.map((c) => cellsKey(c.cells)));
      assert.equal(keys.size, cands.length, `board ${n} ${type}: duplicate cell sets`);
      for (const c of cands) {
        assertSoundCandidate(board, type, c);
        if (c.tspin) assert.ok(type === "T" && (c.path.at(-1) === "CW" || c.path.at(-1) === "CCW"), "T-spin only for a T that just turned");
        checked++;
      }
      if (maxHeight <= 17) {
        for (const d of enumeratePlacements(board, type)) {
          assert.ok(keys.has(cellsKey(d.cells)), `board ${n} ${type}: hard-drop landing ${cellsKey(d.cells)} unreachable\n${snapshot}`);
          landings++;
        }
      }
    }
    assert.equal(JSON.stringify(board), snapshot, "board is not mutated");
  }
  assert.ok(checked > 5000, "enough candidates were checked: " + checked);
  assert.ok(landings > 5000, "enough hard-drop landings were checked: " + landings);
});
