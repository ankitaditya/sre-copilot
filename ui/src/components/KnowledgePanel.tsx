import { useEffect, useState } from "react";
import {
  Body1, Button, Caption1, Field, Input, makeStyles, MessageBar, MessageBarBody,
  Subtitle2, tokens,
} from "@fluentui/react-components";

import { api, errorMessage } from "../api/client";
import type { KnowledgeResults, KnowledgeStatus } from "../types";
import { useAuth } from "./AuthGate";

const useStyles = makeStyles({
  root: {
    padding: tokens.spacingHorizontalL, borderRadius: tokens.borderRadiusLarge,
    backgroundColor: tokens.colorNeutralBackground1,
    display: "flex", flexDirection: "column", gap: tokens.spacingVerticalM,
  },
  controls: { display: "flex", gap: tokens.spacingHorizontalS, flexWrap: "wrap" },
  excerpt: { whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: "200px", overflowY: "auto" },
});

export function KnowledgePanel() {
  const styles = useStyles();
  const { canOperate } = useAuth();
  const [status, setStatus] = useState<KnowledgeStatus | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<KnowledgeResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void api.knowledge.status().then(setStatus).catch((reason) => setError(errorMessage(reason)));
  }, []);

  const perform = async (operation: "search" | "reindex") => {
    setBusy(true);
    setError(null);
    try {
      if (operation === "search") setResults(await api.knowledge.search(query));
      else {
        setStatus(await api.knowledge.reindex());
        setResults(null);
      }
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={styles.root} aria-label="Knowledge and incident memory">
      <Subtitle2>Knowledge and incident memory</Subtitle2>
      {status && <Caption1>
        {status.runbook_chunks} runbook chunks / {status.incident_chunks} incident chunks /
        {" "}{status.embedded_chunks} embedded chunks
      </Caption1>}
      <form onSubmit={(event) => { event.preventDefault(); void perform("search"); }}>
        <Field label="Search runbooks and resolved incidents">
          <Input value={query} onChange={(_, data) => setQuery(data.value)} maxLength={2000} />
        </Field>
        <div className={styles.controls}>
          <Button type="submit" disabled={busy || !query.trim()}>Search knowledge</Button>
          {canOperate && <Button type="button" disabled={busy} onClick={() => void perform("reindex")}>
            Refresh index
          </Button>}
        </div>
      </form>
      {error && <MessageBar intent="error"><MessageBarBody>{error}</MessageBarBody></MessageBar>}
      {(results?.warnings ?? status?.warnings ?? []).map((warning) => (
        <MessageBar key={warning} intent="warning"><MessageBarBody>{warning}</MessageBarBody></MessageBar>
      ))}
      {results && <Caption1>Retrieval mode: {results.mode}</Caption1>}
      {results?.matches.length === 0 && <Body1>No matching knowledge found.</Body1>}
      {results?.matches.map((match) => (
        <article key={match.id}>
          <Subtitle2>{match.title}</Subtitle2>
          <Caption1 block>{match.kind}: {match.source} / relevance {match.score}</Caption1>
          <Body1 as="p" className={styles.excerpt}>{match.excerpt}</Body1>
        </article>
      ))}
    </section>
  );
}
