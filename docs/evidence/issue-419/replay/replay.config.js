import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "/e2e/issue419-replay",
  testMatch: ["issue419-final-replay.spec.js"],
  outputDir: "/tmp/playwright-issue419-final-results",
  reporter: [["line"]],
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://web",
    browserName: "chromium",
    screenshot: "off",
    trace: "off",
  },
});
