"""Read-only macOS accessibility probe for choosing an input backend.

This does not use CDP or the DOM.  It inspects the native AX tree exported by
the target process and reports evidence; the score is a routing heuristic, not
a probability.  Visual/AX agreement is deliberately left to the retina fusion
stage because screen pixels and AX coordinates need an explicit display map.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
from dataclasses import asdict, dataclass
import json
import sys
import time


CONTROL_ROLES = {
    "AXButton", "AXCheckBox", "AXComboBox", "AXLink", "AXMenuItem",
    "AXPopUpButton", "AXRadioButton", "AXSlider", "AXTabGroup",
    "AXTextArea", "AXTextField",
}
GENERIC_ROLES = {"AXApplication", "AXGroup", "AXScrollArea", "AXUnknown", "AXWindow"}


@dataclass
class AXNode:
    role: str
    title: str | None = None
    description: str | None = None
    frame: tuple[float, float, float, float] | None = None
    actions: tuple[str, ...] = ()
    depth: int = 0
    parent_role: str | None = None
    has_name: bool = False
    inside_web_area: bool = False

    @property
    def named(self) -> bool:
        return self.has_name or bool((self.title or self.description or "").strip())

    @property
    def actionable(self) -> bool:
        return bool(self.actions) or self.role in CONTROL_ROLES


def assess(nodes: list[AXNode], *, trusted: bool, errors: Counter | None = None,
           elapsed_ms: float = 0.0, truncated: bool = False) -> dict:
    """Turn observable AX properties into a conservative routing hint."""
    errors = errors or Counter()
    if not trusted:
        return {
            "status": "permission_denied", "route": "pixel", "quality": 0.0,
            "quality_semantics": "routing heuristic, not probability",
            "reason": "Accessibility permission is not granted.",
        }
    if not nodes:
        return {
            "status": "unavailable", "route": "pixel", "quality": 0.0,
            "quality_semantics": "routing heuristic, not probability",
            "reason": "The application returned no accessibility nodes.",
            "errors": dict(errors), "elapsed_ms": round(elapsed_ms, 1),
        }

    content = [n for n in nodes if n.role not in {"AXApplication", "AXWindow"}]
    named = [n for n in content if n.named]
    framed = [n for n in content if n.frame]
    controls = [n for n in content if n.role in CONTROL_ROLES]
    actionable = [n for n in controls if n.actions]
    web_areas = [n for n in content if n.role == "AXWebArea"]
    web_descendants = [n for n in content if n.inside_web_area]
    non_generic = [n for n in content if n.role not in GENERIC_ROLES]

    # Each term answers a separate mechanical question.  The caps avoid large
    # trees looking perfect merely because they contain many nodes.
    structure = min(len(content) / 30, 1.0)
    naming = len(named) / max(len(non_generic), 1)
    geometry = len(framed) / max(len(content), 1)
    action_support = len(actionable) / max(len(controls), 1) if controls else 0.0
    responsiveness = 1.0 if elapsed_ms <= 250 else max(0.0, 1 - (elapsed_ms - 250) / 1750)
    quality = .25 * structure + .2 * min(naming, 1) + .2 * geometry + .25 * action_support + .1 * responsiveness

    partial_web = bool(web_areas) and not web_descendants
    if errors.get("cannot_complete") or errors.get("not_implemented"):
        quality *= .7
    if partial_web:
        quality = min(quality, .59)
    quality = round(max(0.0, min(quality, 1.0)), 3)

    if quality >= .75 and not partial_web:
        status, route = "usable", "accessibility"
    elif quality >= .35:
        status, route = "partial", "hybrid"
    else:
        status, route = "sparse", "pixel"

    return {
        "status": status,
        "route": route,
        "quality": quality,
        "quality_semantics": "routing heuristic, not probability",
        "metrics": {
            "nodes": len(nodes), "content_nodes": len(content),
            "named": len(named), "framed": len(framed),
            "controls": len(controls), "actionable_controls": len(actionable),
            "web_areas": len(web_areas), "web_descendants": len(web_descendants),
            "truncated": truncated,
        },
        "errors": dict(errors),
        "elapsed_ms": round(elapsed_ms, 1),
        "reason": ("A web area exists but its page descendants are not exposed."
                   if partial_web else "AX structure, names, geometry, actions, and latency were measured."),
    }


def _mac_modules():
    if sys.platform != "darwin":
        raise RuntimeError("The native accessibility probe currently supports macOS only.")
    import ApplicationServices as AX
    from AppKit import NSWorkspace
    return AX, NSWorkspace


def _read(AX, element, attribute, errors: Counter):
    code, value = AX.AXUIElementCopyAttributeValue(element, attribute, None)
    if code == AX.kAXErrorSuccess:
        return value
    names = {
        AX.kAXErrorCannotComplete: "cannot_complete",
        AX.kAXErrorNotImplemented: "not_implemented",
        AX.kAXErrorAPIDisabled: "api_disabled",
        AX.kAXErrorInvalidUIElement: "invalid_element",
    }
    # Unsupported/no-value attributes are normal for heterogeneous nodes.
    if code not in (AX.kAXErrorAttributeUnsupported, AX.kAXErrorNoValue):
        errors[names.get(code, f"ax_error_{code}")] += 1
    return None


def _point(AX, value, value_type):
    if value is None:
        return None
    ok, result = AX.AXValueGetValue(value, value_type, None)
    return result if ok else None


def find_application(name: str):
    _, NSWorkspace = _mac_modules()
    target = name.casefold()
    matches = []
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        app_name = str(app.localizedName() or "")
        bundle = str(app.bundleIdentifier() or "")
        if target in app_name.casefold() or target in bundle.casefold():
            matches.append((app_name, bundle, int(app.processIdentifier())))
    return matches


def probe(pid: int, *, max_nodes: int = 1000, max_depth: int = 20,
          include_text: bool = False) -> dict:
    AX, _ = _mac_modules()
    trusted = bool(AX.AXIsProcessTrusted())
    if not trusted:
        return assess([], trusted=False)

    started = time.perf_counter()
    errors = Counter()
    root = AX.AXUIElementCreateApplication(pid)
    queue = deque([(root, 0, None, False)])
    # Application AXChildren is not consistent across frameworks. Seed the
    # documented top-level containers as well; `seen` removes duplicates.
    for attribute in (AX.kAXFocusedWindowAttribute, AX.kAXWindowsAttribute,
                      AX.kAXMenuBarAttribute):
        value = _read(AX, root, attribute, errors)
        if value is None:
            continue
        values = value if isinstance(value, (list, tuple)) else (value,)
        queue.extend((item, 1, "AXApplication", False) for item in values)
    recorded = set()
    nodes: list[AXNode] = []
    traversed = 0
    while queue and len(nodes) < max_nodes and traversed < max_nodes * 5:
        element, depth, parent_role, inside_web_area = queue.popleft()
        traversed += 1
        role = str(_read(AX, element, AX.kAXRoleAttribute, errors) or "AXUnknown")
        title = _read(AX, element, AX.kAXTitleAttribute, errors)
        description = _read(AX, element, AX.kAXDescriptionAttribute, errors)
        position = _point(AX, _read(AX, element, AX.kAXPositionAttribute, errors), AX.kAXValueCGPointType)
        size = _point(AX, _read(AX, element, AX.kAXSizeAttribute, errors), AX.kAXValueCGSizeType)
        frame = None
        if position is not None and size is not None:
            frame = (float(position.x), float(position.y), float(size.width), float(size.height))
        code, action_names = AX.AXUIElementCopyActionNames(element, None)
        actions = tuple(map(str, action_names or ())) if code == AX.kAXErrorSuccess else ()
        fingerprint = (role, str(title or ""), str(description or ""), frame, actions,
                       inside_web_area)
        if fingerprint not in recorded:
            recorded.add(fingerprint)
            nodes.append(AXNode(
                role=role,
                title=str(title) if include_text and title else None,
                description=str(description) if include_text and description else None,
                frame=frame, actions=actions, depth=depth, parent_role=parent_role,
                has_name=bool(str(title or description or "").strip()),
                inside_web_area=inside_web_area,
            ))
        if depth < max_depth:
            children = _read(AX, element, AX.kAXChildrenAttribute, errors) or ()
            queue.extend((child, depth + 1, role, inside_web_area or role == "AXWebArea")
                         for child in children)

    elapsed_ms = (time.perf_counter() - started) * 1000
    result = assess(nodes, trusted=True, errors=errors, elapsed_ms=elapsed_ms,
                    truncated=bool(queue))
    result.update({
        "schema_version": "jev.accessibility.probe.v1",
        "pid": pid,
        "roles": dict(Counter(n.role for n in nodes).most_common()),
        "nodes": [asdict(n) for n in nodes] if include_text else None,
    })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--pid", type=int)
    target.add_argument("--app", help="Substring of app name or bundle id")
    parser.add_argument("--max-nodes", type=int, default=1000)
    parser.add_argument("--include-text", action="store_true")
    args = parser.parse_args()
    pid = args.pid
    if args.app:
        matches = find_application(args.app)
        if not matches:
            raise SystemExit(f"No running application matched {args.app!r}")
        pid = matches[0][2]
    print(json.dumps(probe(pid, max_nodes=args.max_nodes, include_text=args.include_text),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
