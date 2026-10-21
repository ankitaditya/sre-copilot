from __future__ import annotations

import asyncio
import json
import sqlite3
from collections import defaultdict
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from sre_copilot.models import EventRecord, RunState, utc_now


class RunStore:
    def __init__(self, database_path: Path):
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = asyncio.Lock()
        self._subscribers: dict[str, set[asyncio.Queue[EventRecord]]] = defaultdict(set)

    async def initialize(self) -> None:
        async with self._lock:
            self._connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    service TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    state_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_run_id_id ON events(run_id, id);
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    state_json TEXT NOT NULL
                );
                """
            )
            self._connection.commit()

    async def create_run(self, state: RunState) -> None:
        async with self._lock:
            self._connection.execute(
                """
                INSERT INTO runs(id, status, service, severity, created_at, updated_at, state_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.id,
                    state.status.value,
                    state.service,
                    state.severity.value,
                    state.created_at,
                    state.updated_at,
                    state.model_dump_json(),
                ),
            )
            self._insert_checkpoint(state, "run_created")
            self._connection.commit()

    async def save_run(self, state: RunState, reason: str) -> None:
        state.updated_at = utc_now()
        async with self._lock:
            self._connection.execute(
                """
                UPDATE runs
                SET status = ?, service = ?, severity = ?, updated_at = ?, state_json = ?
                WHERE id = ?
                """,
                (
                    state.status.value,
                    state.service,
                    state.severity.value,
                    state.updated_at,
                    state.model_dump_json(),
                    state.id,
                ),
            )
            self._insert_checkpoint(state, reason)
            self._connection.commit()

    def _insert_checkpoint(self, state: RunState, reason: str) -> None:
        self._connection.execute(
            "INSERT INTO checkpoints(run_id, reason, created_at, state_json) VALUES (?, ?, ?, ?)",
            (state.id, reason, utc_now(), state.model_dump_json()),
        )

    async def get_run(self, run_id: str) -> RunState | None:
        async with self._lock:
            row = self._connection.execute(
                "SELECT state_json FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        return RunState.model_validate_json(row["state_json"]) if row else None

    async def list_runs(self, limit: int = 100) -> list[RunState]:
        async with self._lock:
            rows = self._connection.execute(
                "SELECT state_json FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [RunState.model_validate_json(row["state_json"]) for row in rows]

    async def list_recoverable_runs(self) -> list[RunState]:
        async with self._lock:
            rows = self._connection.execute(
                """
                SELECT state_json FROM runs
                WHERE status IN ('queued', 'running')
                ORDER BY created_at
                """
            ).fetchall()
        return [RunState.model_validate_json(row["state_json"]) for row in rows]

    async def add_event(
        self, run_id: str, event_type: str, payload: dict[str, Any]
    ) -> EventRecord:
        created_at = utc_now()
        async with self._lock:
            cursor = self._connection.execute(
                "INSERT INTO events(run_id, type, created_at, payload_json) VALUES (?, ?, ?, ?)",
                (run_id, event_type, created_at, json.dumps(payload, default=str)),
            )
            self._connection.commit()
            event = EventRecord(
                id=int(cursor.lastrowid),
                run_id=run_id,
                type=event_type,
                created_at=created_at,
                payload=payload,
            )
        for queue in tuple(self._subscribers[run_id]):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass
        return event

    async def list_events(
        self, run_id: str, after_id: int = 0, limit: int = 1000
    ) -> list[EventRecord]:
        async with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, run_id, type, created_at, payload_json
                FROM events WHERE run_id = ? AND id > ? ORDER BY id LIMIT ?
                """,
                (run_id, after_id, limit),
            ).fetchall()
        return [
            EventRecord(
                id=row["id"],
                run_id=row["run_id"],
                type=row["type"],
                created_at=row["created_at"],
                payload=json.loads(row["payload_json"]),
            )
            for row in rows
        ]

    async def list_history(self, run_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, reason, created_at, state_json
                FROM checkpoints WHERE run_id = ? ORDER BY id
                """,
                (run_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "reason": row["reason"],
                "created_at": row["created_at"],
                "state": json.loads(row["state_json"]),
            }
            for row in rows
        ]

    async def subscribe(self, run_id: str) -> AsyncIterator[EventRecord]:
        queue: asyncio.Queue[EventRecord] = asyncio.Queue(maxsize=200)
        self._subscribers[run_id].add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers[run_id].discard(queue)

    def close(self) -> None:
        self._connection.close()

