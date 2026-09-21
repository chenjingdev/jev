import chess

import checkmate
import checkmate_piece_list


def test_plain_list_reconstructs_every_piece_and_has_no_fen():
    for row in checkmate.cases():
        board = chess.Board(row["fen"])
        state, side = checkmate_piece_list.state_for(row)
        assert "FEN" not in state
        assert side == ("White" if board.turn else "Black")
        assert f"{side} is the side to move" in state
        for square, piece in board.piece_map().items():
            color = "White" if piece.color else "Black"
            token = f"{chess.piece_name(piece.piece_type)} {chess.square_name(square)}"
            assert token in state.split(f"{color} pieces: ", 1)[1]


def test_bare_noul_request_leaks_no_answer_facts(monkeypatch):
    captured = {}

    class Answer:
        noul = 0.7

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

    monkeypatch.setattr(checkmate_piece_list, "client", lambda: FakeClient())
    row = checkmate.cases()[0]
    result = checkmate_piece_list.ask(row)
    assert captured["questions"]["result"].criteria is None
    assert row["source_move"] not in captured["state"]
    assert "legal_replies" not in captured["state"]
    assert result["predicted"] is True
