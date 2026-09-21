"""The one request per move: the engine's answer sheet goes in, Jev's pick comes out.

Three questions in one `system_one` call, evaluated in parallel, blind to each
other (the tetris pattern):

    move       Choice over the candidates; each option's description is the
               engine's one-line fact string for that point
    threat     Noul: black wins next move unless white blocks now
    standing   Score: black is winning / even / white is winning

The SDK is called directly rather than through `sif` so the panel can show
usage and latency per move.
"""

from __future__ import annotations

import os
import re
import time

import engine as E
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

MODEL = os.environ.get("JEV_MODEL", "jev-1.13.0")
USD_PER_TOKEN = 42 / 1e9  # $42 per billion tokens

MOVE = (
    "The state is a gomoku position (15x15, first to five in a row wins) with white to move. "
    "The options are the empty points the engine considers playable, each described by what a "
    "white stone there does: what it builds for white and what it takes from black. Pick the point "
    "white should play, in this order of priority. 1: a point that completes five for white. "
    "2: a point marked MUST BLOCK, where black completes five next move. 3: a point that makes an "
    "open four or is marked DOUBLE THREAT (a four plus an open three, or two open threes at once): "
    "these win the game. 4: a point marked URGENT, where black would get an open four or a double "
    "threat; that has to be denied before it exists. 5: a point that makes a four black must answer, "
    "if it also leaves white a follow-up, or an open three for white, especially one that also takes "
    "something from black. White loses by only defending: when nothing is forced, build white's own "
    "strongest line rather than pre-emptively taking a point where black could merely start a three. "
    "Prefer points that extend white's existing open threes and open twos toward a double threat."
)
MOVE_FACTS = (
    "The state is a gomoku position (15x15, first to five in a row wins) with white to move. "
    "The options are the empty points the engine considers playable, each described by what a "
    "white stone there does: what it builds for white and what it takes from black. "
    "Pick the point white should play."
)
MOVE_BARE = (
    "The state is a gomoku position (15x15, first to five in a row wins) with white to move; "
    "`board` lists the rows, X is a black stone, O a white stone, . an empty point, with column "
    "letters above and row numbers on the left (renju notation, row 1 at the bottom). The options are "
    "empty points named by column letter and row number. Pick the point white should play."
)
SHEETS = ("labelled", "facts", "bare")
_LABELS = re.compile(r"WINS: |MUST BLOCK: |URGENT: |DOUBLE THREAT: |FORCED WIN: |WATCH: |; block now|; black cannot stop both| that cannot be stopped| that black must answer")


def neutral(desc: str) -> str:
    """The same facts without the engine's verdict words."""
    return _LABELS.sub("", desc)


THREAT = "Black will complete five in a row on the next move unless white blocks it now."
STANDING = "Who is ahead in this position, judged from the lines each side has and the threats on the board?"
STANDING_LEVELS = ["black is winning", "even", "white is winning"]

_client: TypeSafeClient | None = None


def client() -> TypeSafeClient:
    global _client
    if _client is None:
        _client = TypeSafeClient()
    return _client


def state_for(board: E.Board, player: int, last: str | None, move_number: int, sheet: str = "labelled") -> dict:
    state = {
        "game": ("gomoku, 15x15, renju rules: white wins with five or more; black wins with exactly five and may not play a double three, a double four or an overline"
                 if E.RENJU else "gomoku, 15x15, free rules: five or more in a row wins for either colour"),
        "to_move": E.NAME[player],
        "move_number": move_number,
        "last_move": {"by": E.NAME[E.other(player)], "at": last} if last else None,
    }
    if sheet != "bare":
        state["black_has"] = E.threats(board, player) or ["no open threes or fours"]
        state["white_has"] = E.threats(board, E.other(player)) or ["no open threes or fours"]
    state["board"] = E.render(board)
    return state


def think(board: E.Board, player: int, last: str | None, move_number: int, cap: int = 24, sheet: str = "labelled", deep: bool = False) -> dict:
    """Ask Jev where white plays. Returns the pick, the distribution and the meters.

    `sheet` is how much of the engine Jev gets: `labelled` (facts + verdict words +
    numbered priorities), `facts` (the same facts, no verdicts), `bare` (coordinates only).
    """
    ranked = E.candidates(board, player, cap=cap, deep=deep)
    if len(ranked) == 1:
        only = ranked[0]
        return {
            "choice": only["id"],
            "probabilities": {only["id"]: 1.0},
            "confidence": 1.0,
            "candidates": ranked,
            "threat": 0.0,
            "standing": 1.0,
            "latency_ms": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "asked": False,
        }
    if sheet == "bare":
        criteria = {a["id"]: None for a in ranked}
        instructions = MOVE_BARE
    elif sheet == "facts":
        criteria = {a["id"]: neutral(a["desc"]) for a in ranked}
        instructions = MOVE_FACTS
    else:
        criteria = {a["id"]: a["desc"] for a in ranked}
        instructions = MOVE
    state = state_for(board, player, last, move_number, sheet)
    started = time.perf_counter()
    response = client().system_one(
        state=state,
        model=MODEL,
        questions={
            "move": Choice(instructions=instructions, criteria=criteria),
            "threat": Noul(instructions=THREAT),
            "standing": Score(instructions=STANDING, criteria=STANDING_LEVELS),
        },
    )
    latency_ms = (time.perf_counter() - started) * 1000
    answers = response.answers
    move = answers["move"]
    usage = getattr(response, "usage", None)
    tokens_in = usage.input_tokens if usage else 0
    tokens_out = usage.output_tokens if usage else 0
    return {
        "choice": move.choice,
        "probabilities": {k: round(v, 4) for k, v in move.probabilities.items()},
        "confidence": round(move.confidence, 4),
        "candidates": ranked,
        "threat": round(answers["threat"].noul, 4),
        "standing": round(answers["standing"].score, 3),
        "latency_ms": round(latency_ms),
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "cost_usd": (tokens_in + tokens_out) * USD_PER_TOKEN,
        "asked": True,
        "model": getattr(response, "model", None) or MODEL,
    }
