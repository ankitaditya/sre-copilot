import {
  Body1,
  Caption1,
  makeStyles,
  shorthands,
  Skeleton,
  SkeletonItem,
  tokens,
} from "@fluentui/react-components";
import {
  CheckmarkCircle24Regular,
  Clock24Regular,
  ShieldError24Regular,
  Pulse24Regular,
  Wrench24Regular,
} from "@fluentui/react-icons";

import { isActiveStatus, isWaitingStatus } from "../format";
import type { Run } from "../types";

const useStyles = makeStyles({
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
    gap: tokens.spacingHorizontalM,
    "@media (max-width: 1100px)": {
      gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    },
    "@media (max-width: 560px)": {
      gridTemplateColumns: "1fr",
    },
  },
  card: {
    minHeight: "100px",
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalM,
    padding: tokens.spacingHorizontalL,
    ...shorthands.border(`1px solid ${tokens.colorNeutralStroke2}`),
    ...shorthands.borderRadius(tokens.borderRadiusLarge),
    backgroundColor: tokens.colorNeutralBackground1,
    boxShadow: tokens.shadow2,
  },
  icon: {
    width: "40px",
    height: "40px",
    flexShrink: 0,
    display: "grid",
    placeItems: "center",
    ...shorthands.borderRadius(tokens.borderRadiusMedium),
    backgroundColor: tokens.colorBrandBackground2,
    color: tokens.colorBrandForeground1,
  },
  dangerIcon: {
    backgroundColor: tokens.colorPaletteRedBackground1,
    color: tokens.colorPaletteRedForeground1,
  },
  warningIcon: {
    backgroundColor: tokens.colorPaletteYellowBackground1,
    color: tokens.colorPaletteMarigoldForeground2,
  },
  successIcon: {
    backgroundColor: tokens.colorPaletteGreenBackground1,
    color: tokens.colorPaletteGreenForeground1,
  },
  stack: {
    display: "flex",
    flexDirection: "column",
    minWidth: 0,
  },
  value: {
    fontSize: tokens.fontSizeHero700,
    lineHeight: tokens.lineHeightHero700,
    fontWeight: tokens.fontWeightSemibold,
    color: tokens.colorNeutralForeground1,
  },
  label: {
    color: tokens.colorNeutralForeground3,
  },
});

export function KpiCards({
  runs,
  loading,
  toolCount,
}: {
  runs: Run[];
  loading: boolean;
  toolCount: number | null;
}) {
  const styles = useStyles();
  const active = runs.filter((run) => isActiveStatus(run.status)).length;
  const critical = runs.filter(
    (run) =>
      run.severity.toLowerCase() === "critical" &&
      isActiveStatus(run.status),
  ).length;
  const waiting = runs.filter((run) => isWaitingStatus(run.status)).length;
  const resolved = runs.filter(
    (run) => run.status.toLowerCase() === "completed",
  ).length;

  const cards = [
    { label: "Active incidents", value: active, icon: <Pulse24Regular /> },
    {
      label: "Critical active",
      value: critical,
      icon: <ShieldError24Regular />,
      className: styles.dangerIcon,
    },
    {
      label: "Awaiting approval",
      value: waiting,
      icon: <Clock24Regular />,
      className: styles.warningIcon,
    },
    {
      label: "Operational tools",
      value: toolCount ?? "—",
      icon: <Wrench24Regular />,
      className: styles.successIcon,
    },
  ];

  return (
    <section className={styles.grid} aria-label="Operational overview">
      {cards.map((card) => (
        <div className={styles.card} key={card.label}>
          <div className={`${styles.icon} ${card.className ?? ""}`}>
            {card.icon}
          </div>
          <div className={styles.stack}>
            {loading ? (
              <Skeleton aria-label={`Loading ${card.label}`}>
                <SkeletonItem size={32} style={{ width: 54 }} />
              </Skeleton>
            ) : (
              <Body1 as="span" className={styles.value}>
                {card.value}
              </Body1>
            )}
            <Caption1 as="span" className={styles.label}>
              {card.label}
            </Caption1>
          </div>
        </div>
      ))}
    </section>
  );
}
