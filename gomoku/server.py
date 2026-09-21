"""Serve the board page and answer the POSTs: Jev's move (single request, or the
three-layer brain when the page asks for `brain: "neurons"`), the bot's move,
Opus's move (`/api/opus`, through the `claude` CLI - slow, 5-40 s) and Rapfi's
(`/api/rapfi`, the Gomocup engine, when `rapfi_setup.sh` has been run).

    op run --env-file=<(echo 'TYPESAFE_API_KEY="op://Agent/typesafe jev key/credential"') \
      -- uv run python gomoku/server.py            # http://localhost:3460

The game lives in the browser; the server is stateless. The key lives only in
this process and never reaches the page.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import brain  # noqa: E402
import engine as E  # noqa: E402
import neurons  # noqa: E402
import opus  # noqa: E402
import rapfi  # noqa: E402
import sight  # noqa: E402
import basics  # noqa: E402
import colour  # noqa: E402
import completion_encoding  # noqa: E402
import colour_encoding  # noqa: E402
import occupancy  # noqa: E402
import occupancy_boundaries  # noqa: E402
from typesafe_sdk import TypeSafeError  # noqa: E402

PAGE = HERE / "index.html"
SIGHT_PAGE = HERE / "sight.html"
RNG = random.Random()


def _board(payload: dict) -> E.Board:
    board = payload.get("board")
    if not (isinstance(board, list) and len(board) == E.SIZE and all(isinstance(r, list) and len(r) == E.SIZE for r in board)):
        raise ValueError("board must be 15 rows of 15 ints")
    return [[int(v) for v in row] for row in board]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - keep the terminal quiet
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif path in ("/basics", "/basics.html"):
            self._send(200, (HERE / "basics.html").read_bytes(), "text/html; charset=utf-8")
        elif path in ("/sight", "/sight.html"):
            self._send(200, SIGHT_PAGE.read_bytes(), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/basics":
                seed = int(payload.get("seed", 1))
                stage, density = payload.get("stage", "occupied"), payload.get("density", "sparse")
                if not 1 <= seed <= 20 or stage not in (*basics.STAGES, "occupied", "colour") or density not in ("sparse", "dense"):
                    raise ValueError("Invalid stage, density or seed")
                if stage == "colour":
                    probe = int(payload.get("probe", 0))
                    if probe not in (0, 1):raise ValueError("Invalid probe")
                    case = [c for c in colour.cases_for_seed(seed) if c['density'] == density][probe]
                    result = colour.ask(case, payload.get("condition", "base"), payload.get("colour_prompt") or None, payload.get("colour_encoding") or colour_encoding.selected_encoding())
                elif stage == "occupied":
                    variant = payload.get("variant", "boundary")
                    if variant not in ("control", "boundary"):
                        raise ValueError("Unknown occupancy variant")
                    case = next(c for v,c in occupancy_boundaries.cases_for_seed(seed) if v == variant and c.density == density)
                    result = occupancy_boundaries.ask(case, variant, payload.get("condition", "base"), payload.get("prompt") or None)
                else:
                    case = next(c for c in (completion_encoding.cases_for_seed(seed) if stage == 'complete' else basics.cases_for_seed(seed)) if c.stage == stage and c.density == density)
                    result = completion_encoding.ask(case, payload.get("condition", "base"), payload.get("colour_encoding") or "paired") if stage == "complete" else basics.ask(case, payload.get("condition", "base"))
                self._json(200, result)
                return
            if self.path == "/api/sight":  # self-play puzzle, one question, the whole distribution
                stone_colour = payload.get("player", "white")
                if stone_colour not in ("black", "white"):
                    raise ValueError("player must be black or white")
                position = sight.position_for_seed(int(payload.get("seed", 1)), E.BLACK if stone_colour == "black" else E.WHITE)
                rotation = int(payload.get("rotation", 0))
                if rotation not in (0, 90, 180, 270):
                    raise ValueError("rotation must be 0, 90, 180 or 270")
                position = sight.rotate_position(position, rotation // 90)
                rep = payload.get("rep", "sequence")
                kind = payload.get("kind", "all")
                option_order = None
                if payload.get("shuffle", False):
                    option_order = list(sight.options_for(position.board, kind, position.player))
                    random.Random(int(payload.get("seed", 1)) + 31000).shuffle(option_order)
                out = sight.ask(position, kind, rep, probabilities=True, option_order=option_order)
                self._json(200, {"board": position.board, "state": sight.state_for(position, rep), **out})  # state apart: its `board` is text
                return
            board = _board(payload)
            player = int(payload.get("player", E.WHITE))
        except TypeSafeError as error:
            self._json(502, {"error": f"{type(error).__name__}: {error}"})
            return
        except (ValueError, KeyError, TypeError) as error:
            self._json(400, {"error": str(error)})
            return
        if self.path == "/api/jev":
            try:
                args = (board, player, payload.get("last"), int(payload.get("move_number", 0)))
                result = neurons.think(*args, cap=12, sheet_kind="labelled") if payload.get("brain") == "neurons" else brain.think(*args)
            except TypeSafeError as error:
                self._json(502, {"error": f"{type(error).__name__}: {error}"})
                return
            self._json(200, result)
        elif self.path in ("/api/sense", "/api/motor", "/api/verdict"):
            # the three-layer brain, one layer per request, so the page can show each going out and landing
            try:
                n = int(payload.get("move_number", 0))
                ranked, sheet, base = neurons.prepare(board, player, payload.get("last"), n, 12, "labelled", False)
                if self.path == "/api/sense":
                    out = {"candidates": ranked, **neurons.sense(board, ranked, base)}
                elif self.path == "/api/motor":
                    out = neurons.motor(sheet, base, payload["activations"], payload["fired"])
                else:
                    out = neurons.verdict(sheet, base, n, payload["activations"], payload["fired"], payload["directive"], payload["proposals"])
            except TypeSafeError as error:
                self._json(502, {"error": f"{type(error).__name__}: {error}"})
                return
            except (KeyError, TypeError) as error:
                self._json(400, {"error": f"bad payload: {error}"})
                return
            self._json(200, out)
        elif self.path == "/api/bot":
            self._json(200, {"move": E.bot_move(board, player, RNG)})
        elif self.path == "/api/opus":
            log: list[dict] = []
            move = opus.opus_black(board, payload.get("last"), RNG, sheet=bool(payload.get("sheet")), log=log)
            record = {k: v for k, v in log[-1].items() if k != "move"}
            self._json(200, {"move": move, **record})
        elif self.path == "/api/rapfi":
            if not rapfi.available():
                self._json(503, {"error": "Rapfi is not built: run gomoku/rapfi_setup.sh"})
                return
            log = []
            move = rapfi.rapfi_black(board, RNG, log, ms=int(payload.get("ms", 1000)), depth=int(payload.get("depth", 0)))
            record = {k: v for k, v in log[-1].items() if k != "move"}
            self._json(200, {"move": move, **record})
        elif self.path == "/api/forbidden":
            self._json(200, {"forbidden": E.forbidden_points(board, E.BLACK)})
        else:
            self._json(404, {"error": "not found"})


def main() -> int:
    parser = argparse.ArgumentParser(description="Jev가 두는 오목")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "3460")))
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    if not os.environ.get("TYPESAFE_API_KEY"):
        print("TYPESAFE_API_KEY가 없습니다. op run으로 주입하세요 (파일 상단 참조).", file=sys.stderr)
        return 1
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"오목: http://localhost:{args.port}   (모델 {brain.MODEL})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
