from collections import Counter
import importlib.util
from pathlib import Path
import sys


PATH = Path(__file__).parents[1] / "eye" / "accessibility_probe.py"
spec = importlib.util.spec_from_file_location("accessibility_probe", PATH)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
AXNode, assess = module.AXNode, module.assess


def test_permission_failure_routes_to_pixels():
    result = assess([], trusted=False)
    assert result["status"] == "permission_denied"
    assert result["route"] == "pixel"


def test_empty_tree_is_unavailable():
    result = assess([], trusted=True)
    assert result["status"] == "unavailable"
    assert result["quality"] == 0


def test_rich_actionable_tree_uses_accessibility():
    nodes = [AXNode("AXApplication"), AXNode("AXWindow", frame=(0, 0, 800, 600))]
    nodes += [AXNode("AXButton", f"Button {i}", frame=(i * 10, 20, 40, 20), actions=("AXPress",), depth=2)
              for i in range(30)]
    result = assess(nodes, trusted=True, elapsed_ms=20)
    assert result["status"] == "usable"
    assert result["route"] == "accessibility"


def test_empty_web_area_forces_hybrid():
    nodes = [AXNode("AXApplication"), AXNode("AXWindow", frame=(0, 0, 800, 600))]
    nodes += [AXNode("AXButton", f"Button {i}", frame=(i * 10, 20, 40, 20), actions=("AXPress",), depth=2)
              for i in range(30)]
    nodes.append(AXNode("AXWebArea", "Page", frame=(0, 100, 800, 500), actions=("AXScrollToVisible",), depth=2))
    result = assess(nodes, trusted=True, elapsed_ms=20)
    assert result["status"] == "partial"
    assert result["route"] == "hybrid"
    assert result["quality"] <= .59


def test_transport_errors_reduce_quality():
    nodes = [AXNode("AXButton", "OK", frame=(0, 0, 50, 20), actions=("AXPress",)) for _ in range(30)]
    clean = assess(nodes, trusted=True, elapsed_ms=20)
    failing = assess(nodes, trusted=True, errors=Counter(cannot_complete=2), elapsed_ms=20)
    assert failing["quality"] < clean["quality"]
