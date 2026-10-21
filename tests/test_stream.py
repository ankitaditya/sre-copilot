from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Request

from sre_copilot.api import stream_events
from sre_copilot.auth import AuthManager
from sre_copilot.config import Settings
from sre_copilot.models import RunState, Severity
from sre_copilot.store import RunStore


@pytest.mark.parametrize("use_header", [True, False])
async def test_sse_replays_then_survives_heartbeat_and_cleans_up(
    tmp_path: Path, monkeypatch, use_header,
):
    store = RunStore(tmp_path / "stream.db")
    await store.initialize()
    await store.create_run(RunState(
        id="run", title="Stream test", service="demo-api", severity=Severity.HIGH,
        description="Database unavailable",
    ))
    first = await store.add_event("run", "reasoning", {"message": "Initial evidence"})
    second = await store.add_event("run", "diagnosis", {"message": "Database outage"})
    blocker = asyncio.Event()

    async def receive():
        await blocker.wait()
        return {"type": "http.disconnect"}

    app = SimpleNamespace(state=SimpleNamespace(
        store=store, runtime=None, tools=None, auth=AuthManager(Settings()),
    ))
    request = Request({
        "type": "http", "method": "GET", "headers": [], "path": "/api/runs/run/events",
        "query_string": b"", "app": app,
    }, receive=receive)
    real_wait = asyncio.wait

    async def quick_wait(tasks, timeout):
        return await real_wait(tasks, timeout=0.001)

    monkeypatch.setattr("sre_copilot.api.asyncio.wait", quick_wait)
    response = await stream_events(
        "run", request, last_event_id=first.id if use_header else None,
        after_id=0 if use_header else first.id,
    )
    stream = response.body_iterator
    try:
        replay = await anext(stream)
        assert f"id: {second.id}\n" in replay
        assert "event: diagnosis\n" in replay
        heartbeat = await anext(stream)
        assert heartbeat == ": heartbeat\n\n"
        live = await store.add_event("run", "security_blocked", {"code": "tool_not_allowed"})
        received = await anext(stream)
        assert f"id: {live.id}\n" in received
        assert "event: security_blocked\n" in received
    finally:
        await stream.aclose()
        assert not store._subscribers["run"]
        store.close()
