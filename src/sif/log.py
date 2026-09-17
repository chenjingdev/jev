"""Append-only JSONL log of sif calls, one line per call."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path.home() / ".cache" / "sif" / "calls.jsonl"


class CallLog:
    """Writes one JSON object per line: raw answers, usage and latency included."""

    def __init__(self, path: str | Path = DEFAULT_PATH) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(
        self,
        *,
        model: str,
        state_hash: str,
        questions: dict[str, Any],
        answers: dict[str, Any],
        usage: dict[str, Any] | None,
        latency_ms: float,
        cached: bool,
        error: str | None = None,
    ) -> None:
        """Append one call record; never raises into the caller's code path."""
        record = {
            "ts": time.time(),
            "model": model,
            "state_hash": state_hash,
            "questions": questions,
            "answers": answers,
            "usage": usage,
            "latency_ms": round(latency_ms, 3),
            "cached": cached,
        }
        if error is not None:
            record["error"] = error
        line = json.dumps(record, ensure_ascii=False, default=str)
        try:
            with self._lock, self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass
