import { expect, test } from "@playwright/test";

// Issue #41 slice 41b: durability verification of human decisions against the
// REAL backend. No route interception in this file: every request below reaches
// the compose stack (web proxy + FastAPI + Postgres).
//
// Setup (not evidence): incidents are seeded through the same governed store
// the HTTP suites use, run inside the checks container (see the PR body).
// Each test owns its incident id via SEED_STAMP, so no test depends on order
// or on residual data. Idempotency keys are minted by the UI per submit.
//
// What the real contract exposes for verification: the commands endpoint
// answers 202/409, the incident detail carries the durable run state, and the
// timeline lists the persisted decision events (one per accepted decision).
// The accepted free-text reason lives in the decisions store covered by the
// HTTP suite; here the UI must never lose the typed reason on a conflict.
//
// Gate: these journeys need the live compose stack with seeded grants, so they
// skip unless SRE_REAL_BACKEND=1 with REVIEW_API_KEY (a human credential holding
// run.read/run.command/run.approve on incident-response) exported in the shell.
// The static-web CI lane skips them; the key never enters the repository.

const WEB = "http://127.0.0.1:8080";
const API = `${WEB}/api`;
const STAMP = process.env.SEED_STAMP ?? "local";
const KEY = process.env.REVIEW_API_KEY ?? "";
const REAL = process.env.SRE_REAL_BACKEND === "1" && KEY.length > 0;

test.skip(!REAL, "needs the live compose stack: SRE_REAL_BACKEND=1 with REVIEW_API_KEY exported");

const incidentFor = (n) => `inc-41b-j${n}-${STAMP}`;
const runFor = (n) => `run_41bj${n}001${STAMP.replace(/-/g, "")}`;

function commandBody(comment) {
  return {
    command: "approve_mitigation",
    actor: "human",
    actor_reference: { reference_version: "1.0.0", principal_id: "demo-human" },
    authorization: { action: "run.approve", resource: { type: "incident_workflow", id: "incident-response" } },
    comment,
  };
}

async function apiPostCommand(request, incident, run, key, body) {
  const response = await request.post(`${API}/v1/incidents/${incident}/runs/${run}/commands`, {
    headers: { Authorization: `Bearer ${KEY}`, "Idempotency-Key": key, "Content-Type": "application/json" },
    data: body,
  });
  return { status: response.status(), json: await response.json() };
}

async function apiGetIncident(request, incident) {
  const response = await request.get(`${API}/v1/incidents/${incident}`, {
    headers: { Authorization: `Bearer ${KEY}` },
  });
  expect(response.status()).toBe(200);
  return response.json();
}

async function apiGetTimeline(request, incident, run) {
  const response = await request.get(`${API}/v1/incidents/${incident}/timeline?run_id=${run}`, {
    headers: { Authorization: `Bearer ${KEY}` },
  });
  expect(response.status()).toBe(200);
  return response.json();
}

async function openReviewReal(page, incident, run) {
  await page.goto(`${WEB}/public/incident-ui/review.html?incident_id=${incident}&run_id=${run}`);
  await expect(page.locator("#credential-section")).toBeVisible();
  await page.locator("#credential-input").fill(KEY);
  await page.locator("#credential-form button[type=submit]").click();
  await expect(page.locator("#actions-list button")).toHaveCount(3);
}

async function decideReal(page, comment) {
  await page.locator('#actions-list button[data-command="approve_mitigation"]').click();
  await page.locator("#decision-comment").fill(comment);
  const key = (await page.locator("#decision-key").textContent()) ?? "";
  expect(key).toMatch(/^[0-9a-f-]{10,}$/);
  await page.locator("#decision-submit").click();
  return key.trim();
}

test("resubmitting the accepted decision replays without duplicating it", async ({ page, request }) => {
  const incident = incidentFor(1);
  const run = runFor(1);
  const comment = `Durability reason J1 ${STAMP}.`;
  await openReviewReal(page, incident, run);
  const key = await decideReal(page, comment);
  await expect(page.locator("#receipt-line")).toContainText("approve_mitigation", { timeout: 15000 });

  const replay = await apiPostCommand(request, incident, run, key, commandBody(comment));
  expect(replay.status).toBe(202);
  expect(replay.json.run_id).toBe(run);
  expect(replay.json.current_state).toBe("verifying");

  const detail = await apiGetIncident(request, incident);
  expect(detail.state).toBe("verifying");
  const timeline = await apiGetTimeline(request, incident, run);
  expect(timeline.events).toHaveLength(1);
  expect(timeline.events[0].kind).toBe("state_change");
});

test("a conflicting reuse is rejected and the typed reason survives", async ({ page, request }) => {
  const incident = incidentFor(2);
  const run = runFor(2);
  const comment = `Durability reason J2 ${STAMP}.`;
  await openReviewReal(page, incident, run);
  const key = await decideReal(page, comment);
  await expect(page.locator("#receipt-line")).toContainText("approve_mitigation", { timeout: 15000 });

  const conflict = await apiPostCommand(request, incident, run, key, commandBody(`Changed reason ${STAMP}.`));
  expect(conflict.status).toBe(409);

  const detail = await apiGetIncident(request, incident);
  expect(detail.state).toBe("verifying");
  const timeline = await apiGetTimeline(request, incident, run);
  expect(timeline.events).toHaveLength(1);

  await expect(page.locator("#decision-comment")).toHaveValue(comment);
  await page.locator("#refresh-button").click();
  await expect(page.locator("#fact-state")).toContainText("verifying");
});

test("repeating the approval after the state advanced is rejected", async ({ page, request }) => {
  // State-transition conflict, not optimistic versioning: the command contract
  // carries no expected version, so staleness is only observable as "the state
  // no longer admits this command". Uses a fresh key to separate it from the
  // key-content conflict above.
  const incident = incidentFor(4);
  const run = runFor(4);
  const comment = `Durability reason J4 ${STAMP}.`;
  await openReviewReal(page, incident, run);
  await decideReal(page, comment);
  await expect(page.locator("#receipt-line")).toContainText("approve_mitigation", { timeout: 15000 });

  const { randomUUID } = await import("node:crypto");
  const late = await apiPostCommand(request, incident, run, randomUUID(), commandBody(comment));
  expect(late.status).toBe(409);

  const detail = await apiGetIncident(request, incident);
  expect(detail.state).toBe("verifying");
  const timeline = await apiGetTimeline(request, incident, run);
  expect(timeline.events).toHaveLength(1);

  await expect(page.locator("#decision-comment")).toHaveValue(comment);
  await page.locator("#refresh-button").click();
  await expect(page.locator("#fact-state")).toContainText("verifying");
});

test("reload and a second session read back the same accepted decision", async ({ page, browser, request }) => {
  const incident = incidentFor(3);
  const run = runFor(3);
  const comment = `Durability reason J3 ${STAMP}.`;
  await openReviewReal(page, incident, run);
  await decideReal(page, comment);
  await expect(page.locator("#receipt-line")).toContainText("approve_mitigation", { timeout: 15000 });

  const before = await apiGetTimeline(request, incident, run);
  expect(before.events).toHaveLength(1);

  await page.reload();
  await expect(page.locator("#credential-section")).toBeVisible();
  await page.locator("#credential-input").fill(KEY);
  await page.locator("#credential-form button[type=submit]").click();
  await expect(page.locator("#fact-state")).toContainText("verifying");

  const second = await browser.newContext();
  const other = await second.newPage();
  try {
    await other.goto(`${WEB}/public/incident-ui/review.html?incident_id=${incident}&run_id=${run}`);
    await other.locator("#credential-input").fill(KEY);
    await other.locator("#credential-form button[type=submit]").click();
    await expect(other.locator("#fact-state")).toContainText("verifying");
    const storage = await other.evaluate(() => JSON.stringify({ ...localStorage }));
    expect(storage).not.toContain(KEY);
  } finally {
    await second.close();
  }

  const after = await apiGetTimeline(request, incident, run);
  expect(after.events).toHaveLength(1);
  expect(after.events[0].kind).toBe("state_change");
});
