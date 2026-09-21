"""Compare released UI detectors and segmentation models on one desktop frame.

The report assets never contain the real screenshot: desktop results are drawn
as geometry on a blank canvas. A synthetic fixture is used for source overlays.
"""
from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

EYE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EYE))
from perception_models import Detector  # noqa: E402


COLORS = ["#286b4f", "#d17b20", "#3578b8", "#a14f94", "#987126", "#517078"]


def font(size=22):
    path = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
    return ImageFont.truetype(str(path), size) if path.is_file() else ImageFont.load_default()


def release_model(model):
    del model
    gc.collect()
    try:
        import torch
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
    except Exception:
        pass


def xywh_to_xyxy(box):
    x, y, w, h = box
    return [float(x), float(y), float(x + w), float(y + h)]


def run_detector(name, screen, fixture):
    started = time.perf_counter()
    model = Detector(name)
    load_s = time.perf_counter() - started
    model.predict(fixture, conf=.15, size=1280)
    started = time.perf_counter()
    detections = model.predict(screen, conf=.15, size=1280)
    infer_s = time.perf_counter() - started
    regions = [{"box": xywh_to_xyxy(d.box), "label": d.label, "score": float(d.score), "polygon": None}
               for d in detections]
    release_model(model)
    return {"load_s": load_s, "infer_s": infer_s, "regions": regions}


def run_segmenter(name, checkpoint, screen_path, fixture_path):
    from ultralytics import FastSAM, SAM
    cls = FastSAM if name == "FastSAM-s" else SAM
    started = time.perf_counter()
    model = cls(str(checkpoint))
    load_s = time.perf_counter() - started
    kwargs = {"device": "mps", "imgsz": 1024, "verbose": False}
    if name == "FastSAM-s":
        kwargs.update(conf=.25, iou=.7, retina_masks=False)
    model.predict(str(fixture_path), **kwargs)
    started = time.perf_counter()
    result = model.predict(str(screen_path), **kwargs)[0]
    boxes = result.boxes.xyxy.detach().cpu().tolist() if result.boxes is not None else []
    scores = result.boxes.conf.detach().cpu().tolist() if result.boxes is not None and result.boxes.conf is not None else [None] * len(boxes)
    polygons = result.masks.xy if result.masks is not None else [None] * len(boxes)
    regions = []
    for box, score, polygon in zip(boxes, scores, polygons):
        points = None if polygon is None else [[float(x), float(y)] for x, y in np.asarray(polygon)]
        regions.append({"box": [float(v) for v in box], "label": "mask", "score": None if score is None else float(score), "polygon": points})
    infer_s = time.perf_counter() - started
    release_model(model)
    return {"load_s": load_s, "infer_s": infer_s, "regions": regions}


def intersection(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def area(box):
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def iou(a, b):
    inter = intersection(a, b)
    return inter / max(area(a) + area(b) - inter, 1e-9)


def coverage(regions, width, height, scale=.125):
    size = (max(1, round(width * scale)), max(1, round(height * scale)))
    mask = Image.new("1", size, 0)
    draw = ImageDraw.Draw(mask)
    for region in regions:
        polygon = region["polygon"]
        if polygon and len(polygon) >= 3:
            draw.polygon([(round(x * scale), round(y * scale)) for x, y in polygon], fill=1)
        else:
            draw.rectangle([round(v * scale) for v in region["box"]], fill=1)
    return 100 * np.asarray(mask, dtype=np.uint8).mean()


def metrics(result, ground_truth, width, height):
    regions = result["regions"]
    screen_area = width * height
    best = [max((iou(window["box"], region["box"]) for region in regions), default=0) for window in ground_truth]
    cross_window = 0
    for region in regions:
        rarea = area(region["box"])
        if rarea <= 0:
            continue
        overlaps = sum(intersection(region["box"], window["box"]) / rarea >= .15 for window in ground_truth)
        cross_window += overlaps >= 2
    return {
        "regions": len(regions),
        "inference_s": round(result["infer_s"], 3),
        "load_s": round(result["load_s"], 3),
        "coverage_pct": round(coverage(regions, width, height), 1),
        "tiny_regions": sum(area(r["box"]) < screen_area * .001 for r in regions),
        "large_regions": sum(area(r["box"]) > screen_area * .05 for r in regions),
        "mean_best_window_iou": round(sum(best) / max(len(best), 1), 3),
        "windows_iou_50": sum(score >= .5 for score in best),
        "cross_window_regions": cross_window,
    }


def draw_result(result, size, ground_truth, title, source=None, full_resolution=False):
    width, height = size
    scale = 1 if full_resolution else min(1280 / width, 720 / height)
    canvas_size = (round(width * scale), round(height * scale))
    if source is None:
        canvas = Image.new("RGB", canvas_size, "#f4f5f3")
    else:
        canvas = source.resize(canvas_size).convert("RGB")
        shade = Image.new("RGBA", canvas_size, (255, 255, 255, 45))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), shade).convert("RGB")
    draw = ImageDraw.Draw(canvas, "RGBA")
    for index, region in enumerate(result["regions"]):
        color = COLORS[index % len(COLORS)]
        rgb = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
        polygon = region["polygon"]
        if polygon and len(polygon) >= 3:
            points = [(round(x * scale), round(y * scale)) for x, y in polygon]
            if source is not None:
                draw.polygon(points, fill=rgb + (22,))
            draw.line(points + [points[0]], fill=rgb + (150,), width=2)
        else:
            box = [round(v * scale) for v in region["box"]]
            if source is not None:
                draw.rectangle(box, fill=rgb + (14,))
            draw.rectangle(box, outline=rgb + (185,), width=2)
    if ground_truth:
        for window in ground_truth:
            box = [round(v * scale) for v in window["box"]]
            draw.rectangle(box, outline=(20, 25, 22, 255), width=4)
    draw.rectangle((0, 0, canvas.width, 40), fill=(20, 48, 36, 235))
    draw.text((14, 7), title, fill="white", font=font(22))
    return canvas


def grid(images, columns=2, gap=12):
    cell_w = max(image.width for image in images)
    cell_h = max(image.height for image in images)
    rows = (len(images) + columns - 1) // columns
    out = Image.new("RGB", (columns * cell_w + (columns - 1) * gap,
                            rows * cell_h + (rows - 1) * gap), "white")
    for index, image in enumerate(images):
        x = (index % columns) * (cell_w + gap)
        y = (index // columns) * (cell_h + gap)
        out.paste(image, (x, y))
    return out


def quartz_windows(display_x, display_y, width, height):
    import Quartz
    options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    out = []
    for item in Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID):
        bounds = item.get("kCGWindowBounds", {})
        x, y = float(bounds.get("X", 0)), float(bounds.get("Y", 0))
        w, h = float(bounds.get("Width", 0)), float(bounds.get("Height", 0))
        owner = str(item.get("kCGWindowOwnerName", ""))
        if owner == "ChatGPT Computer Use" or w < 200 or h < 150:
            continue
        local = [x - display_x, y - display_y, x - display_x + w, y - display_y + h]
        clipped = [max(0, local[0]), max(0, local[1]), min(width, local[2]), min(height, local[3])]
        if area(clipped) >= width * height * .02:
            out.append({"owner": owner, "box": clipped})
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screen", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, default=EYE / "fixtures/sample.png")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--display-origin", default="-2560,0")
    parser.add_argument("--include-source-overlays", action="store_true")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    screen = Image.open(args.screen).convert("RGB")
    fixture = Image.open(args.fixture).convert("RGB")
    display_x, display_y = (int(value) for value in args.display_origin.split(","))
    ground_truth = quartz_windows(display_x, display_y, *screen.size)
    runners = [
        ("ScreenParser", lambda: run_detector("screenparser", screen, fixture)),
        ("Screen2AX", lambda: run_detector("screen2ax", screen, fixture)),
        ("OmniParser icon detector", lambda: run_detector("omniparser", screen, fixture)),
        ("FastSAM-s", lambda: run_segmenter("FastSAM-s", EYE / "models/FastSAM-s.pt", args.screen, args.fixture)),
        ("SAM 2.1 tiny", lambda: run_segmenter("SAM 2.1 tiny", EYE / "models/sam2.1_t.pt", args.screen, args.fixture)),
    ]
    results = {}
    desktop_maps, source_maps, fixture_maps = [], [], []
    source_dir = args.out / "actual-screen"
    if args.include_source_overlays:
        source_dir.mkdir(parents=True, exist_ok=True)
    for name, runner in runners:
        print(f"Running {name}...", flush=True)
        result = runner()
        result["metrics"] = metrics(result, ground_truth, *screen.size)
        results[name] = result
        desktop_maps.append(draw_result(result, screen.size, ground_truth, name))
        if args.include_source_overlays:
            source_map = draw_result(result, screen.size, [], name, screen, full_resolution=True)
            source_map.save(source_dir / (name.lower().replace(" ", "-").replace(".", "-") + ".png"))
            source_maps.append(source_map.resize((1280, 720)))
        fixture_result = result
        # The model was warmed on the fixture; rerun for an inspectable synthetic overlay.
        if name in {"ScreenParser", "Screen2AX", "OmniParser icon detector"}:
            detector_name = {"ScreenParser": "screenparser", "Screen2AX": "screen2ax",
                             "OmniParser icon detector": "omniparser"}[name]
            detector = Detector(detector_name)
            detections = detector.predict(fixture, conf=.15, size=1280)
            fixture_result = {"regions": [{"box": xywh_to_xyxy(d.box), "label": d.label,
                                            "score": float(d.score), "polygon": None} for d in detections]}
            release_model(detector)
        else:
            checkpoint = EYE / "models" / ("FastSAM-s.pt" if name == "FastSAM-s" else "sam2.1_t.pt")
            fixture_result = run_segmenter(name, checkpoint, args.fixture, args.fixture)
        fixture_maps.append(draw_result(fixture_result, fixture.size, [], name, fixture))
    summary = {
        "screen": {"width": screen.width, "height": screen.height},
        "ground_truth_windows": ground_truth,
        "models": {name: {"metrics": result["metrics"]} for name, result in results.items()},
        "notes": {"real_screen_pixels_persisted": bool(args.include_source_overlays),
                  "desktop_visuals": ("geometry map plus user-authorized source overlays"
                                      if args.include_source_overlays else
                                      "geometry only; black rectangles are Quartz window bounds")},
    }
    (args.out / "results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    grid(desktop_maps).save(args.out / "desktop-boundary-comparison.png")
    if source_maps:
        grid(source_maps).save(args.out / "actual-screen-overlay-comparison.png")
    grid(fixture_maps).save(args.out / "fixture-overlay-comparison.png")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
