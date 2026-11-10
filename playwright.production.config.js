import { defineConfig } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL || "http://web";
const existingTests = ["api-seam.spec.js", "production-proxy.spec.js", "grants-client-seam.spec.js", "consumption-client-seam.spec.js", "console-shell.spec.js", "console-incidents.spec.js", "war-room-runs-real.spec.js", "war-room-reasoning-real.spec.js", "review-mitigation-real.spec.js", "war-room-follow-real.spec.js", "change-events-real.spec.js", "incident-list-real.spec.js", "service-operation-grant-real.spec.js"];

// The postmortem journey needs a resolved incident of the stack under test (see https://github.com/creep1ng/sre-agent/tree/0cb2ad441e4f9923f3ff6d804dc59a6cfc51aa63/docs/evidence/43).
const postmortemJourney = process.env.POSTMORTEM_INCIDENT ? ["postmortem-journey.spec.js"] : [];
// The output-language journey runs a paid investigation, so it runs only when asked (#717).
const languageJourney = process.env.EXPECTED_OUTPUT_LANGUAGE ? ["investigator-language-real.spec.js"] : [];
// A live investigation needs the OTel Demo failure and the paid model (issue #716).
const liveInvestigation = process.env.LIVE_INVESTIGATION === "1" ? ["war-room-logs-evidence-real.spec.js"] : [];
// A live alert's triage status needs the OTel Demo failure firing the alert rule (issue #701).
const liveAlertsTriage = process.env.LIVE_ALERTS_TRIAGE ? ["alerts-triage-status-real.spec.js"] : [];
// The deploy-executor journey needs the executor, the socket proxy and the probe (issue #720).
const executorJourney = process.env.DEPLOY_EXECUTOR_E2E === "1" ? ["deploy-executor-real.spec.js"] : [];
// The second-service journey needs the local demo's sre-checkout and the executor (issue #721).
const checkoutJourney = process.env.CHECKOUT_ALERT_E2E === "1" ? ["checkout-alert-real.spec.js"] : [];

export default defineConfig({
  testDir: "tests/browser",
  testMatch: [...existingTests, ...postmortemJourney, ...languageJourney, ...liveInvestigation, ...liveAlertsTriage, ...executorJourney, ...checkoutJourney],
  outputDir: process.env.PLAYWRIGHT_OUTPUT_DIR || "test-results/production-browser",
  reporter: [["line"]],
  use: {
    baseURL,
    browserName: "chromium",
    screenshot: "off",
    trace: "off",
  },
});
