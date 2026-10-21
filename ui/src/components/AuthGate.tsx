import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import {
  Body1, Button, Field, Input, makeStyles, MessageBar, MessageBarBody,
  Spinner, Subtitle1, tokens,
} from "@fluentui/react-components";

import { api, errorMessage, setAuthSession } from "../api/client";
import type { AuthSession } from "../types";

const AuthContext = createContext({
  role: "viewer" as AuthSession["role"],
  enabled: false,
  canOperate: false,
  canApprove: false,
  logout: async () => {},
});

export const useAuth = () => useContext(AuthContext);

const useStyles = makeStyles({
  root: {
    minHeight: "100vh", display: "grid", placeItems: "center",
    backgroundColor: tokens.colorNeutralBackground3,
  },
  form: {
    width: "min(420px, 90vw)", display: "flex", flexDirection: "column",
    gap: tokens.spacingVerticalL, padding: tokens.spacingHorizontalXXL,
    backgroundColor: tokens.colorNeutralBackground1, borderRadius: tokens.borderRadiusLarge,
  },
});

export function AuthGate({ children }: { children: ReactNode }) {
  const styles = useStyles();
  const [session, setSession] = useState<AuthSession | null>(null);
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const accept = (value: AuthSession) => {
    setAuthSession(value);
    setSession(value);
  };

  const refresh = () => {
    setError(null);
    void api.auth.session().then(accept).catch((reason) => setError(errorMessage(reason)));
  };

  useEffect(() => {
    refresh();
    const expired = () => accept({ enabled: true, authenticated: false, role: null });
    window.addEventListener("sre-auth-required", expired);
    return () => window.removeEventListener("sre-auth-required", expired);
  }, []);

  if (!session?.authenticated) {
    return (
      <div className={styles.root}>
        <form className={styles.form} onSubmit={(event) => {
          event.preventDefault();
          setBusy(true);
          setError(null);
          void api.auth.login(token).then((value) => {
            setToken("");
            accept(value);
          }).catch((reason) => setError(errorMessage(reason))).finally(() => setBusy(false));
        }}>
          <Subtitle1>SRE Copilot</Subtitle1>
          {!session && !error ? <Spinner label="Checking access" /> : (
            <>
              <Body1>Use your configured access token to sign in. It is not saved in browser storage.</Body1>
              <Field label="Access token">
                <Input type="password" value={token} autoComplete="off"
                  onChange={(_, data) => setToken(data.value)} />
              </Field>
              <Button type="submit" appearance="primary" disabled={busy || !token}>
                {busy ? "Signing in..." : "Sign in"}
              </Button>
            </>
          )}
          {error && <MessageBar intent="error"><MessageBarBody>{error}</MessageBarBody></MessageBar>}
          {!session && error && <Button onClick={refresh}>Retry connection</Button>}
        </form>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{
      role: session.role, enabled: session.enabled,
      canOperate: session.role === "operator" || session.role === "approver",
      canApprove: session.role === "approver",
      logout: async () => {
        await api.auth.logout();
        accept({ enabled: true, authenticated: false, role: null });
      },
    }}>
      {children}
    </AuthContext.Provider>
  );
}
