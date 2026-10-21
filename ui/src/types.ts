export type Severity = "critical" | "high" | "medium" | "low" | string;
export type RunStatus =
  | "queued"
  | "running"
  | "paused"
  | "waiting_approval"
  | "completed"
  | "failed"
  | "cancelled"
  | string;

export interface PlanStep {
  id?: string;
  title?: string;
  name?: string;
  description?: string;
  status?: string;
  [key: string]: unknown;
}

export interface PendingAction {
  action_id: string;
  name?: string;
  action?: string;
  tool?: string;
  description?: string;
  args?: unknown;
  risk?: string;
  [key: string]: unknown;
}

export interface Run {
  id: string;
  title: string;
  service: string;
  severity: Severity;
  status: RunStatus;
  created_at: string;
  updated_at: string;
  current_step?: number | string | null;
  plan?: PlanStep[] | string[] | null;
  findings?: unknown[] | Record<string, unknown> | null;
  pending_action?: PendingAction | null;
  budget?: Record<string, unknown> | number | string | null;
  summary?: unknown;
  description?: string;
  [key: string]: unknown;
}

export interface RunEvent {
  id: string;
  run_id: string;
  type: string;
  created_at: string;
  payload: unknown;
}

export interface CreateRunInput {
  title: string;
  service: string;
  severity: string;
  description: string;
}

export interface HealthStatus {
  status?: string;
  ok?: boolean;
  version?: string;
  [key: string]: unknown;
}

export type StreamState = "connecting" | "live" | "reconnecting" | "polling";
