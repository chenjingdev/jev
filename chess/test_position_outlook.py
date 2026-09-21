import chess

import position_outlook


def test_matched_extremes_have_objective_labels():
    rows = position_outlook.cases()
    assert len(rows) == 40
    for index in range(1, 21):
        pair = [row for row in rows if row["index"] == index]
        assert {row["expected"] for row in pair} == {"danger", "advantage"}
        danger = next(row for row in pair if row["expected"] == "danger")
        advantage = next(row for row in pair if row["expected"] == "advantage")
        assert chess.Board(danger["fen"]).is_checkmate()
        board = chess.Board(advantage["fen"])
        mates = []
        for move in list(board.legal_moves):
            board.push(move)
            if board.is_checkmate():
                mates.append(move)
            board.pop()
        assert len(mates) == 1


def test_choice_shuffle_preserves_descriptions():
    for index in range(1, 21):
        base = position_outlook.choice_criteria("base", index)
        shuffled = position_outlook.choice_criteria("shuffle", index)
        assert set(base) == {"danger", "neutral", "advantage"}
        assert base == {key: shuffled[key] for key in base}
