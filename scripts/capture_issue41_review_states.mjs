// Fixture evidence (#41 T2, CA3/CA4): a MOCKED backend replays the published
// workflow transitions while the console Decisiones view is captured, one PNG
// per state plus the conflict recovery pair. Fixtures, not live transport:
// run-command:2.1.0 is not published yet, so a PNG documents UI behavior only.
// Reproduction: PLAYWRIGHT_BASE_URL=... node scripts/capture_issue41_review_states.mjs
// (host with the local node_modules symlink, or inside the e2e container — PR).
import { chromium } from "@playwright/test";
import { connectConsole } from "../tests/browser/support/console-session.mjs";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:4173";
const INCIDENT = "inc-demo";
const RUN = "run_demo0001";

function story(currentState, version) {
  return {
    incident_id: INCIDENT,
    workflow_version: "1.0.0",
    state: currentState,
    severity: "sev2",
    impact: "Checkout failing at payment.",
    alert: {
      alert_id: "alt-payment-error-rate",
      service: "paymentservice",
      severity: "sev2",
      status: "triaged",
      observed_at: "2026-08-24T14:05:00Z",
      summary: "Elevated error rate on paymentservice.",
      source: "grafana-alerting",
    },
    approvals: [],
    version,
    updated_at: "2026-08-24T14:20:00Z",
    runs: [{ run_id: RUN, version, status: "awaiting_human", current_state: currentState, updated_at: "2026-08-24T14:20:00Z" }],
  };
}

const browser = await chromium.launch();

async function shoot(page, name, state) {
  const file = `docs/evidence/41-review-fixtures-${name}.png`;
  const contentHeight = await page.evaluate(() => document.body.scrollHeight);
  await page.setViewportSize({ width: 1440, height: Math.min(contentHeight, 4000) });
  await page.waitForTimeout(200);
  await page.screenshot({ path: file });
  console.log(JSON.stringify({ capture: name, fixture: "mocked-backend", state, file }));
}

async function openPage(getDetail, onCommand) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await page.route("**/api/v1/whoami", (route) =>
    route.fulfill({ json: { principal_id: "demo-human" }, headers: { "Cache-Control": "no-store" } }),
  );
  await page.route("**/api/v1/incidents/**", (route) => {
    const request = route.request();
    if (request.method() === "POST" && request.url().includes("/commands")) {
      return onCommand(route);
    }
    return route.fulfill({ json: getDetail() });
  });
  await page.goto(`${baseURL}/public/incident-ui/review.html?incident_id=${INCIDENT}&run_id=${RUN}`);
  await connectConsole(page);
  return page;
}

// Journey states exactly as the contract gates them. resolved and closed have
// no human decision commands: the neutral copy and empty list are the demo.
for (const [state, version] of [["mitigating", 4], ["verifying", 5], ["resolved", 6], ["closed", 9]]) {
  const page = await openPage(() => story(state, version), (route) => route.abort());
  await shoot(page, state, state);
  await page.close();
}

// CA4 money shot: the closure panel with the explicit, visible approval row
// (submit disabled until the mark) and the backend-guard hint.
{
  const page = await openPage(() => story("postmortem", 7), (route) => route.abort());
  await page.locator('#actions-list button[data-command="close_incident"]').click();
  await page.locator("#decision-approval-row").waitFor({ state: "visible" });
  await shoot(page, "postmortem-panel", "postmortem");
  await page.close();
}

// A stale-version 409 keeps the reason and the recovery is manual: one flow in
// one page (the in-memory draft belongs to it). The 409 shot shows the conflict
// alert; the recovery shot shows the refreshed version with the preserved draft
// and the approval starting unmarked.
{
  let detail = story("postmortem", 7);
  const page = await openPage(
    () => detail,
    (route) => {
      detail = story("postmortem", 8); // the backend advanced; the client version is stale
      return route.fulfill({ status: 409, json: { error: { code: "incident_version_conflict", message: "stale version" } } });
    },
  );
  await page.locator('#actions-list button[data-command="close_incident"]').click();
  await page.locator("#decision-comment").fill("Reviewed the postmortem draft, stable enough.");
  await page.locator("#decision-approval").check();
  await page.locator("#decision-submit").click();
  await page.locator("#error-409").waitFor({ state: "visible" });
  await shoot(page, "conflict", detail.runs[0].current_state);

  await page.locator("#refresh-button").click();
  await page.locator('#actions-list button[data-command="close_incident"]').waitFor({ state: "visible" });
  await page.locator('#actions-list button[data-command="close_incident"]').click();
  await page.locator("#decision-approval-row").waitFor({ state: "visible" });
  const preserved = await page.locator("#decision-comment").inputValue();
  if (preserved !== "Reviewed the postmortem draft, stable enough.") {
    throw new Error("the written reason did not survive the conflict recovery");
  }
  await shoot(page, "conflict-recovered", detail.runs[0].current_state);
  await page.close();
}

await browser.close();
