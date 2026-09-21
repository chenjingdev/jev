"""Serve the built 3D arena and expose local match logs without secrets."""
from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


HERE = Path(__file__).resolve().parent
ARENA = HERE / "arena"
DIST = ARENA / "dist"
MATCHES = HERE / "matches"


class ArenaHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"arena: {fmt % args}")

    def send_bytes(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if content_type.startswith(("application/json", "text/html")) else "public, max-age=3600")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, payload):
        self.send_bytes(status, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.send_json(200, {"ok": True, "matches": len(list(MATCHES.glob("*.json")))})
            return
        if parsed.path == "/api/matches":
            # Only match logs: skip referee/summary side files such as x.referee-200000.json or arms-summary-01.json.
            names = sorted(path.stem for path in MATCHES.glob("*.json")
                           if "." not in path.stem and not path.stem.startswith("arms-summary"))
            self.send_json(200, {"matches": names})
            return
        if parsed.path == "/api/match":
            requested = parse_qs(parsed.query).get("name", ["sunfish-smoke"])[0]
            if Path(requested).name != requested:
                self.send_json(400, {"error": "invalid match name"})
                return
            path = MATCHES / f"{requested}.json"
            if not path.is_file():
                self.send_json(404, {"error": "match not found"})
                return
            self.send_bytes(200, path.read_bytes(), "application/json; charset=utf-8")
            return
        self.serve_static(parsed.path)

    def serve_static(self, request_path: str):
        relative = request_path.lstrip("/") or "index.html"
        root = DIST.resolve()
        path = (DIST / relative).resolve()
        if root not in path.parents and path != root:
            self.send_json(400, {"error": "invalid path"})
            return
        if not path.is_file():
            path = DIST / "index.html"
        if not path.is_file():
            self.send_json(503, {"error": "arena is not built; run npm install && npm run build in chess/arena"})
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
            content_type += "; charset=utf-8"
        self.send_bytes(200, path.read_bytes(), content_type)


if __name__ == "__main__":
    if not DIST.is_dir():
        raise SystemExit("Build the arena first: cd chess/arena && npm install && npm run build")
    port = int(os.environ.get("PORT", "3470"))
    print(f"Jev Chess Arena: http://localhost:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), ArenaHandler).serve_forever()
