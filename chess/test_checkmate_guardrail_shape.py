import chess

import checkmate
import checkmate_guardrail_shape


def test_state_is_one_complete_string_and_noul_has_no_criteria(monkeypatch):
    captured = {}

    class Answer:
        noul = 0.75

    class Usage:
        input_tokens = 1
        output_tokens = 1

    class Response:
        answers = {"result": Answer()}
        usage = Usage()

    class FakeClient:
        def system_one(self, **kwargs):
            captured.update(kwargs)
            return Response()

    monkeypatch.setattr(checkmate_guardrail_shape, "client", lambda: FakeClient())
    row = checkmate.cases()[0]
    result = checkmate_guardrail_shape.ask(row)
    state = captured["state"]
    question = captured["questions"]["result"]
    assert isinstance(state, str)
    assert "This is a chess game." in state
    assert row["fen"] in state
    assert "checkmate" in state.lower()
    assert question.criteria is None
    assert result["predicted"] is True


def test_state_names_correct_side_without_leaking_answer():
    for row in checkmate.cases():
        state, side = checkmate_guardrail_shape.state_for(row)
        board = chess.Board(row["fen"])
        assert side == ("White" if board.turn else "Black")
        assert f"{side} is the side to move" in state
        assert "legal_replies" not in state
        assert "source_move" not in state
        assert "expected" not in state
