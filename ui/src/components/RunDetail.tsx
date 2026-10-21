import { useCallback, useEffect, useState } from "react";
import {
  Body1,
  Button,
  Caption1,
  Divider,
  makeStyles,
  MessageBar,
  MessageBarActions,
  MessageBarBody,
  MessageBarTitle,
  shorthands,
  Spinner,
  Subtitle2,
  Textarea,
  Title2,
  tokens,
  Tooltip,
} from "@fluentui/react-components";
import {
  ArrowClockwise24Regular,
  Dismiss24Regular,
  Pause24Regular,
  Play24Regular,
  Send24Regular,
} from "@fluentui/react-icons";

import { api, errorMessage } from "../api/client";
import { formatDateTime, isActiveStatus, summaryText } from "../format";
import { useRunStream } from "../hooks/useRunStream";
import type { Run } from "../types";
import { ApprovalCard } from "./ApprovalCard";
import { useAuth } from "./AuthGate";
import { EventTimeline } from "./EventTimeline";
import { FindingsPanel } from "./FindingsPanel";
import { PlanPanel } from "./PlanPanel";
import { StatusBadge } from "./StatusBadge";

const useStyles = makeStyles({
  root: {
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalL,
  },
  header: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalL,
    "@media (max-width: 700px)": {
      flexDirection: "column",
    },
  },
  titleGroup: {
    minWidth: 0,
  },
  eyebrow: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    marginBottom: tokens.spacingVerticalXS,
    color: tokens.colorNeutralForeground3,
  },
  title: {
    margin: 0,
    overflowWrap: "anywhere",
  },
  description: {
    maxWidth: "800px",
    marginTop: tokens.spacingVerticalS,
    color: tokens.colorNeutralForeground2,
    whiteSpace: "pre-wrap",
  },
  controls: {
    display: "flex",
    alignItems: "center",
    justifyContent: "flex-end",
    gap: tokens.spacingHorizontalS,
    flexWrap: "wrap",
  },
  metadata: {
    display: "flex",
    alignItems: "stretch",
    flexWrap: "wrap",
    gap: tokens.spacingHorizontalM,
  },
  metaItem: {
    minWidth: "130px",
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXXS,
  },
  metaLabel: {
    color: tokens.colorNeutralForeground3,
  },
  mainGrid: {
    minWidth: 0,
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) minmax(300px, 380px)",
    alignItems: "start",
    gap: tokens.spacingHorizontalL,
    "@media (max-width: 1180px)": {
      gridTemplateColumns: "1fr",
    },
  },
  content: {
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalL,
  },
  side: {
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalL,
  },
  card: {
    padding: tokens.spacingHorizontalL,
    backgroundColor: tokens.colorNeutralBackground1,
    ...shorthands.border(`1px solid ${tokens.colorNeutralStroke2}`),
    ...shorthands.borderRadius(tokens.borderRadiusLarge),
    boxShadow: tokens.shadow2,
  },
  summaryText: {
    marginTop: tokens.spacingVerticalS,
    color: tokens.colorNeutralForeground2,
    whiteSpace: "pre-wrap",
    overflowWrap: "anywhere",
  },
  budget: {
    marginTop: tokens.spacingVerticalS,
    marginBottom: 0,
    padding: tokens.spacingHorizontalS,
    overflowX: "auto",
    backgroundColor: tokens.colorNeutralBackground2,
    ...shorthands.borderRadius(tokens.borderRadiusSmall),
    color: tokens.colorNeutralForeground2,
    fontSize: tokens.fontSizeBase200,
    whiteSpace: "pre-wrap",
  },
  guidance: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalS,
  },
  guidanceActions: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
  },
  guidanceHint: {
    color: tokens.colorNeutralForeground3,
  },
  state: {
    minHeight: "420px",
    display: "grid",
    placeItems: "center",
    textAlign: "center",
  },
});

interface RunDetailProps {
  runId: string;
  run: Run | null;
  loading: boolean;
  error: string | null;
  onRunUpdated: (run: Run) => void;
  onRefresh: () => void;
  onRefreshList: () => void;
}

export function RunDetail({
  runId,
  run,
  loading,
  error,
  onRunUpdated,
  onRefresh,
  onRefreshList,
}: RunDetailProps) {
  const { canOperate } = useAuth();
  const styles = useStyles();
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [guidance, setGuidance] = useState("");
  const [guidanceBusy, setGuidanceBusy] = useState(false);

  useEffect(() => {
    setActionError(null);
    setGuidance("");
  }, [runId]);

  const refreshAll = useCallback(() => {
    onRefreshList();
  }, [onRefreshList]);

  const { events, state: streamState } = useRunStream({
    runId,
    onRun: onRunUpdated,
    onRefresh: refreshAll,
  });

  const perform = async (
    action: "pause" | "resume" | "cancel",
    request: () => Promise<Run>,
  ) => {
    if (
      action === "cancel" &&
      !window.confirm("Cancel this incident run? This cannot be undone.")
    ) {
      return;
    }
    setActionBusy(action);
    setActionError(null);
    try {
      const updated = await request();
      onRunUpdated(updated);
      onRefreshList();
    } catch (requestError) {
      setActionError(errorMessage(requestError));
    } finally {
      setActionBusy(null);
    }
  };

  const sendGuidance = async () => {
    if (!guidance.trim()) return;
    setGuidanceBusy(true);
    setActionError(null);
    try {
      const updated = await api.runs.guide(runId, guidance.trim());
      setGuidance("");
      onRunUpdated(updated);
      onRefreshList();
    } catch (requestError) {
      setActionError(errorMessage(requestError));
    } finally {
      setGuidanceBusy(false);
    }
  };

  if (loading && !run) {
    return (
      <div className={styles.state}>
        <Spinner size="large" label="Loading incident run" />
      </div>
    );
  }

  if (error && !run) {
    return (
      <div className={styles.state}>
        <MessageBar intent="error">
          <MessageBarBody>
            <MessageBarTitle>Could not load this run</MessageBarTitle>
            {error}
          </MessageBarBody>
          <MessageBarActions
            containerAction={
              <Button
                appearance="transparent"
                icon={<ArrowClockwise24Regular />}
                onClick={onRefresh}
              >
                Retry
              </Button>
            }
          />
        </MessageBar>
      </div>
    );
  }

  if (!run) return null;

  const canPause = canOperate && ["running", "queued", "awaiting_approval"].includes(run.status.toLowerCase());
  const canResume = canOperate && ["paused", "needs_human"].includes(run.status.toLowerCase());
  const canCancel = canOperate && isActiveStatus(run.status);
  const budget =
    run.budget === null || run.budget === undefined
      ? ""
      : typeof run.budget === "string"
        ? run.budget
        : JSON.stringify(run.budget, null, 2);

  return (
    <article className={styles.root}>
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <div className={styles.eyebrow}>
            <StatusBadge value={run.severity} />
            <StatusBadge value={run.status} />
            <Caption1 as="span">Run {run.id}</Caption1>
          </div>
          <Title2 as="h1" className={styles.title}>
            {run.title}
          </Title2>
          {(run.description || summaryText(run.summary)) && (
            <Body1 as="p" className={styles.description}>
              {run.description || summaryText(run.summary)}
            </Body1>
          )}
        </div>
        <div className={styles.controls} aria-label="Run controls">
          <Tooltip content="Refresh run" relationship="label">
            <Button
              appearance="subtle"
              icon={<ArrowClockwise24Regular />}
              aria-label="Refresh run"
              disabled={loading}
              onClick={onRefresh}
            />
          </Tooltip>
          {canPause && (
            <Button
              appearance="secondary"
              icon={<Pause24Regular />}
              disabled={actionBusy !== null}
              onClick={() =>
                void perform("pause", () => api.runs.pause(run.id))
              }
            >
              Pause
            </Button>
          )}
          {canResume && (
            <Button
              appearance="primary"
              icon={<Play24Regular />}
              disabled={actionBusy !== null}
              onClick={() =>
                void perform("resume", () => api.runs.resume(run.id))
              }
            >
              Resume
            </Button>
          )}
          {canCancel && (
            <Button
              appearance="subtle"
              icon={<Dismiss24Regular />}
              disabled={actionBusy !== null}
              onClick={() =>
                void perform("cancel", () => api.runs.cancel(run.id))
              }
            >
              Cancel
            </Button>
          )}
        </div>
      </header>

      <div className={styles.metadata}>
        <div className={styles.metaItem}>
          <Caption1 as="span" className={styles.metaLabel}>
            Service
          </Caption1>
          <Body1 as="span">{run.service || "Unspecified"}</Body1>
        </div>
        <Divider vertical />
        <div className={styles.metaItem}>
          <Caption1 as="span" className={styles.metaLabel}>
            Created
          </Caption1>
          <Body1 as="span">{formatDateTime(run.created_at)}</Body1>
        </div>
        <Divider vertical />
        <div className={styles.metaItem}>
          <Caption1 as="span" className={styles.metaLabel}>
            Last update
          </Caption1>
          <Body1 as="span">{formatDateTime(run.updated_at)}</Body1>
        </div>
        <Divider vertical />
        <div className={styles.metaItem}>
          <Caption1 as="span" className={styles.metaLabel}>
            Current step
          </Caption1>
          <Body1 as="span">
            {run.current_step === null || run.current_step === undefined
              ? "—"
              : String(run.current_step)}
          </Body1>
        </div>
      </div>

      {actionError && (
        <MessageBar intent="error">
          <MessageBarBody>
            <MessageBarTitle>Run action failed</MessageBarTitle>
            {actionError}
          </MessageBarBody>
        </MessageBar>
      )}

      <div className={styles.mainGrid}>
        <div className={styles.content}>
          <PlanPanel
            run={run}
            onUpdated={(updated) => {
              onRunUpdated(updated);
              onRefreshList();
            }}
          />
          <EventTimeline events={events} streamState={streamState} />
          <FindingsPanel findings={run.findings} />
        </div>
        <div className={styles.side}>
          {run.pending_action && (
            <ApprovalCard
              runId={run.id}
              action={run.pending_action}
              onUpdated={(updated) => {
                onRunUpdated(updated);
                onRefreshList();
              }}
            />
          )}
          <section className={styles.card} aria-labelledby="guidance-heading">
            <div className={styles.guidance}>
              <Subtitle2 as="h2" id="guidance-heading">
                Operator guidance
              </Subtitle2>
              <Caption1 as="p" className={styles.guidanceHint}>
                Add context, constraints, or a change in investigative direction.
              </Caption1>
              <Textarea
                value={guidance}
                disabled={!canOperate || !isActiveStatus(run.status)}
                onChange={(_, data) => setGuidance(data.value)}
                rows={4}
                resize="vertical"
                placeholder="Check the deployment from 09:30 before scaling..."
                aria-label="Guidance for the SRE copilot"
              />
              <div className={styles.guidanceActions}>
                <Caption1 as="span">{guidance.length}/2000</Caption1>
                <Button
                  appearance="primary"
                  icon={guidanceBusy ? undefined : <Send24Regular />}
                  disabled={
                    guidanceBusy ||
                    !canOperate ||
                    !guidance.trim() ||
                    guidance.length > 2000 ||
                    !isActiveStatus(run.status)
                  }
                  onClick={sendGuidance}
                >
                  {guidanceBusy ? (
                    <Spinner size="tiny" label="Sending" />
                  ) : (
                    "Send guidance"
                  )}
                </Button>
              </div>
            </div>
          </section>
          {(summaryText(run.summary) || budget) && (
            <section className={styles.card} aria-labelledby="context-heading">
              <Subtitle2 as="h2" id="context-heading">
                Run context
              </Subtitle2>
              {summaryText(run.summary) && (
                <>
                  <Caption1 as="span" block>
                    Summary
                  </Caption1>
                  <Body1 as="span" block className={styles.summaryText}>
                    {summaryText(run.summary)}
                  </Body1>
                </>
              )}
              {budget && (
                <>
                  <Caption1 as="span" block>
                    Budget
                  </Caption1>
                  <pre className={styles.budget}>{budget}</pre>
                </>
              )}
            </section>
          )}
        </div>
      </div>
    </article>
  );
}
