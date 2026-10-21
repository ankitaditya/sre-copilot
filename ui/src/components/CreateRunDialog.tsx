import { useState } from "react";
import {
  Button,
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogSurface,
  DialogTitle,
  DialogTrigger,
  Dropdown,
  Field,
  Input,
  makeStyles,
  MessageBar,
  MessageBarBody,
  Option,
  Spinner,
  Textarea,
  tokens,
} from "@fluentui/react-components";

import { api, errorMessage } from "../api/client";
import type { CreateRunInput, Run } from "../types";

const useStyles = makeStyles({
  fields: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: tokens.spacingHorizontalM,
    "@media (max-width: 560px)": {
      gridTemplateColumns: "1fr",
    },
  },
  full: {
    gridColumn: "1 / -1",
  },
});

const INITIAL_FORM: CreateRunInput = {
  title: "",
  service: "",
  severity: "medium",
  description: "",
};

interface CreateRunDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (run: Run) => void;
}

export function CreateRunDialog({
  open,
  onOpenChange,
  onCreated,
}: CreateRunDialogProps) {
  const styles = useStyles();
  const [form, setForm] = useState<CreateRunInput>(INITIAL_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setField = (name: keyof CreateRunInput, value: string) => {
    setForm((current) => ({ ...current, [name]: value }));
  };

  const submit = async () => {
    if (!form.title.trim() || !form.service.trim() || !form.description.trim()) {
      setError("Title, service, and incident description are required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const run = await api.runs.create({
        ...form,
        title: form.title.trim(),
        service: form.service.trim(),
        description: form.description.trim(),
      });
      setForm(INITIAL_FORM);
      onCreated(run);
      onOpenChange(false);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(_, data) => {
        if (!submitting) onOpenChange(data.open);
      }}
    >
      <DialogSurface>
        <DialogBody>
          <DialogTitle>Create incident investigation</DialogTitle>
          <DialogContent>
            <p>
              Start a supervised SRE run. The copilot will build a plan and
              pause before actions that require operator approval.
            </p>
            <div className={styles.fields}>
              <Field label="Incident title" required>
                <Input
                  value={form.title}
                  onChange={(_, data) => setField("title", data.value)}
                  placeholder="Elevated checkout latency"
                  autoFocus
                />
              </Field>
              <Field label="Affected service" required>
                <Input
                  value={form.service}
                  onChange={(_, data) => setField("service", data.value)}
                  placeholder="checkout-api"
                />
              </Field>
              <Field label="Severity" required>
                <Dropdown
                  value={
                    form.severity.charAt(0).toUpperCase() + form.severity.slice(1)
                  }
                  selectedOptions={[form.severity]}
                  onOptionSelect={(_, data) =>
                    setField("severity", String(data.optionValue))
                  }
                >
                  <Option value="critical">Critical</Option>
                  <Option value="high">High</Option>
                  <Option value="medium">Medium</Option>
                  <Option value="low">Low</Option>
                </Dropdown>
              </Field>
              <Field
                className={styles.full}
                label="What is happening?"
                required
                hint="Include symptoms, timing, recent changes, and known constraints."
              >
                <Textarea
                  resize="vertical"
                  rows={6}
                  value={form.description}
                  onChange={(_, data) => setField("description", data.value)}
                  placeholder="Customer requests began returning 5xx responses after..."
                />
              </Field>
              {error && (
                <MessageBar className={styles.full} intent="error">
                  <MessageBarBody>{error}</MessageBarBody>
                </MessageBar>
              )}
            </div>
          </DialogContent>
          <DialogActions>
            <DialogTrigger disableButtonEnhancement>
              <Button appearance="secondary" disabled={submitting}>
                Cancel
              </Button>
            </DialogTrigger>
            <Button appearance="primary" disabled={submitting} onClick={submit}>
              {submitting ? <Spinner size="tiny" label="Creating" /> : "Create run"}
            </Button>
          </DialogActions>
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
}
