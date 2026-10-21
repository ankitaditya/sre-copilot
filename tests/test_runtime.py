from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from sre_copilot.config import Settings
from sre_copilot.models import CreateRunRequest, RunStatus, Severity
from sre_copilot.runtime import AgentRuntime
from sre_copilot.store import RunStore
from sre_copilot.tools import ToolRegistry


def write_fault(path: Path, fault: str = "db-down") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "service": "demo-api",
                "fault": fault,
                "symptoms": ["HTTP 503", "database connection refused"],
                "last_changed_at": "2026-10-21T10:00:00+00:00",
                "logs": ["ERROR database connection refused"],
            }
        ),
        encoding="utf-8",
    )


async def wait_for_status(
    store: RunStore, run_id: str, expected: RunStatus, timeout: float = 3
):
    async with asyncio.timeout(timeout):
        while True:
            state = await store.get_run(run_id)
            assert state is not None
            if state.status == expected:
                return state
            await asyncio.sleep(0.01)


@pytest.fixture
async def runtime_bundle(tmp_path: Path):
    state_path = tmp_path / "sandbox" / "state.json"
    write_fault(state_path)
    runbooks = tmp_path / "runbooks"
    runbooks.mkdir()
    (runbooks / "db-down.md").write_text(
        "# Database unavailable\nconnection refused restart dependency verify readiness",
        encoding="utf-8",
    )
    settings = Settings(
        environment="test",
        database_path=tmp_path / "runs.db",
        sandbox_state_path=state_path,
        runbooks_dir=runbooks,
        ui_build_dir=tmp_path / "missing-ui",
        llm_mode="deterministic",
        tool_timeout_seconds=1,
    )
    store = RunStore(settings.database_path)
    await store.initialize()
    tools = ToolRegistry(settings)
    runtime = AgentRuntime(settings, store, tools)
    await runtime.start()
    yield settings, store, runtime
    await runtime.stop()
    store.close()


async def test_run_requires_approval_and_resolves(runtime_bundle):
    settings, store, runtime = runtime_bundle
    state = await runtime.create_run(
        CreateRunRequest(
            title="Checkout API unavailable",
            service="demo-api",
            severity=Severity.HIGH,
            description="Readiness failures and HTTP 503 responses.",
        )
    )

    waiting = await wait_for_status(store, state.id, RunStatus.AWAITING_APPROVAL)
    assert waiting.pending_action is not None
    assert waiting.pending_action.tool == "restore_demo_service"
    assert json.loads(settings.sandbox_state_path.read_text())["fault"] == "db-down"

    await runtime.approve(
        state.id,
        waiting.pending_action.id,
        {**waiting.pending_action.args, "change_ticket": "CHG-42"},
    )
    resolved = await wait_for_status(store, state.id, RunStatus.RESOLVED)

    assert resolved.summary
    assert json.loads(settings.sandbox_state_path.read_text())["fault"] == "none"
    events = await store.list_events(state.id)
    assert "approval_required" in {event.type for event in events}
    assert "action_approved" in {event.type for event in events}
    assert "run_resolved" in {event.type for event in events}


async def test_rejected_action_waits_for_guidance(runtime_bundle):
    _, store, runtime = runtime_bundle
    state = await runtime.create_run(
        CreateRunRequest(
            title="Demo database alert",
            service="demo-api",
            severity=Severity.MEDIUM,
            description="Database is unavailable.",
        )
    )
    waiting = await wait_for_status(store, state.id, RunStatus.AWAITING_APPROVAL)
    assert waiting.pending_action

    rejected = await runtime.reject(
        state.id, waiting.pending_action.id, "Validate the change window first."
    )

    assert rejected.status == RunStatus.NEEDS_HUMAN
    assert rejected.pending_action is None
    assert rejected.operator_notes[-1] == "Validate the change window first."


async def test_pending_approval_survives_runtime_restart(runtime_bundle):
    settings, store, runtime = runtime_bundle
    state = await runtime.create_run(
        CreateRunRequest(
            title="Persistent approval test",
            service="demo-api",
            severity=Severity.HIGH,
            description="The process will restart while approval is pending.",
        )
    )
    waiting = await wait_for_status(store, state.id, RunStatus.AWAITING_APPROVAL)
    assert waiting.pending_action
    await runtime.stop()

    restarted = AgentRuntime(settings, store, ToolRegistry(settings))
    await restarted.start()
    persisted = await store.get_run(state.id)
    assert persisted is not None
    assert persisted.status == RunStatus.AWAITING_APPROVAL
    assert persisted.pending_action is not None

    await restarted.approve(
        persisted.id, persisted.pending_action.id, persisted.pending_action.args
    )
    await wait_for_status(store, state.id, RunStatus.RESOLVED)
    await restarted.stop()

