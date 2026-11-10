import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Served by the web proxy under /app, next to the current console.
export default defineConfig({
  base: "/app/",
  // CONSOLE_SIMULATOR=1 bundles the scenario simulator (src/simulator) for e2e and demo builds.
  // Without it `__CONSOLE_SIMULATOR__` is the literal false and the simulator is left out.
  define: { __CONSOLE_SIMULATOR__: JSON.stringify(process.env.CONSOLE_SIMULATOR === "1") },
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": `${import.meta.dirname}/src` },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
  },
});
