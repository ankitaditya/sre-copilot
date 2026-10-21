import { useEffect, useMemo, useState } from "react";
import {
  Body1,
  Button,
  Caption1,
  makeStyles,
  MessageBar,
  MessageBarBody,
  ProgressBar,
  shorthands,
  Spinner,
  Subtitle2,
  Textarea,
  tokens,
} from "@fluentui/react-components";
import {
  Checkmark20Regular,
  Edit20Regular,
  Save20Regular,
} from "@fluentui/react-icons";

import { api, errorMessage } from "../api/client";
import { normalizedPlan, sentenceCase, stepTitle } from "../format";
import type { PlanStep, Run } from "../types";
import { StatusBadge } from "./StatusBadge";

const useStyles = makeStyles({
  panel: {
    padding: tokens.spacingHorizontalL,
    backgroundColor: tokens.colorNeutralBackground1,
    ...shorthands.border(`1px solid ${tokens.colorNeutralStroke2}`),
    ...shorthands.borderRadius(tokens.borderRadiusLarge),
    boxShadow: tokens.shadow2,
  },
  header: {
    minHeight: "32px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalM,
    marginBottom: tokens.spacingVerticalM,
  },
  headerText: {
    display: "flex",
    alignItems: "baseline",
    gap: tokens.spacingHorizontalS,
  },
  progress: {
    marginBottom: tokens.spacingVerticalL,
  },
  list: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalXS,
  },
  step: {
    display: "grid",
    gridTemplateColumns: "28px minmax(0, 1fr) auto",
    alignItems: "start",
    gap: tokens.spacingHorizontalS,
    padding: `${tokens.spacingVerticalS} 0`,
    borderBottom: `1px solid ${tokens.colorNeutralStroke3}`,
    ":last-child": {
      borderBottom: "none",
    },
  },
  stepIndex: {
    width: "24px",
    height: "24px",
    display: "grid",
    placeItems: "center",
    ...shorthands.borderRadius(tokens.borderRadiusCircular),
    backgroundColor: tokens.colorNeutralBackground3,
    color: tokens.colorNeutralForeground3,
  },
  currentIndex: {
    backgroundColor: tokens.colorBrandBackground,
    color: tokens.colorNeutralForegroundOnBrand,
  },
  completeIndex: {
    backgroundColor: tokens.colorPaletteGreenBackground2,
    color: tokens.colorPaletteGreenForeground1,
  },
  stepText: {
    minWidth: 0,
  },
  description: {
    color: tokens.colorNeutralForeground3,
    marginTop: tokens.spacingVerticalXXS,
  },
  editor: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
  },
  editorActions: {
    display: "flex",
    justifyContent: "flex-end",
    gap: tokens.spacingHorizontalS,
  },
  empty: {
    color: tokens.colorNeutralForeground3,
    paddingTop: tokens.spacingVerticalL,
    paddingBottom: tokens.spacingVerticalL,
    textAlign: "center",
  },
});

interface PlanPanelProps {
  run: Run;
  onUpdated: (run: Run) => void;
}

export function PlanPanel({ run, onUpdated }: PlanPanelProps) {
  const styles = useStyles();
  const steps = normalizedPlan(run);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!editing) setDraft(JSON.stringify(run.plan ?? [], null, 2));
  }, [editing, run.plan]);

  const currentIndex = useMemo(() => {
    if (typeof run.current_step === "number") {
      return Math.max(0, Math.min(steps.length - 1, run.current_step));
    }
    const byId = steps.findIndex(
      (step) =>
        step.id === run.current_step ||
        step.title === run.current_step ||
        step.name === run.current_step,
    );
    return byId >= 0 ? byId : 0;
  }, [run.current_step, steps]);

  const completedCount = steps.filter(
    (step, index) =>
      step.status?.toLowerCase() === "completed" ||
      step.status?.toLowerCase() === "done" ||
      index < currentIndex ||
      run.status.toLowerCase() === "completed",
  ).length;

  const save = async () => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(draft);
    } catch {
      setError("Plan must be valid JSON.");
      return;
    }
    if (
      !Array.isArray(parsed) ||
      !parsed.every(
        (step) =>
          typeof step === "string" ||
          (typeof step === "object" && step !== null),
      )
    ) {
      setError("Plan must be a JSON array of step strings or objects.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await api.runs.updatePlan(
        run.id,
        parsed as PlanStep[] | string[],
      );
      onUpdated(updated);
      setEditing(false);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className={styles.panel} aria-labelledby="plan-heading">
      <div className={styles.header}>
        <div className={styles.headerText}>
          <Subtitle2 as="h2" id="plan-heading">
            Response plan
          </Subtitle2>
          {!!steps.length && (
            <Caption1 as="span">
              {completedCount} of {steps.length} complete
            </Caption1>
          )}
        </div>
        <Button
          size="small"
          appearance="subtle"
          icon={<Edit20Regular />}
          disabled={saving}
          onClick={() => {
            setError(null);
            setEditing((value) => !value);
          }}
        >
          {editing ? "Close editor" : "Edit plan"}
        </Button>
      </div>

      {editing ? (
        <div className={styles.editor}>
          <Textarea
            aria-label="Plan JSON"
            resize="vertical"
            rows={12}
            value={draft}
            onChange={(_, data) => setDraft(data.value)}
          />
          {error && (
            <MessageBar intent="error">
              <MessageBarBody>{error}</MessageBarBody>
            </MessageBar>
          )}
          <div className={styles.editorActions}>
            <Button
              appearance="secondary"
              disabled={saving}
              onClick={() => {
                setDraft(JSON.stringify(run.plan ?? [], null, 2));
                setEditing(false);
              }}
            >
              Cancel
            </Button>
            <Button
              appearance="primary"
              icon={saving ? undefined : <Save20Regular />}
              disabled={saving}
              onClick={save}
            >
              {saving ? <Spinner size="tiny" label="Saving" /> : "Save plan"}
            </Button>
          </div>
        </div>
      ) : steps.length ? (
        <>
          <ProgressBar
            className={styles.progress}
            value={completedCount}
            max={steps.length}
            aria-label={`${completedCount} of ${steps.length} plan steps complete`}
          />
          <div className={styles.list}>
            {steps.map((step, index) => {
              const complete =
                step.status?.toLowerCase() === "completed" ||
                step.status?.toLowerCase() === "done" ||
                index < currentIndex ||
                run.status.toLowerCase() === "completed";
              const current =
                !complete &&
                index === currentIndex &&
                run.status.toLowerCase() !== "completed";
              return (
                <div className={styles.step} key={step.id ?? index}>
                  <span
                    className={`${styles.stepIndex} ${
                      complete
                        ? styles.completeIndex
                        : current
                          ? styles.currentIndex
                          : ""
                    }`}
                    aria-hidden="true"
                  >
                    {complete ? <Checkmark20Regular /> : index + 1}
                  </span>
                  <div className={styles.stepText}>
                    <Body1 as="span">{stepTitle(step, index)}</Body1>
                    {step.description &&
                      step.description !== stepTitle(step, index) && (
                        <Caption1 as="span" block className={styles.description}>
                          {step.description}
                        </Caption1>
                      )}
                  </div>
                  {step.status ? (
                    <StatusBadge value={step.status} />
                  ) : current ? (
                    <StatusBadge value="running" />
                  ) : (
                    <Caption1 as="span">
                      {complete ? "Done" : sentenceCase("pending")}
                    </Caption1>
                  )}
                </div>
              );
            })}
          </div>
        </>
      ) : (
        <Body1 as="p" className={styles.empty}>
          The response plan has not been generated yet.
        </Body1>
      )}
    </section>
  );
}
