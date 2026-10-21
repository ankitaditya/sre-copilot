import type {
  CreateRunInput,
  HealthStatus,
  PlanStep,
  Run,
} from "../types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch (error) {
    throw new ApiError(0, "The SRE API is unreachable.", error);
  }

  const raw = await response.text();
  let body: unknown = undefined;
  if (raw) {
    try {
      body = JSON.parse(raw);
    } catch {
      body = raw;
    }
  }

  if (!response.ok) {
    const message =
      typeof body === "string"
        ? body
        : typeof body === "object" && body
          ? String(
              (body as Record<string, unknown>).detail ??
                (body as Record<string, unknown>).message ??
                response.statusText,
            )
          : response.statusText;
    throw new ApiError(response.status, message || "Request failed.", body);
  }

  return body as T;
}

function unwrapRuns(value: Run[] | { runs?: Run[] }): Run[] {
  return Array.isArray(value) ? value : (value.runs ?? []);
}

export const api = {
  runs: {
    async list(): Promise<Run[]> {
      return unwrapRuns(await request<Run[] | { runs?: Run[] }>("/api/runs"));
    },
    get(id: string): Promise<Run> {
      return request(`/api/runs/${encodeURIComponent(id)}`);
    },
    create(input: CreateRunInput): Promise<Run> {
      return request("/api/runs", {
        method: "POST",
        body: JSON.stringify(input),
      });
    },
    approve(id: string, actionId: string, args?: unknown): Promise<Run> {
      return request(`/api/runs/${encodeURIComponent(id)}/approve`, {
        method: "POST",
        body: JSON.stringify({
          action_id: actionId,
          ...(args === undefined ? {} : { args }),
        }),
      });
    },
    reject(id: string, actionId: string, reason?: string): Promise<Run> {
      return request(`/api/runs/${encodeURIComponent(id)}/reject`, {
        method: "POST",
        body: JSON.stringify({
          action_id: actionId,
          ...(reason ? { reason } : {}),
        }),
      });
    },
    guide(id: string, message: string): Promise<Run> {
      return request(`/api/runs/${encodeURIComponent(id)}/guide`, {
        method: "POST",
        body: JSON.stringify({ message }),
      });
    },
    pause(id: string): Promise<Run> {
      return request(`/api/runs/${encodeURIComponent(id)}/pause`, {
        method: "POST",
      });
    },
    resume(id: string): Promise<Run> {
      return request(`/api/runs/${encodeURIComponent(id)}/resume`, {
        method: "POST",
      });
    },
    cancel(id: string): Promise<Run> {
      return request(`/api/runs/${encodeURIComponent(id)}/cancel`, {
        method: "POST",
      });
    },
    updatePlan(id: string, steps: PlanStep[] | string[]): Promise<Run> {
      return request(`/api/runs/${encodeURIComponent(id)}/plan`, {
        method: "PATCH",
        body: JSON.stringify({ steps }),
      });
    },
    eventsUrl(id: string): string {
      return `${API_BASE}/api/runs/${encodeURIComponent(id)}/events`;
    },
  },
  tools: {
    list(): Promise<unknown> {
      return request("/api/tools");
    },
  },
  health: {
    get(): Promise<HealthStatus> {
      return request("/api/health");
    },
  },
};

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "An unexpected error occurred.";
}
