from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    PAUSED = "paused"
    NEEDS_HUMAN = "needs_human"
    RESOLVED = "resolved"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PlanStep(BaseModel):
    id: str
    title: str
    hypothesis: str
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"
    notes: str | None = None


class Finding(BaseModel):
    id: str
    title: str
    detail: str
    confidence: int = Field(ge=0, le=100)
    evidence_event_ids: list[int] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)


class PendingAction(BaseModel):
    id: str
    tool: str
    args: dict[str, Any]
    rationale: str
    risk: Literal["low", "medium", "high"]
    blast_radius: str
    created_at: str = Field(default_factory=utc_now)


class Budget(BaseModel):
    steps_used: int = 0
    tool_calls_used: int = 0
    max_steps: int = 12
    max_tool_calls: int = 24


class RunState(BaseModel):
    id: str
    title: str
    service: str
    severity: Severity
    description: str
    status: RunStatus = RunStatus.QUEUED
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    current_step: int = 0
    plan: list[PlanStep] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    failed_attempts: list[str] = Field(default_factory=list)
    operator_notes: list[str] = Field(default_factory=list)
    pending_action: PendingAction | None = None
    last_observation: dict[str, Any] | None = None
    budget: Budget = Field(default_factory=Budget)
    summary: str | None = None
    model_provider: str = "deterministic"
    action_execution_id: str | None = None


class CreateRunRequest(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    service: str = Field(min_length=1, max_length=80)
    severity: Severity = Severity.HIGH
    description: str = Field(min_length=3, max_length=4000)


class ApprovalRequest(BaseModel):
    action_id: str
    args: dict[str, Any] | None = None


class RejectionRequest(BaseModel):
    action_id: str
    reason: str | None = None


class GuidanceRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class PlanUpdateRequest(BaseModel):
    steps: list[PlanStep]


class EventRecord(BaseModel):
    id: int
    run_id: str
    type: str
    created_at: str
    payload: dict[str, Any]


class ToolDefinition(BaseModel):
    name: str
    description: str
    risk: Literal["read_only", "mutating"]
    input_schema: dict[str, Any]


class ModelAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    summary: str = Field(min_length=1, max_length=4000)
    root_cause: str = Field(min_length=1, max_length=500)
    confidence: int = Field(ge=0, le=100)
    recommended_tool: str | None = None
    recommended_args: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(default="", max_length=2000)
    blast_radius: str = Field(default="", max_length=1000)


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)
    service: str | None = Field(default=None, max_length=80)
