import { expect, test } from "@playwright/test";

const connected = process.env.PLAYWRIGHT_PRODUCTION_TOPOLOGY === "1";

function apiKey(name) {
  const value = process.env[name];
  test.skip(!value, `requires ${name}`);
  return value;
}

async function connect(page, key) {
  await page.fill("#api-key", key);
  await page.click("#connect-button");
}

async function storageContents(page) {
  return page.evaluate(() => ({ local: { ...window.localStorage }, session: { ...window.sessionStorage } }));
}

test.beforeEach(async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (message) => {
    if (
      message.type() === "error" &&
      !message.text().includes("Content Security Policy") &&
      !message.text().startsWith("Failed to load resource")
    )
      consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(String(error?.message ?? error)));
  page.context()["__consoleErrors"] = consoleErrors;
  await page.goto("/public/admin/model-aliases.html");
  await expect(page.locator("#model-aliases-page")).toHaveAttribute("data-state", "idle");
});

test.afterEach(async ({ page }) => {
  expect(page.context()["__consoleErrors"] ?? []).toEqual([]);
});

test("lists real model aliases through the same-origin proxy", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  await connect(page, apiKey("ADMIN_HUMAN_API_KEY"));
  await expect(page.locator("#model-aliases-page")).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
  await expect(page.locator("[data-alias-row]")).not.toHaveCount(0);
  await expect(page.locator("[data-alias-row='triage-agent']")).toHaveCount(1);
  await expect(page.locator("[data-alias-row='remediation-agent']")).toHaveCount(1);
  expect(await page.locator("#alias-count").textContent()).toMatch(/alias/);
  expect(await storageContents(page)).toEqual({ local: {}, session: {} });
});

test("renders a real 401 as authentication required", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  await connect(page, "sre_admn_0123456789abcdefghij");
  await expect(page.locator("#model-aliases-page")).toHaveAttribute("data-state", "error", { timeout: 20_000 });
  await expect(page.locator("#page-error-title")).toHaveText("Authentication required");
  await expect(page.locator("[data-alias-row]")).toHaveCount(0);
});

test("renders a real 403 as access unavailable", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  await connect(page, apiKey("RESTRICTED_HARNESS_API_KEY"));
  await expect(page.locator("#model-aliases-page")).toHaveAttribute("data-state", "error", { timeout: 20_000 });
  await expect(page.locator("#page-error-title")).toHaveText("Access unavailable", { timeout: 20_000 });
  await expect(page.locator("[data-alias-row]")).toHaveCount(0);
});

test("surfaces network failure without false data", async ({ page }) => {
  await page.route("**/api/v1/model-aliases**", (route) => route.abort("failed"));
  await page.fill("#api-key", "sre_admn_0123456789abcdefghijklmnop");
  await page.click("#connect-button");
  await expect(page.locator("#model-aliases-page")).toHaveAttribute("data-state", "offline", { timeout: 20_000 });
  await expect(page.locator("#page-error-title")).toHaveText("API unavailable");
  await expect(page.locator("[data-alias-row]")).toHaveCount(0);
});

test("clears stale rows when a loaded list is followed by a 401", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  await connect(page, apiKey("ADMIN_HUMAN_API_KEY"));
  await expect(page.locator("[data-alias-row='triage-agent']")).toHaveCount(1, { timeout: 20_000 });
  const staleModel = await page.locator("[data-alias-row='triage-agent'] td").nth(1).textContent();
  await page.unrouteAll({ behavior: "wait" });
  await page.route("**/api/v1/model-aliases**", (route) =>
    route.fulfill({ status: 401, contentType: "application/json", body: "{}" }),
  );
  await page.click("#refresh-button");
  await expect(page.locator("#model-aliases-page")).toHaveAttribute("data-state", "error", { timeout: 20_000 });
  await expect(page.locator("#page-error-title")).toHaveText("Authentication required");
  await expect(page.locator("[data-alias-row]")).toHaveCount(0);
  expect(await page.locator("#alias-rows").textContent()).not.toContain(staleModel);
  expect(await page.locator("#live-region").textContent()).not.toMatch(/alias(es)?\./);
});

test("clears stale rows when a loaded list is followed by a 403", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  await connect(page, apiKey("ADMIN_HUMAN_API_KEY"));
  await expect(page.locator("[data-alias-row='triage-agent']")).toHaveCount(1, { timeout: 20_000 });
  const staleModel = await page.locator("[data-alias-row='triage-agent'] td").nth(1).textContent();
  await page.unrouteAll({ behavior: "wait" });
  await page.route("**/api/v1/model-aliases**", (route) =>
    route.fulfill({ status: 403, contentType: "application/json", body: "{}" }),
  );
  await page.click("#refresh-button");
  await expect(page.locator("#model-aliases-page")).toHaveAttribute("data-state", "error", { timeout: 20_000 });
  await expect(page.locator("#page-error-title")).toHaveText("Access unavailable");
  await expect(page.locator("[data-alias-row]")).toHaveCount(0);
  expect(await page.locator("#alias-rows").textContent()).not.toContain(staleModel);
});

test("clears stale rows when a loaded list is followed by a network failure", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  await connect(page, apiKey("ADMIN_HUMAN_API_KEY"));
  await expect(page.locator("[data-alias-row='triage-agent']")).toHaveCount(1, { timeout: 20_000 });
  const staleModel = await page.locator("[data-alias-row='triage-agent'] td").nth(1).textContent();
  await page.unrouteAll({ behavior: "wait" });
  await page.route("**/api/v1/model-aliases**", (route) => route.abort("failed"));
  await page.click("#refresh-button");
  await expect(page.locator("#model-aliases-page")).toHaveAttribute("data-state", "offline", { timeout: 20_000 });
  await expect(page.locator("#page-error-title")).toHaveText("API unavailable");
  await expect(page.locator("[data-alias-row]")).toHaveCount(0);
  expect(await page.locator("#alias-rows").textContent()).not.toContain(staleModel);
});

test("clears the session and removes alias rows", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  await connect(page, adminKey);
  await expect(page.locator("[data-alias-row='triage-agent']")).toHaveCount(1, { timeout: 20_000 });
  await page.click("#disconnect-button");
  await expect(page.locator("[data-alias-row]")).toHaveCount(0);
  await expect(page.locator("#alias-count")).toHaveText("Not loaded.");
  await expect(page.locator("#live-region")).toHaveText("Session cleared.");
  expect(await storageContents(page)).toEqual({ local: {}, session: {} });
});

test("keeps credentials out of web storage and the URL", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  await connect(page, adminKey);
  await expect(page.locator("[data-alias-row='triage-agent']")).toHaveCount(1, { timeout: 20_000 });
  expect(await storageContents(page)).toEqual({ local: {}, session: {} });
  const leak = await page.evaluate(() => ({
    href: location.href,
    body: document.body.textContent ?? "",
  }));
  expect(leak.href).not.toContain(adminKey);
  expect(/\bsre_[A-Za-z0-9_-]{24,128}\b/.test(leak.href)).toBe(false);
  expect(leak.body).not.toContain(adminKey);
  expect(/\bsre_[A-Za-z0-9_-]{24,128}\b/.test(leak.body)).toBe(false);
});
