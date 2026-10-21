from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from sre_copilot.auth import require_role
from sre_copilot.models import (
    ApprovalRequest,
    CreateRunRequest,
    GuidanceRequest,
    KnowledgeSearchRequest,
    PlanUpdateRequest,
    RejectionRequest,
    RunState,
)
from sre_copilot.runtime import AgentRuntime, RunNotFound, RuntimeConflict
from sre_copilot.store import RunStore
from sre_copilot.tools import ToolRegistry

router = APIRouter(
    prefix="/api", tags=["agent-runtime"], dependencies=[Depends(require_role("viewer"))]
)


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


@router.post(
    "/runs", response_model=RunState, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("operator"))],
)
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
    after_id: int = Query(default=0, ge=0),
) -> StreamingResponse:
    store, _, _ = _services(request)
    if await store.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    async def event_stream() -> AsyncIterator[str]:
        cursor = max(last_event_id or 0, after_id)
        iterator = store.subscribe(run_id)
        pending = asyncio.ensure_future(anext(iterator))
        await asyncio.sleep(0)
        try:
            while not await request.is_disconnected():
                try:
                    request.app.state.auth.authorize(request, "viewer")
                except HTTPException:
                    return
                replay = await store.list_events(run_id, after_id=cursor)
                if replay:
                    for event in replay:
                        cursor = event.id
                        yield _sse(event.id, event.type, event.model_dump(mode="json"))
                    continue
                ready, _ = await asyncio.wait({pending}, timeout=15)
                if not ready:
                    yield ": heartbeat\n\n"
                    continue
                pending.result()
                pending = asyncio.ensure_future(anext(iterator))
        finally:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
            await iterator.aclose()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post(
    "/runs/{run_id}/approve", response_model=RunState,
    dependencies=[Depends(require_role("approver"))],
)
async def approve(run_id: str, payload: ApprovalRequest, request: Request) -> RunState:
    _, runtime, _ = _services(request)
    return await _runtime_call(
        runtime.approve(run_id, payload.action_id, payload.args)
    )


@router.post(
    "/runs/{run_id}/reject", response_model=RunState,
    dependencies=[Depends(require_role("approver"))],
)
async def reject(run_id: str, payload: RejectionRequest, request: Request) -> RunState:
    _, runtime, _ = _services(request)
    return await _runtime_call(
        runtime.reject(run_id, payload.action_id, payload.reason)
    )


@router.post(
    "/runs/{run_id}/guide", response_model=RunState,
    dependencies=[Depends(require_role("operator"))],
)
async def guide(run_id: str, payload: GuidanceRequest, request: Request) -> RunState:
    _, runtime, _ = _services(request)
    return await _runtime_call(runtime.add_guidance(run_id, payload.message))


@router.post(
    "/runs/{run_id}/pause", response_model=RunState,
    dependencies=[Depends(require_role("operator"))],
)
async def pause(run_id: str, request: Request) -> RunState:
    _, runtime, _ = _services(request)
    return await _runtime_call(runtime.pause(run_id))


@router.post(
    "/runs/{run_id}/resume", response_model=RunState,
    dependencies=[Depends(require_role("operator"))],
)
async def resume(run_id: str, request: Request) -> RunState:
    _, runtime, _ = _services(request)
    return await _runtime_call(runtime.resume(run_id))


@router.post(
    "/runs/{run_id}/cancel", response_model=RunState,
    dependencies=[Depends(require_role("operator"))],
)
async def cancel(run_id: str, request: Request) -> RunState:
    _, runtime, _ = _services(request)
    return await _runtime_call(runtime.cancel(run_id))


@router.patch(
    "/runs/{run_id}/plan", response_model=RunState,
    dependencies=[Depends(require_role("operator"))],
)
async def update_plan(
    run_id: str, payload: PlanUpdateRequest, request: Request
) -> RunState:
    _, runtime, _ = _services(request)
    return await _runtime_call(runtime.update_plan(run_id, payload.steps))


@router.get("/knowledge")
async def knowledge_status(request: Request):
    return await request.app.state.runtime.knowledge.status()


@router.get("/knowledge/search")
async def search_knowledge(
    request: Request, query: str = Query(min_length=1, max_length=2000),
    limit: int = Query(default=5, ge=1, le=20), service: str | None = None,
):
    if service is not None:
        request.app.state.tools.policy.service(service)
    return await request.app.state.runtime.knowledge.search(query, limit, service)


@router.post("/knowledge/reindex", dependencies=[Depends(require_role("operator"))])
async def reindex_knowledge(request: Request):
    return await request.app.state.runtime.knowledge.rebuild()


@router.post("/knowledge/search")
async def search_knowledge_body(payload: KnowledgeSearchRequest, request: Request):
    if payload.service is not None:
        request.app.state.tools.policy.service(payload.service)
    return await request.app.state.runtime.knowledge.search(
        payload.query, payload.limit, payload.service
    )


@router.get("/security")
async def security_status(request: Request):
    settings = request.app.state.tools.policy.settings
    return {
        "authentication_enabled": settings.auth_enabled,
        "prompt_screening": True, "dlp_redaction": True,
        "allowed_services": settings.allowed_services,
        "allowed_tools": settings.allowed_tools,
        "allowed_http_origins": settings.allowed_http_origins,
        "allowed_model_origins": settings.allowed_model_origins,
        "plan_governance": "ordered_safety_stages_required",
    }


@router.get("/security/events")
async def security_events(request: Request, limit: int = Query(default=100, ge=1, le=250)):
    return await request.app.state.store.security_events(limit)


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
