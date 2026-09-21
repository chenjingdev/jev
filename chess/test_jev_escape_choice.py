from copy import deepcopy

import jev_escape_choice as escape


def test_all_squares_and_none_for_every_friendly_piece_without_label_leak():
    for split in ("development", "evaluation"):
        for case in escape.fixtures(split):
            request = escape.request_for(case)
            state = request["state"]
            friendly = [p for p in state["pieces"] if p["color"] == state["side_to_move"]]
            assert len(request["questions"]) == len(friendly)
            for question in request["questions"].values():
                assert set(question["criteria"]) == set(escape.SQUARES) | {"none"}
            serialized = str(request)
            assert "expected" not in serialized and "legal_moves" not in serialized
            assert "checkmate" not in serialized.lower() and "attackers" not in serialized
            changed = deepcopy(case); changed["expected"] = not case["expected"]
            assert escape.request_for(changed) == request
