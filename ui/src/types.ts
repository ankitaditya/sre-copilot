export type Severity = "critical" | "high" | "medium" | "low" | string;
export type RunStatus =
  | "queued"
  | "running"
  | "paused"
  | "waiting_approval"
  | "awaiting_approval"
  | "needs_human"
  | "resolved"
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
  id?: string;
  action_id?: string;
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
  id: string | number;
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

export interface AuthSession {
  enabled: boolean;
  authenticated: boolean;
  role: "viewer" | "operator" | "approver" | null;
  csrf_token?: string | null;
}

export interface KnowledgeMatch {
  id: string;
  kind: "runbook" | "incident";
  source: string;
  title: string;
  excerpt: string;
  score: number;
}

export interface KnowledgeStatus {
  documents: number;
  runbook_chunks: number;
  incident_chunks: number;
  embedding_model: string | null;
  embedded_chunks: number;
  warnings: string[];
}

export interface KnowledgeResults {
  matches: KnowledgeMatch[];
  mode: string;
  warnings: string[];
}
