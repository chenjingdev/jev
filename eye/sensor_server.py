"""Image bytes -> local visual models -> observations. No browser/input control.

    uv run --extra perception python eye/sensor_server.py
"""
from __future__ import annotations
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import time

from PIL import Image, ImageOps, UnidentifiedImageError
from perceive import Retina

HERE = Path(__file__).resolve().parent
MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 40_000_000
STAGES = {"idle": "이미지를 넣고 분석하세요", "loading": "로컬 시각 모델 준비 중", "decode": "입력 이미지 읽는 중", "detection": "ScreenParser · 영역과 종류 탐지 중", "ocr": "OCR · 글자 읽는 중", "fusion": "영역과 글자 연결 중", "captioning": "BLIP · 아이콘 설명 중", "complete": "인식 완료", "error": "인식 실패"}


class BusyError(RuntimeError):
    pass


def normalized_image(data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError("20 MB 이하의 이미지를 넣어 주세요.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError("PNG, JPEG, WebP 이미지를 지원합니다.")
            if image.width * image.height > MAX_PIXELS:
                raise ValueError("입력 이미지는 4천만 픽셀 이하여야 합니다.")
            return ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("이미지 파일을 읽을 수 없습니다.") from exc


class Sensor:
    def __init__(self, ocr="auto", device="auto", factory=Retina):
        self.ocr, self.device, self.factory = ocr, device, factory
        self.model = None
        self.inference_lock = threading.Lock()
        self.status_lock = threading.Lock()
        self.state = {"stage": "idle", "message": STAGES["idle"], "busy": False}

    def status(self):
        with self.status_lock:
            return {**self.state, "mode": "visual_sensor"}

    def progress(self, stage):
        with self.status_lock:
            self.state.update(stage=stage, message=STAGES[stage])

    def analyze(self, data):
        if not self.inference_lock.acquire(blocking=False):
            raise BusyError("분석 중입니다. 완료 후 다시 요청하세요.")
        start = time.perf_counter()
        try:
            with self.status_lock:
                self.state = {"stage": "decode", "message": STAGES["decode"], "busy": True}
            image = normalized_image(data)
            if self.model is None:
                self.progress("loading")
                self.model = self.factory(device=self.device, ocr=self.ocr)
            with tempfile.TemporaryDirectory(prefix="jev-sensor-") as folder:
                path = Path(folder) / "frame.png"
                image.save(path)
                scene = self.model.see(path, progress=self.progress)
                result = scene.to_dict()
            elapsed = round(time.perf_counter() - start, 3)
            with self.status_lock:
                self.state.update(stage="complete", message=STAGES["complete"], elements=len(scene.elements), elapsed_s=elapsed)
            return {"scene": result, "elapsed_s": elapsed}
        except Exception:
            self.progress("error")
            raise
        finally:
            with self.status_lock:
                self.state["busy"] = False
            self.inference_lock.release()


def handler_for(sensor, origin):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, data, mime="application/json"):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8") if mime == "application/json" else data
            self.send_response(status)
            self.send_header("Content-Type", mime + ("; charset=utf-8" if mime.startswith("text/") or mime == "application/json" else ""))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            routes = {
                "/": (HERE / "lab/index.html", "text/html"),
                "/sensor.js": (HERE / "lab/sensor.js", "text/javascript"),
                "/fixture": (HERE / "lab/index.html", "text/html"),
                "/workspace.js": (HERE / "fixtures/workspace.js", "text/javascript"),
                "/sample.png": (HERE / "fixtures/sample.png", "image/png"),
            }
            if self.path == "/api/status":
                return self.send(200, sensor.status())
            if self.path in routes:
                path, mime = routes[self.path]
                if path.is_file():
                    return self.send(200, path.read_bytes(), mime)
            self.send(404, {"error": "요청한 자료가 없습니다."})

        def do_POST(self):
            if self.path != "/api/analyze":
                return self.send(404, {"error": "이미지 분석만 지원합니다. 페이지를 새로고침해 주세요."})
            if self.headers.get("Origin") != origin or self.headers.get("X-Jev-Sensor") != "1":
                return self.send(403, {"error": "센서 테스트 페이지에서 요청해 주세요."})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_BYTES:
                    return self.send(413, {"error": "20 MB 이하의 이미지를 넣어 주세요."})
                self.send(200, sensor.analyze(self.rfile.read(size)))
            except BusyError as exc:
                self.send(409, {"error": str(exc)})
            except ValueError as exc:
                self.send(400, {"error": str(exc)})
            except Exception as exc:
                import traceback
                traceback.print_exc()
                self.send(500, {"error": f"시각 모델 실행 실패: {type(exc).__name__}. 서버 로그를 확인해 주세요."})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--ocr", choices=("auto", "apple", "easyocr"), default="auto")
    parser.add_argument("--device", choices=("auto", "cpu", "mps", "cuda"), default="auto")
    args = parser.parse_args()
    origin = f"http://127.0.0.1:{args.port}"
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(Sensor(args.ocr, args.device), origin))
    print(f"Visual sensor ready: {origin}/", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
