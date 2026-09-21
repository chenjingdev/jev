import chess

import checkmate


def test_matched_cases_are_check_and_have_correct_labels():
    rows = checkmate.cases()
    assert len(rows) == 40
    assert sum(row["expected"] for row in rows) == 20
    for row in rows:
        board = chess.Board(row["fen"])
        assert board.is_check()
        assert board.is_checkmate() == row["expected"]
        assert row["legal_replies"] == board.legal_moves.count()
        if row["expected"]:
            assert row["legal_replies"] == 0
        else:
            assert row["legal_replies"] > 0


def test_each_parent_has_one_positive_and_one_negative():
    rows = checkmate.cases()
    for index in range(1, 21):
        pair = [row for row in rows if row["index"] == index]
        assert {row["kind"] for row in pair} == {"mate", "check_only"}
        assert {row["expected"] for row in pair} == {True, False}


def test_request_state_does_not_leak_label_or_source_move(monkeypatch):
    captured = {}

    class Answer:
        noul = 0.75

    class Usage:
        input_tokens = 1
        output_tokens = 1

    class Response:
        answers = {"is_checkmate": Answer()}
        usage = Usage()

    class FakeClient:
        def system_one(self, **kwargs):
            captured.update(kwargs)
            return Response()

    monkeypatch.setattr(checkmate, "client", lambda: FakeClient())
    row = checkmate.cases()[0]
    result = checkmate.ask(row, "fen")
    assert set(captured["state"]) == {"fen"}
    assert row["source_move"] not in str(captured)
    assert "expected" not in str(captured)
    assert result["predicted"] is True


def test_piece_state_reconstructs_same_board_information():
    for row in checkmate.cases():
        board = chess.Board(row["fen"])
        state = checkmate.state_for(row, "pieces")
        assert state["turn"] == ("white" if board.turn else "black")
        assert len(state["pieces"]) == len(board.piece_map())
        for square, piece in board.piece_map().items():
            expected = ("white" if piece.color else "black") + " " + chess.piece_name(piece.piece_type)
            assert state["pieces"][chess.square_name(square)] == expected
