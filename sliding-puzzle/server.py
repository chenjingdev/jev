"""Browser UI: one static page, GET /api/scramble, POST /api/step.

    op run --env-file=sliding-puzzle/.env.tpl -- uv run python sliding-puzzle/server.py   # :3459

The key lives only in this process. The page keeps the board and asks the server for
the next slide; the server runs `brain.step` and returns Jev's choice with every
candidate's numbers so the page can draw the distribution.
"""

from __future__ import annotations

import json
import os
import random
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import brain  # noqa: E402
import puzzle as P  # noqa: E402
from typesafe_sdk import TypeSafeError  # noqa: E402

PORT = int(os.environ.get("PORT", "3459"))
PAGE = HERE / "index.html"
MAX_BODY = 16 * 1024
rng = random.Random()


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, payload) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/scramble":
            q = parse_qs(url.query)
            depth = int(q.get("depth", ["14"])[0])
            board = P.scramble(depth, rng)
            self._json(200, {"board": list(board), "optimal": depth, "distance": P.cost(board), "home": P.tiles_home(board)})
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/step":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY:
            self._json(413, {"error": "too large"})
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            board = tuple(int(v) for v in body["board"])
            history = [str(h) for h in body.get("history", [])]
            seen = {tuple(int(v) for v in k): int(c) for k, c in body.get("seen", [])}
            last = body.get("last") or None
            assert len(board) == P.N * P.N and sorted(board) == list(range(P.N * P.N))
        except (ValueError, KeyError, TypeError, AssertionError):
            self._json(400, {"error": "bad board"})
            return
        try:
            r = brain.step(board, last, seen, history)
        except TypeSafeError as e:
            self._json(502, {"error": str(e)})
            return
        after = P.moves(board)[r["choice"]]
        r["after"] = list(after)
        r["solved"] = after == P.solved()
        r["distance"] = P.cost(after)
        r["home"] = P.tiles_home(after)
        self._json(200, r)

    def log_message(self, format, *args):  # noqa: A002 - quieter
        if "/api/step" not in (args[0] if args else ""):
            super().log_message(format, *args)


if __name__ == "__main__":
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY is not set. Run via: op run --env-file=sliding-puzzle/.env.tpl -- uv run python sliding-puzzle/server.py")
    P.distance_table()
    print(f"sliding puzzle on http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
