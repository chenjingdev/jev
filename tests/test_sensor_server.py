"""Image-only server contract, using a local fake model rather than GUI control."""
import io
import json
from pathlib import Path
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from PIL import Image
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eye"))
from scene import Scene
from sensor_server import BusyError, Sensor, handler_for, normalized_image


def png():
    data = io.BytesIO()
    Image.new("RGBA", (40, 30), (10, 20, 30, 255)).save(data, format="PNG")
    return data.getvalue()


def test_image_validation_and_rgb_normalization():
    image = normalized_image(png())
    assert image.mode == "RGB" and image.size == (40, 30)
    with pytest.raises(ValueError):
        normalized_image(b"not an image")


def test_model_reused_and_temporary_input_removed():
    loads, inputs = [], []
    class Model:
        def __init__(self, **kwargs):
            loads.append(kwargs)
        def see(self, path, progress):
            assert path.exists()
            inputs.append(path)
            progress("detection")
            return Scene(40, 30, [])
    sensor = Sensor(factory=Model)
    assert sensor.analyze(png())["scene"]["elements"] == []
    sensor.analyze(png())
    assert len(loads) == 1
    assert all(not p.exists() for p in inputs)
    assert sensor.status()["stage"] == "complete"
    assert not sensor.status()["busy"]


def test_failure_releases_inference_lock_and_busy_requests_reject():
    sensor = Sensor()
    with pytest.raises(ValueError):
        sensor.analyze(b"bad image")
    assert not sensor.status()["busy"]
    assert sensor.inference_lock.acquire(blocking=False)
    try:
        with pytest.raises(BusyError):
            sensor.analyze(png())
    finally:
        sensor.inference_lock.release()


def test_old_control_endpoint_does_not_execute_anything():
    sensor = Sensor(factory=lambda **_: pytest.fail("Must not load a model"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(sensor, "unused"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        status = json.load(urllib.request.urlopen(url + "/api/status"))
        assert status["mode"] == "visual_sensor"
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(urllib.request.Request(url + "/api/run", data=b"", method="POST"))
        assert exc.value.code == 404
        assert sensor.model is None
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_live_lab_accepts_pixels_not_fixture_state():
    frames = []
    class Model:
        def __init__(self, **kwargs):
            pass
        def see(self, path, progress):
            with Image.open(path) as image:
                frames.append((image.size, image.getpixel((0, 0))))
            return Scene(40, 30, [])
    sensor = Sensor(factory=Model)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(sensor, "http://sensor.test"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        # Both existing entry URLs now serve the integrated lab.
        for route in ("/", "/fixture"):
            page = urllib.request.urlopen(base + route).read()
            assert b'<canvas id="canvas"' in page
        module = urllib.request.urlopen(base + "/workspace.js")
        assert module.headers.get_content_type() == "text/javascript"
        headers = {"Origin": "http://sensor.test", "X-Jev-Sensor": "1", "Content-Type": "image/png"}
        request = urllib.request.Request(base + "/api/analyze", data=png(), headers=headers)
        result = json.load(urllib.request.urlopen(request))
        assert (result["scene"]["image"]["width"], result["scene"]["image"]["height"]) == (40, 30)
        assert frames == [((40, 30), (10, 20, 30))]
        fake_state = urllib.request.Request(base + "/api/analyze", data=b'{"checked":true}', headers=headers)
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(fake_state)
        assert exc.value.code == 400
        assert len(frames) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
