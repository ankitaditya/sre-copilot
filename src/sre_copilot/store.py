from __future__ import annotations

import asyncio
import json
import sqlite3
from collections import defaultdict
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from sre_copilot.models import EventRecord, RunState, utc_now
from sre_copilot.protection import DataProtection


class RunStore:
    def __init__(self, database_path: Path, data: DataProtection | None = None):
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = asyncio.Lock()
        self._subscribers: dict[str, set[asyncio.Queue[EventRecord]]] = defaultdict(set)
        self._data = data or DataProtection()

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
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    source TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    service TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS security_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    category TEXT NOT NULL,
                    code TEXT NOT NULL,
                    actor TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
                    id UNINDEXED, title, body, tokenize='porter unicode61'
                );
                CREATE TRIGGER IF NOT EXISTS knowledge_insert AFTER INSERT ON knowledge_documents
                BEGIN
                    INSERT INTO knowledge_fts(id, title, body) VALUES (new.id, new.title, new.body);
                END;
                CREATE TRIGGER IF NOT EXISTS knowledge_delete AFTER DELETE ON knowledge_documents
                BEGIN
                    DELETE FROM knowledge_fts WHERE id = old.id;
                END;
                CREATE TRIGGER IF NOT EXISTS knowledge_update AFTER UPDATE ON knowledge_documents
                BEGIN
                    DELETE FROM knowledge_fts WHERE id = old.id;
                    INSERT INTO knowledge_fts(id, title, body) VALUES (new.id, new.title, new.body);
                END;
                """
            )
            self._scrub_existing_records()
            self._connection.commit()

    def _scrub_existing_records(self) -> None:
        for table, column in (
            ("runs", "state_json"), ("events", "payload_json"), ("checkpoints", "state_json")
        ):
            for row in self._connection.execute(f"SELECT id, {column} FROM {table}").fetchall():
                original = json.loads(row[column])
                redacted = self._data.redact(original)
                if original != redacted:
                    self._connection.execute(
                        f"UPDATE {table} SET {column} = ? WHERE id = ?",
                        (json.dumps(redacted), row["id"]),
                    )

    def _state_json(self, state: RunState) -> str:
        return json.dumps(self._data.redact(state.model_dump(mode="json")))

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
                    self._state_json(state),
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
                    self._state_json(state),
                    state.id,
                ),
            )
            self._insert_checkpoint(state, reason)
            self._connection.commit()

    def _insert_checkpoint(self, state: RunState, reason: str) -> None:
        self._connection.execute(
            "INSERT INTO checkpoints(run_id, reason, created_at, state_json) VALUES (?, ?, ?, ?)",
            (state.id, reason, utc_now(), self._state_json(state)),
        )

    async def get_run(self, run_id: str) -> RunState | None:
        async with self._lock:
            row = self._connection.execute(
                "SELECT state_json FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        return RunState.model_validate(self._data.redact(json.loads(row["state_json"]))) if row else None

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
        payload = self._data.redact(payload)
        created_at = utc_now()
        async with self._lock:
            cursor = self._connection.execute(
                "INSERT INTO events(run_id, type, created_at, payload_json) VALUES (?, ?, ?, ?)",
                (run_id, event_type, created_at, json.dumps(payload, default=str)),
            )
            self._connection.commit()
            if cursor.lastrowid is None:
                raise RuntimeError("Event insert did not return an identifier.")
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

    async def subscribe(self, run_id: str) -> AsyncGenerator[EventRecord, None]:
        queue: asyncio.Queue[EventRecord] = asyncio.Queue(maxsize=200)
        self._subscribers[run_id].add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers[run_id].discard(queue)

    async def resolved_runs(self, limit: int) -> list[RunState]:
        async with self._lock:
            rows = self._connection.execute(
                "SELECT state_json FROM runs WHERE status = 'resolved' ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [RunState.model_validate_json(row["state_json"]) for row in rows]

    async def add_security_event(self, category: str, code: str, actor: str = "anonymous") -> None:
        async with self._lock:
            self._connection.execute(
                "INSERT INTO security_events(created_at, category, code, actor) VALUES (?, ?, ?, ?)",
                (utc_now(), category, code, actor),
            )
            self._connection.commit()

    async def security_events(self, limit: int = 100) -> list[dict[str, Any]]:
        async with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM security_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    async def knowledge_documents(self) -> list[dict[str, Any]]:
        async with self._lock:
            rows = self._connection.execute("SELECT * FROM knowledge_documents").fetchall()
        return [dict(row) for row in rows]

    async def replace_knowledge(
        self, kind: str, documents: list[dict[str, Any]], limit: int,
        source: str | None = None,
    ) -> None:
        async with self._lock:
            with self._connection:
                if source is None:
                    self._connection.execute("DELETE FROM knowledge_documents WHERE kind = ?", (kind,))
                else:
                    self._connection.execute(
                        "DELETE FROM knowledge_documents WHERE kind = ? AND source = ?", (kind, source)
                    )
                for document in documents:
                    document = {
                        **document, "title": self._data.redact(document["title"]),
                        "body": self._data.redact(document["body"]),
                    }
                    self._connection.execute(
                        """INSERT INTO knowledge_documents
                        (id, kind, source, title, body, service, content_hash,
                         embedding_model, embedding_json, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        tuple(document[key] for key in (
                            "id", "kind", "source", "title", "body", "service", "content_hash",
                            "embedding_model", "embedding_json", "updated_at",
                        )),
                    )
                self._connection.execute(
                    """DELETE FROM knowledge_documents WHERE id NOT IN
                    (SELECT id FROM knowledge_documents ORDER BY updated_at DESC, id LIMIT ?)""",
                    (limit,),
                )

    async def search_knowledge(self, expression: str, limit: int) -> list[dict[str, Any]]:
        async with self._lock:
            rows = self._connection.execute(
                """SELECT d.*, bm25(knowledge_fts, 0, 3, 1) AS rank
                FROM knowledge_fts JOIN knowledge_documents d ON d.id = knowledge_fts.id
                WHERE knowledge_fts MATCH ? ORDER BY rank LIMIT ?""",
                (expression, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self._connection.close()
