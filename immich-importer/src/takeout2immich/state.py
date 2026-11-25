"""SQLite-backed state: export sets plus a request queue.

Interactive front-ends (CLI ``confirm``, the TUI) never mutate an export set directly while the
worker might hold it in memory; they enqueue a request that the worker applies at the start of its
next tick. A file lock makes sure only one worker runs at a time.
"""

from __future__ import annotations

import fcntl
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from takeout2immich.domain import ExportSet, now

_SCHEMA = """
CREATE TABLE IF NOT EXISTS export_sets (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    export_id TEXT,
    action TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
"""


@dataclass
class Request:
    id: int
    export_id: str | None
    action: str
    payload: dict


class WorkerBusyError(RuntimeError):
    pass


class StateStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        finally:
            conn.close()

    # export sets ---------------------------------------------------------
    def get(self, export_id: str) -> ExportSet | None:
        with self._conn() as c:
            row = c.execute("SELECT data FROM export_sets WHERE id=?", (export_id,)).fetchone()
        return ExportSet.model_validate_json(row[0]) if row else None

    def list(self) -> list[ExportSet]:
        with self._conn() as c:
            rows = c.execute("SELECT data FROM export_sets ORDER BY id").fetchall()
        return [ExportSet.model_validate_json(r[0]) for r in rows]

    def save(self, export_set: ExportSet) -> None:
        export_set.updated_at = now()
        with self._conn() as c:
            c.execute(
                "INSERT INTO export_sets(id, data, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                (export_set.id, export_set.model_dump_json(), export_set.updated_at.isoformat()),
            )

    # requests ------------------------------------------------------------
    def add_request(self, action: str, export_id: str | None = None, **payload) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO requests(export_id, action, payload, created_at) VALUES(?,?,?,?)",
                (export_id, action, json.dumps(payload), now().isoformat()),
            )

    def pending_requests(self) -> list[Request]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, export_id, action, payload FROM requests ORDER BY id"
            ).fetchall()
        return [Request(r[0], r[1], r[2], json.loads(r[3])) for r in rows]

    def pop_requests(self) -> list[Request]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, export_id, action, payload FROM requests ORDER BY id"
            ).fetchall()
            if rows:
                c.execute("DELETE FROM requests WHERE id <= ?", (rows[-1][0],))
        return [Request(r[0], r[1], r[2], json.loads(r[3])) for r in rows]

    # worker lock ---------------------------------------------------------
    @contextmanager
    def worker_lock(self) -> Iterator[None]:
        lock_path = self.db_path.with_suffix(".lock")
        fh = open(lock_path, "w")
        try:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise WorkerBusyError(
                    "Another takeout2immich worker is running (e.g. the `watch` daemon). "
                    "Use `confirm`/`status`, or stop the daemon first."
                ) from exc
            yield
        finally:
            fh.close()
