import jev_mate_pipeline as pipeline


def test_evasion_queries_cover_all_friendly_pieces_without_truth():
    for case in pipeline.fixtures("development") + pipeline.fixtures("evaluation"):
        first_request = pipeline.first_request(case["fen"])
        first = {"request": first_request, "probabilities": {key: 0.01 for key in first_request["questions"]}}
        second = pipeline.second_request(first)
        state = second["state"]
        assert state["earlier_model_assessment"]["predicted_attackers"] == []
        expected = {"evasion_" + p["square"] for p in state["pieces"] if p["color"] == state["side_to_move"]}
        assert set(second["questions"]) == expected
        assert not {"truth_evasions", "legal_moves", "expected", "mate"} & state.keys()


def test_composition_uses_predictions_only(monkeypatch):
    fen = "7k/6Q1/5K2/8/8/8/8/8 b - - 0 1"

    def fake_call(request):
        probabilities = {key: .01 for key in request["questions"]}
        if "attack_g7" in probabilities:
            probabilities["attack_g7"] = .99
        return {"request": request, "probabilities": probabilities}

    monkeypatch.setattr(pipeline.attack, "call", fake_call)
    result = pipeline.infer(fen)
    assert result["predictions"]["per_piece_evasion"] is True
    assert result["predictions"]["direct"] is False
    original = fake_call

    def false_escape(request):
        r = original(request)
        if "evasion_h8" in r["probabilities"]:
            r["probabilities"]["evasion_h8"] = .99
        return r

    monkeypatch.setattr(pipeline.attack, "call", false_escape)
    assert pipeline.infer(fen)["predictions"]["per_piece_evasion"] is False
