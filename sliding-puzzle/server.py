"""Browser UI for peel mode: one static page, GET /api/scramble, POST /api/peel.

    op run --env-file=sliding-puzzle/.env.tpl -- uv run python sliding-puzzle/server.py   # :3459

The key lives only in this process. The page keeps the board and the unsolved region; each
POST asks Jev which line to peel (unless only one is possible), peels it with the BFS and
returns the slide path so the page can animate it.
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
G = P.Grid()
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
            walk = int(q.get("walk", ["0"])[0])
            board = G.random_walk(walk, rng) if walk else G.shuffle(rng)
            self._json(200, {"rows": G.rows, "cols": G.cols, "board": list(board), "distance": G.manhattan(board), "home": G.tiles_home(board)})
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/peel":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY:
            self._json(413, {"error": "too large"})
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            board = tuple(int(v) for v in body["board"])
            region = (int(body["region"][0]), int(body["region"][1]))
            hinted = bool(body.get("hinted", True))
            assert len(board) == G.cells and sorted(board) == list(range(G.cells))
        except (ValueError, KeyError, TypeError, AssertionError):
            self._json(400, {"error": "bad board"})
            return
        keep = frozenset(t for t in range(1, G.cells) if board[t - 1] == t and (G.rc(t - 1)[0] < region[0] or G.rc(t - 1)[1] < region[1]))
        lines = P.region_lines(G, region)
        if not lines:  # last 2×2
            rest = [t for t in range(1, G.cells) if t not in keep]
            after, _, path = P.peel(G, board, keep, rest)
            self._json(200, {"line": "end", "forced": True, "tiles": rest, "path": path, "after": list(after),
                             "region": list(region), "solved": after == G.solved()})
            return
        if len(lines) == 1:
            choice = next(iter(lines))
            f = P.line_facts(G, board, lines[choice])
            r = {"choice": choice, "forced": True, "probabilities": {choice: 1.0}, "progress": None,
                 "candidates": {choice: {**f, "text": brain.describe_line(choice, f)}}, "latency_ms": 0}
        else:
            try:
                r = brain.peel_choice(G, board, region, lines, hinted=hinted)
                r["forced"] = False
            except TypeSafeError as e:
                self._json(502, {"error": str(e)})
                return
        choice = r["choice"]
        after, _, path = P.peel(G, board, keep, lines[choice])
        new_region = (region[0] + 1, region[1]) if choice == "row" else (region[0], region[1] + 1)
        r.update({"line": choice, "tiles": lines[choice], "path": path, "after": list(after), "region": list(new_region),
                  "solved": after == G.solved()})
        self._json(200, r)

    def log_message(self, format, *args):  # noqa: A002 - quieter
        if "/api/peel" not in (args[0] if args else ""):
            super().log_message(format, *args)


if __name__ == "__main__":
    if not os.environ.get("TYPESAFE_API_KEY"):
        sys.exit("TYPESAFE_API_KEY is not set. Run via: op run --env-file=sliding-puzzle/.env.tpl -- uv run python sliding-puzzle/server.py")
    print(f"sliding puzzle ({G.rows}×{G.cols}, peel mode) on http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
