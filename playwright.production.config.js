import { defineConfig } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL || "http://web";
const triageReview = process.env.T23_REVIEW === "1";
const triageTests = ["triage-origin.spec.js", "triage-persistence.spec.js", "triage-recovery.spec.js", "ca5-forbidden.spec.js", "session-isolation.spec.js", "triage-conflict-recovery.spec.js", "triage-context.spec.js", "triage-eligible.spec.js", "triage.spec.js"];
const existingTests = ["api-seam.spec.js", "production-proxy.spec.js", "principals.spec.js", "principals-create.spec.js", "principals-status.spec.js", "principals-credentials.spec.js", "model-aliases.spec.js", "grants-client-seam.spec.js", "consumption-client-seam.spec.js", "consumption-request-drilldown.spec.js", "grants.spec.js", "audit-events.spec.js", "triage.spec.js", "console-shell.spec.js", "console-incidents.spec.js", "war-room-runs-real.spec.js", "war-room-reasoning-real.spec.js", "review-mitigation-real.spec.js", "war-room-follow-real.spec.js", "service-operation-grant-real.spec.js"];

// The postmortem journey needs a resolved incident of the stack under test (docs/evidence/43).
const postmortemJourney = process.env.POSTMORTEM_INCIDENT ? ["postmortem-journey.spec.js"] : [];
// The output-language journey runs a paid investigation, so it runs only when asked (#717).
const languageJourney = process.env.EXPECTED_OUTPUT_LANGUAGE ? ["investigator-language-real.spec.js"] : [];
// A live investigation needs the OTel Demo failure and the paid model (issue #716).
const liveInvestigation = process.env.LIVE_INVESTIGATION === "1" ? ["war-room-logs-evidence-real.spec.js"] : [];
// A live alert's triage status needs the OTel Demo failure firing the alert rule (issue #701).
const liveAlertsTriage = process.env.LIVE_ALERTS_TRIAGE ? ["alerts-triage-status-real.spec.js"] : [];
// The deploy-executor journey needs the executor, the socket proxy and the probe (issue #720).
const executorJourney = process.env.DEPLOY_EXECUTOR_E2E === "1" ? ["deploy-executor-real.spec.js"] : [];

export default defineConfig({
  testDir: "tests/browser",
  testMatch: triageReview
    ? triageTests
    : [...existingTests, ...postmortemJourney, ...languageJourney, ...liveInvestigation, ...liveAlertsTriage, ...executorJourney],
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR || "test-results/production-browser",
  reporter: [["line"]],
  use: {
    baseURL,
    browserName: "chromium",
    screenshot: "off",
    trace: "off",
  },
});
