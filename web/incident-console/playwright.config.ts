import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  timeout: 240_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  outputDir: "e2e/artifacts/results",
  reporter: [["list"], ["html", { outputFolder: "e2e/artifacts/report", open: "never" }]],
  use: {
    // The console lives under /app of the web proxy; specs navigate relative to it.
    baseURL: `${process.env.BASE_URL ?? "http://127.0.0.1:8080"}/app/`,
    viewport: { width: 1440, height: 960 },
    locale: "es-CO",
    timezoneId: "America/Bogota",
    video: "on",
    trace: "retain-on-failure",
  },
});
