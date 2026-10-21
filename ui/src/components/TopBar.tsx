import { useState } from "react";
import {
  Avatar,
  Body1,
  Button,
  Caption1,
  makeStyles,
  shorthands,
  tokens,
  Tooltip,
} from "@fluentui/react-components";
import {
  Navigation24Regular,
  WeatherMoon24Regular,
  WeatherSunny24Regular,
} from "@fluentui/react-icons";

import type { HealthStatus } from "../types";
import { errorMessage } from "../api/client";
import { useAuth } from "./AuthGate";
import { StatusBadge } from "./StatusBadge";

const useStyles = makeStyles({
  root: {
    gridArea: "topbar",
    height: "64px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: tokens.spacingHorizontalM,
    paddingLeft: tokens.spacingHorizontalL,
    paddingRight: tokens.spacingHorizontalL,
    backgroundColor: tokens.colorNeutralBackground1,
    borderBottom: `1px solid ${tokens.colorNeutralStroke2}`,
    zIndex: 4,
  },
  brandGroup: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalM,
    minWidth: 0,
  },
  brandMark: {
    width: "34px",
    height: "34px",
    display: "grid",
    placeItems: "center",
    ...shorthands.borderRadius(tokens.borderRadiusMedium),
    backgroundColor: tokens.colorBrandBackground,
    color: tokens.colorNeutralForegroundOnBrand,
    fontWeight: tokens.fontWeightSemibold,
    letterSpacing: "-0.03em",
    boxShadow: tokens.shadow4,
  },
  brandText: {
    display: "flex",
    flexDirection: "column",
    minWidth: 0,
  },
  title: {
    color: tokens.colorNeutralForeground1,
    fontWeight: tokens.fontWeightSemibold,
    whiteSpace: "nowrap",
  },
  environment: {
    color: tokens.colorNeutralForeground3,
    whiteSpace: "nowrap",
  },
  actions: {
    display: "flex",
    alignItems: "center",
    gap: tokens.spacingHorizontalS,
  },
  menuButton: {
    display: "none",
    "@media (max-width: 900px)": {
      display: "inline-flex",
    },
  },
  hideSmall: {
    "@media (max-width: 560px)": {
      display: "none",
    },
  },
});

interface TopBarProps {
  darkMode: boolean;
  health: HealthStatus | null;
  healthLoading: boolean;
  onToggleTheme: () => void;
  onOpenNavigation: () => void;
}

export function TopBar({
  darkMode,
  health,
  healthLoading,
  onToggleTheme,
  onOpenNavigation,
}: TopBarProps) {
  const { enabled, role, logout } = useAuth();
  const [authError, setAuthError] = useState<string | null>(null);
  const styles = useStyles();
  const healthValue = healthLoading
    ? "checking"
    : health?.ok === false || health?.status === "error"
      ? "degraded"
      : health
        ? health.status || "healthy"
        : "unavailable";

  return (
    <header className={styles.root}>
      <div className={styles.brandGroup}>
        <Button
          className={styles.menuButton}
          appearance="subtle"
          icon={<Navigation24Regular />}
          aria-label="Open incident navigation"
          onClick={onOpenNavigation}
        />
        <div className={styles.brandMark} aria-hidden="true">
          SR
        </div>
        <div className={styles.brandText}>
          <Body1 as="span" className={styles.title}>
            SRE Copilot
          </Body1>
          <Caption1 as="span" className={styles.environment}>
            Operations control plane
          </Caption1>
        </div>
      </div>
      <div className={styles.actions}>
        <Caption1 role={authError ? "alert" : undefined}>
          {authError ?? (enabled ? role : "Local demo - authentication off")}
        </Caption1>
        {enabled && <Button appearance="subtle" onClick={() => {
          setAuthError(null);
          void logout().catch((reason) => setAuthError(errorMessage(reason)));
        }}>Sign out</Button>}
        <div className={styles.hideSmall}>
          <StatusBadge value={healthValue} />
        </div>
        <Tooltip
          content={darkMode ? "Use light theme" : "Use dark theme"}
          relationship="label"
        >
          <Button
            appearance="subtle"
            icon={
              darkMode ? <WeatherSunny24Regular /> : <WeatherMoon24Regular />
            }
            aria-label={darkMode ? "Use light theme" : "Use dark theme"}
            onClick={onToggleTheme}
          />
        </Tooltip>
        <Avatar
          name="SRE Operator"
          color="colorful"
          size={32}
          aria-label="SRE operator"
        />
      </div>
    </header>
  );
}
