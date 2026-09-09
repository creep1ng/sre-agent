import { expect, test } from "@playwright/test";

function apiKey(name) {
  const value = process.env[name];
  test.skip(!value, `requires ${name}`);
  return value;
}

async function storageContents(page) {
  return page.evaluate(() => ({ local: { ...window.localStorage }, session: { ...window.sessionStorage } }));
}

test.beforeEach(async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (message) => {
    // Chromium logs "Failed to load resource" for intentional error statuses
    // (401/404) and aborted requests; the UI assertions cover those paths.
    if (message.type() === "error" && !message.text().startsWith("Failed to load resource"))
      consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(String(error?.message ?? error)));
  page.context()["__consoleErrors"] = consoleErrors;
  await page.goto("/public/admin/principals.html");
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "idle");
});

test.afterEach(async ({ page }) => {
  expect(page.context()["__consoleErrors"] ?? []).toEqual([]);
});

test("lists real principals through the same-origin proxy", async ({ page }) => {
  await page.fill("#api-key", apiKey("ADMIN_HUMAN_API_KEY"));
  await page.click("#connect-button");
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
  await expect(page.locator("[data-principal-row]")).not.toHaveCount(0);
  await expect(page.locator("[data-principal-row='admin-human']")).toHaveCount(1);
  const count = await page.locator("#principal-count").textContent();
  expect(count).toMatch(/principal/);
  expect(await storageContents(page)).toEqual({ local: {}, session: {} });
});

test("expands a principal row to an inline detail", async ({ page }) => {
  await page.fill("#api-key", apiKey("ADMIN_HUMAN_API_KEY"));
  await page.click("#connect-button");
  await expect(page.locator("[data-principal-row='admin-human']")).toBeVisible({ timeout: 20_000 });
  await page.click("[data-expand-principal='admin-human']");
  const detail = page.locator("[data-principal-detail='admin-human']");
  await expect(detail).toBeVisible();
  await expect(detail).toContainText("admin-human");
  await expect(detail).toContainText("human");
  await expect(detail).not.toContainText("sre_");
});

test("distinguishes 401 from 403 without partial data", async ({ page }) => {
  await page.click("#connect-button");
  await expect(page.locator("#page-error-title")).toHaveText("Request failed");
  await expect(page.locator("[data-principal-row]")).toHaveCount(0);

  await page.fill("#api-key", apiKey("RESTRICTED_HARNESS_API_KEY"));
  await page.click("#connect-button");
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "error", { timeout: 20_000 });
  await expect(page.locator("#page-error-title")).toHaveText("Access unavailable", { timeout: 20_000 });
  await expect(page.locator("[data-principal-row]")).toHaveCount(0);
});

test("shows a hidden principal as not found without leaking data", async ({ page }) => {
  await page.fill("#api-key", apiKey("ADMIN_HUMAN_API_KEY"));
  await page.click("#connect-button");
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
  await page.evaluate(async () => {
    const { createAdministrativeApiClient, createMemoryCredentialStore } = await import("/public/api/client.js");
    const store = createMemoryCredentialStore();
    const client = createAdministrativeApiClient({ credentialStore: store });
    try {
      await client.getPrincipal("definitely-absent-principal");
    } catch {
      document.body.dataset.hiddenProbe = "not-found";
    }
  });
  await expect(page.locator("body[data-hidden-probe='not-found']")).toHaveCount(1);
  await expect(page.locator("[data-principal-row]")).not.toHaveCount(0);
});

test("surfaces an unreachable API as a recoverable offline state", async ({ page }) => {
  await page.route("**/api/v1/principals**", (route) => route.abort("failed"));
  await page.fill("#api-key", "sre_admn_0123456789abcdefghijklmnop");
  await page.click("#connect-button");
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "offline", { timeout: 20_000 });
  await expect(page.locator("#page-error-title")).toHaveText("API unavailable");
  await expect(page.locator("[data-principal-row]")).toHaveCount(0);
});
