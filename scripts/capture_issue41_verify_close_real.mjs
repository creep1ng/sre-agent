// Real-backend evidence for #41 T2 (Decisiones: verify and close). Drives the
// console review page against the REAL compose stack (web proxy, API,
// PostgreSQL) as the operator and writes single-shot PNGs. No route is mocked.
//
//   verify:     run awaiting approval (scripts/seed_verification_close_demo.py)
//               -> Aprobar mitigación -> verifying -> Verificación estable -> resolved
//   postmortem: API only, no UI: POST /runs objective=postmortem (resolved -> postmortem),
//               PUT the #335 artifact citing this run's events, approve its version
//   close:      RUN_ID = the postmortem run -> Cerrar incidente with the explicit
//               approval -> closed, then the API confirms the closed incident
//
// Env: PLAYWRIGHT_BASE_URL, DEMO_HUMAN_API_KEY, INCIDENT_ID, RUN_ID, EVIDENCE_DIR.
// Usage: node scripts/capture_issue41_verify_close_real.mjs verify|postmortem|close
import { chromium, request } from "@playwright/test";
import { connectConsole } from "../tests/browser/support/console-session.mjs";

const phase = process.argv[2];
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://web";
const { DEMO_HUMAN_API_KEY: key, INCIDENT_ID: incident, RUN_ID: run } = process.env;
const out = process.env.EVIDENCE_DIR ?? "docs/evidence";
if (!["verify", "postmortem", "close"].includes(phase)) throw new Error("unknown phase");
if (!key || !incident || !run) throw new Error("DEMO_HUMAN_API_KEY, INCIDENT_ID and RUN_ID are required.");

const log = (step, data) => console.log(JSON.stringify({ phase, step, incident, run, ...data }));
const api = await request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${key}` } });
async function call(method, path, data, idempotencyKey) {
  const headers = idempotencyKey ? { "idempotency-key": idempotencyKey } : {};
  const response = await api.fetch(`${baseURL}/api${path}`, { method, data, headers });
  log(`${method} ${path}`, { status: response.status() });
  if (!response.ok()) throw new Error(`${method} ${path} answered ${response.status()}`);
  return response.json();
}

if (phase === "postmortem") {
  const started = await call("POST", `/v1/incidents/${incident}/runs`,
    { workflow_version: "1.0.0", objective: "postmortem" }, `pm-start-${incident}`);
  const { events } = await call("GET", `/v1/incidents/${incident}/runs/${run}/events`);
  const cite = (state, description) => ({ event_id: events.find((e) => e.state === state).event_id, description });
  const content = {
    summary: "Checkout payments failed while the paymentFailure flag was on.",
    impact: "Part of the checkouts failed at payment; revenue impact unknown.",
    timeline: [cite("verifying", "Mitigation approved by the operator."),
      cite("resolved", "Stability check passed.")],
    cause: { statement: "The paymentFailure feature flag was enabled.", certainty: "probable" },
    strategy: "Turn the flag off and watch the payment error rate.",
    actions_taken: [cite("verifying", "Operator turned paymentFailure off.")],
    verification: "Payment error rate stayed below 1% for ten minutes.",
    pending: ["Alert on feature flag changes in payment."],
    unknowns: ["Exact revenue impact."],
  };
  const written = await call("PUT", `/v1/incidents/${incident}/postmortem`, { expected_version: 0, content });
  await call("POST", `/v1/incidents/${incident}/postmortem/reviews`,
    { version: written.version, outcome: "approved", comment: "Matches the timeline." });
  const read = await call("GET", `/v1/incidents/${incident}/postmortem`);
  log("ready_to_close", { postmortem_run: started.run_id, run_state: started.current_state,
    postmortem_id: read.postmortem_id, version: read.version, review: read.review });
  await api.dispose();
  process.exit(0);
}

const text = async (page, selector) => ((await page.locator(selector).textContent()) ?? "").trim();
const facts = async (page) => ({
  state: await text(page, "#fact-state"),
  version: await text(page, "#fact-incident-version"),
  actions: await page.locator("#actions-list button").allTextContents(),
});
const ready = (page) =>
  page.waitForFunction(() => document.querySelector("#review")?.dataset.state === "ready");

async function refresh(page) {
  await page.locator("#refresh-button").click();
  await ready(page);
  return facts(page);
}

// One single-shot capture: the viewport grows to the content height, so no
// sticky-header stitching ever enters the evidence.
async function shot(page, name) {
  const height = await page.evaluate(() => document.body.scrollHeight);
  await page.setViewportSize({ width: 1440, height: Math.min(height, 4000) });
  await page.waitForTimeout(200);
  await page.screenshot({ path: `${out}/${name}` });
  await page.setViewportSize({ width: 1440, height: 1000 });
}

async function open(page, command, comment) {
  await page.locator(`#actions-list button[data-command="${command}"]`).click();
  await page.locator("#decision-comment").fill(comment);
}

async function submit(page) {
  await page.locator("#decision-submit").click();
  await page.locator("#receipt-section").waitFor({ state: "visible", timeout: 15000 });
  return text(page, "#receipt-line");
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
try {
  await page.goto(`${baseURL}/public/incident-ui/review.html?incident_id=${incident}&run_id=${run}`);
  await connectConsole(page, key);
  await ready(page);
  log("loaded", await facts(page));
  if (phase === "verify") {
    await open(page, "approve_mitigation", "Flag paymentFailure apagado por el operador.");
    log("approve_mitigation", { receipt: await submit(page) });
    log("refreshed", await refresh(page));
    await shot(page, "41-real-verifying.png");
    await open(page, "verification_passed", "Tasa de error bajo 1% durante diez minutos.");
    log("verification_passed", { receipt: await submit(page) });
    await shot(page, "41-real-verification-receipt.png");
    log("refreshed", await refresh(page));
    await shot(page, "41-real-resolved.png");
  } else {
    await open(page, "close_incident", "Postmortem revisado y aprobado; cierro el incidente.");
    const blocked = await page.locator("#decision-submit").isDisabled();
    log("close_panel", { approval_checked: await page.locator("#decision-approval").isChecked(), submit_disabled: blocked });
    if (!blocked) throw new Error("close submit must start disabled until the approval is marked");
    await shot(page, "41-real-close-panel.png");
    await page.locator("#decision-approval").check();
    log("close_incident", { receipt: await submit(page) });
    await shot(page, "41-real-close-receipt.png");
    log("refreshed", await refresh(page));
    await shot(page, "41-real-closed.png");
    const detail = await call("GET", `/v1/incidents/${incident}`);
    log("api_after", { state: detail.state, version: detail.version, runs: detail.runs });
  }
} finally {
  await browser.close();
  await api.dispose();
}
