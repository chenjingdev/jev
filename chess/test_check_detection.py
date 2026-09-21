import chess

import check_detection


def test_matched_children_have_expected_check_status():
    rows = check_detection.cases()
    assert len(rows) == 40
    for index in range(1, 21):
        pair = [row for row in rows if row["index"] == index]
        assert {row["expected"] for row in pair} == {True, False}
        assert len({row["moving_piece"] for row in pair}) == 1
        for row in pair:
            board = chess.Board(row["fen"])
            assert board.is_check() == row["expected"]
            if row["expected"]:
                assert not board.is_checkmate()


def test_request_is_atomic_bare_noul_without_answer_leak(monkeypatch):
    captured = {}

    class Answer:
        noul = 0.8

    class Usage:
        input_tokens = 1
        output_tokens = 1

    class Response:
        answers = {"in_check": Answer()}
        usage = Usage()

    class FakeClient:
        def system_one(self, **kwargs):
            captured.update(kwargs)
            return Response()

    monkeypatch.setattr(check_detection, "client", lambda: FakeClient())
    row = check_detection.cases()[0]
    result = check_detection.ask(row)
    assert isinstance(captured["state"], str)
    assert row["fen"] in captured["state"]
    assert captured["questions"]["in_check"].criteria is None
    assert row["source_move"] not in captured["state"]
    assert "expected" not in captured["state"]
    assert result["predicted"] is True
