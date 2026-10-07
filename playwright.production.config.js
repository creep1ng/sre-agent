import { defineConfig } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL || "http://web";
const triageReview = process.env.T23_REVIEW === "1";
const triageTests = ["triage-origin.spec.js", "triage-persistence.spec.js", "triage-recovery.spec.js", "ca5-forbidden.spec.js", "session-isolation.spec.js", "triage-conflict-recovery.spec.js", "triage.spec.js"];
const existingTests = ["api-seam.spec.js", "production-proxy.spec.js", "principals.spec.js", "principals-create.spec.js", "principals-status.spec.js", "principals-credentials.spec.js", "model-aliases.spec.js", "grants-client-seam.spec.js", "consumption-client-seam.spec.js", "grants.spec.js", "triage.spec.js"];

export default defineConfig({
  testDir: "tests/browser",
  testMatch: triageReview ? triageTests : existingTests,
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR || "test-results/production-browser",
  reporter: [["line"]],
  use: {
    baseURL,
    browserName: "chromium",
    screenshot: "off",
    trace: "off",
  },
});
