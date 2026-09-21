import chess

import checkmate
import checkmate_prompt


def test_explicit_state_and_instruction_name_correct_side():
    for row in checkmate.cases():
        board = chess.Board(row["fen"])
        expected = "White" if board.turn else "Black"
        for encoding in ("fen", "pieces"):
            state, side = checkmate_prompt.explicit_state(row, encoding)
            text = checkmate_prompt.instruction(side, encoding)
            assert side == expected
            assert state["side_to_move"] == expected
            assert state["opponent"] != expected
            assert text.startswith(f"{expected} is the side to move.")
            assert f"is {expected} currently checkmated?" in text


def test_no_answer_facts_leak_into_state_or_instruction():
    for row in checkmate.cases():
        for encoding in ("fen", "pieces"):
            state, side = checkmate_prompt.explicit_state(row, encoding)
            request_text = str(state) + checkmate_prompt.instruction(side, encoding)
            assert "legal_replies" not in request_text
            assert "source_move" not in request_text
            assert "expected" not in request_text
