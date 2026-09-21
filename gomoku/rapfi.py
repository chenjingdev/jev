"""Rapfi (Gomocup-winning open-source engine) as the black player, over the piskvork pipe.

Rapfi is a separate process: `rapfi_setup.sh` clones, builds (NEON on this Mac) and
puts the executable, its config and the network weights in `gomoku/rapfi/`. One
process per move (the server is stateless): START, the rule, the time limit,
the whole position via BOARD, one line `x,y` back. The local engine stays the
referee: an occupied or locally forbidden answer is logged and replaced by a
random legal point, like Opus.
"""

from __future__ import annotations

import os
import random
import re
import subprocess
import time
from pathlib import Path

import engine as E

RAPFI_DIR = Path(os.environ.get("RAPFI_DIR", Path(__file__).with_name("rapfi")))
RAPFI_BIN = RAPFI_DIR / "pbrain-rapfi"
RULE_RENJU, RULE_FREESTYLE = 4, 0  # piskvork rule ids
_MOVE = re.compile(r"^(\d+),(\d+)$", re.M)
_INFO = re.compile(r"Depth (\d+)[^|]*\| Eval ([+-]?\w+)")


def available() -> bool:
    return RAPFI_BIN.is_file() and os.access(RAPFI_BIN, os.X_OK)


def ask_rapfi(board: E.Board, ms: int, strength: int, depth: int = 0, player: int = E.BLACK) -> tuple[str, float]:
    """One engine run on the position with `player` to move; returns (stdout, seconds)."""
    # Rapfi takes the first listed stone as black and expects the colours to alternate
    # (it inserts passes otherwise), so interleave black, white, black, ... and mark
    # the engine's own colour as 1.
    own = {E.BLACK: 1, E.WHITE: 2} if player == E.BLACK else {E.WHITE: 1, E.BLACK: 2}
    blacks = [f"{c},{r},{own[E.BLACK]}" for r in range(E.SIZE) for c in range(E.SIZE) if board[r][c] == E.BLACK]
    whites = [f"{c},{r},{own[E.WHITE]}" for r in range(E.SIZE) for c in range(E.SIZE) if board[r][c] == E.WHITE]
    stones = [s for pair in zip(blacks, whites) for s in pair] + blacks[len(whites):] + whites[len(blacks):]
    lines = [f"START {E.SIZE}", f"INFO rule {RULE_RENJU if E.RENJU else RULE_FREESTYLE}", f"INFO timeout_turn {ms}", "INFO timeout_match 0",
             f"INFO max_memory {256 << 20}", f"INFO strength {strength}"]
    if depth:
        lines.append(f"INFO max_depth {depth}")
    lines += ["BOARD", *stones, "DONE"] if stones else ["BEGIN"]
    lines.append("END")
    started = time.time()
    try:
        out = subprocess.run([str(RAPFI_BIN)], input="\n".join(lines) + "\n", capture_output=True, text=True,
                             timeout=ms / 1000 + 20, cwd=RAPFI_DIR)
        text = out.stdout
    except subprocess.TimeoutExpired:
        text = ""
    return text, time.time() - started


def rapfi_move(board: E.Board, rng: random.Random, log: list[dict], ms: int = 1000, strength: int = 100, depth: int = 0,
               player: int = E.BLACK) -> dict:
    """Rapfi picks a point; the local referee decides whether it counts.

    Appends one record per move to `log`: move, seconds, legal, and Rapfi's last
    reported depth and eval (from its own side, centipawn-like). `depth` caps the
    search (0 = none): the one knob that visibly weakens it."""
    text, seconds = ask_rapfi(board, ms, strength, depth, player)
    found = _MOVE.findall(text)
    info = _INFO.findall(text)
    depth, evaluation = (int(info[-1][0]), info[-1][1]) if info else (None, None)
    record = {"tries": 1, "seconds": round(seconds, 2), "depth": depth, "eval": evaluation, "text": ""}
    if found:
        x, y = map(int, found[-1])
        r, c = y, x
        if 0 <= r < E.SIZE and 0 <= c < E.SIZE and board[r][c] == E.EMPTY and not E.forbidden(board, r, c, player):
            log.append({"move": E.coord(r, c), "legal": True, **record})
            return E.analyze(board, r, c, player)
        record["text"] = f"{E.coord(r, c)} rejected by the local referee"
    else:
        record["text"] = "no move line" if text else "engine timed out or failed to start"
    fallback = rng.choice(E.candidates(board, player, cap=225))
    log.append({"move": fallback["id"], "legal": False, **record})
    return fallback


rapfi_black = rapfi_move  # the page and play.py's black side
