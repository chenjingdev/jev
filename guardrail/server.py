"""Browser UI for the guardrail: one static page plus POST /api/screen.

    op run --env-file=guardrail/.env.tpl -- uv run python guardrail/server.py

The API key lives only in this process; the page talks to /api/screen.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import guard  # noqa: E402
from typesafe_sdk import TypeSafeError  # noqa: E402

PORT = int(os.environ.get("PORT", "3457"))
PAGE = HERE / "index.html"
MAX_BODY = 64 * 1024


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/categories":
            self._json(200, {"categories": [n for n, _ in guard.CATEGORIES.values()], "severity": list(guard.SEVERITY)})
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/screen":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY:
            self._json(413, {"error": "too large"})
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            text = str(body.get("text", "")).strip()
        except (ValueError, AttributeError):
            self._json(400, {"error": "bad json"})
            return
        if not text:
            self._json(400, {"error": "text is empty"})
            return
        try:
            verdict = guard.screen(text)
        except TypeSafeError as error:
            self._json(502, {"error": f"{type(error).__name__}: {error}"})
            return
        self._json(200, verdict.as_dict())

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        sys.stderr.write(f"{self.address_string()} {format % args}\n")


def main() -> int:
    if not os.environ.get("TYPESAFE_API_KEY", "").strip():
        print(
            "TYPESAFE_API_KEY is not set. Start through 1Password:\n"
            "  op run --env-file=guardrail/.env.tpl -- uv run python guardrail/server.py",
            file=sys.stderr,
        )
        return 1
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"guardrail UI: http://127.0.0.1:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
