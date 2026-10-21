import { useState } from "react";
import {
  Body1,
  Button,
  Caption1,
  Input,
  makeStyles,
  mergeClasses,
  shorthands,
  Spinner,
  tokens,
  Tooltip,
} from "@fluentui/react-components";
import {
  Add24Regular,
  Dismiss24Regular,
  Search20Regular,
} from "@fluentui/react-icons";

import { relativeTime } from "../format";
import type { Run } from "../types";
import { StatusBadge } from "./StatusBadge";

const useStyles = makeStyles({
  root: {
    gridArea: "sidebar",
    minWidth: 0,
    minHeight: 0,
    display: "flex",
    flexDirection: "column",
    backgroundColor: tokens.colorNeutralBackground2,
    borderRight: `1px solid ${tokens.colorNeutralStroke2}`,
    "@media (max-width: 900px)": {
      position: "fixed",
      top: "64px",
      bottom: 0,
      left: 0,
      width: "min(360px, calc(100vw - 32px))",
      zIndex: 20,
      boxShadow: tokens.shadow64,
      transform: "translateX(-105%)",
      transitionProperty: "transform",
      transitionDuration: tokens.durationNormal,
      transitionTimingFunction: tokens.curveEasyEase,
    },
  },
  mobileOpen: {
    "@media (max-width: 900px)": {
      transform: "translateX(0)",
    },
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalS,
    padding: tokens.spacingHorizontalL,
    borderBottom: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  heading: {
    fontWeight: tokens.fontWeightSemibold,
  },
  closeButton: {
    display: "none",
    "@media (max-width: 900px)": {
      display: "inline-flex",
    },
  },
  filters: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalS,
    padding: `${tokens.spacingVerticalM} ${tokens.spacingHorizontalM}`,
  },
  filterRow: {
    display: "flex",
    gap: tokens.spacingHorizontalXS,
    flexWrap: "wrap",
  },
  filterButton: {
    minWidth: "auto",
  },
  list: {
    flex: 1,
    minHeight: 0,
    overflowY: "auto",
    padding: `0 ${tokens.spacingHorizontalS} ${tokens.spacingVerticalM}`,
  },
  runButton: {
    width: "100%",
    display: "flex",
    alignItems: "stretch",
    gap: tokens.spacingHorizontalS,
    padding: `${tokens.spacingVerticalM} ${tokens.spacingHorizontalM}`,
    marginBottom: tokens.spacingVerticalXS,
    textAlign: "left",
    cursor: "pointer",
    color: tokens.colorNeutralForeground1,
    backgroundColor: "transparent",
    ...shorthands.border("1px", "solid", "transparent"),
    ...shorthands.borderRadius(tokens.borderRadiusMedium),
    ":hover": {
      backgroundColor: tokens.colorNeutralBackground1Hover,
    },
    ":focus-visible": {
      outline: `2px solid ${tokens.colorStrokeFocus2}`,
      outlineOffset: "-2px",
    },
  },
  selected: {
    backgroundColor: tokens.colorBrandBackground2,
    ...shorthands.border("1px", "solid", tokens.colorBrandStroke2),
    ":hover": {
      backgroundColor: tokens.colorBrandBackground2Hover,
    },
  },
  severityRail: {
    width: "3px",
    flexShrink: 0,
    ...shorthands.borderRadius(tokens.borderRadiusCircular),
    backgroundColor: tokens.colorNeutralStroke1,
  },
  critical: { backgroundColor: tokens.colorPaletteRedBorder2 },
  high: { backgroundColor: tokens.colorPaletteDarkOrangeBorder2 },
  medium: { backgroundColor: tokens.colorPaletteYellowBorder2 },
  low: { backgroundColor: tokens.colorPaletteGreenBorder2 },
  runContent: {
    minWidth: 0,
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXS,
  },
  runTitle: {
    fontWeight: tokens.fontWeightSemibold,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  meta: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalXS,
    color: tokens.colorNeutralForeground3,
  },
  service: {
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  center: {
    minHeight: "180px",
    display: "grid",
    placeItems: "center",
    padding: tokens.spacingHorizontalL,
    textAlign: "center",
    color: tokens.colorNeutralForeground3,
  },
});

type Filter = "all" | "active" | "attention";

interface RunSidebarProps {
  runs: Run[];
  selectedId?: string;
  loading: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  onSelect: (id: string) => void;
  onCreate: () => void;
}

export function RunSidebar({
  runs,
  selectedId,
  loading,
  mobileOpen,
  onCloseMobile,
  onSelect,
  onCreate,
}: RunSidebarProps) {
  const styles = useStyles();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const visibleRuns = runs.filter((run) => {
    const searchMatch = `${run.title} ${run.service} ${run.id}`
      .toLowerCase()
      .includes(query.toLowerCase());
    if (!searchMatch) return false;
    if (filter === "active") {
      return ["running", "queued", "paused"].includes(run.status.toLowerCase());
    }
    if (filter === "attention") {
      return (
        ["critical", "high"].includes(run.severity.toLowerCase()) ||
        run.status.toLowerCase().includes("approval") ||
        run.status.toLowerCase() === "failed"
      );
    }
    return true;
  });

  return (
    <aside
      className={mergeClasses(styles.root, mobileOpen && styles.mobileOpen)}
      aria-label="Incident runs"
    >
      <div className={styles.header}>
        <Body1 as="span" className={styles.heading}>
          Incident runs
        </Body1>
        <div>
          <Tooltip content="Create incident" relationship="label">
            <Button
              appearance="primary"
              icon={<Add24Regular />}
              aria-label="Create incident"
              onClick={onCreate}
            />
          </Tooltip>
          <Button
            className={styles.closeButton}
            appearance="subtle"
            icon={<Dismiss24Regular />}
            aria-label="Close incident navigation"
            onClick={onCloseMobile}
          />
        </div>
      </div>
      <div className={styles.filters}>
        <Input
          value={query}
          onChange={(_, data) => setQuery(data.value)}
          contentBefore={<Search20Regular />}
          placeholder="Search runs or services"
          aria-label="Search incident runs"
        />
        <div className={styles.filterRow} aria-label="Run filters">
          {(["all", "active", "attention"] as Filter[]).map((value) => (
            <Button
              key={value}
              className={styles.filterButton}
              size="small"
              appearance={filter === value ? "primary" : "subtle"}
              onClick={() => setFilter(value)}
              aria-pressed={filter === value}
            >
              {value === "all"
                ? "All"
                : value === "active"
                  ? "Active"
                  : "Needs attention"}
            </Button>
          ))}
        </div>
      </div>
      <div className={styles.list}>
        {loading ? (
          <div className={styles.center}>
            <Spinner label="Loading incident runs" />
          </div>
        ) : visibleRuns.length === 0 ? (
          <div className={styles.center}>
            <Caption1 as="p">
              {runs.length
                ? "No runs match the current filters."
                : "No incident runs yet. Create one to begin an investigation."}
            </Caption1>
          </div>
        ) : (
          visibleRuns.map((run) => (
            <button
              type="button"
              key={run.id}
              className={mergeClasses(
                styles.runButton,
                selectedId === run.id && styles.selected,
              )}
              aria-current={selectedId === run.id ? "page" : undefined}
              onClick={() => {
                onSelect(run.id);
                onCloseMobile();
              }}
            >
              <span
                className={mergeClasses(
                  styles.severityRail,
                  styles[
                    run.severity.toLowerCase() as
                      | "critical"
                      | "high"
                      | "medium"
                      | "low"
                  ],
                )}
                aria-hidden="true"
              />
              <span className={styles.runContent}>
                <Body1 as="span" className={styles.runTitle}>
                  {run.title}
                </Body1>
                <span className={styles.meta}>
                  <Caption1 as="span" className={styles.service}>
                    {run.service || "Unspecified service"}
                  </Caption1>
                  <Caption1 as="span">{relativeTime(run.updated_at)}</Caption1>
                </span>
                <span>
                  <StatusBadge value={run.status} />
                </span>
              </span>
            </button>
          ))
        )}
      </div>
    </aside>
  );
}
