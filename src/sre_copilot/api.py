from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from sre_copilot.models import (
    ApprovalRequest,
    CreateRunRequest,
    GuidanceRequest,
    PlanUpdateRequest,
    RejectionRequest,
    RunState,
)
from sre_copilot.runtime import AgentRuntime, RunNotFound, RuntimeConflict
from sre_copilot.store import RunStore
from sre_copilot.tools import ToolRegistry

router = APIRouter(prefix="/api", tags=["agent-runtime"])


def _services(request: Request) -> tuple[RunStore, AgentRuntime, ToolRegistry]:
    return request.app.state.store, request.app.state.runtime, request.app.state.tools


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    store, _, tools = _services(request)
    runs = await store.list_runs(limit=1)
    return {
        "status": "ok",
        "service": "sre-copilot",
        "runtime": "ready",
        "registered_tools": len(tools.definitions()),
        "has_runs": bool(runs),
    }


@router.get("/tools")
async def list_tools(request: Request) -> list[dict[str, object]]:
    _, _, tools = _services(request)
    return [tool.model_dump() for tool in tools.definitions()]


@router.post("/runs", response_model=RunState, status_code=status.HTTP_201_CREATED)
async def create_run(payload: CreateRunRequest, request: Request) -> RunState:
    _, runtime, _ = _services(request)
    return await runtime.create_run(payload)


@router.get("/runs", response_model=list[RunState])
async def list_runs(request: Request, limit: int = 100) -> list[RunState]:
    store, _, _ = _services(request)
    return await store.list_runs(limit=max(1, min(limit, 250)))


@router.get("/runs/{run_id}", response_model=RunState)
async def get_run(run_id: str, request: Request) -> RunState:
    store, _, _ = _services(request)
    state = await store.get_run(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return state


@router.get("/runs/{run_id}/history")
async def get_history(run_id: str, request: Request) -> list[dict[str, object]]:
    store, _, _ = _services(request)
    if await store.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return await store.list_history(run_id)


@router.get("/runs/{run_id}/events")
async def stream_events(
    run_id: str,
    request: Request,
    last_event_id: int | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    store, _, _ = _services(request)
    if await store.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    async def event_stream() -> AsyncIterator[str]:
        cursor = last_event_id or 0
        for event in await store.list_events(run_id, after_id=cursor):
            cursor = event.id
            yield _sse(event.id, event.type, event.model_dump(mode="json"))
        iterator = store.subscribe(run_id).__aiter__()
        while not await request.is_disconnected():
            try:
                event = await asyncio.wait_for(iterator.__anext__(), timeout=15)
                if event.id > cursor:
                    cursor = event.id
                    yield _sse(event.id, event.type, event.model_dump(mode="json"))
            except TimeoutError:
                yield ": heartbeat\n\n"
            except StopAsyncIteration:
                return

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/runs/{run_id}/approve", response_model=RunState)
async def approve(run_id: str, payload: ApprovalRequest, request: Request) -> RunState:
    _, runtime, _ = _services(request)
    return await _runtime_call(
        runtime.approve(run_id, payload.action_id, payload.args)
    )


@router.post("/runs/{run_id}/reject", response_model=RunState)
async def reject(run_id: str, payload: RejectionRequest, request: Request) -> RunState:
    _, runtime, _ = _services(request)
    return await _runtime_call(
        runtime.reject(run_id, payload.action_id, payload.reason)
    )


@router.post("/runs/{run_id}/guide", response_model=RunState)
async def guide(run_id: str, payload: GuidanceRequest, request: Request) -> RunState:
    _, runtime, _ = _services(request)
    return await _runtime_call(runtime.add_guidance(run_id, payload.message))


@router.post("/runs/{run_id}/pause", response_model=RunState)
async def pause(run_id: str, request: Request) -> RunState:
    _, runtime, _ = _services(request)
    return await _runtime_call(runtime.pause(run_id))


@router.post("/runs/{run_id}/resume", response_model=RunState)
async def resume(run_id: str, request: Request) -> RunState:
    _, runtime, _ = _services(request)
    return await _runtime_call(runtime.resume(run_id))


@router.post("/runs/{run_id}/cancel", response_model=RunState)
async def cancel(run_id: str, request: Request) -> RunState:
    _, runtime, _ = _services(request)
    return await _runtime_call(runtime.cancel(run_id))


@router.patch("/runs/{run_id}/plan", response_model=RunState)
async def update_plan(
    run_id: str, payload: PlanUpdateRequest, request: Request
) -> RunState:
    _, runtime, _ = _services(request)
    return await _runtime_call(runtime.update_plan(run_id, payload.steps))


async def _runtime_call(awaitable):
    try:
        return await awaitable
    except RunNotFound as exc:
        raise HTTPException(status_code=404, detail="Run not found.") from exc
    except RuntimeConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _sse(event_id: int, event_type: str, payload: dict[str, object]) -> str:
    return (
        f"id: {event_id}\n"
        f"event: {event_type}\n"
        f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
    )
