"""Pinned open-model adapters for the element retina. Lazy optional imports."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

from scene import CAPTION_TYPES, Detection, Scene


DETECTORS = {
    "screenparser": ("docling-project/ScreenParser", "f029e565f1206577402e43206454522075be3f72", "best.pt"),
    "screen2ax": ("macpaw-research/yolov11l-ui-elements-detection", "0a742b1e6bb8ce40a1a3c822ee491ada09879587", "ui-elements-detection.pt"),
}
CAPTION_REPO = "macpaw-research/blip-icon-captioning"
CAPTION_REV = "097ebc9d718051939cf5a676daad48476a53643c"


@dataclass(frozen=True)
class ScreenTile:
    crop: tuple[int, int, int, int]
    ownership: tuple[float, float, float, float]


def _axis_tiles(length: int, detector_size: int) -> list[tuple[int, int, float, float]]:
    """Return crop start/size and a non-overlapping center-ownership interval."""
    extent = max(detector_size, round(detector_size * 1.1))
    overlap = max(32, round(detector_size * .2))
    if length <= extent + overlap // 2:
        return [(0, length, 0, length)]
    last = length - extent
    min_overlap = min(overlap, 64)
    count = max(2, math.ceil((length - min_overlap) / (extent - min_overlap)))
    starts = [round(index * last / (count - 1)) for index in range(count)]
    boundaries = [0.0]
    for left, right in zip(starts, starts[1:]):
        boundaries.append((left + extent + right) / 2)
    boundaries.append(float(length))
    return [(start, min(extent, length - start), boundaries[i], boundaries[i + 1])
            for i, start in enumerate(starts)]


def screen_tiles(width: int, height: int, detector_size: int = 1280) -> list[ScreenTile]:
    xs, ys = _axis_tiles(width, detector_size), _axis_tiles(height, detector_size)
    if len(xs) == len(ys) == 1:
        return []
    return [ScreenTile((x, y, w, h), (own_x0, own_y0, own_x1, own_y1))
            for x, w, own_x0, own_x1 in xs
            for y, h, own_y0, own_y1 in ys]


def _box_iou(a, b) -> float:
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    inter = max(0, min(ax + aw, bx + bw) - max(ax, bx)) * max(0, min(ay + ah, by + bh) - max(ay, by))
    return inter / max(aw * ah + bw * bh - inter, 1e-9)


def merge_detection_passes(detections: list[Detection], threshold: float = .55) -> list[Detection]:
    """Prefer native-scale tile boxes while removing their full-frame duplicates."""
    ordered = sorted(detections, key=lambda d: (d.source != "full", d.score), reverse=True)
    kept = []
    for detection in ordered:
        duplicate = any(detection.label == prior.label and _box_iou(detection.box, prior.box) >= threshold
                        for prior in kept)
        if not duplicate:
            kept.append(detection)
    return kept


def device_for(requested: str) -> str:
    import torch
    if requested != "auto":
        return requested
    return "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"


def synchronize(device: str) -> None:
    import torch
    if device == "mps":
        torch.mps.synchronize()
    elif device == "cuda":
        torch.cuda.synchronize()


class Detector:
    def __init__(self, name: str = "screenparser", device: str = "auto"):
        from ultralytics import YOLO
        from huggingface_hub import hf_hub_download
        self.name, self.device = name, device_for(device)
        if name == "omniparser":
            path = Path(__file__).parent / "models" / "omniparser_icon_detect.pt"
            if not path.is_file():
                raise FileNotFoundError(f"Existing OmniParser weights missing: {path}")
            self.provenance = {"repo": "microsoft/OmniParser-v2.0", "revision": "local-existing", "filename": path.name}
        else:
            repo, revision, filename = DETECTORS[name]
            path = hf_hub_download(repo, filename, revision=revision)
            self.provenance = {"repo": repo, "revision": revision, "filename": filename}
        self.model = YOLO(str(path))

    def predict(self, image, conf: float = .15, size: int = 1280, max_det: int = 600) -> list[Detection]:
        result = self.model.predict(image, device=self.device, imgsz=size, conf=conf, iou=.45,
                                    max_det=max_det, verbose=False)[0]
        synchronize(self.device)
        out = []
        for xy, cls, score in zip(result.boxes.xyxy.tolist(), result.boxes.cls.tolist(), result.boxes.conf.tolist()):
            x0, y0, x1, y1 = xy
            label = "icon" if self.name == "omniparser" else self.model.names[int(cls)]
            out.append(Detection((x0, y0, x1-x0, y1-y0), label, score))
        return out

    def predict_screen(self, image, conf: float = .15, size: int = 1280) -> tuple[list[Detection], dict]:
        """Combine a global pass with overlapping native-scale tiles for large screens."""
        tiles = screen_tiles(*image.size, size)
        full = self.predict(image, conf, size)
        candidates = [Detection(d.box, d.label, d.score, "full") for d in full]
        per_tile = []
        for index, tile in enumerate(tiles):
            x, y, width, height = tile.crop
            ox0, oy0, ox1, oy1 = tile.ownership
            local = self.predict(image.crop((x, y, x + width, y + height)), conf, size)
            accepted = 0
            for detection in local:
                dx, dy, dw, dh = detection.box
                cx, cy = x + dx + dw / 2, y + dy + dh / 2
                if not (ox0 <= cx < ox1 and oy0 <= cy < oy1):
                    continue
                # Partial objects at an internal crop edge are represented by
                # the global pass. Keeping them would fabricate split elements.
                margin = 3
                hits_internal_edge = ((x > 0 and dx <= margin) or
                                      (y > 0 and dy <= margin) or
                                      (x + width < image.width and dx + dw >= width - margin) or
                                      (y + height < image.height and dy + dh >= height - margin))
                if hits_internal_edge:
                    continue
                candidates.append(Detection((x + dx, y + dy, dw, dh), detection.label,
                                            detection.score, f"tile:{index}"))
                accepted += 1
            per_tile.append({"crop": [x, y, width, height], "raw": len(local), "accepted": accepted})
        merged = merge_detection_passes(candidates)
        return merged, {
            "enabled": bool(tiles), "tile_count": len(tiles), "passes": 1 + len(tiles),
            "full_frame_detections": len(full), "candidates": len(candidates),
            "merged_detections": len(merged), "tiles": per_tile,
        }




class Captioner:
    def __init__(self, device: str = "auto"):
        from transformers import BlipProcessor, BlipForConditionalGeneration
        self.device = device_for(device)
        self.processor = BlipProcessor.from_pretrained(CAPTION_REPO, revision=CAPTION_REV, use_fast=False)
        self.model = BlipForConditionalGeneration.from_pretrained(CAPTION_REPO, revision=CAPTION_REV).eval().to(self.device)

    def describe(self, scene: Scene, image, batch_size: int = 8, max_elements: int = 32) -> dict:
        import torch
        # Small text-free visual controls. Large pictures need a different
        # image captioner, and OCR words already describe labelled controls.
        candidates = [e for e in scene.elements if e.type in CAPTION_TYPES and not e.text
                      and max(e.box[2:]) <= max(image.size)*.16
                      and min(e.box[2:]) >= 4]
        # Dense desktops can contain hundreds of tiny glyphs. Caption the most
        # confident functional icons first instead of turning every frame into
        # a long generative-model batch.
        priority = {"utility_button": 4, "app_icon": 3, "file_icon": 3,
                    "icon": 3, "button": 2, "image": 1}
        candidates.sort(key=lambda e: (priority.get(e.type, 0), e.confidence.get("type") or 0), reverse=True)
        selected = candidates[:max_elements]
        for start in range(0, len(selected), batch_size):
            batch = selected[start:start+batch_size]
            crops = []
            for e in batch:
                x, y, w, h = e.box
                crops.append(image.crop((int(x), int(y), int(x+w+.999), int(y+h+.999))))
            inputs = self.processor(images=crops, return_tensors="pt").to(self.device)
            with torch.inference_mode():
                result = self.model.generate(**inputs, max_new_tokens=24, num_beams=1, do_sample=False)
            synchronize(self.device)
            for e, description in zip(batch, self.processor.batch_decode(result, skip_special_tokens=True)):
                e.description = " | ".join(dict.fromkeys(s.strip() for s in description.split("|") if s.strip())) or None
                e.evidence["description"] = {"source": CAPTION_REPO, "revision": CAPTION_REV, "status": "unverified_prediction", "crop_context": "element_only", "raw_caption": description}
                # Token likelihood is not a calibrated probability that the
                # inferred function is correct. Leave description score null.
        return {"candidates": len(candidates), "captioned": len(selected), "limit": max_elements}
