import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "/e2e/tests/browser",
  testMatch: ["review.spec.js"],
  outputDir: "/tmp/playwright-issue419-results",
  reporter: [["line"]],
  use: {
    baseURL: "http://127.0.0.1:4173",
    browserName: "chromium",
    screenshot: "off",
    trace: "off",
  },
  webServer: {
    command: "python3 -m http.server 4173 --bind 127.0.0.1",
    cwd: "/workspace",
    port: 4173,
    reuseExistingServer: false,
  },
});
