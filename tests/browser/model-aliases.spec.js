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

test("opens real detail for triage-agent", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  await connect(page, apiKey("ADMIN_HUMAN_API_KEY"));
  await expect(page.locator("[data-alias-row='triage-agent']")).toHaveCount(1, { timeout: 20_000 });
  await page.click("[data-detail-open='triage-agent']");
  await expect(page.locator("#alias-detail")).not.toHaveAttribute("hidden");
  await expect(page.locator("#alias-detail-subtitle")).toContainText("triage-agent");
  await expect(page.locator("[data-detail-field='model_alias_id']")).toHaveText("triage-agent");
  await expect(page.locator("[data-detail-field='alias']")).toHaveText("triage-agent");
  await expect(page.locator("[data-detail-field='concrete_model']")).not.toBeEmpty();
  await expect(page.locator("[data-detail-field='router']")).toHaveText("openrouter");
  await expect(page.locator("[data-detail-field='inference_provider']")).not.toBeEmpty();
  await expect(page.locator("[data-detail-field='status']")).toHaveText("active");
});

test("detail fields match the selected list alias", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  await connect(page, apiKey("ADMIN_HUMAN_API_KEY"));
  await expect(page.locator("[data-alias-row='remediation-agent']")).toHaveCount(1, { timeout: 20_000 });
  const rowModel = await page.locator("[data-alias-row='remediation-agent'] td").nth(1).textContent();
  await page.click("[data-detail-open='remediation-agent']");
  await expect(page.locator("[data-detail-field='alias']")).toHaveText("remediation-agent");
  await expect(page.locator("[data-detail-field='concrete_model']")).toHaveText(rowModel.trim());
});

test("selecting B after A renders B authoritatively", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  await connect(page, apiKey("ADMIN_HUMAN_API_KEY"));
  await expect(page.locator("[data-alias-row='triage-agent']")).toHaveCount(1, { timeout: 20_000 });
  await page.click("[data-detail-open='triage-agent']");
  await expect(page.locator("[data-detail-field='alias']")).toHaveText("triage-agent");
  await page.click("[data-detail-open='remediation-agent']");
  await expect(page.locator("[data-detail-field='alias']")).toHaveText("remediation-agent");
  await expect(page.locator("[data-detail-field='concrete_model']")).not.toBeEmpty();
});

test("a stale A response cannot overwrite a newer B", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  await connect(page, apiKey("ADMIN_HUMAN_API_KEY"));
  await expect(page.locator("[data-alias-row='triage-agent']")).toHaveCount(1, { timeout: 20_000 });
  let releaseA;
  const gateA = new Promise((resolve) => {
    releaseA = resolve;
  });
  await page.route("**/api/v1/model-aliases/triage-agent", async (route) => {
    await gateA;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        model_alias_id: "triage-agent",
        alias: "triage-agent",
        concrete_model: "openai/stale-model",
        router: "openrouter",
        inference_provider: "openai",
        status: "active",
        updated_at: "2026-01-01T00:00:00Z",
      }),
    });
  });
  await page.route("**/api/v1/model-aliases/remediation-agent", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        model_alias_id: "remediation-agent",
        alias: "remediation-agent",
        concrete_model: "anthropic/fresh-model",
        router: "openrouter",
        inference_provider: "anthropic",
        status: "active",
        updated_at: "2026-01-02T00:00:00Z",
      }),
    }),
  );
  await page.click("[data-detail-open='triage-agent']");
  await expect(page.locator("#alias-detail-subtitle")).toContainText("Loading triage-agent");
  await page.click("[data-detail-open='remediation-agent']");
  await expect(page.locator("[data-detail-field='alias']")).toHaveText("remediation-agent");
  await expect(page.locator("[data-detail-field='concrete_model']")).toHaveText("anthropic/fresh-model");
  releaseA();
  await page.waitForTimeout(500);
  await expect(page.locator("[data-detail-field='alias']")).toHaveText("remediation-agent");
  await expect(page.locator("[data-detail-field='concrete_model']")).toHaveText("anthropic/fresh-model");
});

test("safe 404 shows Alias unavailable without stale metadata", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  await connect(page, apiKey("ADMIN_HUMAN_API_KEY"));
  await expect(page.locator("[data-alias-row='triage-agent']")).toHaveCount(1, { timeout: 20_000 });
  await page.click("[data-detail-open='triage-agent']");
  await expect(page.locator("[data-detail-field='alias']")).toHaveText("triage-agent");
  await page.unrouteAll({ behavior: "wait" });
  await page.route("**/api/v1/model-aliases/triage-agent", (route) =>
    route.fulfill({ status: 404, contentType: "application/json", body: "{}" }),
  );
  await page.click("[data-detail-open='triage-agent']");
  await expect(page.locator("#detail-error-title")).toHaveText("Alias unavailable");
  await expect(page.locator("[data-detail-field]")).toHaveCount(0);
  expect(await page.locator("#alias-detail").textContent()).not.toContain("openai/gpt-4o-mini");
});

test("late detail response cannot repopulate after Clear session", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  await connect(page, apiKey("ADMIN_HUMAN_API_KEY"));
  await expect(page.locator("[data-alias-row='triage-agent']")).toHaveCount(1, { timeout: 20_000 });
  let releaseDetail;
  const gate = new Promise((resolve) => {
    releaseDetail = resolve;
  });
  await page.route("**/api/v1/model-aliases/triage-agent", async (route) => {
    await gate;
    route.continue();
  });
  const pending = page.click("[data-detail-open='triage-agent']");
  await page.waitForTimeout(500);
  await page.click("#disconnect-button");
  await expect(page.locator("#model-aliases-page")).toHaveAttribute("data-state", "idle");
  releaseDetail();
  await pending;
  await page.waitForTimeout(500);
  await expect(page.locator("#alias-detail")).toHaveAttribute("hidden", "");
  await expect(page.locator("[data-detail-field]")).toHaveCount(0);
});

test("detail does not expose credentials or secrets", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  await connect(page, adminKey);
  await expect(page.locator("[data-alias-row='triage-agent']")).toHaveCount(1, { timeout: 20_000 });
  await page.click("[data-detail-open='triage-agent']");
  await expect(page.locator("[data-detail-field='alias']")).toHaveText("triage-agent");
  const detailText = (await page.locator("#alias-detail").textContent()) ?? "";
  expect(detailText).not.toContain(adminKey);
  expect(/\bsre_[A-Za-z0-9_-]{24,128}\b/.test(detailText)).toBe(false);
  expect(detailText.toLowerCase()).not.toContain("secret");
  expect(detailText.toLowerCase()).not.toContain("api_key");
  expect(await storageContents(page)).toEqual({ local: {}, session: {} });
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
