import { expect, test } from "@playwright/test";
// C1 ISSUE: REAL=connected API; CONTROLLED=real API + route delay/offline only.
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
async function createActivePrincipal(page, adminKey, tag) {
  const id = ephemeralId(tag);
  await page.evaluate(async ({ key, principalId }) => {
    const { createAdministrativeApiClient, createMemoryCredentialStore } = await import("/public/api/client.js");
    const store = createMemoryCredentialStore();
    store.set(key);
    const client = createAdministrativeApiClient({ credentialStore: store });
    const b = new Uint8Array(16);
    crypto.getRandomValues(b);
    const idem = `principal-create-${[...b].map((x) => x.toString(16).padStart(2, "0")).join("")}`;
    await client.createPrincipal({ principal_id: principalId, kind: "agent", display_name: `Ephemeral ${principalId}` }, idem);
  }, { key: adminKey, principalId: id });
  return id;
}
async function seamIssue(page, key, principalId, idem, body) {
  return page.evaluate(async ({ key, principalId, idem, body }) => {
    const { ApiClientError, createAdministrativeApiClient, createMemoryCredentialStore } = await import("/public/api/client.js");
    const store = createMemoryCredentialStore();
    store.set(key);
    const client = createAdministrativeApiClient({ credentialStore: store });
    try {
      const issued = await client.issueCredential(principalId, body, idem);
      return { ok: true, credential_id: issued.credential.credential_id, revealed: issued.secret_revealed, hasKey: "key" in issued };
    } catch (error) {
      if (!(error instanceof ApiClientError)) throw error;
      return { ok: false, kind: error.kind, status: error.status, code: error.code };
    }
  }, { key, principalId, idem, body });
}
async function openCredentials(page, id) {
  await page.click(`[data-expand-principal='${id}']`);
  await expect(page.locator(`[data-principal-detail='${id}']`)).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(`[data-issue-credential='${id}']`)).toBeVisible();
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
test("issues a credential, reveals the secret once, and lists metadata only", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  const id = await createActivePrincipal(page, adminKey, "c01");
  await connect(page, adminKey);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  await openCredentials(page, id);
  await expect(page.locator(`[data-principal-detail='${id}']`)).toContainText("No credentials");
  await page.click(`[data-issue-credential='${id}']`);
  await page.click("#issue-submit");
  await expect(page.locator("#secret-dialog")).toBeVisible({ timeout: 20_000 });
  const secret = await page.locator("#secret-value").textContent();
  expect(typeof secret === "string" && secret.length > 0).toBe(true);
  await expect(page.locator(`[data-credential-list='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  const listLeaks = await page.locator(`[data-credential-list='${id}']`).evaluate((el, s) => (el.textContent ?? "").includes(s), secret);
  expect(listLeaks).toBe(false);
  await page.click("#secret-close");
  await expect(page.locator("#secret-dialog")).toBeHidden();
  const wiped = await page.evaluate((s) => {
    const body = document.body.textContent ?? "";
    return !body.includes(s) && (document.getElementById("secret-value")?.textContent ?? "") === "" && localStorage.length === 0 && sessionStorage.length === 0 && !location.href.includes("sre_");
  }, secret);
  expect(wiped).toBe(true);
  await page.click(`[data-expand-principal='${id}']`);
  await page.click(`[data-expand-principal='${id}']`);
  await expect(page.locator(`[data-credential-list='${id}']`)).toContainText("active", { timeout: 20_000 });
});
test("stable replay never reveals the secret again", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  const id = await createActivePrincipal(page, adminKey, "c02");
  const idem = `credential-issue-${id}-replay`;
  const first = await seamIssue(page, adminKey, id, idem, {});
  expect(first.ok && first.revealed && first.hasKey).toBe(true);
  const replay = await seamIssue(page, adminKey, id, idem, {});
  expect(replay).toEqual({ ok: true, credential_id: first.credential_id, revealed: false, hasKey: false });
  const meta = await page.evaluate(async ({ key, principalId }) => {
    const { createAdministrativeApiClient, createMemoryCredentialStore } = await import("/public/api/client.js");
    const store = createMemoryCredentialStore();
    store.set(key);
    const list = await createAdministrativeApiClient({ credentialStore: store }).listCredentials(principalId);
    return { n: list.items.length, clean: list.items.every((c) => !("key" in c)) };
  }, { key: adminKey, principalId: id });
  expect(meta.n).toBe(1);
  expect(meta.clean).toBe(true);
  await connect(page, adminKey);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  await openCredentials(page, id);
  await expect(page.locator(`[data-credential-list='${id}']`)).toContainText(first.credential_id, { timeout: 20_000 });
});
test("surfaces real idempotency conflict without false success", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  const id = await createActivePrincipal(page, adminKey, "c03");
  const idem = `credential-issue-${id}-conflict`;
  const first = await seamIssue(page, adminKey, id, idem, {});
  expect(first.ok).toBe(true);
  const clash = await seamIssue(page, adminKey, id, idem, { expires_at: "2031-01-02T03:04:05Z" });
  expect(clash).toEqual({ ok: false, kind: "conflict", status: 409, code: "idempotency_conflict" });
  await connect(page, adminKey);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  await openCredentials(page, id);
  await expect(page.locator(`[data-credential-list='${id}']`).locator("li")).toHaveCount(1, { timeout: 20_000 });
});
test("distinguishes administrative 401 and 403 without partial credential data", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  const restrictedKey = apiKey("RESTRICTED_HARNESS_API_KEY");
  const id = await createActivePrincipal(page, adminKey, "c04");
  const bad = await seamIssue(page, "sre_admn_0123456789abcdefghij", id, `credential-issue-${id}-bad`, {});
  const denied = await seamIssue(page, restrictedKey, id, `credential-issue-${id}-denied`, {});
  expect(bad).toEqual({ ok: false, kind: "authentication", status: 401, code: "authentication_failed" });
  expect(denied).toEqual({ ok: false, kind: "authorization", status: 403, code: "resource_unavailable" });
  await connect(page, adminKey);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  await openCredentials(page, id);
  await page.click(`[data-issue-credential='${id}']`);
  await page.evaluate((key) => {
    document.getElementById("api-key").value = key;
    document.getElementById("session-form").requestSubmit();
  }, "sre_admn_0123456789abcdefghij");
  await expect(page.locator("#page-error-title")).toHaveText("Authentication required", { timeout: 20_000 });
  await page.click("#issue-submit");
  await expect(page.locator("#issue-error-title")).toHaveText("Authentication required", { timeout: 20_000 });
  await expect(page.locator("#secret-dialog")).toBeHidden();
});
test("keeps one logical issuance across network retry and clears late secrets", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  const id = await createActivePrincipal(page, adminKey, "c05");
  await connect(page, adminKey);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  await openCredentials(page, id);
  await page.click(`[data-issue-credential='${id}']`);
  await page.route("**/api/**/credentials", (route) => (route.request().method() === "POST" ? route.abort("failed") : route.continue()));
  await page.click("#issue-submit");
  await expect(page.locator("#issue-error-title")).toHaveText("API unavailable", { timeout: 20_000 });
  await expect(page.locator("#secret-dialog")).toBeHidden();
  await page.unroute("**/api/**/credentials");
  await page.click("#issue-submit");
  await expect(page.locator("#secret-dialog")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(`[data-credential-list='${id}']`).locator("li")).toHaveCount(1, { timeout: 20_000 });
  await page.click("#secret-close");
  await page.click(`[data-issue-credential='${id}']`);
  await expect(page.locator(`[data-credential-list='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  await page.route("**/api/**/credentials", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    await new Promise((r) => setTimeout(r, 1500));
    await route.continue();
  });
  await page.click("#issue-submit");
  await expect(page.locator("#issue-submit")).toBeDisabled();
  await expect(page.locator("#issue-cancel")).toBeDisabled();
  await page.waitForTimeout(300);
  await page.locator("#disconnect-button").dispatchEvent("click"); // modal blocks pointer; exercise handler directly
  await page.waitForTimeout(2500);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(0);
  await expect(page.locator("#principal-count")).toHaveText("Not loaded.");
  await expect(page.locator("#secret-dialog")).toBeHidden();
  await expect(page.locator("#live-region")).toHaveText("Session cleared.");
  await page.unroute("**/api/**/credentials");
});
