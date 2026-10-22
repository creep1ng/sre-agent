import { expect, request, test } from "@playwright/test";
import { writeFileSync } from "node:fs";
import { connectConsole } from "./support/console-session.mjs";

// Issue #701 against the REAL stack: web proxy, FastAPI, PostgreSQL, the AWS OpenTelemetry Demo
// with paymentUnreachable on and the governed Grafana MCP. Ways this can fail:
// 1. a firing alert nobody triaged is listed with a decision or an incident;
// 2. after the console declares it, GET /v1/alerts still says `new`, or names no incident, or
//    another incident than the one Triage created;
// 3. after the console dismisses it, the alert is not `dismissed` or still carries an incident.
// One run decides one episode (LIVE_ALERTS_TRIAGE=declare|dismiss): a decided episode stays
// decided, so the next decision needs `otel_ec2.py reset` and `fail` for a new episode.
const DEMO_KEY = process.env.DEMO_HUMAN_API_KEY ?? "";
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://web";
const ARTIFACTS = process.env.LIVE_ALERTS_ARTIFACT_DIR ?? "test-results/issue-701";
const DECISION = process.env.LIVE_ALERTS_TRIAGE ?? "";

test.skip(!["declare", "dismiss"].includes(DECISION) || !DEMO_KEY, "requires LIVE_ALERTS_TRIAGE and a demo key");

test(`a live alert the console decides (${DECISION}) is listed with that triage status`, async ({ page }) => {
  test.setTimeout(900_000);
  const api = await request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${DEMO_KEY}` } });
  const transcript = [];
  const list = async (step) => {
    const response = await api.get(`${BASE}/api/v1/alerts`);
    expect(response.status()).toBe(200);
    const body = await response.json();
    transcript.push({ step, at: new Date().toISOString(), alerts: body.alerts });
    return body.alerts;
  };

  let alert;
  await expect
    .poll(async () => {
      alert = (await list("waiting for an untriaged firing alert")).find((a) => a.triage_status === "new");
      return Boolean(alert);
    }, { timeout: 600_000, intervals: [15_000] })
    .toBe(true);
  expect(alert.incident_id).toBeNull();
  transcript.splice(0, transcript.length - 1);

  await page.goto("/");
  await connectConsole(page, DEMO_KEY);
  await page.locator(`#alert-list [data-alert-id="${alert.alert_id}"]`).click();
  await page.locator("#start-triage").click();
  if (DECISION === "declare") {
    await page.locator("#command-operation").selectOption("triage_declare");
    await page.locator("#command-reason").fill("Live checkout payment alert; customers cannot pay.");
    await page.locator("#command-severity").selectOption(alert.severity);
    await page.locator("#command-impact").fill("Checkout cannot charge payments in the store.");
    await page.locator("#alert-context-confirmed").check();
  } else {
    await page.locator("#command-operation").selectOption("triage_dismiss");
    await page.locator("#command-reason").fill("Expected failure while testing the payment flag.");
  }
  await page.locator("#submit-button").click();
  const status = DECISION === "declare" ? "declared" : "dismissed";
  await expect(page.locator("#result-status")).toHaveText(status, { timeout: 30_000 });
  const shown = (await page.locator("#result-incident").textContent()).trim();
  await page.screenshot({ path: `${ARTIFACTS}/triage-${status}.png`, fullPage: true });

  const listed = (await list(`after triage_${DECISION}`)).find((a) => a.alert_id === alert.alert_id);
  expect(listed, "the decided episode is still firing").toBeTruthy();
  expect(listed.triage_status).toBe(status);
  if (DECISION === "declare") expect(listed.incident_id).toMatch(/^inc-/);
  expect(listed.incident_id).toBe(DECISION === "declare" ? shown : null);

  // The same answer as the browser receives it, for the evidence screenshot.
  await page.setExtraHTTPHeaders({ authorization: `Bearer ${DEMO_KEY}` });
  await page.goto(`${BASE}/api/v1/alerts`);
  await page.screenshot({ path: `${ARTIFACTS}/alerts-${status}.png`, fullPage: true });
  writeFileSync(`${ARTIFACTS}/alerts-${status}.json`, JSON.stringify(transcript, null, 2));
  test.info().annotations.push(
    { type: "alert", description: alert.alert_id },
    { type: "incident", description: String(listed.incident_id) },
  );
});
