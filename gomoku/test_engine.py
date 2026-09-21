"""uv run pytest gomoku -q   (no API key needed)"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import engine as E  # noqa: E402


def board_from(rows: list[str]) -> E.Board:
    b = E.new_board()
    for r, row in enumerate(rows):
        for c, ch in enumerate(row.split()):
            b[r][c] = {".": 0, "X": 1, "O": 2}[ch]
    return b


def place(b, cells, player):
    for r, c in cells:
        b[r][c] = player
    return b


def test_coord_roundtrip():
    assert E.coord(0, 0) == "a15" and E.coord(14, 14) == "o1" and E.coord(7, 7) == "h8"  # renju: row 1 at the bottom
    assert E.parse_coord("h8") == (7, 7) and E.parse_coord("o15") == (0, 14)


def test_win_detection_all_directions():
    for d in E.DIRECTIONS:
        b = E.new_board()
        cells = [(7 + d[0] * i, 7 + d[1] * i) for i in range(5)]
        place(b, cells[:4], E.BLACK)
        assert E.winner(b) == E.EMPTY
        assert E.wins_at(b, *cells[4], E.BLACK)
        b[cells[4][0]][cells[4][1]] = E.BLACK
        assert E.winner(b) == E.BLACK
        assert set(E.winning_line(b)) == set(cells)


def test_patterns_open_and_closed():
    b = E.new_board()
    place(b, [(7, 6), (7, 7)], E.BLACK)  # two blacks, both ends open
    assert E.patterns_at(b, 7, 8, E.BLACK)[0][0] == "open three"
    b[7][5] = E.WHITE  # close the left end
    assert E.patterns_at(b, 7, 8, E.BLACK)[0][0] == "three"
    place(b, [(7, 8)], E.BLACK)
    assert E.patterns_at(b, 7, 9, E.BLACK)[0][0] == "four"
    place(b, [(7, 9)], E.BLACK)
    assert E.patterns_at(b, 7, 10, E.BLACK)[0][0] == "five"


def test_candidates_flag_win_and_block():
    b = E.new_board()
    place(b, [(7, 3), (7, 4), (7, 5), (7, 6)], E.BLACK)  # black four, open both ends
    place(b, [(5, 5), (6, 6), (8, 8)], E.WHITE)
    ranked = E.candidates(b, E.WHITE)
    ids = [a["id"] for a in ranked]
    assert ids[0] in ("c8", "h8")  # either end of the four
    assert ranked[0]["must_block"] and "MUST BLOCK" in ranked[0]["desc"]
    assert all(a["r"] != a["c"] or b[a["r"]][a["c"]] == 0 for a in ranked)
    # white four: the winning point is first and marked
    b2 = E.new_board()
    place(b2, [(2, 2), (3, 3), (4, 4), (5, 5)], E.WHITE)
    place(b2, [(0, 0), (0, 1), (0, 2), (1, 0)], E.BLACK)
    top = E.candidates(b2, E.WHITE)[0]
    assert top["wins"] and top["id"] in ("g9", "b14")
    # black open three: both ends are URGENT and survive a tiny cap
    b3 = E.new_board()
    place(b3, [(7, 5), (7, 6), (7, 7)], E.BLACK)
    place(b3, [(2, 2), (3, 3), (12, 12)], E.WHITE)
    ranked = E.candidates(b3, E.WHITE, cap=1)
    urgent = {a["id"] for a in ranked if a["urgent"]}
    assert urgent == {"e8", "i8"} and all("URGENT" in a["desc"] for a in ranked if a["urgent"])


def test_candidates_prune_and_cap():
    b = E.new_board()
    assert [a["id"] for a in E.candidates(b, E.BLACK)] == ["h8"]
    place(b, [(7, 7)], E.BLACK)
    ranked = E.candidates(b, E.WHITE)
    assert len(ranked) == 24  # 5x5 minus the stone
    assert all(max(abs(a["r"] - 7), abs(a["c"] - 7)) <= 2 for a in ranked)
    for i in range(8):
        b[3][3 + i] = E.BLACK if i % 2 else E.WHITE
    assert len(E.candidates(b, E.WHITE, cap=10)) == 10


def test_threats_sentences():
    b = E.new_board()
    place(b, [(7, 5), (7, 6), (7, 7)], E.BLACK)
    lines = E.threats(b, E.WHITE)
    assert lines == ["black has an open three from f8 (horizontal)"]


def test_bot_blocks_and_wins():
    rng = random.Random(1)
    b = E.new_board()
    place(b, [(7, 3), (7, 4), (7, 5), (7, 6)], E.BLACK)
    place(b, [(2, 2), (3, 3), (4, 4)], E.WHITE)
    move = E.bot_move(b, E.WHITE, rng)
    assert move["id"] in ("c8", "h8")
    b[5][5] = E.WHITE
    move = E.bot_move(b, E.WHITE, rng)
    assert move["wins"]


def test_render_shape():
    rows = E.render(E.new_board())
    assert len(rows) == 16 and rows[0].strip().startswith("a b c")


def test_double_threat_marked():
    b = E.new_board()
    place(b, [(7, 5), (7, 6), (5, 7), (6, 7)], E.WHITE)  # two open twos meeting at h8
    place(b, [(0, 0), (0, 1), (0, 2), (0, 3)], E.BLACK)
    a = E.analyze(b, 7, 7, E.WHITE)
    assert a["double"] and "DOUBLE THREAT" in a["desc"]
    # the same point on black's sheet is URGENT: white would get the double there
    assert E.analyze(b, 7, 7, E.BLACK)["urgent"]
    # black about to get a four-three (allowed under renju): white's sheet marks that point URGENT
    b2 = E.new_board()
    place(b2, [(7, 4), (7, 5), (7, 6), (5, 7), (6, 7)], E.BLACK)
    place(b2, [(7, 3), (12, 13)], E.WHITE)
    w = E.analyze(b2, 7, 7, E.WHITE)
    assert w["urgent"] and "URGENT" in w["desc"]


def test_neurons_facts_and_neutral():
    import brain
    import neurons

    b = E.new_board()
    place(b, [(7, 3), (7, 4), (7, 5), (7, 6)], E.BLACK)
    place(b, [(2, 2), (3, 3), (4, 4)], E.WHITE)
    ranked = E.candidates(b, E.WHITE)
    facts = neurons.facts_for(b, ranked)
    assert facts["points_where_black_completes_five_next_move"] >= 1
    assert facts["points_where_white_completes_five_now"] == 0
    for a in ranked:
        n = brain.neutral(a["desc"])
        assert not any(tag in n for tag in ("WINS:", "MUST BLOCK:", "URGENT:", "DOUBLE THREAT:", "block now"))


def test_renju_forbidden_for_black_only():
    b = E.new_board()
    place(b, [(7, 5), (7, 6), (5, 7), (6, 7)], E.BLACK)  # two open twos meeting at h8 -> double three
    assert E.forbidden(b, 7, 7, E.BLACK) == "double three"
    assert E.forbidden(b, 7, 7, E.WHITE) is None
    assert all(a["id"] != "h8" for a in E.candidates(b, E.BLACK))
    # white's sheet: black cannot play h8, so h8 is no URGENT point
    assert not E.analyze(b, 7, 7, E.WHITE)["urgent"]
    # overline: black six is not a win and the point is forbidden
    b2 = E.new_board()
    place(b2, [(7, 2), (7, 3), (7, 4), (7, 6), (7, 7)], E.BLACK)
    assert E.forbidden(b2, 7, 5, E.BLACK) == "overline"
    assert not E.wins_at(b2, 7, 5, E.BLACK)
    place(b2, [(3, 2), (3, 3), (3, 4), (3, 6), (3, 7)], E.WHITE)
    assert E.wins_at(b2, 3, 5, E.WHITE)  # white may make six
    # exactly five beats the bans
    b3 = E.new_board()
    place(b3, [(7, 3), (7, 4), (7, 5), (7, 6), (5, 7), (6, 7), (8, 7), (9, 7)], E.BLACK)
    assert E.forbidden(b3, 7, 7, E.BLACK) is None and E.wins_at(b3, 7, 7, E.BLACK)
    # double four
    b4 = E.new_board()
    place(b4, [(7, 4), (7, 5), (7, 6), (4, 7), (5, 7), (6, 7)], E.BLACK)
    place(b4, [(7, 3), (3, 7)], E.WHITE)
    assert E.forbidden(b4, 7, 7, E.BLACK) == "double four"


def test_vcf_four_then_double():
    # white c8 d8 e8 with b8 black: f8 makes a closed four, black must answer g8.
    # white also has h6 i5 (j4 black) and h7 i7: after f8 stands, g9 (index 6,6) makes a closed
    # four on the f8-i5 diagonal and an open three on row 7 at once -> forced win.
    b = E.new_board()
    place(b, [(7, 2), (7, 3), (7, 4), (5, 7), (4, 8), (6, 7), (6, 8)], E.WHITE)
    place(b, [(7, 1), (3, 9), (0, 0), (0, 1), (0, 2), (14, 14), (14, 13)], E.BLACK)
    assert E.analyze(b, 7, 5, E.WHITE)["attack"] == ["four"]  # f8 alone is just a four
    starts = E.vcf_starts(b, E.WHITE)
    assert starts[(7, 5)] == [((7, 5), (7, 6)), ((6, 6), None)]
    ranked = E.candidates(b, E.WHITE, deep=True)
    assert ranked[0]["forced_win"] and "FORCED WIN" in ranked[0]["desc"]
    assert next(a for a in ranked if a["id"] == "f8")["forced_win"]
    # black's sheet marks the start (f8), the block (g8) and the end (g9) as WATCH, label at the end
    black = E.candidates(b, E.BLACK, deep=True)
    watch = {a["id"] for a in black if a["watch"]}
    assert {"f8", "g8", "g9"} <= watch
    assert all(not a["desc"].startswith("WATCH") for a in black)
    # the bot's sheet does not know
    assert not any(a.get("forced_win") for a in E.candidates(b, E.WHITE))


def test_split_shapes_count():
    # X.XXX is a four (one cell completes five), not a three; XX.X with room is an open three
    b = E.new_board()
    place(b, [(4, 8), (6, 8), (8, 8)], E.BLACK)
    place(b, [(0, 0), (0, 1), (0, 2)], E.WHITE)
    assert E.patterns_at(b, 7, 8, E.BLACK)[0][0] == "four"
    assert E._four_block_point(b, 7, 8, E.BLACK, (1, 0)) == (5, 8)
    b2 = E.new_board()
    place(b2, [(7, 4), (7, 5)], E.WHITE)
    assert E.patterns_at(b2, 7, 7, E.WHITE)[0][0] == "open three"
    # a four plus an open three where the three is split is a legal 4-3 for black, not a double three
    b3 = E.new_board()
    place(b3, [(4, 8), (6, 8), (8, 8), (5, 6), (6, 7)], E.BLACK)
    place(b3, [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4)], E.WHITE)
    assert E.forbidden(b3, 7, 8, E.BLACK) is None
