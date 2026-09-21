"""Claude Opus as the black player, through the `claude -p` CLI on this Mac.

No API key: it runs on the user's own Claude Code subscription. One call per
move, a system prompt with the renju rules, the board as words, and the answer
ends with `MOVE: h8`. An illegal or forbidden point is asked about once more;
after that the caller falls back to a random legal point and records it.
"""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import time

import engine as E

OPUS_MODEL = "opus"
OPUS_SYSTEM = (
    "You are a strong gomoku (five in a row) player playing BLACK on a 15x15 board under renju rules: black moved "
    "first, wins with exactly five, and may not play a double three, a double four or an overline (six or more); "
    "white wins with five or more and has no restrictions. "
    "Coordinates are renju notation: a column letter a-o and a row number 1-15 counted from the bottom, like h8. "
    "Think briefly about threats on both sides, then end your reply with one line of the form `MOVE: h8`."
)
_COORD = re.compile(r"MOVE:\s*([a-oA-O])\s*(1[0-5]|[1-9])\b")


SHEET_CAP = 12  # what Jev's sheet keeps, so a sheet-fed Opus sees exactly the same points

# Jev's priority paragraph (brain.MOVE) with the colours swapped: the same hint, word for word.
SHEET_RULES = (
    "The engine has listed the empty points it considers playable, each described by what a black stone "
    "there does: what it builds for black and what it takes from white. Pick one of the listed points, in "
    "this order of priority. 1: a point that completes five for black. 2: a point marked MUST BLOCK, where "
    "white completes five next move. 3: a point that makes an open four or is marked DOUBLE THREAT (a four "
    "plus an open three): these win the game. 4: a point marked URGENT, where white would get an open four "
    "or a double threat; that has to be denied before it exists. 5: a point that makes a four white must "
    "answer, if it also leaves black a follow-up, or an open three for black, especially one that also takes "
    "something from white. Black loses by only defending: when nothing is forced, build black's own strongest "
    "line rather than pre-emptively taking a point where white could merely start a three. Prefer points that "
    "extend black's existing open threes and open twos toward a four-three."
)


def opus_prompt(board: E.Board, last: str | None, sheet: bool) -> str:
    lines = ["Current position (X black, O white, . empty):", *E.render(board)]
    lines.append(f"White's last move: {last}" if last else "The board is empty; you play first.")
    if sheet:
        ranked = E.candidates(board, E.BLACK, cap=SHEET_CAP)
        lines.append("")
        lines.append(SHEET_RULES)
        lines.append("Points the engine considers (choose one of these):")
        lines += [f"  {a['id']}: {a['desc']}" for a in ranked]
    lines.append("Choose black's move. End with `MOVE: <coordinate>`.")
    return "\n".join(lines)


def ask_opus(prompt: str) -> tuple[str, float]:
    """One headless `claude -p` call on the user's own subscription. Returns (text, seconds)."""
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_CHILD_SESSION")}
    started = time.time()
    try:
        out = subprocess.run(
            ["claude", "-p", "--model", OPUS_MODEL, "--output-format", "json", "--max-turns", "1", "--tools", "",
             "--system-prompt", OPUS_SYSTEM, prompt],
            capture_output=True, text=True, timeout=120, env=env,
        )
    except subprocess.TimeoutExpired:  # the CLI occasionally hangs; count it as no answer
        return "", time.time() - started
    try:
        text = json.loads(out.stdout)["result"]
    except (ValueError, KeyError):
        text = out.stdout + out.stderr
    return text, time.time() - started


def opus_black(board: E.Board, last: str | None, rng: random.Random, sheet: bool, log: list[dict]) -> dict:
    """Opus picks a coordinate; one retry on an illegal answer, then a random legal point.

    Appends one record per move to `log`: the move, tries, seconds, whether it was
    legal, and the text Opus wrote (for the page to show)."""
    prompt = opus_prompt(board, last, sheet)
    allowed = {a["id"] for a in E.candidates(board, E.BLACK, cap=SHEET_CAP)} if sheet else None
    tries = 0
    seconds = 0.0
    while tries < 2:
        text, secs = ask_opus(prompt)
        seconds += secs
        tries += 1
        found = _COORD.findall(text)
        if found:
            col, row = found[-1]
            r, c = E.parse_coord(col.lower() + row)
            why = E.forbidden(board, r, c, E.BLACK)
            if allowed is not None and E.coord(r, c) not in allowed and board[r][c] == E.EMPTY and not why:
                prompt += f"\n\n{E.coord(r, c)} is not on the engine's list. Choose one of the listed points. End with `MOVE: <coordinate>`."
                continue
            if board[r][c] == E.EMPTY and not why:
                log.append({"move": E.coord(r, c), "tries": tries, "seconds": round(seconds, 1), "legal": True, "text": text})
                return E.analyze(board, r, c, E.BLACK)
            reason = f"is a forbidden {why} for black" if why else "is occupied"
            prompt += f"\n\n{E.coord(r, c)} {reason}. Choose another point. End with `MOVE: <coordinate>`."
        else:
            prompt += "\n\nYour reply had no `MOVE: <coordinate>` line. End with one." if text else ""
    fallback = rng.choice(E.candidates(board, E.BLACK, cap=SHEET_CAP if sheet else 225))
    log.append({"move": fallback["id"], "tries": tries, "seconds": round(seconds, 1), "legal": False, "text": text})
    return fallback


