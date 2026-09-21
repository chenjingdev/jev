import checkmate
import checkmate_prompt
import checkmate_three_way


def test_three_options_are_distinct_and_shuffle_only_changes_order():
    for row in checkmate.cases():
        _, side = checkmate_prompt.explicit_state(row, "fen")
        base = checkmate_three_way.criteria_for(side, "base", row["index"])
        shuffled = checkmate_three_way.criteria_for(side, "shuffle", row["index"])
        assert set(base) == {"checkmate", "not_checkmate", "unknown"}
        assert shuffled == checkmate_three_way.criteria_for(side, "shuffle", row["index"])
        assert base == checkmate_three_way.criteria_for(side, "repeat", row["index"])
        assert dict(base) == {key: shuffled[key] for key in base}


def test_expected_choice_never_unknown(monkeypatch):
    captured = {}

    class Answer:
        choice = "unknown"
        probabilities = {"checkmate": 0.1, "not_checkmate": 0.2, "unknown": 0.7}
        confidence = 0.6

    class Usage:
        input_tokens = 1
        output_tokens = 1

    class Response:
        answers = {"status": Answer()}
        usage = Usage()

    class FakeClient:
        def system_one(self, **kwargs):
            captured.update(kwargs)
            return Response()

    monkeypatch.setattr(checkmate_three_way, "client", lambda: FakeClient())
    for row in checkmate.cases()[:2]:
        result = checkmate_three_way.ask(row)
        assert result["expected_choice"] in {"checkmate", "not_checkmate"}
        assert result["pick"] == "unknown"
        assert result["hit"] is False
        assert set(captured["state"]) == {"position_format", "fen", "side_to_move", "opponent"}
