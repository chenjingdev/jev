"""Drive the overlay cursor from any process.

    from cursor_client import Cursor
    cursor = Cursor()
    cursor.move(800, 400)
    cursor.look(700, 350, 200, 100, label="결제하기 0.83")
    cursor.click()

Every call is one JSON line on the unix socket; nothing waits for the overlay.
If the overlay is not running the calls are dropped with one warning, so the
eye can run headless.
"""

from __future__ import annotations

import json
import os
import socket
import sys

SOCKET_PATH = os.environ.get("JEV_CURSOR_SOCKET", "/tmp/jev-cursor.sock")


class Cursor:
    def __init__(self, path: str = SOCKET_PATH) -> None:
        self.path = path
        self._sock: socket.socket | None = None
        self._warned = False

    def _send(self, command: dict) -> None:
        try:
            if self._sock is None:
                self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self._sock.connect(self.path)
            self._sock.sendall((json.dumps(command, ensure_ascii=False) + "\n").encode("utf-8"))
        except OSError as error:
            self._sock = None
            if not self._warned:
                print(f"cursor: overlay not reachable at {self.path} ({error}); continuing without it", file=sys.stderr)
                self._warned = True

    def move(self, x: float, y: float, ms: float | None = None) -> None:
        command = {"op": "move", "x": x, "y": y}
        if ms is not None:
            command["ms"] = ms
        self._send(command)

    def click(self) -> None:
        self._send({"op": "click"})

    def look(self, x: float, y: float, w: float, h: float, label: str | None = None) -> None:
        self._send({"op": "look", "x": x, "y": y, "w": w, "h": h, "label": label})

    def heat(self, cells: list[list[float]]) -> None:
        """cells: [[x, y, w, h, probability], ...]"""
        self._send({"op": "heat", "cells": cells})

    def label(self, text: str | None) -> None:
        self._send({"op": "label", "text": text})

    def clear(self) -> None:
        self._send({"op": "clear"})

    def show(self) -> None:
        self._send({"op": "show"})

    def hide(self) -> None:
        self._send({"op": "hide"})

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None
