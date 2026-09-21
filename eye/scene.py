"""Element-level retina output and fusion. No model, macOS, or Jev dependencies.

Boxes use source-image pixels (x, y, width, height), never display points.
Scores retain their provenance; they are not calibrated probabilities.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math


Box = tuple[float, float, float, float]
CONTAINERS = {
    "table", "column_browser", "navigation_bar", "toolbar", "tab_bar", "side_bar",
    "context_menu", "dock_menu", "edit_menu", "window", "screen", "list", "menu",
    "popup_menu", "bottom_navigation", "breadcrumb", "calendar", "carousel",
}
INPUTS = {"text_input", "search_field", "search_bar"}
TEXT_TYPES = {"text", "heading", "code_snippet"}
CAPTION_TYPES = {"button", "utility_button", "app_icon", "file_icon", "icon", "image"}
CONTROL_TYPES = INPUTS | {"button", "utility_button", "checkbox", "radio", "toggle", "slider", "select", "tab"}


def kind(label: str) -> str:
    return {
        "Column/Browser": "column_browser", "ContextMenu": "context_menu",
        "DockMenu": "dock_menu", "EditMenu": "edit_menu", "PopUp Menu": "popup_menu",
        "Radiobox": "radio", "Toggles": "toggle", "Switch": "toggle",
        "Date-Time picker": "date_time_picker",
        "AXButton": "button", "AXTextArea": "text_input", "AXImage": "image",
        "AXLink": "link", "AXDisclosureTriangle": "disclosure",
    }.get(label, label.lower().replace(" ", "_"))


def area(box: Box) -> float:
    return max(0, box[2]) * max(0, box[3])


def overlap(a: Box, b: Box) -> float:
    return max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])) * max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))


def iou(a: Box, b: Box) -> float:
    inter = overlap(a, b)
    return inter / max(area(a) + area(b) - inter, 1e-9)


def clip(box: Box, width: int, height: int) -> Box | None:
    if len(box) != 4 or not all(math.isfinite(v) for v in box):
        return None
    x, y, w, h = box
    if w <= 0 or h <= 0:
        return None
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(width, x + w), min(height, y + h)
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1 - x0, y1 - y0)


@dataclass
class Detection:
    box: Box
    label: str
    score: float
    source: str | None = None


@dataclass
class Word:
    box: Box
    text: str
    score: float
    line: int | None = None


def text_runs(words: list[Word]) -> list[list[Word]]:
    """Join nearby free OCR words into readable labels without crossing controls.

    A shared OCR line is not sufficient by itself: tabs can share that line.
    Require close spacing and vertical alignment too. This is display geometry,
    not language-specific matching or a known target title.
    """
    groups: list[list[Word]] = []
    for word in sorted(words, key=lambda w: (w.line is None,
                       w.line if w.line is not None else round((w.box[1]+w.box[3]/2)/6), w.box[0])):
        candidates = []
        for group in groups:
            last = group[-1]
            x, y, w, h = word.box
            lx, ly, lw, lh = last.box
            gap = x - (lx+lw)
            aligned = abs((y+h/2)-(ly+lh/2)) <= min(h, lh)*.35
            same_line = word.line == last.line
            if same_line and aligned and -.1*min(h, lh) <= gap <= .8*min(h, lh):
                candidates.append((gap, group))
        if candidates:
            min(candidates, key=lambda p: p[0])[1].append(word)
        else:
            groups.append([word])
    return groups


@dataclass
class Element:
    id: str
    box: Box
    type: str
    text: str | None = None  # visible text, NOT necessarily the field's value
    description: str | None = None  # unverified model caption, not an action guarantee
    group: str | None = None
    state: dict[str, bool | None] = field(default_factory=lambda: {
        "focused": None, "disabled": None, "selected": None, "checked": None,
        "expanded": None, "empty": None,
    })
    confidence: dict[str, float | None] = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)


@dataclass
class Scene:
    width: int
    height: int
    elements: list[Element]
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema_version": "jev.retina.elements.v1",
            "image": {"width": self.width, "height": self.height, "coordinates": "image_pixels_xywh"},
            "unknown": "null means unobserved or unsupported, not false",
            "score_semantics": "uncalibrated per-model scores; missing scores are null",
            "id_scope": "this image only; no temporal tracking yet",
            "capabilities": {"detection": True, "ocr": True, "icon_captioning": self.metadata.get("captioning", False), "state_recognition": False, "temporal_tracking": False},
            "elements": [asdict(e) for e in self.elements],
            "metadata": self.metadata,
        }



def fuse(width: int, height: int, detections: list[Detection], words: list[Word], detector: str, ocr_source="apple_vision") -> Scene:
    """Link OCR to the smallest containing non-container element.

    Text-only detector boxes are replaced by OCR when they cover the same words,
    avoiding duplicate text choices. A word belongs to one element; nearby labels
    remain separate instead of being fabricated as input values/placeholders.
    """
    valid_words = [Word(b, w.text.strip(), w.score, w.line) for w in words
                   if w.text.strip() and (b := clip(w.box, width, height)) is not None]
    elements = []
    for d in sorted(detections, key=lambda d: -d.score):
        b = clip(d.box, width, height)
        if b is None:
            continue
        k = kind(d.label)
        # Merge near-identical leaf boxes, retaining competing model labels as
        # evidence. Actual container/child or small nested boxes remain intact.
        duplicate = next((e for e in elements if iou(e.box, b) >= .8
                          and (e.type == k or (e.type not in CONTAINERS | TEXT_TYPES and k not in CONTAINERS | TEXT_TYPES))), None)
        if duplicate:
            duplicate.evidence.setdefault("alternative_detections", []).append({"label": d.label, "score": round(d.score, 4)})
            continue
        if k in TEXT_TYPES and any(overlap(b, w.box) / area(w.box) >= .7 for w in valid_words):
            continue
        type_evidence = {"source": detector, "label": d.label}
        if d.source:
            type_evidence["detector_pass"] = d.source
        elements.append(Element("", b, k, confidence={"type": round(d.score, 4), "text": None, "description": None, "state": None},
                                evidence={"type": type_evidence, "state": {"status": "not_implemented"}}))

    # ScreenParser may detect both a control's full boundary and its text/glyph
    # as the same control type. Treat fully nested same-family detections as
    # alternate extents, not separate controls. Keep the outer score unchanged.
    # Different types (e.g. icon inside a field) remain independent observations.
    nested = set()
    def family(e):
        return "input" if e.type in INPUTS else e.type
    for i, e in enumerate(elements):
        if e.type not in CONTROL_TYPES:
            continue
        parents = [p for p in elements if p.type in CONTROL_TYPES and family(p) == family(e)
                   and area(p.box) > area(e.box)*1.2 and overlap(p.box, e.box)/area(e.box) >= .95]
        if parents:
            parent = max(parents, key=lambda p: area(p.box))
            parent.evidence.setdefault("contained_predictions", []).append({"box": e.box, "label": e.evidence["type"]["label"], "score": e.confidence["type"]})
            nested.add(i)
    elements = [e for i, e in enumerate(elements) if i not in nested]

    owners: dict[int, list[Word]] = {}
    free = []
    for w in valid_words:
        candidates = [(i, e) for i, e in enumerate(elements) if e.type not in CONTAINERS | TEXT_TYPES
                      and overlap(e.box, w.box) / area(w.box) >= .75]
        if candidates:
            i, _ = min(candidates, key=lambda item: area(item[1].box))
            owners.setdefault(i, []).append(w)
        else:
            free.append(w)
    for i, ws in owners.items():
        # OCR already supplies reading order. Keep it instead of sorting by tiny
        # baseline differences between words of different font heights.
        elements[i].text = " ".join(w.text for w in ws)
        elements[i].confidence["text"] = round(min(w.score for w in ws), 4)
        elements[i].evidence["text"] = {"source": ocr_source, "word_boxes": [w.box for w in ws], "score_aggregation": "minimum word score"}
    for run in text_runs(free):
        x, y = min(w.box[0] for w in run), min(w.box[1] for w in run)
        box = (x, y, max(w.box[0]+w.box[2] for w in run)-x, max(w.box[1]+w.box[3] for w in run)-y)
        elements.append(Element("", box, "text", text=" ".join(w.text for w in run),
                                confidence={"type": None, "text": round(min(w.score for w in run), 4), "description": None, "state": None},
                                evidence={"type": {"source": "ocr_text_box"}, "text": {"source": ocr_source, "word_boxes": [w.box for w in run], "score_aggregation": "minimum word score"}, "state": {"status": "not_implemented"}}))
    elements.sort(key=lambda e: (round(e.box[1] / 12), e.box[0], area(e.box)))
    for i, e in enumerate(elements, 1):
        e.id = f"e{i}"
    for e in elements:
        parents = [p for p in elements if p is not e and p.type in CONTAINERS | INPUTS
                   and area(p.box) > area(e.box) * 1.2
                   and overlap(p.box, e.box) / area(e.box) >= .9]
        if parents:
            e.group = min(parents, key=lambda p: area(p.box)).id
            e.evidence["group"] = {"source": "geometric_containment", "not_semantic_hierarchy": True}
    return Scene(width, height, elements)
