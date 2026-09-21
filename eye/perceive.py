"""Visual sensor: an image in, structured observations out. No actions or API calls."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from scene import Scene, fuse
from perception_models import Captioner, Detector, synchronize
from ocr_backends import OCR


class Retina:
    """Keep the models loaded across images; all timings synchronize the GPU."""

    def __init__(self, detector="screenparser", device="auto", captions=True, ocr="auto", ocr_device="auto"):
        started = time.perf_counter()
        self.detector = Detector(detector, device)
        self.captioner = Captioner(self.detector.device) if captions else None
        self.ocr = OCR(ocr, ocr_device)
        synchronize(self.detector.device)
        self.load_s = time.perf_counter() - started

    def see(self, path: Path, conf=.15, size=1280, progress=None) -> Scene:
        from PIL import Image
        progress = progress or (lambda stage: None)
        start = time.perf_counter()
        progress("decode")
        with Image.open(path) as source:
            image = source.convert("RGB")
        decoded = time.perf_counter()
        progress("detection")
        detections, tiling = self.detector.predict_screen(image, conf, size)
        detected = time.perf_counter()
        progress("ocr")
        words = self.ocr.read(path)
        read = time.perf_counter()
        progress("fusion")
        scene = fuse(*image.size, detections, words, self.detector.provenance["repo"], self.ocr.name)
        fused = time.perf_counter()
        progress("captioning")
        caption_stats = self.captioner.describe(scene, image) if self.captioner else {"candidates": 0, "captioned": 0, "limit": 0}
        finish = time.perf_counter()
        scene.metadata = {
            "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "detector": self.detector.provenance, "device": self.detector.device,
            "ocr": self.ocr.provenance(),
            "captioning": self.captioner is not None,
            "captioned_elements": caption_stats["captioned"], "caption_candidates": caption_stats["candidates"],
            "caption_limit": caption_stats["limit"], "raw_detections": len(detections), "ocr_words": len(words),
            "tiling": tiling,
            "settings": {"confidence_threshold": conf, "detector_image_size": size,
                         "iou_threshold": .45, "max_detections_per_pass": 600},
            "timings": {"load_models_s": round(self.load_s, 4), "decode_s": round(decoded-start, 4),
                        "detect_s": round(detected-decoded, 4), "ocr_s": round(read-detected, 4),
                        "fuse_s": round(fused-read, 4), "caption_s": round(finish-fused, 4),
                        "total_s": round(finish-start, 4)},
        }
        return scene



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--out", type=Path, help="Write JSON here; otherwise print it")
    parser.add_argument("--detector", choices=("screenparser", "screen2ax", "omniparser"), default="screenparser")
    parser.add_argument("--device", choices=("auto", "cpu", "mps", "cuda"), default="auto")
    parser.add_argument("--ocr", choices=("auto", "apple", "easyocr"), default="auto")
    parser.add_argument("--ocr-device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--no-caption", action="store_true")
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error("Image file not found")
    print("Loading visual sensor models…", file=sys.stderr)
    retina = Retina(args.detector, args.device, not args.no_caption, args.ocr, args.ocr_device)
    scene = retina.see(args.image)
    result = json.dumps(scene.to_dict(), ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(result, encoding="utf-8")
    else:
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
