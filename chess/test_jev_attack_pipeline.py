"""Validate inference without using an engine as an input feature."""
import chess
import jev_attack_pipeline as pipeline


def test_representation_and_exhaustive_attacker_candidates():
    for split in ("development", "evaluation"):
        for case in pipeline.fixtures(split):
            state = pipeline.parse_position(case["fen"])
            board = chess.Board(case["fen"])
            assert len(state["pieces"]) == len(board.piece_map())
            for p in state["pieces"]:
                piece = board.piece_at(chess.parse_square(p["square"]))
                assert p["kind"] == chess.piece_name(piece.piece_type)
                assert p["color"] == ("White" if piece.color else "Black")
                assert p["column"] == chess.square_file(chess.parse_square(p["square"])) + 1
                assert p["rank"] == chess.square_rank(chess.parse_square(p["square"])) + 1
            request = pipeline.request_for(state)
            actual = {key[7:] for key in request["questions"] if key.startswith("attack_")}
            assert actual == {p["square"] for p in state["pieces"] if p["color"] != state["side_to_move"]}
            assert not {"expected", "legal_moves", "attackers", "is_check"} & state.keys()


def test_pipeline_uses_model_answers_and_all_obstacles(monkeypatch):
    # Bishop attacks h8 along b2-h8 unless the c3 blocker is present.
    fen = "7k/8/8/8/8/2p5/1B6/K7 b - - 0 1"
    captured = []

    def fake_call(request):
        captured.append(request)
        values = {key: 0.01 for key in request["questions"]}
        if "direct" in values:
            values.update({"direct": 0.1, "attack_b2": 0.1, "geometry_b2": 0.99, "clear_b2": 0.01})
        else:
            values["block_b2_c3"] = 0.99
        return {"request": request, "probabilities": values}

    monkeypatch.setattr(pipeline, "call", fake_call)
    result = pipeline.infer(fen)
    assert not any(result["predictions"].values())
    assert set(captured[1]["questions"]) == {"block_b2_c3", "block_b2_a1"}
    # Changing only the model's blocker answer changes the composed result.
    original = fake_call

    def no_blocker(request):
        response = original(request)
        if "block_b2_c3" in response["probabilities"]:
            response["probabilities"]["block_b2_c3"] = 0.01
        return response

    monkeypatch.setattr(pipeline, "call", no_blocker)
    assert pipeline.infer(fen)["predictions"]["pointwise"] is True


def test_development_and_evaluation_do_not_share_parents():
    development = {r["index"] for r in pipeline.fixtures("development")}
    evaluation = {r["index"] for r in pipeline.fixtures("evaluation")}
    assert len(development) == len(evaluation) == 10
    assert not development & evaluation


def test_single_request_path_uses_only_per_piece_answers(monkeypatch):
    requests = []

    def fake_call(request):
        requests.append(request)
        assert all(key.startswith("attack_") for key in request["questions"])
        probabilities = {key: .01 for key in request["questions"]}
        probabilities["attack_g7"] = .99
        return {"request": request, "probabilities": probabilities}

    monkeypatch.setattr(pipeline, "call", fake_call)
    result = pipeline.infer_check("7k/6Q1/5K2/8/8/8/8/8 b - - 0 1")
    assert result["predictions"]["per_piece"] is True
    assert len(requests) == 1
    assert len(result["attackers"]) == 2
