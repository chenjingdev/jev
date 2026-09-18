"""play.py의 라이브 보드 서버: 표준 라이브러리만 쓰는 SSE 브로드캐스터.

세 엔드포인트:
    GET /        live.html
    GET /events  Server-Sent Events (최근 200개 이벤트를 먼저 흘려보낸 뒤 실시간)
    GET /state   현재 진행 중인 판들의 최신 스냅샷 + 셀 요약 JSON
"""

from __future__ import annotations

import collections
import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BUFFER_SIZE = 200
HEARTBEAT_SECONDS = 15.0
SUB_QUEUE_SIZE = 1000


class EventBus:
    """이벤트를 버퍼에 쌓고 붙어 있는 SSE 구독자들에게 흘려보낸다."""

    def __init__(self, maxlen: int = BUFFER_SIZE) -> None:
        self._lock = threading.Lock()
        self._buffer: collections.deque[dict] = collections.deque(maxlen=maxlen)
        self._subs: list[queue.Queue] = []
        self._seq = 0
        self._snapshot: dict[str, dict] = {}
        self._summary: dict = {}

    # ---------------------------------------------------------------- 발행

    def publish(self, kind: str, data: dict) -> None:
        with self._lock:
            self._seq += 1
            event = {"seq": self._seq, "type": kind, "data": data}
            self._buffer.append(event)
            self._apply(kind, data)
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass

    def _apply(self, kind: str, data: dict) -> None:
        """/state가 돌려줄 스냅샷을 갱신한다 (호출자가 락을 쥐고 있다)."""
        if kind == "game_start":
            self._snapshot[data["game_id"]] = {**data, "moves": 0, "last": None, "done": False}
        elif kind == "move":
            game = self._snapshot.get(data["game_id"])
            if game is not None:
                game["moves"] = data["ply"]
                game["fen"] = data["fen"]
                game["last"] = {
                    k: data.get(k)
                    for k in ("ply", "san", "uci", "by", "confidence", "cp_loss", "best_uci", "top5")
                }
        elif kind == "game_end":
            game = self._snapshot.get(data["game_id"])
            if game is not None:
                game.update({k: v for k, v in data.items() if k != "game_id"})
                game["done"] = True
        elif kind == "summary":
            self._summary = data

    # ---------------------------------------------------------------- 구독

    def subscribe(self) -> tuple[queue.Queue, list[dict]]:
        q: queue.Queue = queue.Queue(maxsize=SUB_QUEUE_SIZE)
        with self._lock:
            history = list(self._buffer)
            self._subs.append(q)
        return q, history

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def state(self) -> dict:
        with self._lock:
            return {
                "seq": self._seq,
                "games": list(self._snapshot.values()),
                "summary": self._summary,
            }


def _make_handler(bus: EventBus, html_path: Path, stop: threading.Event):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "jev-chess-live"

        def log_message(self, fmt, *args):  # 조용히
            pass

        # ------------------------------------------------------------ 유틸

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        # ------------------------------------------------------------ 라우팅

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/":
                self._serve_html()
            elif path == "/state":
                body = json.dumps(bus.state(), ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
            elif path == "/events":
                self._serve_events()
            elif path == "/healthz":
                self._send(200, b"ok", "text/plain; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")

        def _serve_html(self) -> None:
            try:
                body = html_path.read_bytes()
            except OSError as exc:
                self._send(500, str(exc).encode("utf-8"), "text/plain; charset=utf-8")
                return
            self._send(200, body, "text/html; charset=utf-8")

        def _serve_events(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self.close_connection = True  # Content-Length가 없으니 keep-alive로 재사용하지 않는다
            q, history = bus.subscribe()
            try:
                self.wfile.write(b": open\n\n")
                self.wfile.flush()
                for event in history:
                    self._write_event(event)
                while not stop.is_set():
                    try:
                        event = q.get(timeout=HEARTBEAT_SECONDS)
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        continue
                    self._write_event(event)
            except (BrokenPipeError, ConnectionResetError, OSError, ValueError):
                pass
            finally:
                bus.unsubscribe(q)

        def _write_event(self, event: dict) -> None:
            payload = json.dumps(event["data"], ensure_ascii=False)
            chunk = f"id: {event['seq']}\nevent: {event['type']}\ndata: {payload}\n\n"
            self.wfile.write(chunk.encode("utf-8"))
            self.wfile.flush()

    return Handler


class LiveServer:
    def __init__(self, bus: EventBus, html_path: Path, port: int, host: str = "127.0.0.1") -> None:
        self.bus = bus
        self.stop = threading.Event()
        handler = _make_handler(bus, html_path, self.stop)
        self.httpd = ThreadingHTTPServer((host, port), handler)
        self.httpd.daemon_threads = True
        self.url = f"http://{host}:{self.httpd.server_address[1]}/"
        self._thread = threading.Thread(target=self.httpd.serve_forever, name="live-server", daemon=True)

    def start(self) -> str:
        self._thread.start()
        return self.url

    def shutdown(self) -> None:
        self.stop.set()
        self.httpd.shutdown()
        self.httpd.server_close()
