import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("/react-router")) return "router-vendor";
          if (
            id.includes("/react/") ||
            id.includes("/react-dom/") ||
            id.includes("/scheduler/") ||
            id.includes("@griffel/") ||
            id.includes("@floating-ui/") ||
            id.includes("@fluentui/react-icons") ||
            id.includes("@fluentui/react-utilities") ||
            id.includes("@fluentui/react-shared-contexts") ||
            id.includes("@fluentui/react-theme") ||
            id.includes("@fluentui/react-jsx-runtime") ||
            id.includes("@fluentui/react-tabster") ||
            id.includes("@fluentui/react-portal") ||
            id.includes("@fluentui/react-motion") ||
            id.includes("@fluentui/react-positioning") ||
            id.includes("@fluentui/tokens")
          ) {
            return "ui-core";
          }
          if (id.includes("@fluentui/")) return "fluent-components";
          return undefined;
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
