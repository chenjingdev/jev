from copy import deepcopy

import jev_attack_layers as layers
import jev_attack_polarity as polarity


def test_requests_are_label_independent_and_later_layers_receive_choices():
    sample = polarity.samples()[0]
    delta_request = layers.delta_request(sample)
    assert len(delta_request["questions"]) == 4
    fake_delta = {"answers": {
        "r0_file_delta": {"choice": "1"}, "r0_rank_delta": {"choice": "1"},
        "r1_file_delta": {"choice": "2"}, "r1_rank_delta": {"choice": "1"},
    }}
    geometry = layers.geometry_request(sample, fake_delta)
    assert geometry["questions"]["r0_geometry"]["instructions"]["model_selected_file_delta"] == 1
    assert geometry["questions"]["r1_geometry"]["instructions"]["model_selected_rank_delta"] == 1
    changed = deepcopy(sample)
    for relation in changed["relations"]:
        relation["expected"] = not relation["expected"]
        relation["probability"] = 999
    assert layers.delta_request(changed) == delta_request
    assert layers.geometry_request(changed, fake_delta) == geometry


def test_blocker_layer_supplies_every_non_endpoint_piece():
    sample = polarity.samples()[0]
    fake_geometry = {"answers": {"r0_geometry": {"choice": "valid"}, "r1_geometry": {"choice": "valid"}}}
    request = layers.blocker_request(sample, fake_geometry)
    pieces = sample["state"]["pieces"]
    expected = sum(len(pieces) - 2 for source, _ in layers.relation_inputs(sample) if source["kind"] in pipeline_sliders())
    assert len(request["questions"]) == expected


def pipeline_sliders():
    import jev_attack_pipeline
    return jev_attack_pipeline.SLIDERS


def test_truth_helpers_cover_common_geometry():
    assert layers.geometry_truth("bishop", "White", 3, -3)
    assert not layers.geometry_truth("bishop", "White", 3, -2)
    assert layers.geometry_truth("rook", "White", 0, 4)
    assert layers.geometry_truth("knight", "White", -2, 1)
    assert layers.geometry_truth("pawn", "Black", 1, -1)
    a={"column":2,"rank":2}; b={"column":8,"rank":8}
    assert layers.between_truth(a,b,{"column":3,"rank":3})
    assert not layers.between_truth(a,b,{"column":3,"rank":4})
