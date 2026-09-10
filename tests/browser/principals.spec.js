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
    // Nginx CSP (default-src 'self') blocks third-party font fetch locally,
    // and route.abort("failed") intentionally logs a resource error; the UI
    // assertions cover those paths.
    if (
      message.type() === "error" &&
      !message.text().includes("Content Security Policy") &&
      !message.text().startsWith("Failed to load resource")
    )
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

test("rejects an invalid non-empty credential with a real 401", async ({ page }) => {
  // Static mode has no /api backend (python http.server 404s /api/*), so the
  // contract-level 401 is asserted where the real API exists (CI
  // production-browser). Here the UI must surface a recoverable error state
  // without rendering rows or leaking data.
  await page.route("**/api/v1/principals**", async (route) => {
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({
        error: { code: "authentication_failed", message: "Authentication failed." },
        request_id: "00000000-0000-4000-8000-000000000001",
        retryable: false,
      }),
    });
  });
  await page.fill("#api-key", "sre_admn_0123456789abcdefghij");
  await page.click("#connect-button");
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "error", { timeout: 20_000 });
  await expect(page.locator("#page-error-title")).toHaveText("Authentication required");
  await expect(page.locator("#list-empty-detail")).toHaveText("Provide a valid API key.");
  await expect(page.locator("[data-principal-row]")).toHaveCount(0);
  await page.unroute("**/api/v1/principals**");
});

test("hides the list for a restricted identity without partial data", async ({ page }) => {
  await page.fill("#api-key", apiKey("RESTRICTED_HARNESS_API_KEY"));
  await page.click("#connect-button");
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "error", { timeout: 20_000 });
  await expect(page.locator("#page-error-title")).toHaveText("Access unavailable", { timeout: 20_000 });
  await expect(page.locator("[data-principal-row]")).toHaveCount(0);
});

test("shows a hidden principal as not found without leaking data", async ({ page }) => {
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  await page.fill("#api-key", adminKey);
  await page.click("#connect-button");
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
  const probe = await page.evaluate(async (key) => {
    const { ApiClientError, createAdministrativeApiClient, createMemoryCredentialStore } =
      await import("/public/api/client.js");
    const store = createMemoryCredentialStore();
    store.set(key);
    const client = createAdministrativeApiClient({ credentialStore: store });
    try {
      await client.getPrincipal("definitely-absent-principal");
      return { reached: true };
    } catch (error) {
      if (!(error instanceof ApiClientError)) throw error;
      document.body.dataset.hiddenProbe = `${error.kind}:${error.status}`;
      return { kind: error.kind, status: error.status };
    }
  }, adminKey);
  expect(probe).toEqual({ kind: "not_found", status: 404 });
  await expect(page.locator("body[data-hidden-probe='not_found:404']")).toHaveCount(1);
  await expect(page.locator("[data-principal-row]")).not.toHaveCount(0);
});

test("ignores a stale list response after the session is cleared", async ({ page }) => {
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  await page.route("**/api/v1/principals?limit=100", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.continue();
  });
  await page.fill("#api-key", adminKey);
  await page.click("#connect-button");
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "loading", { timeout: 20_000 });
  await page.click("#disconnect-button");
  await page.waitForTimeout(2500);
  await expect(page.locator("[data-principal-row]")).toHaveCount(0);
  await expect(page.locator("#principal-count")).toHaveText("Not loaded.");
  await page.unroute("**/api/v1/principals?limit=100");
});

test("surfaces an unreachable API as a recoverable offline state", async ({ page }) => {
  await page.route("**/api/v1/principals**", (route) => route.abort("failed"));
  await page.fill("#api-key", "sre_admn_0123456789abcdefghijklmnop");
  await page.click("#connect-button");
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "offline", { timeout: 20_000 });
  await expect(page.locator("#page-error-title")).toHaveText("API unavailable");
  await expect(page.locator("[data-principal-row]")).toHaveCount(0);
});
