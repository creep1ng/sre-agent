import { expect, test } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL ?? "http://127.0.0.1:8081";
const DECLARATION_IMPACT = "Payments are unavailable for new customer orders.";

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
  await page.locator("#alert-id").fill(alertId);
  await page.locator("#command-operation").selectOption("triage_declare");
  await page.locator("#command-reason").fill("E2E persistence proof.");
  await page.locator("#command-severity").selectOption("sev2");
  await page.locator("#command-impact").fill(DECLARATION_IMPACT);
  await page.locator("#submit-button").click();
  await expect(page.locator("#result-status")).toHaveText("declared");
  const href = await page.locator("#result-incident a").getAttribute("href");
  const incidentId = await page.locator("#result-incident").textContent();
  return { href, incidentId: (incidentId ?? "").trim() };
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
  const before = await readFacts(page);
  await page.reload();
  await page.locator("#credential-input").fill(key);
  await page.locator("#credential-form button[type=submit]").click();
  await expect(page.locator("#fact-id")).toHaveText(incidentId);
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
