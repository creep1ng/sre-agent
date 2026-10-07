import { expect, test } from "@playwright/test";

const WEB = process.env.E2E_BASE_URL ?? "http://web";
const API = process.env.E2E_API_BASE_URL ?? "http://api:8000";

function requiredKey(name) {
  const value = process.env[name];
  if (!value) throw new Error(`requires ${name} from the isolated triage fixture`);
  return value;
}

function alertId(kind) {
  return `al-t23-14-${kind}-${Date.now().toString(36)}`;
}

async function postCommand(request, key, id, body) {
  return request.post(`${API}/v1/alerts/${encodeURIComponent(id)}/triage/commands`, {
    headers: {
      Authorization: `Bearer ${key}`,
      "Idempotency-Key": `t23-14-${crypto.randomUUID()}`,
    },
    data: body,
  });
}

async function connectForAlert(page, id, key) {
  await page.goto(`${WEB}/public/admin/triage.html?alert_id=${encodeURIComponent(id)}`);
  await page.locator("#api-key").fill(key);
  await page.locator("#connect-button").click();
}

async function expectNoDecision(page) {
  await expect(page.locator("#result-summary")).toHaveText("No recorded decision for this alert.");
  await expect(page.locator("#result-status")).toHaveText("—");
  await expect(page.locator("#result-origin")).toHaveText("—");
  await expect(page.locator("#result-responsible-system")).toHaveText("—");
}

test("external producer dismissal is labeled from backend provenance after reload", async ({ page, request }) => {
  const producer = requiredKey("E2E_EXTERNAL_API_KEY");
  const operator = requiredKey("E2E_TRIAGE_API_KEY");
  const id = alertId("external");
  await connectForAlert(page, id, producer);
  await expect(page.locator("#command-operation option[value='open_triage']")).toBeDisabled();
  await expect(page.locator("#command-operation option[value='triage_declare']")).toBeDisabled();
  await expect(page.locator("#command-operation option[value='triage_dismiss']")).toBeEnabled();
  await expect(page.locator("#command-operation option[value='triage_link']")).toBeEnabled();
  await page.locator("#disconnect-button").click();
  const response = await postCommand(request, producer, id, {
    operation: "triage_dismiss",
    expected_version: 1,
    reason: "External producer emitted a dismissal decision.",
  });
  expect(response.status()).toBe(200);
  const decision = await response.json();
  expect(decision.decision_origin).toBe("external_automatic");
  expect(decision.responsible_system).toBe("producer-e2e");

  await connectForAlert(page, id, operator);
  await expect(page.locator("#result-status")).toHaveText("dismissed");
  await expect(page.locator("#result-origin")).toHaveText("External automatic");
  await expect(page.locator("#result-responsible-system")).toHaveText("producer-e2e");
  await expect(page.locator("#submit-button")).toBeDisabled();
  await expect(page.locator("#api-key")).toHaveValue("");
  if (process.env.T23_14_ARTIFACT_DIR) {
    await page.screenshot({
      path: `${process.env.T23_14_ARTIFACT_DIR}/external-origin.png`,
      fullPage: true,
    });
  }

  await page.reload();
  await page.locator("#api-key").fill(operator);
  await page.locator("#connect-button").click();
  await expect(page.locator("#result-origin")).toHaveText("External automatic");
  await expect(page.locator("#result-responsible-system")).toHaveText("producer-e2e");
  await page.locator("#disconnect-button").click();
  await expect(page.locator("#result-origin")).toHaveText("—");
  await expect(page.locator("#result-responsible-system")).toHaveText("—");
});

test("authorized external producer links to a real backend-eligible incident", async ({ page, request }) => {
  const producer = requiredKey("E2E_EXTERNAL_API_KEY");
  const operator = requiredKey("E2E_TRIAGE_API_KEY");
  const alert = alertId("linked");
  const incidentId = "inc-0000-t23-linkable";
  const linked = await postCommand(request, producer, alert, {
    operation: "triage_link",
    expected_version: 1,
    reason: "Authorized producer correlates this alert to the active incident.",
    target_incident_id: incidentId,
  });
  expect(linked.status()).toBe(200);
  expect(await linked.json()).toMatchObject({
    status: "linked",
    incident_id: incidentId,
    decision_origin: "external_automatic",
    responsible_system: "producer-e2e",
  });
  await connectForAlert(page, alert, operator);
  await expect(page.locator("#result-status")).toHaveText("linked");
  await expect(page.locator("#result-incident")).toContainText(incidentId);
  await expect(page.locator("#result-origin")).toHaveText("External automatic");
  await expect(page.locator("#result-responsible-system")).toHaveText("producer-e2e");
});

test("manual declaration remains manual and has no responsible external system", async ({ page }) => {
  const operator = requiredKey("E2E_TRIAGE_API_KEY");
  const id = alertId("manual");
  await page.goto(`${WEB}/public/admin/triage.html`);
  await page.locator("#api-key").fill(operator);
  await page.locator("#connect-button").click();
  await page.locator("#alert-id").fill(id);
  await expect(page.locator("#command-operation")).toBeEnabled();
  await page.locator("#command-operation").selectOption("triage_declare");
  await page.locator("#command-reason").fill("Operator declares after assessing impact.");
  await page.locator("#command-severity").selectOption("sev2");
  await page.locator("#command-impact").fill("New customer payments cannot be processed.");
  await page.locator("#submit-button").click();
  await expect(page.locator("#result-status")).toHaveText("declared");
  await expect(page.locator("#result-origin")).toHaveText("Manual");
  await expect(page.locator("#result-responsible-system")).toHaveText("—");

  await page.reload();
  await page.locator("#api-key").fill(operator);
  await page.locator("#connect-button").click();
  await expect(page.locator("#result-status")).toHaveText("declared");
  await expect(page.locator("#result-origin")).toHaveText("Manual");
  await expect(page.locator("#result-responsible-system")).toHaveText("—");
});

test("legacy decision displays backend unknown without inferring from its actor", async ({ page }) => {
  const operator = requiredKey("E2E_TRIAGE_API_KEY");
  const id = requiredKey("E2E_TRIAGE_LEGACY_ALERT_ID");
  await connectForAlert(page, id, operator);
  await expect(page.locator("#result-status")).toHaveText("dismissed");
  await expect(page.locator("#result-origin")).toHaveText("Unknown (legacy)");
  await expect(page.locator("#result-responsible-system")).toHaveText("—");
});

test("denied producer and forged origins leave no UI decision", async ({ page, request }) => {
  const operator = requiredKey("E2E_TRIAGE_API_KEY");
  const deniedProducer = requiredKey("E2E_EXTERNAL_NOGRANT_API_KEY");
  const producer = requiredKey("E2E_EXTERNAL_API_KEY");
  const deniedId = alertId("denied");
  const forgedId = alertId("forged");
  const declareId = alertId("agent-declare");

  const denied = await postCommand(request, deniedProducer, deniedId, {
    operation: "triage_dismiss", expected_version: 1, reason: "No grant must deny this decision.",
  });
  expect(denied.status()).toBe(403);
  const forged = await postCommand(request, operator, forgedId, {
    operation: "triage_dismiss",
    expected_version: 1,
    reason: "A client cannot claim external provenance.",
    decision_origin: "external_automatic",
    responsible_system: "forged-producer",
  });
  expect(forged.status()).toBe(422);
  const agentDeclare = await postCommand(request, producer, declareId, {
    operation: "triage_declare",
    expected_version: 1,
    reason: "External producers cannot declare incidents.",
    severity: "sev2",
    impact: "Operator-established impact is required for manual declaration.",
  });
  expect(agentDeclare.status()).toBe(403);

  for (const id of [deniedId, forgedId, declareId]) {
    await connectForAlert(page, id, operator);
    await expectNoDecision(page);
  }
});
