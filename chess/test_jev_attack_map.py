import itertools
import json
from copy import deepcopy

import chess
import pytest

import jev_attack_map as graph
import jev_attack_pipeline as pipeline


def test_all_pairs_once_with_valid_target_labels_and_bounded_batches():
    for split in ("development", "evaluation"):
        for case in pipeline.fixtures(split):
            board = chess.Board(case["fen"])
            friendly = {chess.square_name(sq) for sq, piece in board.piece_map().items() if piece.color == board.turn}
            enemy = {chess.square_name(sq) for sq, piece in board.piece_map().items() if piece.color != board.turn}
            requests = graph.requests_for(case["fen"])
            keys = [key for r in requests for key in r["questions"]]
            expected = {"attack_" + s + "_" + t for s, t in itertools.product(enemy, friendly)}
            assert set(keys) == expected
            assert len(keys) == len(expected)
            assert all(1 <= len(r["questions"]) <= 64 for r in requests)
            for request in requests:
                assert not {"target_king", "expected", "attacks", "legal_moves"} & request["state"].keys()
                for key, question in request["questions"].items():
                    _, source, target = key.split("_")
                    assert source in question["instructions"]["question"]
                    assert target in question["instructions"]["question"]


def test_target_aggregation_uses_jev_values_only(monkeypatch):
    calls = []

    def fake_call(request):
        calls.append(request)
        p = {key: .01 for key in request["questions"]}
        if "attack_b2_h8" in p:
            p["attack_b2_h8"] = .9
        return {"request": request, "probabilities": p}

    monkeypatch.setattr(pipeline, "call", fake_call)
    # Real bishop is blocked by the c3 pawn; fake model says otherwise.
    result = graph.infer_attack_map("7k/8/8/8/8/2p5/1B6/K7 b - - 0 1", batch_size=2)
    assert len(result["relations"]) == 4
    assert len(calls) == 2
    assert next(t for t in result["targets"] if t["square"] == "h8")["predicted_attackers"] == ["b2"]
    assert "expected" not in json.dumps(result)


def test_attack_semantics_include_pinned_pieces_but_not_blocked_rays():
    # Knight e7 is pinned to black king e8 by white rook e1, but attacks c6.
    board = chess.Board("4k3/4n3/2B5/8/8/8/8/K3R3 w - - 0 1")
    assert board.is_pinned(chess.BLACK, chess.E7)
    assert chess.C6 in board.attacks(chess.E7)
    blocker = chess.Board("7k/8/8/8/8/2p5/1B6/K7 b - - 0 1")
    assert chess.H8 not in blocker.attacks(chess.B2)
    assert chess.C3 in blocker.attacks(chess.B2)


def test_confusion_metrics_do_not_hide_sparse_positive_failures():
    rows = [{"expected": True, "predicted": False}] + [{"expected": False, "predicted": False}] * 9
    scored = graph.metrics(rows)
    assert scored["accuracy"] == .9
    assert scored["recall"] == 0
    assert scored["balanced_accuracy"] == .5
    assert scored["precision"] is None


def test_perspective_override_reverses_source_and_target_colors():
    fen = "7k/6Q1/5K2/8/8/8/8/8 b - - 0 1"
    req = graph.requests_for(fen, perspective="White")[0]
    assert set(req["questions"]) == {"attack_h8_g7", "attack_h8_f6"}
    with pytest.raises(ValueError):
        graph.requests_for(fen, perspective="Other")


def test_verification_ignores_labels_and_can_reject_a_false_attack(monkeypatch):
    fen = "7k/8/8/8/8/2p5/1B6/K7 b - - 0 1"

    def first_call(request):
        p = {key: .01 for key in request["questions"]}
        p["attack_b2_h8"] = .9
        return {"request": request, "probabilities": p}

    monkeypatch.setattr(pipeline, "call", first_call)
    original = graph.infer_attack_map(fen)
    corrupt_labels = deepcopy(original)
    for r in corrupt_labels["relations"]:
        r["expected"] = True
    for t in corrupt_labels["targets"]:
        t["truth_attackers"] = ["fake"]
    assert graph.verification_requests(original) == graph.verification_requests(corrupt_labels)

    def verify_call(request):
        assert set(request["questions"]) == {"geometry_b2_h8", "clear_b2_h8"}
        return {"request": request, "probabilities": {"geometry_b2_h8": .99, "clear_b2_h8": .01}}

    monkeypatch.setattr(pipeline, "call", verify_call)
    result = graph.verify_attack_map(original)
    assert not any(t["predicted_attacked"] for t in result["targets"])
    assert next(t for t in original["targets"] if t["square"] == "h8")["predicted_attacked"]
