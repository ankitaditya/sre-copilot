import {
  Body1,
  Caption1,
  makeStyles,
  shorthands,
  Subtitle2,
  tokens,
} from "@fluentui/react-components";
import {
  Info20Regular,
  Warning20Regular,
} from "@fluentui/react-icons";

import type { Run } from "../types";

const useStyles = makeStyles({
  panel: {
    padding: tokens.spacingHorizontalL,
    backgroundColor: tokens.colorNeutralBackground1,
    ...shorthands.border(`1px solid ${tokens.colorNeutralStroke2}`),
    ...shorthands.borderRadius(tokens.borderRadiusLarge),
    boxShadow: tokens.shadow2,
  },
  heading: {
    marginBottom: tokens.spacingVerticalM,
  },
  list: {
    display: "flex",
    flexDirection: "column",
    gap: tokens.spacingVerticalS,
  },
  finding: {
    display: "grid",
    gridTemplateColumns: "24px minmax(0, 1fr)",
    gap: tokens.spacingHorizontalS,
    padding: tokens.spacingHorizontalM,
    backgroundColor: tokens.colorNeutralBackground2,
    ...shorthands.borderRadius(tokens.borderRadiusMedium),
    borderLeft: `3px solid ${tokens.colorBrandStroke1}`,
  },
  icon: {
    color: tokens.colorBrandForeground1,
    paddingTop: "2px",
  },
  warning: {
    color: tokens.colorPaletteDarkOrangeForeground1,
  },
  content: {
    minWidth: 0,
    overflowWrap: "anywhere",
  },
  title: {
    fontWeight: tokens.fontWeightSemibold,
  },
  detail: {
    color: tokens.colorNeutralForeground3,
    marginTop: tokens.spacingVerticalXXS,
    whiteSpace: "pre-wrap",
  },
  evidence: {
    marginTop: tokens.spacingVerticalS,
    padding: tokens.spacingHorizontalS,
    overflowX: "auto",
    backgroundColor: tokens.colorNeutralBackground1,
    color: tokens.colorNeutralForeground2,
    ...shorthands.borderRadius(tokens.borderRadiusSmall),
    fontSize: tokens.fontSizeBase200,
    whiteSpace: "pre-wrap",
  },
  empty: {
    color: tokens.colorNeutralForeground3,
    textAlign: "center",
    paddingTop: tokens.spacingVerticalL,
    paddingBottom: tokens.spacingVerticalL,
  },
});

function entries(findings: Run["findings"]): unknown[] {
  if (Array.isArray(findings)) return findings;
  if (findings && typeof findings === "object") {
    return Object.entries(findings).map(([key, value]) => ({
      title: key,
      value,
    }));
  }
  return [];
}

function renderFinding(item: unknown, index: number) {
  if (typeof item === "string") {
    return { title: `Finding ${index + 1}`, detail: item, evidence: "" };
  }
  if (typeof item !== "object" || item === null) {
    return {
      title: `Finding ${index + 1}`,
      detail: String(item),
      evidence: "",
    };
  }
  const record = item as Record<string, unknown>;
  const title = String(
    record.title ?? record.name ?? record.kind ?? `Finding ${index + 1}`,
  );
  const detailValue =
    record.description ?? record.detail ?? record.message ?? record.value ?? "";
  const evidenceValue =
    record.evidence ?? record.data ?? record.source ?? record.observation;
  return {
    title,
    detail:
      typeof detailValue === "string"
        ? detailValue
        : JSON.stringify(detailValue, null, 2),
    evidence:
      evidenceValue === undefined
        ? ""
        : typeof evidenceValue === "string"
          ? evidenceValue
          : JSON.stringify(evidenceValue, null, 2),
    warning: ["warning", "critical", "error"].includes(
      String(record.severity ?? record.level ?? "").toLowerCase(),
    ),
  };
}

export function FindingsPanel({ findings }: { findings: Run["findings"] }) {
  const styles = useStyles();
  const items = entries(findings);

  return (
    <section className={styles.panel} aria-labelledby="findings-heading">
      <Subtitle2 as="h2" className={styles.heading} id="findings-heading">
        Findings & evidence
      </Subtitle2>
      {items.length ? (
        <div className={styles.list}>
          {items.map((item, index) => {
            const finding = renderFinding(item, index);
            return (
              <article className={styles.finding} key={index}>
                <span
                  className={`${styles.icon} ${finding.warning ? styles.warning : ""}`}
                  aria-hidden="true"
                >
                  {finding.warning ? <Warning20Regular /> : <Info20Regular />}
                </span>
                <div className={styles.content}>
                  <Body1 as="span" block className={styles.title}>
                    {finding.title}
                  </Body1>
                  {finding.detail && (
                    <Caption1 as="span" block className={styles.detail}>
                      {finding.detail}
                    </Caption1>
                  )}
                  {finding.evidence && (
                    <pre className={styles.evidence}>{finding.evidence}</pre>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <Body1 as="p" className={styles.empty}>
          No findings have been recorded for this run.
        </Body1>
      )}
    </section>
  );
}
