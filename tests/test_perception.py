"""Offline regressions for the model boundary: geometry, OCR ownership, unknowns.

These tests neither download models nor call Jev. Actual model smoke-test
results and failure examples are documented separately in eye/README.md.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eye"))

from perception_models import merge_detection_passes, screen_tiles
from scene import Detection, Word, fuse


def test_nested_ocr_is_owned_by_control_and_placeholder_is_not_value():
    scene = fuse(800, 600, [
        Detection((0, 0, 800, 100), "Toolbar", .9),
        Detection((100, 20, 300, 50), "Search Field", .8),
        Detection((150, 30, 80, 20), "Text", .7),
    ], [Word((150, 30, 80, 20), "검색", .95)], "test")
    control = next(e for e in scene.elements if e.type == "search_field")
    assert control.text == "검색"
    assert control.state["empty"] is None  # OCR could be value OR placeholder
    assert control.state["focused"] is None
    assert control.group == next(e.id for e in scene.elements if e.type == "toolbar")
    assert len([e for e in scene.elements if e.text == "검색"]) == 1


def test_nearby_label_is_not_swallowed_and_ocr_reading_order_is_kept():
    scene = fuse(400, 200, [Detection((100, 50, 200, 50), "Button", .9)], [
        Word((10, 50, 60, 20), "Label", .9),
        Word((110, 61, 70, 20), "Save", .95),
        Word((190, 59, 40, 20), "as", .85),
    ], "test")
    assert next(e for e in scene.elements if e.type == "button").text == "Save as"
    assert any(e.text == "Label" and e.type == "text" for e in scene.elements)


def test_boxes_are_clipped_and_invalid_boxes_do_not_enter_payload():
    scene = fuse(100, 80, [
        Detection((-10, 5, 30, 20), "Button", .8),
        Detection((200, 200, 20, 20), "Button", .9),
        Detection((10, 10, -2, 20), "Button", .9),
        Detection((float("nan"), 0, 20, 20), "Button", .9),
    ], [], "test")
    assert len(scene.elements) == 1
    assert scene.elements[0].box == (0, 5, 20, 20)
    assert scene.to_dict()["image"]["coordinates"] == "image_pixels_xywh"


def test_conflicting_leaf_labels_merge_but_nested_control_is_preserved():
    scene = fuse(600, 200, [
        Detection((0, 0, 400, 80), "Search Field", .9),
        Detection((10, 10, 20, 20), "Button", .8),
        Detection((10, 10, 20, 20), "Image", .7),
    ], [], "test")
    assert len(scene.elements) == 2
    child = next(e for e in scene.elements if e.type == "button")
    assert child.evidence["alternative_detections"] == [{"label": "Image", "score": .7}]
    assert child.group == next(e.id for e in scene.elements if e.type == "search_field")


def test_empty_scene_reports_no_elements_and_unknown_states():
    scene = fuse(100, 100, [], [], "test")
    assert scene.to_dict()["elements"] == []
    assert scene.to_dict()["capabilities"]["state_recognition"] is False
    assert scene.to_dict()["capabilities"]["temporal_tracking"] is False


def test_nested_button_text_box_does_not_steal_ocr_from_full_button():
    scene = fuse(400, 200, [
        Detection((100, 50, 150, 50), "Button", .7),
        Detection((150, 65, 40, 20), "Button", .9),
    ], [Word((150, 65, 40, 20), "검색", .95)], "test")
    assert len(scene.elements) == 1
    e = scene.elements[0]
    assert e.box == (100, 50, 150, 50)
    assert e.text == "검색"
    assert e.confidence["type"] == .7
    assert e.evidence["contained_predictions"][0]["score"] == .9



def test_free_ocr_title_is_one_choice_but_distant_tabs_stay_separate():
    scene = fuse(500, 300, [], [
        Word((10, 21, 30, 18), "망막", .9, 1),
        Word((44, 20, 30, 18), "모델", .9, 1),
        Word((78, 20, 30, 18), "노트", .9, 1),
        Word((160, 20, 30, 18), "설정", .9, 1),
        Word((10, 50, 30, 18), "다음", .9, 2),
    ], "test")
    assert [e.text for e in scene.elements] == ["망막 모델 노트", "설정", "다음"]
    assert scene.elements[0].box == (10, 20, 98, 19)


def test_large_desktop_is_tiled_with_complete_non_overlapping_ownership():
    tiles = screen_tiles(2560, 1440, 1280)
    assert [tile.crop for tile in tiles] == [(0, 0, 1408, 1440), (1152, 0, 1408, 1440)]
    assert [tile.ownership for tile in tiles] == [(0, 0, 1280, 1440), (1280, 0, 2560, 1440)]
    assert screen_tiles(1280, 900, 1280) == []
    wide = screen_tiles(3840, 1440, 1280)
    assert [tile.crop[0] for tile in wide] == [0, 1216, 2432]


def test_tile_detection_replaces_duplicate_full_frame_box_in_global_coordinates():
    merged = merge_detection_passes([
        Detection((100, 100, 200, 50), "Button", .9, "full"),
        Detection((102, 99, 198, 51), "Button", .7, "tile:0"),
        Detection((500, 100, 200, 50), "Button", .8, "tile:0"),
        Detection((102, 99, 198, 51), "Text", .95, "tile:0"),
    ])
    assert [(d.label, d.box, d.source) for d in merged] == [
        ("Text", (102, 99, 198, 51), "tile:0"),
        ("Button", (500, 100, 200, 50), "tile:0"),
        ("Button", (102, 99, 198, 51), "tile:0"),
    ]
