from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eye"))
from attention import Region, coarse_candidates, detail_candidates, padded_box


def region(name, box, rectangularity=.95, texts=None):
    return Region(name, box, [], rectangularity, .8, texts or [])


def test_coarse_candidates_keep_large_rectangular_ui_regions_not_irregular_content():
    regions = [
        region("window", (1000, 700, 1500, 1350), .98, ["점채널"]),
        region("video-person", (0, 0, 1200, 900), .35),
        region("tiny", (10, 10, 50, 50), .99),
    ]
    selected = coarse_candidates(regions, 2000, 1400)
    assert len(selected) == 1
    assert selected[0].id == "R01"
    assert selected[0].texts == ["점채널"]


def test_detail_candidates_include_text_input_next_to_selected_chat():
    chat = (1500, 600, 2000, 1250)
    focus = padded_box(chat, 2000, 1400)
    regions = [
        region("input", (1500, 1240, 2000, 1400), .98, ["메시지 입력"]),
        region("elsewhere", (0, 0, 500, 200), .98, ["메시지 입력"]),
    ]
    selected = detail_candidates(regions, focus, 2000, 1400)
    assert [item.texts for item in selected] == [["메시지 입력"]]
    assert selected[0].id == "D01"


def test_detail_ids_do_not_mutate_coarse_candidate_ids():
    source = region("source", (1000, 700, 1500, 1350), .98, ["점채널"])
    coarse = coarse_candidates([source], 2000, 1400)
    detail_candidates([source], padded_box(source.box, 2000, 1400), 2000, 1400)
    assert source.id == "source"
    assert coarse[0].id == "R01"


def test_region_state_is_sdk_json_serializable():
    import numpy as np
    state = region("numpy", (0, 0, 500, 500), np.float64(.98), ["점채널"]).state(1000, 1000)
    assert json.loads(json.dumps(state))["rectangularity"] == .98
