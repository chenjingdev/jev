"""Coarse-to-fine visual attention over FastSAM regions and OCR text."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
import time

import numpy as np


Box = tuple[float, float, float, float]  # x0, y0, x1, y1


@dataclass
class Region:
    id: str
    box: Box
    polygon: list[tuple[float, float]]
    rectangularity: float
    score: float | None
    texts: list[str] = field(default_factory=list)

    @property
    def area(self) -> float:
        x0, y0, x1, y1 = self.box
        return max(0, x1 - x0) * max(0, y1 - y0)

    def state(self, width: int, height: int) -> dict:
        x0, y0, x1, y1 = self.box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        return {
            "id": self.id,
            "bounds_xywh": [round(x0), round(y0), round(x1 - x0), round(y1 - y0)],
            "screen_position": [round(100 * cx / width), round(100 * cy / height)],
            "area_percent": round(float(100 * self.area / (width * height)), 2),
            "rectangularity": round(float(self.rectangularity), 3),
            "observed_text": " | ".join(self.texts)[:1200] or "(no text read)",
        }


def polygon_area(points) -> float:
    pts = np.asarray(points, dtype=float)
    if len(pts) < 3:
        return 0.0
    return abs(np.dot(pts[:, 0], np.roll(pts[:, 1], 1)) -
               np.dot(pts[:, 1], np.roll(pts[:, 0], 1))) / 2


def contains_center(box: Box, word) -> bool:
    x0, y0, x1, y1 = box
    x, y, width, height = word.box
    return x0 <= x + width / 2 <= x1 and y0 <= y + height / 2 <= y1


def observed_regions(result, words) -> list[Region]:
    boxes = result.boxes.xyxy.detach().cpu().tolist() if result.boxes is not None else []
    scores = result.boxes.conf.detach().cpu().tolist() if result.boxes is not None and result.boxes.conf is not None else [None] * len(boxes)
    polygons = result.masks.xy if result.masks is not None else [None] * len(boxes)
    regions = []
    for index, (box, score, polygon) in enumerate(zip(boxes, scores, polygons)):
        x0, y0, x1, y1 = (float(v) for v in box)
        points = [] if polygon is None else [(float(x), float(y)) for x, y in polygon]
        bbox_area = max(1, (x1 - x0) * (y1 - y0))
        texts = [word.text for word in words if contains_center((x0, y0, x1, y1), word)]
        regions.append(Region(f"M{index:03d}", (x0, y0, x1, y1), points,
                              polygon_area(points) / bbox_area, None if score is None else float(score), texts))
    return regions


def coarse_candidates(regions: list[Region], width: int, height: int, limit: int = 20) -> list[Region]:
    screen_area = width * height
    selected = [region for region in regions
                if .04 <= region.area / screen_area <= .45
                and region.rectangularity >= .70
                and region.box[2] - region.box[0] >= 240
                and region.box[3] - region.box[1] >= 160]
    selected.sort(key=lambda region: region.area, reverse=True)
    return [replace(region, id=f"R{index:02d}") for index, region in enumerate(selected[:limit], 1)]


def padded_box(box: Box, width: int, height: int, x_ratio=.15, y_ratio=.20, minimum=80) -> Box:
    x0, y0, x1, y1 = box
    px = max(minimum, (x1 - x0) * x_ratio)
    py = max(minimum, (y1 - y0) * y_ratio)
    return max(0, x0 - px), max(0, y0 - py), min(width, x1 + px), min(height, y1 + py)


def intersection_over_region(region: Region, box: Box) -> float:
    x0, y0, x1, y1 = region.box
    bx0, by0, bx1, by1 = box
    inter = max(0, min(x1, bx1) - max(x0, bx0)) * max(0, min(y1, by1) - max(y0, by0))
    return inter / max(region.area, 1)


def detail_candidates(regions: list[Region], focus: Box, width: int, height: int, limit: int = 48) -> list[Region]:
    screen_area = width * height
    selected = [region for region in regions
                if .0005 <= region.area / screen_area <= .08
                and region.rectangularity >= .42
                and intersection_over_region(region, focus) >= .70
                and (region.texts or region.area / screen_area >= .008)]
    # Text-bearing regions first, then more rectangular regions and larger context.
    selected.sort(key=lambda region: (bool(region.texts), region.rectangularity, region.area), reverse=True)
    return [replace(region, id=f"D{index:02d}") for index, region in enumerate(selected[:limit], 1)]


def ask_jev(state: dict, candidates: list[Region], instructions: str, presence: str,
            model: str = "jev-latest", client=None) -> dict:
    from typesafe_sdk import Choice, Noul, NoulCriteria, TypeSafeClient
    client = client or TypeSafeClient(timeout=120.0)
    criteria = {region.id: None for region in candidates}
    started = time.perf_counter()
    response = client.system_one(
        model=model,
        state=state,
        questions={
            "region": Choice(instructions=instructions, criteria=criteria),
            "exists": Noul(
                instructions=presence,
                criteria=NoulCriteria(
                    true="The supplied region observations contain the requested target.",
                    false="None of the supplied region observations contain the requested target.",
                ),
            ),
        },
    )
    answer = response.answers["region"]
    usage = response.usage
    return {
        "choice": answer.choice,
        "probabilities": dict(answer.probabilities),
        "confidence": answer.confidence,
        "exists": response.answers["exists"].noul,
        "model": response.model,
        "latency_ms": round(1000 * (time.perf_counter() - started)),
        "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
    }


def region_by_id(regions: list[Region], region_id: str) -> Region:
    return next(region for region in regions if region.id == region_id)


def fastsam_observe(image_path: Path, model_path: Path):
    from ultralytics import FastSAM
    from ocr_backends import OCR
    model = FastSAM(str(model_path))
    started = time.perf_counter()
    result = model.predict(str(image_path), device="mps", imgsz=1024, retina_masks=False,
                           conf=.25, iou=.7, verbose=False)[0]
    inference_s = time.perf_counter() - started
    words = OCR("apple").read(image_path)
    return observed_regions(result, words), words, inference_s
