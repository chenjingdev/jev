"""Portable OCR contract, without downloading models or importing macOS APIs."""

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eye"))
from ocr_backends import OCR, backend_for, easyocr_words
from scene import Detection, fuse


@pytest.mark.parametrize("platform,expected", [("win32", "easyocr"), ("linux", "easyocr"), ("darwin", "apple")])
def test_auto_ocr_uses_only_supported_backend(platform, expected):
    assert backend_for("auto", platform) == expected


def test_apple_on_windows_has_actionable_error():
    with pytest.raises(ValueError, match="--ocr easyocr"):
        backend_for("apple", "win32")


def test_easyocr_keeps_segment_box_and_honest_source():
    words = easyocr_words([([[11, 22], [121, 20], [119, 44], [10, 45]], "검색 입력", .83)])
    assert words[0].box == (10, 20, 111, 25)
    assert words[0].text == "검색 입력"  # no fabricated per-word coordinates
    scene = fuse(300, 200, [Detection((5, 15, 140, 40), "Search Field", .9)], words, "test", "easyocr")
    e = scene.elements[0]
    assert e.text == "검색 입력"
    assert e.evidence["text"]["source"] == "easyocr"
    assert e.confidence["text"] == .83


def test_easyocr_cpu_route_is_lazy_and_uses_bytes_for_unicode_paths(monkeypatch, tmp_path):
    seen = {}
    class Reader:
        def __init__(self, languages, **kw):
            seen.update(languages=languages, **kw)
        def readtext(self, image, **kw):
            seen["image"] = image
            return [([[0, 0], [10, 0], [10, 10], [0, 10]], "검색", .9)]
    monkeypatch.setitem(sys.modules, "easyocr", SimpleNamespace(Reader=Reader))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)))
    for module in ["Quartz", "Vision", "Foundation"]:
        monkeypatch.setitem(sys.modules, module, None)
    p = tmp_path / "한국어 화면.png"
    p.write_bytes(b"image bytes")
    engine = OCR("easyocr")
    assert engine.read(p)[0].text == "검색"
    assert engine.device == "cpu" and seen["gpu"] is False
    assert seen["languages"] == ["ko", "en"]
    assert seen["image"] == b"image bytes"
