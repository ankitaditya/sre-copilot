import { useEffect, useState } from "react";
import {
  Body1,
  Button,
  Caption1,
  Field,
  Input,
  makeStyles,
  MessageBar,
  MessageBarBody,
  shorthands,
  Spinner,
  Subtitle2,
  Textarea,
  tokens,
} from "@fluentui/react-components";
import {
  Checkmark24Regular,
  Dismiss24Regular,
  ShieldLock24Regular,
} from "@fluentui/react-icons";

import { api, errorMessage } from "../api/client";
import { sentenceCase } from "../format";
import type { PendingAction, Run } from "../types";

const useStyles = makeStyles({
  card: {
    position: "sticky",
    top: tokens.spacingVerticalM,
    padding: tokens.spacingHorizontalL,
    backgroundColor: tokens.colorPaletteYellowBackground1,
    ...shorthands.border(`1px solid ${tokens.colorPaletteYellowBorder1}`),
    ...shorthands.borderRadius(tokens.borderRadiusLarge),
    boxShadow: tokens.shadow8,
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
    marginBottom: tokens.spacingVerticalXS,
    color: tokens.colorPaletteMarigoldForeground2,
  },
  description: {
    color: tokens.colorNeutralForeground2,
    marginBottom: tokens.spacingVerticalM,
  },
  actionName: {
    fontWeight: tokens.fontWeightSemibold,
    overflowWrap: "anywhere",
  },
  fields: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalM,
  },
  textarea: {
    fontFamily: '"Cascadia Code", Consolas, monospace',
  },
  actions: {
    display: "flex",
    gap: tokens.spacingHorizontalS,
    justifyContent: "flex-end",
    flexWrap: "wrap",
  },
});

interface ApprovalCardProps {
  runId: string;
  action: PendingAction;
  onUpdated: (run: Run) => void;
}

export function ApprovalCard({
  runId,
  action,
  onUpdated,
}: ApprovalCardProps) {
  const styles = useStyles();
  const [args, setArgs] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setArgs(JSON.stringify(action.args ?? {}, null, 2));
    setReason("");
    setError(null);
  }, [action.action_id, action.args]);

  const approve = async () => {
    let parsed: unknown;
    try {
      parsed = args.trim() ? JSON.parse(args) : undefined;
    } catch {
      setError("Action arguments must be valid JSON.");
      return;
    }
    setBusy("approve");
    setError(null);
    try {
      onUpdated(await api.runs.approve(runId, action.action_id, parsed));
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy(null);
    }
  };

  const reject = async () => {
    setBusy("reject");
    setError(null);
    try {
      onUpdated(
        await api.runs.reject(runId, action.action_id, reason.trim() || undefined),
      );
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setBusy(null);
    }
  };

  const name =
    action.name ?? action.action ?? action.tool ?? "Proposed operational action";

  return (
    <aside className={styles.card} aria-labelledby="approval-heading">
      <div className={styles.header}>
        <ShieldLock24Regular aria-hidden="true" />
        <Subtitle2 as="h2" id="approval-heading">
          Operator approval required
        </Subtitle2>
      </div>
      <Caption1 as="p" className={styles.description}>
        Review the exact action and arguments before authorizing execution.
      </Caption1>
      <div className={styles.fields}>
        <div>
          <Caption1 as="span" block>
            Proposed action
          </Caption1>
          <Body1 as="span" block className={styles.actionName}>
            {sentenceCase(name)}
          </Body1>
          {action.description && (
            <Caption1 as="p">{action.description}</Caption1>
          )}
        </div>
        <Field label="Editable JSON arguments">
          <Textarea
            className={styles.textarea}
            resize="vertical"
            rows={8}
            value={args}
            onChange={(_, data) => setArgs(data.value)}
            aria-label="Action arguments as JSON"
          />
        </Field>
        <Field label="Rejection reason (optional)">
          <Input
            value={reason}
            onChange={(_, data) => setReason(data.value)}
            placeholder="Explain why this action should not proceed"
          />
        </Field>
        {error && (
          <MessageBar intent="error">
            <MessageBarBody>{error}</MessageBarBody>
          </MessageBar>
        )}
        <div className={styles.actions}>
          <Button
            appearance="secondary"
            icon={busy === "reject" ? undefined : <Dismiss24Regular />}
            disabled={busy !== null}
            onClick={reject}
          >
            {busy === "reject" ? (
              <Spinner size="tiny" label="Rejecting" />
            ) : (
              "Reject"
            )}
          </Button>
          <Button
            appearance="primary"
            icon={busy === "approve" ? undefined : <Checkmark24Regular />}
            disabled={busy !== null}
            onClick={approve}
          >
            {busy === "approve" ? (
              <Spinner size="tiny" label="Approving" />
            ) : (
              "Approve action"
            )}
          </Button>
        </div>
      </div>
    </aside>
  );
}
