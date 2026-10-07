import { expect, test } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL ?? "http://127.0.0.1:8081";
const API = process.env.E2E_API_BASE_URL ?? "http://api:8000";
const DECLARATION_IMPACT = "Payments are unavailable for new customer orders.";
const ALERT_CONTEXT = Object.freeze({
  service: "checkout-api",
  summary: "New customer payment attempts return errors.",
  observed_at: "2026-10-07T17:30:00Z",
  source: "operator-confirmed monitoring report",
  severity: "sev4",
});

function journeyKey(name) {
  const value = process.env[name];
  test.skip(!value, `requires ${name} from a seeded stack`);
  return value;
}

async function connectTriage(page, key) {
  await page.goto(`${BASE}/public/admin/triage.html`);
  await page.locator("#api-key").fill(key);
  await page.locator("#connect-button").click();
}

async function declareAlert(page, alertId, key) {
  const posts = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/triage/commands"))
      posts.push(request.postDataJSON());
  });
  await page.locator("#alert-id").fill(alertId);
  await expect(page.locator("#command-operation")).toBeEnabled();
  await page.locator("#command-operation").selectOption("triage_declare");
  await page.locator("#command-reason").fill("E2E persistence proof.");
  await page.locator("#command-severity").selectOption("sev2");
  await page.locator("#command-impact").fill(DECLARATION_IMPACT);

  await page.locator("#submit-button").click();
  await expect(page.locator("#page-error-title")).toHaveText("Invalid request");
  await expect(page.locator("#page-error-detail")).toContainText(/alert context|service|source/i);
  expect(posts).toHaveLength(0);

  await page.locator("#alert-context-service").fill(ALERT_CONTEXT.service);
  await page.locator("#alert-context-summary").fill(ALERT_CONTEXT.summary);
  await page.locator("#alert-context-observed-at").fill(ALERT_CONTEXT.observed_at);
  await page.locator("#alert-context-source").fill(ALERT_CONTEXT.source);
  await page.locator("#alert-context-severity").selectOption(ALERT_CONTEXT.severity);
  await page.locator("#submit-button").click();
  expect(posts).toHaveLength(0);
  await page.locator("#alert-context-confirmed").check();

  await page.locator("#alert-id").fill(`${alertId}-other`);
  await expect(page.locator("#command-operation")).toBeEnabled();
  await expect(page.locator("#alert-context-service")).toHaveValue("");
  await expect(page.locator("#alert-context-summary")).toHaveValue("");
  await expect(page.locator("#alert-context-observed-at")).toHaveValue("");
  await expect(page.locator("#alert-context-source")).toHaveValue("");
  await expect(page.locator("#alert-context-severity")).toHaveValue("");
  await expect(page.locator("#alert-context-confirmed")).not.toBeChecked();
  await page.locator("#alert-id").fill(alertId);
  await expect(page.locator("#command-operation")).toBeEnabled();

  await page.locator("#alert-context-service").fill(ALERT_CONTEXT.service);
  await page.locator("#alert-context-summary").fill(ALERT_CONTEXT.summary);
  await page.locator("#alert-context-observed-at").fill(ALERT_CONTEXT.observed_at);
  await page.locator("#alert-context-source").fill(ALERT_CONTEXT.source);
  await page.locator("#alert-context-severity").selectOption(ALERT_CONTEXT.severity);
  await page.locator("#alert-context-confirmed").check();
  await page.locator("#submit-button").click();
  await expect(page.locator("#result-status")).toHaveText("declared");
  expect(posts).toHaveLength(1);
  expect(posts[0].alert_context).toEqual(ALERT_CONTEXT);
  const href = await page.locator("#result-incident a").getAttribute("href");
  const incidentId = await page.locator("#result-incident").textContent();
  const normalizedIncidentId = (incidentId ?? "").trim();
  const response = await page.request.get(`${API}/v1/incidents/${encodeURIComponent(normalizedIncidentId)}`, {
    headers: { Authorization: `Bearer ${key}` },
  });
  expect(response.status()).toBe(200);
  expect((await response.json()).alert).toMatchObject({ alert_id: alertId, ...ALERT_CONTEXT });
  if (process.env.T23_18_ARTIFACT_DIR) {
    await page.screenshot({
      path: `${process.env.T23_18_ARTIFACT_DIR}/triage-declaration-alert-context.png`,
      fullPage: true,
    });
  }
  return { href, incidentId: normalizedIncidentId };
}

async function openWarRoom(page, incidentId, key) {
  await page.goto(`${BASE}/public/incident-ui/war-room.html?incident_id=${incidentId}`);
  await page.locator("#credential-input").fill(key);
  await page.locator("#credential-form button[type=submit]").click();
  await expect(page.locator("#fact-id")).toHaveText(incidentId);
}

async function readFacts(page) {
  return {
    id: await page.locator("#fact-id").textContent(),
    state: await page.locator("#incident-state").textContent(),
    version: await page.locator("#version-line").textContent(),
    impact: await page.locator("#fact-impact").textContent(),
  };
}

test("declare navigates to the authoritative incident across reload", async ({ page }) => {
  const key = journeyKey("E2E_TRIAGE_API_KEY");
  const stamp = Date.now().toString(36);
  const alertId = `al-e2e-${stamp}`;
  await connectTriage(page, key);
  const { href, incidentId } = await declareAlert(page, alertId, key);
  expect(href).toBe(`/public/incident-ui/war-room.html?incident_id=${incidentId}`);
  await page.locator("#result-incident a").click();
  await page.locator("#credential-input").fill(key);
  await page.locator("#credential-form button[type=submit]").click();
  await expect(page.locator("#fact-id")).toHaveText(incidentId);
  await expect(page.locator("#fact-impact")).toHaveText(DECLARATION_IMPACT);
  await expect(page.locator("#fact-alert")).toHaveText(
    `${ALERT_CONTEXT.service} · ${ALERT_CONTEXT.severity} · ${ALERT_CONTEXT.summary}`,
  );
  const before = await readFacts(page);
  await page.reload();
  await page.locator("#credential-input").fill(key);
  await page.locator("#credential-form button[type=submit]").click();
  await expect(page.locator("#fact-id")).toHaveText(incidentId);
  await expect(page.locator("#fact-alert")).toHaveText(
    `${ALERT_CONTEXT.service} · ${ALERT_CONTEXT.severity} · ${ALERT_CONTEXT.summary}`,
  );
  expect(await readFacts(page)).toEqual(before);
});

test("second session reads the same persisted incident", async ({ browser }) => {
  const key = journeyKey("E2E_TRIAGE_API_KEY");
  const stamp = Date.now().toString(36);
  const first = await browser.newContext();
  const declarer = await first.newPage();
  await connectTriage(declarer, key);
  const { incidentId } = await declareAlert(declarer, `al-e2e-${stamp}`, key);
  await first.close();
  const second = await browser.newContext();
  const reader = await second.newPage();
  await openWarRoom(reader, incidentId, key);
  await expect(reader.locator("#fact-id")).toHaveText(incidentId);
  await expect(reader.locator("#fact-impact")).toHaveText(DECLARATION_IMPACT);
  await second.close();
});

test("unknown incident shows not-found without invented content", async ({ page }) => {
  const key = journeyKey("E2E_TRIAGE_API_KEY");
  await page.goto(`${BASE}/public/incident-ui/war-room.html?incident_id=inc-no-such-thing`);
  await page.locator("#credential-input").fill(key);
  await page.locator("#credential-form button[type=submit]").click();
  await expect(page.locator("#war-room")).toHaveAttribute("data-state", "error");
  await expect(page.locator("#fact-id")).toBeEmpty();
});

test("wrong credential shows authentication without incident data", async ({ page }) => {
  journeyKey("E2E_TRIAGE_API_KEY");
  await page.goto(`${BASE}/public/incident-ui/war-room.html?incident_id=inc-no-such-thing`);
  await page.locator("#credential-input").fill("sre_admn_0123456789abcdefghij");
  await page.locator("#credential-form button[type=submit]").click();
  await expect(page.locator("#war-room")).toHaveAttribute("data-state", "error");
  await expect(page.locator("#fact-id")).toBeEmpty();
});
