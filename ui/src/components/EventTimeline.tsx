import { useEffect, useRef } from "react";
import {
  Body1,
  Caption1,
  makeStyles,
  shorthands,
  Subtitle2,
  tokens,
} from "@fluentui/react-components";
import {
  CheckmarkCircle20Regular,
  Circle20Regular,
  ErrorCircle20Regular,
  Wrench20Regular,
} from "@fluentui/react-icons";

import { formatDateTime, sentenceCase } from "../format";
import type { RunEvent, StreamState } from "../types";
import { StatusBadge } from "./StatusBadge";

const useStyles = makeStyles({
  panel: {
    minHeight: "360px",
    display: "flex",
    flexDirection: "column",
    padding: tokens.spacingHorizontalL,
    backgroundColor: tokens.colorNeutralBackground1,
    ...shorthands.border(`1px solid ${tokens.colorNeutralStroke2}`),
    ...shorthands.borderRadius(tokens.borderRadiusLarge),
    boxShadow: tokens.shadow2,
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalM,
    marginBottom: tokens.spacingVerticalM,
  },
  timeline: {
    minHeight: 0,
    maxHeight: "520px",
    overflowY: "auto",
    paddingRight: tokens.spacingHorizontalS,
  },
  event: {
    display: "grid",
    gridTemplateColumns: "28px minmax(0, 1fr)",
    gap: tokens.spacingHorizontalS,
    position: "relative",
    paddingBottom: tokens.spacingVerticalL,
    ":not(:last-child)::before": {
      content: '""',
      position: "absolute",
      top: "24px",
      bottom: 0,
      left: "9px",
      width: "1px",
      backgroundColor: tokens.colorNeutralStroke2,
    },
  },
  icon: {
    position: "relative",
    zIndex: 1,
    color: tokens.colorBrandForeground1,
    backgroundColor: tokens.colorNeutralBackground1,
  },
  eventHeader: {
    display: "flex",
    alignItems: "baseline",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalS,
  },
  eventType: {
    fontWeight: tokens.fontWeightSemibold,
  },
  time: {
    flexShrink: 0,
    color: tokens.colorNeutralForeground3,
  },
  payload: {
    marginTop: tokens.spacingVerticalXS,
    marginBottom: 0,
    padding: tokens.spacingHorizontalS,
    overflowX: "auto",
    color: tokens.colorNeutralForeground2,
    backgroundColor: tokens.colorNeutralBackground2,
    ...shorthands.borderRadius(tokens.borderRadiusSmall),
    fontSize: tokens.fontSizeBase200,
    whiteSpace: "pre-wrap",
    overflowWrap: "anywhere",
  },
  empty: {
    flex: 1,
    minHeight: "260px",
    display: "grid",
    placeItems: "center",
    color: tokens.colorNeutralForeground3,
    textAlign: "center",
  },
});

function payloadText(payload: unknown): string {
  if (typeof payload === "string") return payload;
  if (payload === null || payload === undefined) return "";
  if (typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    const primary = record.message ?? record.summary ?? record.description;
    if (typeof primary === "string" && Object.keys(record).length <= 2) {
      return primary;
    }
  }
  try {
    return JSON.stringify(payload, null, 2);
  } catch {
    return String(payload);
  }
}

function iconFor(type: string) {
  const normalized = type.toLowerCase();
  if (normalized.includes("error") || normalized.includes("fail")) {
    return <ErrorCircle20Regular />;
  }
  if (normalized.includes("complete") || normalized.includes("success")) {
    return <CheckmarkCircle20Regular />;
  }
  if (normalized.includes("tool") || normalized.includes("action")) {
    return <Wrench20Regular />;
  }
  return <Circle20Regular />;
}

export function EventTimeline({
  events,
  streamState,
}: {
  events: RunEvent[];
  streamState: StreamState;
}) {
  const styles = useStyles();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [events.length]);

  return (
    <section className={styles.panel} aria-labelledby="timeline-heading">
      <div className={styles.header}>
        <Subtitle2 as="h2" id="timeline-heading">
          Live activity
        </Subtitle2>
        <StatusBadge
          value={
            streamState === "live"
              ? "live"
              : streamState === "polling"
                ? "polling fallback"
                : streamState
          }
        />
      </div>
      {events.length ? (
        <div
          className={styles.timeline}
          role="log"
          aria-live="polite"
          aria-relevant="additions"
        >
          {events.map((event) => (
            <article className={styles.event} key={event.id}>
              <span className={styles.icon} aria-hidden="true">
                {iconFor(event.type)}
              </span>
              <div>
                <div className={styles.eventHeader}>
                  <Body1 as="span" className={styles.eventType}>
                    {sentenceCase(event.type)}
                  </Body1>
                  <time dateTime={event.created_at}>
                    <Caption1 as="span" className={styles.time}>
                      {formatDateTime(event.created_at)}
                    </Caption1>
                  </time>
                </div>
                {payloadText(event.payload) && (
                  <pre className={styles.payload}>
                    {payloadText(event.payload)}
                  </pre>
                )}
              </div>
            </article>
          ))}
          <div ref={endRef} />
        </div>
      ) : (
        <div className={styles.empty}>
          <div>
            <Body1 as="p">Waiting for run activity…</Body1>
            <Caption1 as="p">
              Events will appear here as the investigation progresses.
            </Caption1>
          </div>
        </div>
      )}
    </section>
  );
}
