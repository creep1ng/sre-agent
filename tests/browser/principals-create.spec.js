import { expect, test } from "@playwright/test";
// B1 CREATE: REAL=connected API; CONTROLLED=real API + route delay/offline only.
const connected = process.env.PLAYWRIGHT_PRODUCTION_TOPOLOGY === "1";
function apiKey(name) {
  const value = process.env[name];
  test.skip(!value, `requires ${name}`);
  return value;
}
function ephemeralId(tag) {
  return `tst-${Date.now().toString(36)}-${Math.floor(Math.random() * 46656).toString(36).padStart(3, "0")}-${tag}`.slice(0, 60).toLowerCase();
}
async function connect(page, key) {
  await page.fill("#api-key", key);
  await page.click("#connect-button");
}
async function openCreate(page, { id, name, kind = "agent" }) {
  await page.click("#create-button");
  await expect(page.locator("#create-dialog")).toBeVisible();
  await page.fill("#create-principal-id", id);
  await page.fill("#create-display-name", name);
  await page.selectOption("#create-kind", kind);
}
test.beforeEach(async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (m) => {
    if (m.type() === "error" && !m.text().includes("Content Security Policy") && !m.text().startsWith("Failed to load resource")) consoleErrors.push(m.text());
  });
  page.on("pageerror", (e) => consoleErrors.push(String(e?.message ?? e)));
  page.context()["__consoleErrors"] = consoleErrors;
  await page.goto("/public/admin/principals.html");
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "idle");
});
test.afterEach(async ({ page }) => { expect(page.context()["__consoleErrors"] ?? []).toEqual([]); });
test("creates a real agent principal and keeps it after reload", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  await connect(page, adminKey);
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
  const id = ephemeralId("a01");
  await openCreate(page, { id, name: `Ephemeral ${id}`, kind: "agent" });
  await page.click("#create-submit");
  await expect(page.locator("#live-region")).toContainText(`Principal ${id} created.`, { timeout: 20_000 });
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  await page.reload();
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "idle");
  await connect(page, adminKey);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
});
test("disables submit while creating and rejects a conflicting retry token", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  await connect(page, adminKey);
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
  const id = ephemeralId("b02");
  await openCreate(page, { id, name: `Ephemeral ${id}`, kind: "agent" });
  const submit = page.locator("#create-submit");
  await submit.click();
  await expect(submit).toBeDisabled({ timeout: 5_000 });
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  const replay = await page.evaluate(async ({ key, principalId }) => {
    const { ApiClientError, createAdministrativeApiClient, createMemoryCredentialStore } = await import("/public/api/client.js");
    const store = createMemoryCredentialStore();
    store.set(key);
    const client = createAdministrativeApiClient({ credentialStore: store });
    const b = new Uint8Array(16);
    crypto.getRandomValues(b);
    const retryKey = `principal-create-${[...b].map((x) => x.toString(16).padStart(2, "0")).join("")}`;
    const first = await client.createPrincipal({ principal_id: principalId, kind: "agent", display_name: `Ephemeral ${principalId}` }, retryKey);
    let conflict = null;
    try {
      await client.createPrincipal({ principal_id: principalId, kind: "agent", display_name: "Different payload" }, retryKey);
    } catch (error) {
      if (error instanceof ApiClientError) conflict = { kind: error.kind, status: error.status, code: error.code };
      else throw error;
    }
    return { firstId: first?.principal_id ?? null, conflict };
  }, { key: adminKey, principalId: ephemeralId("b03") });
  expect(replay.firstId).toMatch(/^tst-/);
  expect(replay.conflict).toEqual({ kind: "conflict", status: 409, code: "idempotency_conflict" });
  await expect(page.locator("#page-error")).toBeHidden();
});
test("keeps form data on invalid input and proves a real 422", async ({ page }) => {
  await page.click("#create-button");
  await page.fill("#create-principal-id", "BAD ID");
  await page.fill("#create-display-name", `Keep ${Date.now()}`);
  await page.click("#create-submit");
  await expect(page.locator("#create-error-title")).toHaveText("Invalid principal");
  await expect(page.locator("#create-principal-id")).toHaveValue("BAD ID");
  await expect(page.locator("#create-dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  test.skip(!connected, "requires the connected control-plane API for the 422 proof");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  await connect(page, adminKey);
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
  const probe = await page.evaluate(async (key) => {
    const { ApiClientError, createAdministrativeApiClient, createMemoryCredentialStore } = await import("/public/api/client.js");
    const store = createMemoryCredentialStore();
    store.set(key);
    const client = createAdministrativeApiClient({ credentialStore: store });
    const pb = new Uint8Array(16);
    crypto.getRandomValues(pb);
    const probeKey = `principal-create-${[...pb].map((x) => x.toString(16).padStart(2, "0")).join("")}`;
    try {
      await client.createPrincipal({ principal_id: "ab", kind: "agent", display_name: "" }, probeKey);
      return { reached: true };
    } catch (error) {
      if (!(error instanceof ApiClientError)) throw error;
      return { kind: error.kind, status: error.status, code: error.code };
    }
  }, adminKey);
  expect(probe).toEqual({ kind: "api", status: 422, code: "validation_error" });
  await expect(page.locator("[data-principal-row='ab']")).toHaveCount(0);
});
test("blocks create for invalid and restricted credentials without data", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const restrictedKey = apiKey("RESTRICTED_HARNESS_API_KEY");
  await connect(page, "sre_admn_0123456789abcdefghij");
  await expect(page.locator("#page-error-title")).toHaveText("Authentication required", { timeout: 20_000 });
  const badId = ephemeralId("d01");
  await openCreate(page, { id: badId, name: `Ephemeral ${badId}` });
  await page.click("#create-submit");
  await expect(page.locator("#create-error-title")).toHaveText("Authentication required", { timeout: 20_000 });
  await expect(page.locator(`[data-principal-row='${badId}']`)).toHaveCount(0);
  await page.keyboard.press("Escape");
  await page.click("#disconnect-button");
  await connect(page, restrictedKey);
  await expect(page.locator("#page-error-title")).toHaveText("Access unavailable", { timeout: 20_000 });
  const deniedId = ephemeralId("d02");
  await openCreate(page, { id: deniedId, name: `Ephemeral ${deniedId}` });
  await page.click("#create-submit");
  await expect(page.locator("#create-error-title")).toHaveText("Access unavailable", { timeout: 20_000 });
  await expect(page.locator(`[data-principal-row='${deniedId}']`)).toHaveCount(0);
});
test("surfaces an aborted create as recoverable without false success", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  await connect(page, adminKey);
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
  await page.route("**/api/v1/principals", (route) => (route.request().method() === "POST" ? route.abort("failed") : route.continue()));
  const id = ephemeralId("e01");
  await openCreate(page, { id, name: `Ephemeral ${id}` });
  await page.click("#create-submit");
  await expect(page.locator("#create-error-title")).toHaveText("API unavailable", { timeout: 20_000 });
  await expect(page.locator("#create-principal-id")).toHaveValue(id);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(0);
  await expect(page.locator("#live-region")).not.toContainText(`Principal ${id} created.`);
  await page.unroute("**/api/v1/principals");
  await page.click("#create-submit");
  await expect(page.locator("#live-region")).toContainText(`Principal ${id} created.`, { timeout: 20_000 });
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
});
test("ignores a stale create response after the session is cleared", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  await connect(page, adminKey);
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
  const id = ephemeralId("f01");
  await page.route("**/api/v1/principals", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    await new Promise((r) => setTimeout(r, 1500));
    await route.continue();
  });
  await openCreate(page, { id, name: `Ephemeral ${id}` });
  await page.click("#create-submit");
  await expect(page.locator("#create-submit")).toBeDisabled();
  await page.waitForTimeout(300);
  await page.click("#disconnect-button");
  await page.waitForTimeout(2500);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(0);
  await expect(page.locator("#principal-count")).toHaveText("Not loaded.");
  await expect(page.locator("#page-error")).toBeHidden();
  await expect(page.locator("#live-region")).toHaveText("Session cleared.");
  await page.unroute("**/api/v1/principals");
});
test("successful create does not announce success when authoritative refresh fails", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  await connect(page, adminKey);
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
  const id = ephemeralId("g01");
  let posts = 0;
  await page.route("**/api/v1/principals**", (route) => (route.request().method() === "POST" ? (posts++, route.continue()) : route.abort("failed")));
  await openCreate(page, { id, name: `Ephemeral ${id}` });
  await page.click("#create-submit");
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "offline", { timeout: 20_000 });
  await expect(page.locator("#page-error-title")).toHaveText("API unavailable");
  await expect(page.locator("#principal-count")).toHaveText("Not loaded.");
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(0);
  await expect(page.locator("#live-region")).not.toContainText(`Principal ${id} created.`);
  expect(posts).toBe(1);
  await page.unroute("**/api/v1/principals**");
  await page.click("#refresh-button");
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  await expect(page.locator("#live-region")).not.toContainText(`Principal ${id} created.`);
});
test("keeps create locked across Escape/Cancel while POST is in flight", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  await connect(page, adminKey);
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
  const id = ephemeralId("h01");
  let posts = 0;
  await page.route("**/api/v1/principals", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    posts++;
    await new Promise((r) => setTimeout(r, 1500));
    await route.continue();
  });
  await openCreate(page, { id, name: `Ephemeral ${id}` });
  await page.click("#create-submit");
  await expect(page.locator("#create-submit")).toBeDisabled();
  await expect(page.locator("#create-cancel")).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(page.locator("#create-dialog")).toBeVisible();
  await page.evaluate(() => document.getElementById("create-form").requestSubmit());
  await page.waitForTimeout(300);
  await expect(page.locator("#create-dialog")).toBeVisible();
  expect(posts).toBe(1);
  await expect(page.locator("#live-region")).toContainText(`Principal ${id} created.`, { timeout: 20_000 });
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  expect(posts).toBe(1);
  await expect(page.locator("#create-dialog")).toBeHidden();
  await page.click("#create-button");
  await expect(page.locator("#create-dialog")).toBeVisible();
  await expect(page.locator("#create-cancel")).toBeEnabled();
  await page.keyboard.press("Escape");
  await expect(page.locator("#create-dialog")).toBeHidden();
  await page.unroute("**/api/v1/principals");
});
