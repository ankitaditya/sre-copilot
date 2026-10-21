import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  FluentProvider,
  IdPrefixProvider,
} from "@fluentui/react-components";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import App from "./App";
import { AuthGate } from "./components/AuthGate";
import "./index.css";
import { darkTheme, lightTheme } from "./styles/theme";

function Root() {
  const [darkMode, setDarkMode] = useState(() => {
    const stored = window.localStorage.getItem("sre-copilot-theme");
    return stored
      ? stored === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  useEffect(() => {
    window.localStorage.setItem(
      "sre-copilot-theme",
      darkMode ? "dark" : "light",
    );
  }, [darkMode]);

  const app = (
    <App
      darkMode={darkMode}
      onToggleTheme={() => setDarkMode((value) => !value)}
    />
  );

  return (
    <IdPrefixProvider value="sre-copilot-">
      <FluentProvider theme={darkMode ? darkTheme : lightTheme}>
        <AuthGate>
          <BrowserRouter>
            <Routes>
              <Route path="/" element={app} />
              <Route path="/runs/:runId" element={app} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </AuthGate>
      </FluentProvider>
    </IdPrefixProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
