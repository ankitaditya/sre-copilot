from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from sre_copilot.config import Settings
from sre_copilot.llm import OllamaReasoner
from sre_copilot.models import (
    Budget,
    CreateRunRequest,
    Finding,
    PendingAction,
    PlanStep,
    RunState,
    RunStatus,
)
from sre_copilot.store import RunStore
from sre_copilot.tools import ToolRegistry

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {
    RunStatus.RESOLVED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
}


class AgentRuntime:
    def __init__(
        self,
        settings: Settings,
        store: RunStore,
        tools: ToolRegistry,
    ):
        self._settings = settings
        self._store = store
        self._tools = tools
        self._reasoner = OllamaReasoner(settings)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._closing = False

    async def start(self) -> None:
        for state in await self._store.list_recoverable_runs():
            await self._store.add_event(
                state.id,
                "run_recovered",
                {"message": "Recovered unfinished run after process restart."},
            )
            self._schedule(state.id)

    async def stop(self) -> None:
        self._closing = True
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def create_run(self, request: CreateRunRequest) -> RunState:
        run_id = str(uuid.uuid4())
        state = RunState(
            id=run_id,
            title=request.title,
            service=request.service,
            severity=request.severity,
            description=request.description,
            budget=Budget(
                max_steps=self._settings.max_steps,
                max_tool_calls=self._settings.max_tool_calls,
            ),
            plan=[
                PlanStep(
                    id="scope",
                    title="Establish incident scope",
                    hypothesis="The alert contains enough context to define a bounded investigation.",
                ),
                PlanStep(
                    id="evidence",
                    title="Collect service evidence",
                    hypothesis="Health state, logs, and runbooks will expose the failure mode.",
                ),
                PlanStep(
                    id="diagnose",
                    title="Correlate evidence and identify root cause",
                    hypothesis="Independent signals will converge on one actionable cause.",
                ),
                PlanStep(
                    id="remediate",
                    title="Propose the safest remediation",
                    hypothesis="A bounded change can restore service without expanding blast radius.",
                ),
                PlanStep(
                    id="verify",
                    title="Verify recovery and close",
                    hypothesis="Post-change signals must prove the service is healthy.",
                ),
            ],
        )
        await self._store.create_run(state)
        await self._store.add_event(
            state.id,
            "run_created",
            {
                "title": state.title,
                "service": state.service,
                "severity": state.severity.value,
                "message": "Incident accepted and queued for autonomous triage.",
            },
        )
        self._schedule(state.id)
        return state

    async def approve(
        self, run_id: str, action_id: str, edited_args: dict[str, Any] | None
    ) -> RunState:
        async with self._lock_for(run_id):
            state = await self._required_run(run_id)
            action = state.pending_action
            if state.status != RunStatus.AWAITING_APPROVAL or action is None:
                raise RuntimeConflict("Run is not awaiting approval.")
            if action.id != action_id:
                raise RuntimeConflict("Approval does not match the pending action.")
            if edited_args is not None:
                action.args = edited_args
            state.status = RunStatus.RUNNING
            await self._store.add_event(
                run_id,
                "action_approved",
                {
                    "action_id": action.id,
                    "tool": action.tool,
                    "args": action.args,
                    "message": "Operator approved the proposed change.",
                },
            )
            result, event_id = await self._execute_tool(state, action.tool, action.args)
            state.last_observation = result
            state.pending_action = None
            if result["ok"]:
                state.plan[state.current_step].status = "completed"
                state.plan[state.current_step].notes = "Approved remediation executed."
                state.current_step = min(state.current_step + 1, len(state.plan) - 1)
            else:
                state.failed_attempts.append(
                    f"{action.tool}: {result.get('error', 'unknown error')}"
                )
                state.plan[state.current_step].status = "failed"
                state.current_step = 1
                await self._store.add_event(
                    run_id,
                    "replan",
                    {
                        "reason": "Approved action failed; returning to evidence collection.",
                        "source_event_id": event_id,
                    },
                )
            await self._store.save_run(state, "operator_approval")
        self._schedule(run_id)
        return state

    async def reject(self, run_id: str, action_id: str, reason: str | None) -> RunState:
        async with self._lock_for(run_id):
            state = await self._required_run(run_id)
            action = state.pending_action
            if state.status != RunStatus.AWAITING_APPROVAL or action is None:
                raise RuntimeConflict("Run is not awaiting approval.")
            if action.id != action_id:
                raise RuntimeConflict("Rejection does not match the pending action.")
            note = reason or "Operator rejected the proposed action."
            state.operator_notes.append(note)
            state.failed_attempts.append(f"rejected {action.tool}: {note}")
            state.pending_action = None
            state.status = RunStatus.NEEDS_HUMAN
            state.plan[state.current_step].status = "pending"
            await self._store.add_event(
                run_id,
                "action_rejected",
                {
                    "action_id": action.id,
                    "tool": action.tool,
                    "reason": note,
                    "message": "Action rejected; the run is waiting for operator guidance.",
                },
            )
            await self._store.save_run(state, "operator_rejection")
            return state

    async def add_guidance(self, run_id: str, message: str) -> RunState:
        async with self._lock_for(run_id):
            state = await self._required_run(run_id)
            if state.status in TERMINAL_STATUSES:
                raise RuntimeConflict("Cannot guide a terminal run.")
            state.operator_notes.append(message)
            if state.status == RunStatus.NEEDS_HUMAN:
                state.status = RunStatus.RUNNING
                state.current_step = min(2, len(state.plan) - 1)
            await self._store.add_event(
                run_id,
                "operator_guidance",
                {"message": message},
            )
            await self._store.save_run(state, "operator_guidance")
        self._schedule(run_id)
        return state

    async def pause(self, run_id: str) -> RunState:
        async with self._lock_for(run_id):
            state = await self._required_run(run_id)
            if state.status in TERMINAL_STATUSES:
                raise RuntimeConflict("Cannot pause a terminal run.")
            state.status = RunStatus.PAUSED
            await self._store.add_event(run_id, "run_paused", {"message": "Run paused."})
            await self._store.save_run(state, "run_paused")
            return state

    async def resume(self, run_id: str) -> RunState:
        async with self._lock_for(run_id):
            state = await self._required_run(run_id)
            if state.status not in {RunStatus.PAUSED, RunStatus.NEEDS_HUMAN}:
                raise RuntimeConflict("Only paused or needs-human runs can be resumed.")
            state.status = (
                RunStatus.AWAITING_APPROVAL
                if state.pending_action
                else RunStatus.RUNNING
            )
            await self._store.add_event(run_id, "run_resumed", {"message": "Run resumed."})
            await self._store.save_run(state, "run_resumed")
        if state.status == RunStatus.RUNNING:
            self._schedule(run_id)
        return state

    async def cancel(self, run_id: str) -> RunState:
        async with self._lock_for(run_id):
            state = await self._required_run(run_id)
            if state.status in TERMINAL_STATUSES:
                return state
            state.status = RunStatus.CANCELLED
            state.summary = "Cancelled by the operator."
            state.pending_action = None
            await self._store.add_event(
                run_id, "run_cancelled", {"message": "Run cancelled by operator."}
            )
            await self._store.save_run(state, "run_cancelled")
            return state

    async def update_plan(self, run_id: str, steps: list[PlanStep]) -> RunState:
        if not steps:
            raise RuntimeConflict("A run must retain at least one plan step.")
        async with self._lock_for(run_id):
            state = await self._required_run(run_id)
            if state.status in TERMINAL_STATUSES:
                raise RuntimeConflict("Cannot edit the plan of a terminal run.")
            state.plan = steps
            state.current_step = min(state.current_step, len(steps) - 1)
            await self._store.add_event(
                run_id,
                "plan_updated",
                {"steps": [step.model_dump() for step in steps]},
            )
            await self._store.save_run(state, "plan_updated")
            return state

    def _schedule(self, run_id: str) -> None:
        if self._closing:
            return
        existing = self._tasks.get(run_id)
        if existing and not existing.done():
            return
        task = asyncio.create_task(self._drive(run_id), name=f"agent-run-{run_id}")
        self._tasks[run_id] = task
        task.add_done_callback(lambda completed, rid=run_id: self._task_done(rid, completed))

    def _task_done(self, run_id: str, task: asyncio.Task[None]) -> None:
        self._tasks.pop(run_id, None)
        if task.cancelled():
            return
        error = task.exception()
        if error:
            logger.exception("Agent run %s crashed", run_id, exc_info=error)

    async def _drive(self, run_id: str) -> None:
        while not self._closing:
            async with self._lock_for(run_id):
                state = await self._required_run(run_id)
                if state.status in TERMINAL_STATUSES | {
                    RunStatus.PAUSED,
                    RunStatus.NEEDS_HUMAN,
                    RunStatus.AWAITING_APPROVAL,
                }:
                    return
                if self._budget_exhausted(state):
                    state.status = RunStatus.NEEDS_HUMAN
                    state.summary = "Automation budget exhausted before resolution."
                    await self._store.add_event(
                        run_id,
                        "budget_exhausted",
                        {
                            "budget": state.budget.model_dump(),
                            "message": "Hard automation budget reached; operator intervention required.",
                        },
                    )
                    await self._store.save_run(state, "budget_exhausted")
                    return
                state.status = RunStatus.RUNNING
                state.budget.steps_used += 1
                await self._run_current_step(state)
                await self._store.save_run(state, f"step_{state.current_step}")
            await asyncio.sleep(0)

    async def _run_current_step(self, state: RunState) -> None:
        step = state.plan[state.current_step]
        step.status = "running"
        await self._store.add_event(
            state.id,
            "reasoning",
            {
                "step_id": step.id,
                "title": step.title,
                "summary": self._reasoning_summary(state),
            },
        )

        if step.id == "scope":
            step.status = "completed"
            step.notes = f"Investigation bounded to service {state.service}."
            state.current_step = self._next_step(state)
            return
        if step.id == "evidence":
            await self._collect_evidence(state)
            return
        if step.id == "diagnose":
            await self._diagnose(state)
            return
        if step.id == "remediate":
            await self._propose_remediation(state)
            return
        if step.id == "verify":
            await self._verify(state)
            return

        step.status = "completed"
        step.notes = "Operator-defined step acknowledged by the runtime."
        state.current_step = self._next_step(state)

    async def _collect_evidence(self, state: RunState) -> None:
        calls: list[tuple[str, dict[str, Any]]]
        if state.service == "demo-api":
            calls = [
                ("inspect_demo_service", {}),
                ("read_demo_logs", {"limit": 100}),
                (
                    "search_runbooks",
                    {"query": f"{state.service} {state.description}"},
                ),
            ]
        else:
            calls = [
                ("list_containers", {}),
                ("get_container_logs", {"name": state.service, "tail": 100}),
                (
                    "search_runbooks",
                    {"query": f"{state.service} {state.description}"},
                ),
            ]
        observations: list[dict[str, Any]] = []
        event_ids: list[int] = []
        for tool, args in calls:
            result, event_id = await self._execute_tool(state, tool, args)
            observations.append({"tool": tool, "result": result, "event_id": event_id})
            event_ids.append(event_id)
        state.last_observation = {"evidence": observations}
        successful = sum(1 for item in observations if item["result"]["ok"])
        if successful == 0:
            state.plan[state.current_step].status = "failed"
            state.plan[state.current_step].notes = "All evidence tools failed."
            state.status = RunStatus.NEEDS_HUMAN
            state.summary = "Unable to collect service evidence with available tools."
            return
        state.findings.append(
            Finding(
                id=str(uuid.uuid4()),
                title="Initial evidence collected",
                detail=f"{successful} of {len(observations)} evidence sources returned successfully.",
                confidence=min(95, 45 + successful * 15),
                evidence_event_ids=event_ids,
            )
        )
        state.plan[state.current_step].status = "completed"
        state.plan[state.current_step].notes = f"Collected {len(observations)} evidence sources."
        state.current_step = self._next_step(state)

    async def _diagnose(self, state: RunState) -> None:
        evidence = (state.last_observation or {}).get("evidence", [])
        model_result = await self._reasoner.analyze(
            service=state.service,
            description=state.description,
            observations=evidence,
            operator_notes=state.operator_notes,
        )
        if model_result:
            state.model_provider = f"ollama:{self._settings.ollama_model}"
            root_cause = str(model_result.get("root_cause") or "Model identified an anomaly.")
            confidence = int(model_result.get("confidence") or 60)
            detail = str(model_result.get("summary") or root_cause)
            state.last_observation = {
                **(state.last_observation or {}),
                "model_recommendation": {
                    "tool": model_result.get("recommended_tool"),
                    "args": model_result.get("recommended_args") or {},
                    "rationale": model_result.get("rationale"),
                    "blast_radius": model_result.get("blast_radius"),
                },
            }
        else:
            state.model_provider = "deterministic-fallback"
            root_cause, detail, confidence = self._deterministic_diagnosis(state, evidence)
        source_ids = [item["event_id"] for item in evidence if item.get("event_id")]
        state.findings.append(
            Finding(
                id=str(uuid.uuid4()),
                title=root_cause,
                detail=detail,
                confidence=max(0, min(confidence, 100)),
                evidence_event_ids=source_ids,
            )
        )
        await self._store.add_event(
            state.id,
            "diagnosis",
            {
                "root_cause": root_cause,
                "detail": detail,
                "confidence": confidence,
                "provider": state.model_provider,
                "evidence_event_ids": source_ids,
            },
        )
        state.plan[state.current_step].status = "completed"
        state.plan[state.current_step].notes = root_cause
        state.current_step = self._next_step(state)

    def _deterministic_diagnosis(
        self, state: RunState, evidence: list[dict[str, Any]]
    ) -> tuple[str, str, int]:
        for item in evidence:
            if item["tool"] != "inspect_demo_service" or not item["result"]["ok"]:
                continue
            data = item["result"]["data"]
            fault = data.get("fault", "none")
            if fault != "none":
                symptoms = ", ".join(data.get("symptoms", [])) or "service degradation"
                return (
                    f"Injected {fault.replace('-', ' ')} fault",
                    f"The service state reports {fault}; correlated symptoms: {symptoms}.",
                    94,
                )
            return (
                "No active service fault",
                "Current service state is healthy; the alert may have self-recovered.",
                88,
            )
        errors = [
            item["result"].get("error")
            for item in evidence
            if not item["result"].get("ok")
        ]
        return (
            "Container-level service degradation",
            f"Available local evidence indicates the service is unavailable. Tool errors: {errors}",
            62,
        )

    async def _propose_remediation(self, state: RunState) -> None:
        latest = state.findings[-1] if state.findings else None
        if latest and latest.title == "No active service fault":
            state.plan[state.current_step].status = "skipped"
            state.plan[state.current_step].notes = "No mutating action required."
            state.current_step = self._next_step(state)
            return
        recommendation = (state.last_observation or {}).get("model_recommendation") or {}
        recommended_tool = recommendation.get("tool")
        model_tool_allowed = False
        if isinstance(recommended_tool, str):
            try:
                model_tool_allowed = (
                    self._tools.get(recommended_tool).definition.risk == "mutating"
                )
            except KeyError:
                model_tool_allowed = False
        if model_tool_allowed:
            tool = recommended_tool
            args = (
                recommendation.get("args")
                if isinstance(recommendation.get("args"), dict)
                else {}
            )
            blast_radius = str(
                recommendation.get("blast_radius")
                or f"Bounded to the approved {tool} target."
            )
            rationale = str(
                recommendation.get("rationale")
                or "The local model selected this allow-listed mutating tool from the evidence."
            )
            risk = "medium"
        elif state.service == "demo-api":
            fault = "unknown"
            evidence = (state.last_observation or {}).get("evidence", [])
            for item in evidence:
                if item["tool"] == "inspect_demo_service" and item["result"]["ok"]:
                    fault = item["result"]["data"].get("fault", "unknown")
            tool = "restore_demo_service"
            args: dict[str, Any] = {"expected_fault": fault}
            blast_radius = "Only the local demo-api fault state; no external systems."
            risk = "low"
        else:
            tool = "restart_container"
            args = {"name": state.service}
            blast_radius = f"One local container: {state.service}. In-flight requests may be interrupted."
            risk = "medium"
        if not model_tool_allowed:
            rationale = (
                f"Evidence supports a bounded {tool} action. The runtime will verify health "
                "after execution and replan if the signal remains unhealthy."
            )
        action = PendingAction(
            id=str(uuid.uuid4()),
            tool=tool,
            args=args,
            rationale=rationale,
            risk=risk,
            blast_radius=blast_radius,
        )
        state.pending_action = action
        state.status = RunStatus.AWAITING_APPROVAL
        await self._store.add_event(
            state.id,
            "approval_required",
            {
                "action": action.model_dump(),
                "message": "A mutating action is blocked pending explicit operator approval.",
            },
        )

    async def _verify(self, state: RunState) -> None:
        if state.service == "demo-api":
            result, event_id = await self._execute_tool(state, "inspect_demo_service", {})
            healthy = bool(result.get("ok") and result.get("data", {}).get("healthy"))
        else:
            result, event_id = await self._execute_tool(state, "list_containers", {})
            healthy = bool(result.get("ok"))
        state.last_observation = result
        if healthy:
            state.plan[state.current_step].status = "completed"
            state.plan[state.current_step].notes = "Post-remediation verification passed."
            state.status = RunStatus.RESOLVED
            state.summary = (
                f"Resolved {state.title}. Root cause: "
                f"{state.findings[-1].title if state.findings else 'unknown'}. "
                f"Verification event: {event_id}."
            )
            await self._store.add_event(
                state.id,
                "run_resolved",
                {
                    "summary": state.summary,
                    "verification_event_id": event_id,
                    "budget": state.budget.model_dump(),
                },
            )
            return
        state.failed_attempts.append(f"verification failed: {result.get('error', result)}")
        state.plan[state.current_step].status = "failed"
        await self._store.add_event(
            state.id,
            "verification_failed",
            {
                "result": result,
                "message": "Service remains unhealthy; replanning from evidence collection.",
            },
        )
        state.current_step = next(
            (index for index, step in enumerate(state.plan) if step.id == "evidence"),
            0,
        )

    async def _execute_tool(
        self, state: RunState, tool: str, args: dict[str, Any]
    ) -> tuple[dict[str, Any], int]:
        definition = self._tools.get(tool).definition
        if definition.risk == "mutating" and (
            state.pending_action is None or state.pending_action.tool != tool
        ):
            raise RuntimeConflict(f"Mutating tool {tool} bypassed the approval gate.")
        attempts = 0
        result: dict[str, Any] = {"ok": False, "error": "not_executed"}
        event_id = 0
        while attempts < 3:
            attempts += 1
            if state.budget.tool_calls_used >= state.budget.max_tool_calls:
                return {"ok": False, "error": "tool_budget_exhausted", "retryable": False}, event_id
            state.budget.tool_calls_used += 1
            await self._store.add_event(
                state.id,
                "tool_call",
                {
                    "tool": tool,
                    "args": args,
                    "risk": definition.risk,
                    "attempt": attempts,
                },
            )
            result = await self._tools.execute(tool, args)
            event = await self._store.add_event(
                state.id,
                "tool_result",
                {
                    "tool": tool,
                    "args": args,
                    "attempt": attempts,
                    "result": result,
                },
            )
            event_id = event.id
            if result["ok"] or not result.get("retryable") or attempts >= 3:
                break
            await self._store.add_event(
                state.id,
                "tool_retry",
                {
                    "tool": tool,
                    "attempt": attempts,
                    "delay_seconds": 0.25 * (2 ** (attempts - 1)),
                    "error": result.get("error"),
                },
            )
            await asyncio.sleep(0.25 * (2 ** (attempts - 1)))
        return result, event_id

    @staticmethod
    def _reasoning_summary(state: RunState) -> str:
        step = state.plan[state.current_step]
        if state.operator_notes:
            return (
                f"Working on '{step.title}' while incorporating the latest operator guidance. "
                "The next decision will be grounded in recorded evidence."
            )
        return (
            f"Working on '{step.title}'. The agent will collect or evaluate evidence before "
            "taking any action; mutating tools remain approval-gated."
        )

    @staticmethod
    def _next_step(state: RunState) -> int:
        return min(state.current_step + 1, len(state.plan) - 1)

    @staticmethod
    def _budget_exhausted(state: RunState) -> bool:
        return (
            state.budget.steps_used >= state.budget.max_steps
            or state.budget.tool_calls_used >= state.budget.max_tool_calls
        )

    async def _required_run(self, run_id: str) -> RunState:
        state = await self._store.get_run(run_id)
        if state is None:
            raise RunNotFound(run_id)
        return state

    def _lock_for(self, run_id: str) -> asyncio.Lock:
        return self._locks.setdefault(run_id, asyncio.Lock())


class RunNotFound(Exception):
    pass


class RuntimeConflict(Exception):
    pass
