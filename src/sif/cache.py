"""Disk cache for sif calls: sqlite, keyed by model + state + questions."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path.home() / ".cache" / "sif" / "cache.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS answers (
    key     TEXT PRIMARY KEY,
    model   TEXT NOT NULL,
    created REAL NOT NULL,
    answers TEXT NOT NULL
)
"""


def _canonical(value: Any) -> str:
    """Stable JSON text for hashing (sorted keys, non-ASCII kept as-is)."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))


def state_hash(state: Any) -> str:
    """sha256 of the state alone, used as a log field."""
    return hashlib.sha256(_canonical(state).encode("utf-8")).hexdigest()


def make_key(model: str, state: Any, questions: Any) -> str:
    """sha256 of the model, the state and the serialized questions."""
    digest = hashlib.sha256()
    digest.update(model.encode("utf-8"))
    digest.update(_canonical(state).encode("utf-8"))
    digest.update(_canonical(questions).encode("utf-8"))
    return digest.hexdigest()


class Cache:
    """Tiny sqlite key/value store holding raw answer payloads."""

    def __init__(self, path: str | Path = DEFAULT_PATH) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def get(self, key: str) -> tuple[dict[str, Any], str] | None:
        """Return (raw answers, answering model) for `key`, or None on a miss."""
        with self._lock:
            row = self._conn.execute(
                "SELECT answers, model FROM answers WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0]), row[1]
        except json.JSONDecodeError:
            return None

    def set(self, key: str, model: str, answers: dict[str, Any], created: float) -> None:
        """Store raw answers under `key`, replacing any previous entry.

        `model` is the model that actually answered (e.g. "jev-1.13.0"), not the
        alias that was requested, so a cache hit can still report the version.
        """
        payload = json.dumps(answers, ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO answers (key, model, created, answers) VALUES (?, ?, ?, ?)",
                (key, model, created, payload),
            )
            self._conn.commit()

    def close(self) -> None:
        """Close the underlying sqlite connection."""
        with self._lock:
            self._conn.close()
