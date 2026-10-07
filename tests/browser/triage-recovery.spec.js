import { expect, test } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL ?? "http://127.0.0.1:8081";
const SUFFIX = Date.now().toString(36);

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

async function dismissAlert(page, alertId, reason) {
  await page.locator("#alert-id").fill(alertId);
  await expect(page.locator("#command-operation")).toBeEnabled();
  await page.locator("#command-operation").selectOption("triage_dismiss");
  await page.locator("#command-reason").fill(reason);
  await page.locator("#submit-button").click();
  await expect(page.locator("#result-status")).toHaveText("dismissed");
}

async function readRecovery(page) {
  return {
    status: await page.locator("#result-status").textContent(),
    reason: await page.locator("#result-reason").textContent(),
    actor: await page.locator("#result-actor").textContent(),
    version: await page.locator("#result-version").textContent(),
  };
}

async function connectExisting(page, key) {
  await page.locator("#api-key").fill(key);
  await page.locator("#connect-button").click();
}

test("dismiss persists across reload and reads back from the API", async ({ page }) => {
  const key = journeyKey("E2E_TRIAGE_API_KEY");
  const alertId = `al-ca1-dismiss-${SUFFIX}`;
  await connectTriage(page, key);
  await dismissAlert(page, alertId, "CA1 recovery proof.");
  const before = await readRecovery(page);
  expect(before.reason).toBe("CA1 recovery proof.");
  await page.reload();
  await expect(page.locator("#alert-id")).toHaveValue(alertId);
  await connectExisting(page, key);
  await expect(page.locator("#result-summary")).toContainText("Recovered from backend");
  expect(await readRecovery(page)).toEqual(before);
});

test("second session reads the same dismiss from a direct URL", async ({ browser }) => {
  const key = journeyKey("E2E_TRIAGE_API_KEY");
  const alertId = `al-ca1-direct-${SUFFIX}`;
  const writer = await browser.newPage();
  await connectTriage(writer, key);
  await dismissAlert(writer, alertId, "CA1 direct proof.");
  const before = await readRecovery(writer);
  await writer.close();
  const reader = await browser.newPage();
  await reader.goto(`${BASE}/public/admin/triage.html?alert_id=${alertId}`);
  await reader.locator("#api-key").fill(key);
  await reader.locator("#connect-button").click();
  await expect(reader.locator("#result-summary")).toContainText("Recovered from backend");
  expect(await readRecovery(reader)).toEqual(before);
  await reader.close();
});

test("unknown alert shows no recorded decision without error", async ({ page }) => {
  journeyKey("E2E_TRIAGE_API_KEY");
  await page.goto(`${BASE}/public/admin/triage.html?alert_id=al-ca1-ghost-${SUFFIX}`);
  await page.locator("#api-key").fill(journeyKey("E2E_TRIAGE_API_KEY"));
  await page.locator("#connect-button").click();
  await expect(page.locator("#result-summary")).toHaveText("No recorded decision for this alert.");
  await expect(page.locator("#page-error")).toBeHidden();
});

test("wrong credential blocks the recovery read without data", async ({ page }) => {
  journeyKey("E2E_TRIAGE_API_KEY");
  await page.goto(`${BASE}/public/admin/triage.html?alert_id=al-ca1-dismiss-${SUFFIX}`);
  await page.locator("#api-key").fill("sre_bogus_00000000000000000000000000000000");
  await page.locator("#connect-button").click();
  await expect(page.locator("#page-error-title")).toHaveText("Authentication required");
  await expect(page.locator("#result-status")).toHaveText("—");
});

test("declared incident shows operator-confirmed alert context", async ({ page }) => {
  const key = journeyKey("E2E_TRIAGE_API_KEY");
  const alertId = `al-ca1-warroom-${SUFFIX}`;
  await connectTriage(page, key);
  await page.locator("#alert-id").fill(alertId);
  await expect(page.locator("#command-operation")).toBeEnabled();
  await page.locator("#command-operation").selectOption("triage_declare");
  await page.locator("#command-reason").fill("CA1 null-alert proof.");
  await page.locator("#command-severity").selectOption("sev2");
  await page.locator("#command-impact").fill("The affected service cannot process new payments.");
  await page.locator("#alert-context-service").fill("payments-api");
  await page.locator("#alert-context-summary").fill("New payment attempts return errors.");
  await page.locator("#alert-context-observed-at").fill("2026-10-07T17:30:00Z");
  await page.locator("#alert-context-source").fill("operator-confirmed monitoring report");
  await page.locator("#alert-context-severity").selectOption("sev2");
  await page.locator("#alert-context-confirmed").check();
  await page.locator("#submit-button").click();
  await expect(page.locator("#result-status")).toHaveText("declared");
  const incidentId = await page.locator("#result-incident").textContent();
  await page.goto(`${BASE}/public/incident-ui/war-room.html?incident_id=${incidentId.trim()}`);
  await page.locator("#credential-input").fill(key);
  await page.locator("#credential-form button[type=submit]").click();
  await expect(page.locator("#fact-alert")).toHaveText(
    "payments-api · sev2 · New payment attempts return errors.",
  );
});
