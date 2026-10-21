import { Badge, type BadgeProps } from "@fluentui/react-components";

import { sentenceCase } from "../format";

function statusColor(value: string): BadgeProps["color"] {
  const status = value.toLowerCase();
  if (["failed", "critical", "cancelled", "error"].includes(status)) return "danger";
  if (
    ["paused", "high", "waiting_approval", "awaiting_approval", "blocked"].includes(
      status,
    )
  ) {
    return "warning";
  }
  if (["completed", "healthy", "ok", "low"].includes(status)) return "success";
  if (["running", "medium", "queued"].includes(status)) return "informative";
  return "subtle";
}

export function StatusBadge({
  value,
  appearance = "tint",
}: {
  value: string;
  appearance?: BadgeProps["appearance"];
}) {
  return (
    <Badge appearance={appearance} color={statusColor(value)} size="small">
      {sentenceCase(value)}
    </Badge>
  );
}
