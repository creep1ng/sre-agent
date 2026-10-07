import { expect, test } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL ?? "http://127.0.0.1:8081";
const SUFFIX = Date.now().toString(36);

function journeyKeys() {
  const full = process.env.E2E_TRIAGE_API_KEY;
  const grantless = process.env.E2E_NOGRANT_API_KEY;
  test.skip(!full || !grantless, "requires full and grantless keys from a seeded stack");
  return { full, grantless };
}

async function connect(page, key, alertId = null) {
  await page.goto(`${BASE}/public/admin/triage.html${alertId ? `?alert_id=${alertId}` : ""}`);
  await page.locator("#api-key").fill(key);
  await page.locator("#connect-button").click();
}

test("command with a grantless identity is forbidden and persists nothing", async ({ page }) => {
  const { full, grantless } = journeyKeys();
  const alertId = `al-ca5-nopersist-${SUFFIX}`;
  let posts = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/triage/commands")) posts += 1;
  });
  await connect(page, grantless, alertId);
  await expect(page.locator("#page-error-title")).toHaveText("Access unavailable");
  await expect(page.locator("#page-error-detail")).toContainText("cannot read triage state");
  await expect(page.locator("#submit-button")).toBeDisabled();
  await expect(page.locator("#command-operation option[value='triage_dismiss']")).toBeDisabled();
  await expect(page.locator("#result-status")).toHaveText("—");
  await expect(page.locator("#result-reason")).toHaveText("—");
  await expect(page.locator("#result-actor")).toHaveText("—");
  expect(posts).toBe(0);
  await connect(page, full, alertId);
  await expect(page.locator("#result-summary")).toHaveText("No recorded decision for this alert.");
  await expect(page.locator("#page-error")).toBeHidden();
});

test("recovery read with a grantless identity shows forbidden without data", async ({ page }) => {
  const { full, grantless } = journeyKeys();
  const alertId = `al-ca5-noread-${SUFFIX}`;
  await connect(page, full);
  await page.locator("#alert-id").fill(alertId);
  await expect(page.locator("#command-operation")).toBeEnabled();
  await page.locator("#command-operation").selectOption("triage_dismiss");
  await page.locator("#command-reason").fill("CA5 decided proof.");
  await page.locator("#submit-button").click();
  await expect(page.locator("#result-status")).toHaveText("dismissed");
  await connect(page, grantless, alertId);
  await expect(page.locator("#page-error-title")).toHaveText("Access unavailable");
  await expect(page.locator("#page-error-detail")).toContainText("cannot read triage state");
  await expect(page.locator("#result-status")).toHaveText("—");
  await expect(page.locator("#result-reason")).toHaveText("—");
  await expect(page.locator("#result-actor")).toHaveText("—");
  await page.screenshot({ path: "docs/evidence/c3e-ca5-forbidden.png", fullPage: true });
  await page.locator("#disconnect-button").click();
  await expect(page.locator("#triage-page")).toHaveAttribute("data-state", "idle");
  await expect(page.locator("#page-error")).toBeHidden();
  await page.reload();
  await expect(page.locator("#triage-page")).toHaveAttribute("data-state", "idle");
  await expect(page.locator("#result-status")).toHaveText("—");
});
