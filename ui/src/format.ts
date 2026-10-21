import type { PlanStep, Run } from "./types";

export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

export function relativeTime(value?: string | null): string {
  if (!value) return "Unknown";
  const time = new Date(value).getTime();
  if (Number.isNaN(time)) return value;
  const seconds = Math.round((time - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (Math.abs(seconds) < 60) return formatter.format(seconds, "second");
  const minutes = Math.round(seconds / 60);
  if (Math.abs(minutes) < 60) return formatter.format(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return formatter.format(hours, "hour");
  return formatter.format(Math.round(hours / 24), "day");
}

export function sentenceCase(value?: string | null): string {
  if (!value) return "Unknown";
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function normalizedPlan(run: Run): PlanStep[] {
  if (!Array.isArray(run.plan)) return [];
  return run.plan.map((step, index) =>
    typeof step === "string"
      ? { id: String(index), title: step }
      : { ...step, id: step.id ?? String(index) },
  );
}

export function stepTitle(step: PlanStep, index: number): string {
  return step.title ?? step.name ?? step.description ?? `Step ${index + 1}`;
}

export function isActiveStatus(status: string): boolean {
  return !["completed", "failed", "cancelled"].includes(status.toLowerCase());
}

export function isWaitingStatus(status: string): boolean {
  return ["waiting_approval", "awaiting_approval", "blocked"].includes(
    status.toLowerCase(),
  );
}

export function summaryText(summary: unknown): string {
  if (typeof summary === "string") return summary;
  if (summary === null || summary === undefined) return "";
  try {
    return JSON.stringify(summary, null, 2);
  } catch {
    return String(summary);
  }
}
