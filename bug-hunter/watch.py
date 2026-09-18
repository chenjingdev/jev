"""Watch Python files and re-judge a function the moment its source changes.

    op run --env-file=<(echo 'TYPESAFE_API_KEY="op://Personal/typesafe jev key/credential"') \
      -- uv run python bug-hunter/watch.py src/sif/core.py

Opens http://localhost:3458 with a live panel: every function as a bar, sorted
riskiest first. Save a file and only the functions whose source actually
changed go to Jev; unchanged ones keep their verdict, and identical sources
hit the sif cache. No git involved - the unit of change is the function body.

The API key lives only in this process; the page listens on /events (SSE).
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import queue
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import hunter  # noqa: E402
from typesafe_sdk import TypeSafeError  # noqa: E402

PAGE = HERE / "panel.html"
POLL_SECONDS = 0.3
WORKERS = 4


def _digest(source: str) -> str:
    return hashlib.sha1(source.encode("utf-8")).hexdigest()[:12]


def _changed_lines(previous: str | None, current: str) -> list[int]:
    """0-based line numbers in `current` that are new or edited since `previous`."""
    if previous is None:
        return []
    matcher = difflib.SequenceMatcher(a=previous.splitlines(), b=current.splitlines())
    out: list[int] = []
    for tag, _, _, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            out.extend(range(j1, j2))
    return out


class Board:
    """Current verdict per function plus a fan-out of events to open pages."""

    def __init__(self, threshold: float) -> None:
        self.threshold = threshold
        self.lock = threading.Lock()
        self.verdicts: dict[str, dict] = {}  # id -> verdict dict (+ status)
        self.digests: dict[str, str] = {}  # id -> source digest
        self.sources: dict[str, str] = {}  # id -> last judged source, for the diff
        self.listeners: list[queue.Queue] = []
        self.requests = 0
        self.started = time.time()

    # -- events --------------------------------------------------------------

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self.lock:
            self.listeners.append(q)
            snapshot = {"type": "snapshot", "functions": list(self.verdicts.values()), "stats": self._stats()}
        q.put(snapshot)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self.lock:
            if q in self.listeners:
                self.listeners.remove(q)

    def emit(self, event: dict) -> None:
        with self.lock:
            event.setdefault("stats", self._stats())
            for q in self.listeners:
                q.put(event)

    def _stats(self) -> dict:
        return {
            "functions": len(self.verdicts),
            "requests": self.requests,
            "uptime": round(time.time() - self.started),
        }

    # -- state ---------------------------------------------------------------

    def pending(self, function: hunter.Function) -> None:
        fid = f"{function.file}::{function.name}"
        with self.lock:
            previous = self.verdicts.get(fid) or {"id": fid, "file": function.file, "function": function.name}
            row = {
                **previous,
                "lineno": function.lineno,
                "source": function.source,
                "changed_lines": _changed_lines(self.sources.get(fid), function.source),
                "status": "pending",
            }
            self.verdicts[fid] = row
        self.emit({"type": "pending", "function": row})

    def settle(self, function: hunter.Function, verdict: hunter.Verdict | None, error: str | None) -> None:
        fid = f"{function.file}::{function.name}"
        with self.lock:
            changed = _changed_lines(self.sources.get(fid), function.source)
            self.sources[fid] = function.source
            if verdict is not None:
                row = {**verdict.as_dict(), "id": fid, "status": "done"}
            else:
                row = {"id": fid, "file": function.file, "function": function.name, "lineno": function.lineno, "status": "error", "error": error}
            row["source"] = function.source
            row["changed_lines"] = changed
            self.verdicts[fid] = row
            self.requests += 1
        self.emit({"type": "verdict", "function": row})

    def remove(self, fid: str) -> None:
        with self.lock:
            self.verdicts.pop(fid, None)
            self.digests.pop(fid, None)
            self.sources.pop(fid, None)
        self.emit({"type": "removed", "id": fid})

    def syntax_error(self, file: str, message: str) -> None:
        self.emit({"type": "syntax", "file": file, "message": message})


class Watcher(threading.Thread):
    """Poll file mtimes; on change, re-extract and judge the functions that differ."""

    def __init__(self, paths: list[str], board: Board) -> None:
        super().__init__(daemon=True)
        self.paths = paths
        self.board = board
        self.mtimes: dict[Path, float] = {}
        self.pool = ThreadPoolExecutor(max_workers=WORKERS)

    def files(self) -> list[Path]:
        out: list[Path] = []
        for raw in self.paths:
            path = Path(raw)
            candidates = sorted(path.rglob("*.py")) if path.is_dir() else [path]
            out.extend(f for f in candidates if not any(p in {".venv", "__pycache__", "node_modules", ".git"} for p in f.parts))
        return out

    def run(self) -> None:
        while True:
            for file in self.files():
                try:
                    mtime = file.stat().st_mtime
                except FileNotFoundError:
                    continue
                if self.mtimes.get(file) == mtime:
                    continue
                self.mtimes[file] = mtime
                self.scan(file)
            time.sleep(POLL_SECONDS)

    @staticmethod
    def display(file: Path) -> str:
        """The name the panel and the verdicts use for a file."""
        return os.path.relpath(file) if not file.is_absolute() or file.is_relative_to(Path.cwd()) else str(file)

    def scan(self, file: Path) -> None:
        name = self.display(file)
        try:
            functions = hunter.extract_functions(file.read_text(encoding="utf-8"), name)
        except SyntaxError as error:
            self.board.syntax_error(name, f"line {error.lineno}: {error.msg}")
            return
        seen: set[str] = set()
        changed: list[hunter.Function] = []
        for function in functions:
            fid = f"{name}::{function.name}"
            seen.add(fid)
            digest = _digest(function.source)
            if self.board.digests.get(fid) == digest:
                continue
            self.board.digests[fid] = digest
            changed.append(function)
        for fid in [f for f in list(self.board.digests) if f.startswith(name + "::") and f not in seen]:
            self.board.remove(fid)
        if changed:
            self.board.emit({"type": "changed", "file": name, "count": len(changed)})
        for function in changed:
            self.board.pending(function)
            self.pool.submit(self.judge, function)

    def judge(self, function: hunter.Function) -> None:
        try:
            verdict = hunter.judge(function, threshold=self.board.threshold)
        except TypeSafeError as error:
            self.board.settle(function, None, f"{type(error).__name__}: {error}")
            return
        self.board.settle(function, verdict, None)


def make_handler(board: Board, watcher: Watcher):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - keep the terminal quiet
            pass

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path in ("/", "/index.html"):
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/api/smells":
                payload = {"smells": {k: v[0] for k, v in hunter.SMELLS.items()}, "severity": list(hunter.SEVERITY), "threshold": board.threshold}
                self._send(200, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            elif self.path == "/api/files":
                files = [{"file": watcher.display(f), "text": f.read_text(encoding="utf-8")} for f in watcher.files()]
                self._send(200, json.dumps({"files": files}, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            elif self.path == "/events":
                self.stream()
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:  # noqa: N802
            """Write a watched file from the in-page editor; the watcher picks it up."""
            if self.path != "/api/save":
                self._send(404, b"not found", "text/plain")
                return
            length = int(self.headers.get("Content-Length", "0"))
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
                file, text = str(body["file"]), str(body["text"])
            except (ValueError, KeyError):
                self._send(400, b"bad json", "text/plain")
                return
            target = next((f for f in watcher.files() if watcher.display(f) == file), None)
            if target is None:
                self._send(403, b"not a watched file", "text/plain")
                return
            target.write_text(text, encoding="utf-8")
            self._send(200, b"{}", "application/json")

        def stream(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            q = board.subscribe()
            try:
                while True:
                    try:
                        event = q.get(timeout=15)
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        continue
                    self.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                board.unsubscribe(q)

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Jev 버그헌터 감시 모드: 저장하면 바뀐 함수만 다시 판정")
    parser.add_argument("paths", nargs="+", help="Python 파일 또는 디렉터리")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "3458")))
    parser.add_argument("--threshold", type=float, default=hunter.DEFAULT_THRESHOLD)
    args = parser.parse_args()

    if not os.environ.get("TYPESAFE_API_KEY"):
        print("TYPESAFE_API_KEY가 없습니다. op run으로 주입하세요 (파일 상단 참조).", file=sys.stderr)
        return 1

    board = Board(threshold=args.threshold)
    watcher = Watcher(args.paths, board)
    watcher.start()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(board, watcher))
    print(f"버그헌터 감시 중: {' '.join(args.paths)}\n패널: http://localhost:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
