import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Body1,
  Button,
  makeStyles,
  MessageBar,
  MessageBarActions,
  MessageBarBody,
  MessageBarTitle,
  shorthands,
  Subtitle1,
  tokens,
} from "@fluentui/react-components";
import {
  Add24Regular,
  ArrowClockwise24Regular,
  ClipboardTaskListLtr24Regular,
} from "@fluentui/react-icons";
import { useNavigate, useParams } from "react-router-dom";

import { api, errorMessage } from "./api/client";
import { CreateRunDialog } from "./components/CreateRunDialog";
import { useAuth } from "./components/AuthGate";
import { KnowledgePanel } from "./components/KnowledgePanel";
import { KpiCards } from "./components/KpiCards";
import { RunDetail } from "./components/RunDetail";
import { RunSidebar } from "./components/RunSidebar";
import { TopBar } from "./components/TopBar";
import type { HealthStatus, Run } from "./types";

const useStyles = makeStyles({
  shell: {
    width: "100%",
    height: "100%",
    display: "grid",
    gridTemplateColumns: "320px minmax(0, 1fr)",
    gridTemplateRows: "64px minmax(0, 1fr)",
    gridTemplateAreas: `
      "topbar topbar"
      "sidebar main"
    `,
    backgroundColor: tokens.colorNeutralBackground3,
    color: tokens.colorNeutralForeground1,
    "@media (max-width: 900px)": {
      gridTemplateColumns: "1fr",
      gridTemplateAreas: `
        "topbar"
        "main"
      `,
    },
  },
  main: {
    gridArea: "main",
    minWidth: 0,
    minHeight: 0,
    overflowY: "auto",
  },
  inner: {
    width: "100%",
    maxWidth: "1600px",
    minHeight: "100%",
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXL,
    marginLeft: "auto",
    marginRight: "auto",
    padding: `${tokens.spacingVerticalXL} ${tokens.spacingHorizontalXXL}`,
    "@media (max-width: 700px)": {
      padding: tokens.spacingHorizontalL,
    },
  },
  pageHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalL,
    flexWrap: "wrap",
  },
  pageTitle: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXXS,
  },
  subtitle: {
    color: tokens.colorNeutralForeground3,
  },
  empty: {
    flex: 1,
    minHeight: "420px",
    display: "grid",
    placeItems: "center",
    textAlign: "center",
    padding: tokens.spacingHorizontalXXL,
    backgroundColor: tokens.colorNeutralBackground1,
    ...shorthands.border(`1px solid ${tokens.colorNeutralStroke2}`),
    ...shorthands.borderRadius(tokens.borderRadiusLarge),
    boxShadow: tokens.shadow2,
  },
  emptyInner: {
    maxWidth: "440px",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: tokens.spacingVerticalM,
  },
  emptyIcon: {
    width: "64px",
    height: "64px",
    display: "grid",
    placeItems: "center",
    ...shorthands.borderRadius(tokens.borderRadiusCircular),
    backgroundColor: tokens.colorBrandBackground2,
    color: tokens.colorBrandForeground1,
  },
  backdrop: {
    display: "none",
    "@media (max-width: 900px)": {
      position: "fixed",
      inset: "64px 0 0",
      zIndex: 19,
      display: "block",
      backgroundColor: "rgba(0, 0, 0, 0.38)",
    },
  },
});

export interface AppProps {
  darkMode: boolean;
  onToggleTheme: () => void;
}

export default function App({ darkMode, onToggleTheme }: AppProps) {
  const { canOperate } = useAuth();
  const styles = useStyles();
  const navigate = useNavigate();
  const { runId } = useParams<{ runId: string }>();
  const [runs, setRuns] = useState<Run[]>([]);
  const [runsLoading, setRunsLoading] = useState(true);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [toolCount, setToolCount] = useState<number | null>(null);

  const refreshRuns = useCallback(async () => {
    setRunsError(null);
    try {
      const list = await api.runs.list();
      setRuns(list);
      if (!runId && list.length > 0) {
        navigate(`/runs/${encodeURIComponent(list[0].id)}`, { replace: true });
      }
    } catch (error) {
      setRunsError(errorMessage(error));
    } finally {
      setRunsLoading(false);
    }
  }, [navigate, runId]);

  const refreshSelected = useCallback(async () => {
    if (!runId) {
      setSelectedRun(null);
      return;
    }
    setDetailLoading(true);
    setDetailError(null);
    try {
      setSelectedRun(await api.runs.get(runId));
    } catch (error) {
      setDetailError(errorMessage(error));
    } finally {
      setDetailLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    void refreshRuns();
  }, [refreshRuns]);

  useEffect(() => {
    void refreshSelected();
  }, [refreshSelected]);

  useEffect(() => {
    let active = true;
    void Promise.allSettled([api.health.get(), api.tools.list()]).then(
      ([healthResult, toolsResult]) => {
        if (!active) return;
        if (healthResult.status === "fulfilled") setHealth(healthResult.value);
        if (toolsResult.status === "fulfilled") {
          const value = toolsResult.value;
          const count = Array.isArray(value)
            ? value.length
            : typeof value === "object" && value
              ? Array.isArray((value as { tools?: unknown[] }).tools)
                ? (value as { tools: unknown[] }).tools.length
                : Object.keys(value).length
              : 0;
          setToolCount(count);
        }
        setHealthLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, []);

  const updateRun = useCallback((updated: Run) => {
    setSelectedRun(updated);
    setRuns((current) => {
      const exists = current.some((run) => run.id === updated.id);
      const next = exists
        ? current.map((run) => (run.id === updated.id ? updated : run))
        : [updated, ...current];
      return next.sort(
        (left, right) =>
          new Date(right.updated_at).getTime() -
          new Date(left.updated_at).getTime(),
      );
    });
  }, []);

  const selectedId = useMemo(() => runId, [runId]);

  return (
    <div className={styles.shell}>
      <TopBar
        darkMode={darkMode}
        health={health}
        healthLoading={healthLoading}
        onToggleTheme={onToggleTheme}
        onOpenNavigation={() => setNavigationOpen(true)}
      />
      <RunSidebar
        runs={runs}
        selectedId={selectedId}
        loading={runsLoading}
        mobileOpen={navigationOpen}
        onCloseMobile={() => setNavigationOpen(false)}
        onCreate={() => setCreateOpen(true)}
        onSelect={(id) => navigate(`/runs/${encodeURIComponent(id)}`)}
      />
      {navigationOpen && (
        <button
          className={styles.backdrop}
          aria-label="Close incident navigation"
          onClick={() => setNavigationOpen(false)}
        />
      )}
      <main className={styles.main}>
        <div className={styles.inner}>
          <div className={styles.pageHeader}>
            <div className={styles.pageTitle}>
              <Subtitle1 as="h2">Operations overview</Subtitle1>
              <Body1 as="p" className={styles.subtitle}>
                Supervise investigations, approve changes, and direct active
                incident response.
              </Body1>
            </div>
            <Button
              appearance="primary"
              disabled={!canOperate}
              icon={<Add24Regular />}
              onClick={() => setCreateOpen(true)}
            >
              New incident
            </Button>
          </div>

          <KpiCards
            runs={runs}
            loading={runsLoading}
            toolCount={toolCount}
          />
          <KnowledgePanel />

          {runsError && (
            <MessageBar intent="error">
              <MessageBarBody>
                <MessageBarTitle>Could not load incident runs</MessageBarTitle>
                {runsError}
              </MessageBarBody>
              <MessageBarActions
                containerAction={
                  <Button
                    appearance="transparent"
                    icon={<ArrowClockwise24Regular />}
                    onClick={() => void refreshRuns()}
                  >
                    Retry
                  </Button>
                }
              />
            </MessageBar>
          )}

          {runId ? (
            <RunDetail
              runId={runId}
              run={selectedRun?.id === runId ? selectedRun : null}
              loading={detailLoading}
              error={detailError}
              onRunUpdated={updateRun}
              onRefresh={() => void refreshSelected()}
              onRefreshList={() => void refreshRuns()}
            />
          ) : (
            !runsLoading && (
              <section className={styles.empty}>
                <div className={styles.emptyInner}>
                  <div className={styles.emptyIcon} aria-hidden="true">
                    <ClipboardTaskListLtr24Regular />
                  </div>
                  <Subtitle1 as="h1">
                    {runs.length
                      ? "Select an incident run"
                      : "No incident runs yet"}
                  </Subtitle1>
                  <Body1 as="p" className={styles.subtitle}>
                    {runs.length
                      ? "Choose a run from the navigation to inspect its live activity and response plan."
                      : "Create an incident to start a supervised investigation with SRE Copilot."}
                  </Body1>
                  <Button
                    appearance="primary"
                    disabled={!canOperate}
                    icon={<Add24Regular />}
                    onClick={() => setCreateOpen(true)}
                  >
                    Create incident
                  </Button>
                </div>
              </section>
            )
          )}
        </div>
      </main>
      <CreateRunDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={(run) => {
          updateRun(run);
          navigate(`/runs/${encodeURIComponent(run.id)}`);
        }}
      />
    </div>
  );
}
