import { expect, test } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL ?? "http://127.0.0.1:8081";

function journeyKeys() {
  const full = process.env.E2E_TRIAGE_API_KEY;
  const grantless = process.env.E2E_NOGRANT_API_KEY;
  test.skip(!full || !grantless, "requires full and grantless keys from a seeded stack");
  return { full, grantless };
}

async function connect(page, key) {
  await page.goto(`${BASE}/public/admin/triage.html`);
  await page.locator("#api-key").fill(key);
  await page.locator("#connect-button").click();
}

async function switchCredential(page, key) {
  await page.locator("#api-key").fill(key);
  await page.locator("#connect-button").click();
}

async function dismiss(page, alertId, reason) {
  await page.locator("#alert-id").fill(alertId);
  await page.locator("#command-operation").selectOption("triage_dismiss");
  await page.locator("#command-reason").fill(reason);
  await page.locator("#submit-button").click();
}

async function expectNeutralPanel(page, stateLine = "Connect to begin.") {
  await expect(page.locator("#result-operation")).toHaveText("—");
  await expect(page.locator("#result-status")).toHaveText("—");
  await expect(page.locator("#result-reason")).toHaveText("—");
  await expect(page.locator("#result-incident")).toHaveText("—");
  await expect(page.locator("#result-version")).toHaveText("—");
  await expect(page.locator("#result-actor")).toHaveText("—");
  await expect(page.locator("#result-decided")).toHaveText("—");
  await expect(page.locator("#result-summary")).toHaveText("No command sent yet.");
  await expect(page.locator("#triage-state")).toHaveText(stateLine);
  await expect(page.locator("#expected-version")).toHaveValue("1");
}

test("clear session leaves a fully neutral panel", async ({ page }) => {
  const { full } = journeyKeys();
  const alertId = `al-c3a-clear-${Date.now().toString(36)}`;
  await connect(page, full);
  await dismiss(page, alertId, "C3a isolation clear proof.");
  await expect(page.locator("#result-status")).toHaveText("dismissed");
  await expect(page.locator("#result-actor")).not.toHaveText("—");
  await page.locator("#disconnect-button").click();
  await expectNeutralPanel(page);
  await expect(page.locator("#triage-page")).toHaveAttribute("data-state", "idle");
  await expect(page.locator("#page-error")).toBeHidden();
});

test("direct credential switch never shows the previous identity facts", async ({ page }) => {
  const { full, grantless } = journeyKeys();
  const alertA = `al-c3a-switch-a-${Date.now().toString(36)}`;
  await connect(page, full);
  await dismiss(page, alertA, "C3a isolation switch proof.");
  await expect(page.locator("#result-status")).toHaveText("dismissed");
  await switchCredential(page, grantless);
  await expectNeutralPanel(page, "Connected. Enter an alert and send a command.");
  const alertB = `al-c3a-switch-b-${Date.now().toString(36)}`;
  await dismiss(page, alertB, "C3a grantless probe.");
  await expect(page.locator("#page-error-title")).toHaveText("Access unavailable");
  await expectNeutralPanel(page, "Connected. Enter an alert and send a command.");
  await page.screenshot({ path: "docs/evidence/c3a-session-isolation.png", fullPage: true });
});

test("a fresh valid identity still renders its own decision", async ({ page }) => {
  const { full } = journeyKeys();
  const alertId = `al-c3a-positive-${Date.now().toString(36)}`;
  await connect(page, full);
  await dismiss(page, alertId, "C3a isolation positive proof.");
  await expect(page.locator("#result-status")).toHaveText("dismissed");
  await expect(page.locator("#result-actor")).not.toHaveText("—");
  await expect(page.locator("#result-summary")).toContainText("dismissed");
});

async function expectPristineForm(page) {
  await expect(page.locator("#command-reason")).toHaveValue("");
  await expect(page.locator("#alert-id")).toHaveValue("");
  await expect(page.locator("#command-target")).toHaveValue("");
  await expect(page.locator("#command-severity")).toHaveValue("");
}

test("clear and switch reset the reusable command form", async ({ page }) => {
  const { full, grantless } = journeyKeys();
  const stamp = Date.now().toString(36);
  await connect(page, full);
  await page.locator("#alert-id").fill(`al-c3e-form-${stamp}`);
  await page.locator("#command-operation").selectOption("triage_declare");
  await page.locator("#command-reason").fill("C3e form reset proof.");
  await page.locator("#command-severity").selectOption("sev2");
  await page.locator("#command-target").fill("inc-c3e-form");
  await page.locator("#submit-button").click();
  await expect(page.locator("#result-status")).toHaveText("declared");
  await page.locator("#disconnect-button").click();
  await expectNeutralPanel(page);
  await expectPristineForm(page);
  await page.locator("#api-key").fill(full);
  await page.locator("#connect-button").click();
  await page.locator("#alert-id").fill(`al-c3e-form-b-${stamp}`);
  await page.locator("#command-operation").selectOption("triage_declare");
  await page.locator("#command-reason").fill("C3e form second proof.");
  await page.locator("#command-severity").selectOption("sev3");
  await page.locator("#command-target").fill("inc-c3e-form-b");
  await page.locator("#submit-button").click();
  await expect(page.locator("#result-status")).toHaveText("declared");
  await switchCredential(page, grantless);
  await expectNeutralPanel(page, "Connected. Enter an alert and send a command.");
  await expectPristineForm(page);
  await dismiss(page, `al-c3e-form-c-${stamp}`, "C3e grantless probe.");
  await expect(page.locator("#page-error-title")).toHaveText("Access unavailable");
  await expectNeutralPanel(page, "Connected. Enter an alert and send a command.");
  await expect(page.locator("#command-reason")).toHaveValue("C3e grantless probe.");
});

test("first connect from a deep link recovers without inheriting form state", async ({ page }) => {
  const { full, grantless } = journeyKeys();
  const stamp = Date.now().toString(36);
  const alertId = `al-c3e-deeplink-${stamp}`;
  await connect(page, full);
  await dismiss(page, alertId, "C3e deep-link seed reason.");
  await expect(page.locator("#result-status")).toHaveText("dismissed");
  await page.goto(`${BASE}/public/admin/triage.html?alert_id=${alertId}`);
  await expect(page.locator("#alert-id")).toHaveValue(alertId);
  await page.locator("#api-key").fill(full);
  await page.locator("#connect-button").click();
  await expect(page.locator("#result-status")).toHaveText("dismissed");
  await expect(page.locator("#result-summary")).toContainText("Recovered from backend");
  await expect(page.locator("#result-reason")).toHaveText("C3e deep-link seed reason.");
  await expect(page.locator("#command-reason")).toHaveValue("");
  await expect(page.locator("#command-target")).toHaveValue("");
  await expect(page.locator("#command-severity")).toHaveValue("");
  await switchCredential(page, grantless);
  await expectNeutralPanel(page, "Connected. Enter an alert and send a command.");
  await expectPristineForm(page);
});
