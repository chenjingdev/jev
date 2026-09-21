"""OCR backends producing the same image-pixel boxes on macOS and Windows."""
from __future__ import annotations

from pathlib import Path
import sys
from scene import Word


def backend_for(requested: str, platform: str | None = None) -> str:
    platform = sys.platform if platform is None else platform
    if requested == "auto":
        return "apple" if platform == "darwin" else "easyocr"
    if requested not in {"apple", "easyocr"}:
        raise ValueError(f"Unknown OCR backend: {requested}")
    if requested == "apple" and platform != "darwin":
        raise ValueError("Apple Vision requires macOS; use --ocr easyocr")
    return requested


def easyocr_words(rows) -> list[Word]:
    """Keep real segment boxes; never invent per-word positions in a line."""
    out = []
    for line, (quad, text, score) in enumerate(rows):
        if not str(text).strip():
            continue
        xs, ys = zip(*quad)
        box = (float(min(xs)), float(min(ys)), float(max(xs)-min(xs)), float(max(ys)-min(ys)))
        out.append(Word(box, str(text).strip(), float(score), line))
    return out


class OCR:
    def __init__(self, backend="auto", device="auto"):
        self.backend = backend_for(backend)
        self.name = "apple_vision" if self.backend == "apple" else "easyocr"
        self.reader = None
        self.device = "apple_vision"
        if self.backend == "easyocr":
            try:
                import easyocr
            except ImportError as exc:
                raise RuntimeError("EasyOCR is required: uv sync --extra perception --extra portable") from exc
            import torch
            # CPU is the portable default on non-CUDA hosts. MPS inference of
            # EasyOCR is not assumed even when the detector uses MPS.
            if device == "auto":
                device = "cuda" if torch.cuda.is_available() else "cpu"
            if device not in {"cpu", "cuda"}:
                raise ValueError("EasyOCR supports --ocr-device cpu or cuda here")
            if device == "cuda" and not torch.cuda.is_available():
                raise ValueError("CUDA requested for OCR but unavailable")
            self.device = device
            self.reader = easyocr.Reader(["ko", "en"], gpu=device if device == "cuda" else False, verbose=False)

    def read(self, path: Path) -> list[Word]:
        if self.backend == "apple":
            return _read_apple_words(path)
        # Bytes avoid Windows/OpenCV Unicode path decoding differences.
        rows = self.reader.readtext(path.read_bytes(), detail=1, paragraph=False, workers=0, batch_size=8)
        if self.device == "cuda":
            import torch
            torch.cuda.synchronize()
        return easyocr_words(rows)

    def provenance(self):
        from importlib.metadata import version
        return {"backend": self.name, "device": self.device,
                "languages": ["ko-KR", "en-US"] if self.backend == "apple" else ["ko", "en"],
                "package_version": None if self.backend == "apple" else version("easyocr"),
                "box_granularity": "word" if self.backend == "apple" else "segment"}


def _read_apple_words(path: Path) -> list[Word]:
    """Apple Vision on an image file, with pixel coordinates and UTF-16 ranges.

    No screenshot capture, accessibility tree, window focus or cursor overlay.
    Keep the image source alive until Vision has finished decoding the image.
    """
    import Quartz
    import Vision
    from Foundation import NSURL
    source = Quartz.CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(str(path.resolve())), None)
    image = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None) if source else None
    if image is None:
        raise ValueError(f"Cannot decode image: {path}")
    width, height = Quartz.CGImageGetWidth(image), Quartz.CGImageGetHeight(image)
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setRecognitionLanguages_(["ko-KR", "en-US"])
    request.setUsesLanguageCorrection_(True)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, None)
    ok, error = handler.performRequests_error_([request], None)
    if not ok:
        raise RuntimeError(f"Apple Vision OCR failed: {error}")
    out = []
    import re
    def box(bb):
        return (bb.origin.x*width, (1-bb.origin.y-bb.size.height)*height, bb.size.width*width, bb.size.height*height)
    for line_id, observation in enumerate(request.results() or []):
        candidates = observation.topCandidates_(1)
        if not candidates:
            continue
        top = candidates[0]
        text = str(top.string())
        line_words = []
        for match in re.finditer(r"\S+", text):
            start = len(text[:match.start()].encode("utf-16-le")) // 2
            length = len(match.group().encode("utf-16-le")) // 2
            rect, _ = top.boundingBoxForRange_error_((start, length), None)
            if rect is None:
                # A whole-line box for each word would misassign labels. Preserve
                # the line once instead when fine-grained boxes are unavailable.
                line_words = [Word(box(observation.boundingBox()), text, float(top.confidence()), line_id)]
                break
            line_words.append(Word(box(rect.boundingBox()), match.group(), float(top.confidence()), line_id))
        out.extend(line_words)
    return out

