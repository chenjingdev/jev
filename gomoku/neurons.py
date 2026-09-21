"""The tetris brain, moved to gomoku: sense -> motor -> verdict, three requests a move.

The single-request `brain.think` hands Jev a sheet with verdict words (MUST BLOCK,
URGENT, DOUBLE THREAT) and a numbered priority list. This version takes those
verdicts out of the text and asks Jev to make them itself, in layers:

    R1 sense     four Nouls on a summary of the position (no candidate list):
                 danger / attack / defend / develop. >= 0.5 fires.
    R2 motor     one Choice per fired sensor over the *neutral* fact sheet
                 (brain.neutral: same facts, no verdict words), with a role
                 instruction; plus the always-on HABIT neuron with the plain
                 instruction. Each proposes a point.
    R3 verdict   arbiter Choice over the distinct proposals (sees what backed
                 each one and its facts, not the board or the sheet) and a
                 coach veto Noul per proposal. Final = arbiter x (1 - veto);
                 veto >= 0.65 zeroes a proposal.

Same vocabulary and thresholds as tetris/docs/neurons-spec.md.
"""

from __future__ import annotations

import time

import brain
import engine as E
from typesafe_sdk import Choice, Noul, Score

FIRE_AT = 0.5
HARD_VETO = 0.65
SENSORS = ("danger", "attack", "defend", "develop")

SCENE = (
    "A game of gomoku is in progress (15x15, first to five in a row wins) and white is to move. "
    "`board` shows the position, X black, O white, . empty. `black_has` and `white_has` list the "
    "open threes and fours each side already has on the board. `facts` holds what the engine "
    "measured: how many empty points would complete five for black on its next move, how many "
    "would give black an open four or two threats at once, how many start a forced win for black "
    "(a four white must answer, then a winning shape), and the same for white right now. "
    "`last_move` is black's latest stone. "
)

SENSE = {
    "danger": (
        SCENE + "You are the DANGER neuron of the white player. Is white in immediate danger: will black "
        "win or reach an unstoppable position (an open four, or two threats at once) on its very next move "
        "unless white answers it with this stone? Say yes only for a threat that is one black move away, "
        "not for lines black might build later.",
        "Yes: answer black's threat with this stone, whatever it costs.",
        "No: black has nothing that wins or becomes unstoppable next move.",
    ),
    "attack": (
        SCENE + "You are the ATTACK neuron of the white player. Can white strike now: complete five, make an "
        "open four, or make two threats at once with this single stone, so that black cannot hold? Say yes "
        "only when the strike is available with this stone, not when it needs preparation.",
        "Yes: strike now, the winning shape is one stone away.",
        "No: white has no decisive stone available yet.",
    ),
    "defend": (
        SCENE + "You are the DEFEND neuron of the white player. Is black building faster than white, so that "
        "this stone should be spent taking a point out of black's growing lines (an open three, a pair of "
        "open twos) before they turn into a threat that must be answered? Weigh black's lines in `black_has` "
        "against white's in `white_has`. Say no when white's own lines are at least as advanced.",
        "Yes: spend this stone breaking black's shape.",
        "No: black's lines can wait; white has better things to do.",
    ),
    "develop": (
        SCENE + "You are the DEVELOP neuron of the white player. Is this a free move, with nothing forced on "
        "either side, that white should spend building its own strongest line toward a four or a double "
        "threat? Say yes when white can build without giving black a free tempo.",
        "Yes: build white's own line with this stone.",
        "No: something else is more urgent than building.",
    ),
}

MOTOR = {
    "danger": (
        "You are the DANGER neuron of the white player; the appraisal fired you at {activation}. The options are "
        "the empty points the engine considers playable, each described by what a white stone there builds and "
        "what it takes from black. Choose the point a player whose one goal right now is to survive would play: "
        "a point where black would otherwise complete five beats everything; then a point where black would get "
        "an open four or two threats at once (marked URGENT); only then a point marked WATCH, where black could "
        "start a forced win a tempo later. If several points answer the threat, prefer the one that also builds "
        "something for white."
    ),
    "attack": (
        "You are the ATTACK neuron of the white player; the appraisal fired you at {activation}. The options are "
        "the empty points the engine considers playable, each described by what a white stone there builds and "
        "what it takes from black. Choose the point a player whose one goal right now is to win would play: a "
        "point that completes five for white beats everything; then a point that makes an open four; then one "
        "that makes two threats at once or is marked FORCED WIN; then a four black must answer that leaves white a follow-up."
    ),
    "defend": (
        "You are the DEFEND neuron of the white player; the appraisal fired you at {activation}. The options are "
        "the empty points the engine considers playable, each described by what a white stone there builds and "
        "what it takes from black. Choose the point that takes the most out of black's lines: a point where black "
        "would make an open three or a four, best if it sits on two black lines at once, and better still if it "
        "also builds something for white."
    ),
    "develop": (
        "You are the DEVELOP neuron of the white player; the appraisal fired you at {activation}. The options are "
        "the empty points the engine considers playable, each described by what a white stone there builds and "
        "what it takes from black. Choose the point that grows white's strongest line: an open three over a "
        "closed three, a closed three over an open two, a point on two white lines over a point on one, and "
        "stones that stay connected over scattered ones."
    ),
}
HABIT = brain.MOVE_FACTS

DIRECTIVE = {
    "danger": "answer black's threat first",
    "attack": "strike now",
    "defend": "break black's shape",
    "develop": "build white's own line",
}

ARBITRATE = (
    "Several motor neurons of the same white gomoku player each proposed a point for this move; `proposals` "
    "lists them by coordinate, with the goal that backs each one and what the engine says the stone does. The "
    "appraisal asked this stone to {DIRECTIVE}. `black_has` and `white_has` list the lines already on the board. "
    "You cannot see the board; you see only what the neurons proposed, each with how strongly its sensor fired. "
    "Pick the proposal to play. A proposal that completes five for white, or that stops black completing five, "
    "wins over everything; after that, a strongly fired DANGER or ATTACK neuron outranks DEFEND, DEVELOP and "
    "habit, and the number of backers does not decide. Habit wins only when its point serves the asked-for goal "
    "nearly as well while building more for white. Choose as a player choosing between their own competing instincts."
)
VETO = (
    "A coach is watching over the white player's shoulder. The appraisal asked this stone to {DIRECTIVE}. "
    "Consider `proposals.{id}`, one of the points on the table. Would the coach put a hand on the player's arm "
    "and stop this stone? Stop it only for reasons a coach would state: it ignores a point where black completes "
    "five or gets an open four next move, it plays far from every line while a threat stands, or it defeats the "
    "very goal that backs it. Do not stop a stone merely for being imperfect, and do not stop it because another "
    "proposal looks better. Never stop a stone that completes five for white or that stops black completing five."
)
VETO_TRUE = "Stop it: the stone ignores a standing threat, wastes the move, or defeats its own goal."
VETO_FALSE = "Let it through: the stone is consistent with its goal, even if it is not the best possible."


def facts_for(board: E.Board, ranked: list[dict]) -> dict:
    """Neutral counts the sensors read instead of the candidate sheet."""
    return {
        "points_where_black_completes_five_next_move": sum(1 for a in ranked if a["must_block"]),
        "points_where_black_gets_open_four_or_double_next_move": sum(1 for a in ranked if a["urgent"] and not a["must_block"]),
        "points_where_white_completes_five_now": sum(1 for a in ranked if a["wins"]),
        "points_where_white_makes_open_four_now": sum(1 for a in ranked if "open four" in a["attack"]),
        "points_where_white_makes_double_threat_now": sum(1 for a in ranked if a["double"]),
        "points_where_white_wins_by_force": sum(1 for a in ranked if a.get("forced_win")),
        "points_where_black_could_start_a_forced_win": sum(1 for a in ranked if a.get("watch")),
        "stones_on_board": E.stones(board),
    }


def _usage(response) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    return (usage.input_tokens, usage.output_tokens) if usage else (0, 0)


def prepare(board: E.Board, player: int, last: str | None, move_number: int, cap: int, sheet_kind: str, deep: bool) -> tuple[list[dict], dict, dict]:
    """The engine's part, shared by the three layers: ranked candidates, the sheet, the base state."""
    ranked = E.candidates(board, player, cap=cap, deep=deep)
    sheet = {a["id"]: (a["desc"] if sheet_kind == "labelled" else brain.neutral(a["desc"])) for a in ranked}
    base = brain.state_for(board, player, last, move_number, "facts")
    return ranked, sheet, base


def sense(board: E.Board, ranked: list[dict], base: dict) -> dict:
    """R1: the four sensors and the standing, from a summary - no candidate list."""
    started = time.perf_counter()
    r1 = brain.client().system_one(
        state={**base, "facts": facts_for(board, ranked)},
        model=brain.MODEL,
        questions={
            **{name: Noul(instructions=q, criteria={"true": t, "false": f}) for name, (q, t, f) in SENSE.items()},
            "standing": Score(instructions=brain.STANDING, criteria=brain.STANDING_LEVELS),
        },
    )
    i, o = _usage(r1)
    activations = {name: round(r1.answers[name].noul, 3) for name in SENSORS}
    fired = [name for name in SENSORS if activations[name] >= FIRE_AT]
    return {
        "activations": activations,
        "fired": fired,
        "directive": " and ".join(DIRECTIVE[n] for n in fired) or "play the natural move",
        "standing": round(r1.answers["standing"].score, 3),
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "input_tokens": i,
        "output_tokens": o,
    }


def motor(sheet: dict, base: dict, activations: dict, fired: list[str]) -> dict:
    """R2: one Choice per fired sensor plus the habit, in one request."""
    started = time.perf_counter()
    questions = {f"motor_{name}": Choice(instructions=MOTOR[name].format(activation=f"{activations[name]:.2f}"), criteria=sheet) for name in fired}
    questions["motor_habit"] = Choice(instructions=HABIT, criteria=sheet)
    r2 = brain.client().system_one(state={**base, "candidates": sheet}, model=brain.MODEL, questions=questions)
    i, o = _usage(r2)
    proposals: dict[str, list[str]] = {}
    picks = {}
    for qname, answer in r2.answers.items():
        backer = qname.removeprefix("motor_")
        picks[backer] = {"choice": answer.choice, "p": round(answer.probabilities.get(answer.choice, 0), 3)}
        proposals.setdefault(answer.choice, []).append(backer)
    return {"motor": picks, "proposals": proposals, "latency_ms": round((time.perf_counter() - started) * 1000), "input_tokens": i, "output_tokens": o}


def verdict(sheet: dict, base: dict, move_number: int, activations: dict, fired: list[str], directive: str, proposals: dict[str, list[str]]) -> dict:
    """R3: the arbiter over the proposals and a coach veto per proposal, same request."""
    started = time.perf_counter()

    def backer_text(b: str) -> str:
        return "HABIT" if b == "habit" else f"{b.upper()} (fired at {activations[b]:.2f})"

    props = {pid: f"{' and '.join(backer_text(b) for b in backers)} proposed this: {sheet[pid]}" for pid, backers in proposals.items()}
    state = {
        "to_move": "white",
        "move_number": move_number,
        "last_move": base["last_move"],
        "fired": fired,
        "directive": directive,
        "black_has": base["black_has"],
        "white_has": base["white_has"],
        "proposals": props,
    }
    questions = {"arbitrate": Choice(instructions=ARBITRATE.format(DIRECTIVE=directive), criteria=props)} if len(props) >= 2 else {}
    for pid in props:
        questions[f"veto_{pid}"] = Noul(instructions=VETO.format(DIRECTIVE=directive, id=pid), criteria={"true": VETO_TRUE, "false": VETO_FALSE})
    r3 = brain.client().system_one(state=state, model=brain.MODEL, questions=questions)
    i, o = _usage(r3)
    arbiter = dict(r3.answers["arbitrate"].probabilities) if len(props) >= 2 else {next(iter(props)): 1.0}
    vetoes = {pid: round(r3.answers[f"veto_{pid}"].noul, 3) for pid in props}
    final = {pid: (0.0 if vetoes[pid] >= HARD_VETO else arbiter.get(pid, 0.0) * (1 - vetoes[pid])) for pid in props}
    if all(v == 0.0 for v in final.values()):  # everything vetoed: fall back to the arbiter alone
        final = {pid: arbiter.get(pid, 0.0) for pid in props}
    total = sum(final.values()) or 1.0
    final = {pid: round(v / total, 4) for pid, v in final.items()}
    choice = max(final, key=lambda pid: final[pid])
    return {
        "arbiter": {k: round(v, 3) for k, v in arbiter.items()},
        "vetoes": vetoes,
        "vetoed": [pid for pid, v in vetoes.items() if v >= HARD_VETO],
        "final": final,
        "choice": choice,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "input_tokens": i,
        "output_tokens": o,
    }


def think(board: E.Board, player: int, last: str | None, move_number: int, cap: int = 24, sheet_kind: str = "facts", deep: bool = False) -> dict:
    """The three requests in a row. Returns the same shape as brain.think plus a `layers` record.

    `sheet_kind` is what the motor and verdict layers read: `facts` (neutral) or
    `labelled` (the verdict words kept; the numbered priority list is never given).
    The page calls the layers one at a time instead (server.py) so each request is
    visible as it goes out and lands.
    """
    ranked, sheet, base = prepare(board, player, last, move_number, cap, sheet_kind, deep)
    if len(ranked) == 1:
        return {**brain.think(board, player, last, move_number, cap), "layers": None}
    started = time.perf_counter()
    r1 = sense(board, ranked, base)
    r2 = motor(sheet, base, r1["activations"], r1["fired"])
    r3 = verdict(sheet, base, move_number, r1["activations"], r1["fired"], r1["directive"], r2["proposals"])
    tokens_in = r1["input_tokens"] + r2["input_tokens"] + r3["input_tokens"]
    tokens_out = r1["output_tokens"] + r2["output_tokens"] + r3["output_tokens"]
    habit_pick = r2["motor"].get("habit", {}).get("choice")
    return {
        "choice": r3["choice"],
        "probabilities": r3["final"],
        "confidence": r3["final"][r3["choice"]],
        "candidates": ranked,
        "threat": r1["activations"]["danger"],
        "standing": r1["standing"],
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "cost_usd": (tokens_in + tokens_out) * brain.USD_PER_TOKEN,
        "asked": True,
        "model": brain.MODEL,
        "layers": {
            "activations": r1["activations"],
            "fired": r1["fired"],
            "directive": r1["directive"],
            "motor": r2["motor"],
            "proposals": r2["proposals"],
            "arbiter": r3["arbiter"],
            "vetoes": r3["vetoes"],
            "changed_habit": habit_pick is not None and r3["choice"] != habit_pick,
            "vetoed": r3["vetoed"],
        },
    }
