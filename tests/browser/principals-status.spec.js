import { expect, test } from "@playwright/test";
// B2 DEACTIVATE: REAL=connected API; CONTROLLED=real API + route delay/offline only.
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
  const created = await page.evaluate(async ({ key, principalId }) => {
    const { createAdministrativeApiClient, createMemoryCredentialStore } = await import("/public/api/client.js");
    const store = createMemoryCredentialStore();
    store.set(key);
    const client = createAdministrativeApiClient({ credentialStore: store });
    const b = new Uint8Array(16);
    crypto.getRandomValues(b);
    const idem = `principal-create-${[...b].map((x) => x.toString(16).padStart(2, "0")).join("")}`;
    return client.createPrincipal({ principal_id: principalId, kind: "agent", display_name: `Ephemeral ${principalId}` }, idem);
  }, { key: adminKey, principalId: id });
  expect(created.principal_id).toBe(id);
  expect(created.status).toBe("active");
  return id;
}
async function openDeactivate(page, id) {
  await page.click(`[data-expand-principal='${id}']`);
  await expect(page.locator(`[data-principal-detail='${id}']`)).toBeVisible({ timeout: 20_000 });
  await page.click(`[data-deactivate-principal='${id}']`);
  await expect(page.locator("#deactivate-dialog")).toBeVisible();
  await expect(page.locator("#deactivate-title")).toContainText(id);
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
test("deactivates a real active principal and persists after reload", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  const id = await createActivePrincipal(page, adminKey, "s01");
  await connect(page, adminKey);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  await openDeactivate(page, id);
  await expect(page.locator("#deactivate-detail")).toContainText(id);
  await page.click("#deactivate-submit");
  await expect(page.locator("#live-region")).toContainText(`Principal ${id} deactivated.`, { timeout: 20_000 });
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1);
  const detail = page.locator(`[data-principal-detail='${id}']`);
  await expect(detail).toContainText("inactive");
  await expect(page.locator(`[data-deactivate-principal='${id}']`)).toHaveCount(0);
  await expect(page.locator(`[data-deactivate-unavailable='${id}']`)).toHaveCount(1);
  await expect(page.locator("#deactivate-dialog")).toBeHidden();
  await page.reload();
  await expect(page.locator("#principals-page")).toHaveAttribute("data-state", "idle");
  await connect(page, adminKey);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  await page.click(`[data-expand-principal='${id}']`);
  await expect(page.locator(`[data-principal-detail='${id}']`)).toContainText("inactive", { timeout: 20_000 });
  const probe = await page.evaluate(async ({ key, principalId }) => {
    const { createAdministrativeApiClient, createMemoryCredentialStore } = await import("/public/api/client.js");
    const store = createMemoryCredentialStore();
    store.set(key);
    const client = createAdministrativeApiClient({ credentialStore: store });
    const got = await client.getPrincipal(principalId);
    const list = await client.listPrincipals();
    return { status: got.status, count: list.items.filter((i) => i.principal_id === principalId).length };
  }, { key: adminKey, principalId: id });
  expect(probe).toEqual({ status: "inactive", count: 1 });
});
test("rejects stale expected_updated_at with a real 409 and refreshes authoritative state", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  const id = await createActivePrincipal(page, adminKey, "s02");
  await connect(page, adminKey);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  await openDeactivate(page, id);
  const bump = await page.evaluate(async ({ key, principalId }) => {
    const { ApiClientError, createAdministrativeApiClient, createMemoryCredentialStore } = await import("/public/api/client.js");
    const store = createMemoryCredentialStore();
    store.set(key);
    const client = createAdministrativeApiClient({ credentialStore: store });
    const fresh = await client.getPrincipal(principalId);
    const touched = await client.replacePrincipalStatus(principalId, { status: "active", expected_updated_at: fresh.updated_at });
    let stale = null;
    try {
      await client.replacePrincipalStatus(principalId, { status: "inactive", expected_updated_at: fresh.updated_at });
    } catch (error) {
      if (error instanceof ApiClientError) stale = { kind: error.kind, status: error.status, code: error.code };
      else throw error;
    }
    return { before: fresh.updated_at, after: touched.updated_at, stale };
  }, { key: adminKey, principalId: id });
  expect(bump.before).not.toBe(bump.after);
  expect(bump.stale).toEqual({ kind: "conflict", status: 409, code: "status_conflict" });
  await page.click("#deactivate-submit");
  await expect(page.locator("#deactivate-error-title")).toHaveText("Resource changed", { timeout: 20_000 });
  await expect(page.locator("#deactivate-error-detail")).toContainText("Refresh and retry");
  await expect(page.locator("#live-region")).toContainText("Resource changed");
  await expect(page.locator("#live-region")).not.toContainText(`Principal ${id} deactivated.`);
  await expect(page.locator("#deactivate-dialog")).toBeVisible();
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1);
  const detail = page.locator(`[data-principal-detail='${id}']`);
  await expect(detail).toContainText("active", { timeout: 20_000 });
  await expect(detail).toContainText(bump.after);
  await page.click("#deactivate-submit");
  await expect(page.locator("#live-region")).toContainText(`Principal ${id} deactivated.`, { timeout: 20_000 });
  await expect(page.locator(`[data-principal-detail='${id}']`)).toContainText("inactive");
});
test("blocks deactivate for invalid/restricted credentials without false mutation", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  const restrictedKey = apiKey("RESTRICTED_HARNESS_API_KEY");
  const id = await createActivePrincipal(page, adminKey, "s03");
  await connect(page, adminKey);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  await openDeactivate(page, id);
  const denied = await page.evaluate(async ({ admin, restricted, principalId }) => {
    const { ApiClientError, createAdministrativeApiClient, createMemoryCredentialStore } = await import("/public/api/client.js");
    async function attempt(key) {
      const store = createMemoryCredentialStore();
      store.set(key);
      const client = createAdministrativeApiClient({ credentialStore: store });
      const fresh = await client.getPrincipal(principalId).catch(() => null);
      const token = fresh?.updated_at ?? "2026-01-01T00:00:00Z";
      try {
        await client.replacePrincipalStatus(principalId, { status: "inactive", expected_updated_at: token });
        return { reached: true };
      } catch (error) {
        if (!(error instanceof ApiClientError)) throw error;
        return { kind: error.kind, status: error.status, code: error.code };
      }
    }
    const bad = await attempt("sre_admn_0123456789abcdefghij");
    const res = await attempt(restricted);
    const store = createMemoryCredentialStore();
    store.set(admin);
    const client = createAdministrativeApiClient({ credentialStore: store });
    const still = (await client.getPrincipal(principalId)).status;
    return { bad, res, still };
  }, { admin: adminKey, restricted: restrictedKey, principalId: id });
  expect(denied.bad.kind).toBe("authentication");
  expect(denied.bad.status).toBe(401);
  expect(denied.res.kind).toBe("authorization");
  expect(denied.res.status).toBe(403);
  expect(denied.bad).not.toEqual(denied.res);
  expect(denied.still).toBe("active");
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1);
  await expect(page.locator("#live-region")).not.toContainText(`Principal ${id} deactivated.`);
  await expect(page.locator("#deactivate-dialog")).toBeVisible();
  // UI submit with an invalid session (credential swap via JS to bypass modal
  // backdrop; the PUT itself is real and must fail 401 without local mutation).
  await page.evaluate((key) => {
    document.getElementById("api-key").value = key;
    document.getElementById("session-form").requestSubmit();
  }, "sre_admn_0123456789abcdefghij");
  await expect(page.locator("#page-error-title")).toHaveText("Authentication required", { timeout: 20_000 });
  await expect(page.locator("#deactivate-dialog")).toBeVisible();
  await page.click("#deactivate-submit");
  await expect(page.locator("#deactivate-error-title")).toHaveText("Authentication required", { timeout: 20_000 });
  await expect(page.locator("#live-region")).not.toContainText(`Principal ${id} deactivated.`);
  await page.evaluate((key) => {
    document.getElementById("api-key").value = key;
    document.getElementById("session-form").requestSubmit();
  }, restrictedKey);
  await expect(page.locator("#page-error-title")).toHaveText("Access unavailable", { timeout: 20_000 });
  await expect(page.locator("#deactivate-dialog")).toBeVisible();
  await page.click("#deactivate-submit");
  await expect(page.locator("#deactivate-error-title")).toHaveText("Access unavailable", { timeout: 20_000 });
  await expect(page.locator("#live-region")).not.toContainText(`Principal ${id} deactivated.`);
  const still = await page.evaluate(async ({ key, principalId }) => {
    const { createAdministrativeApiClient, createMemoryCredentialStore } = await import("/public/api/client.js");
    const store = createMemoryCredentialStore();
    store.set(key);
    const client = createAdministrativeApiClient({ credentialStore: store });
    return (await client.getPrincipal(principalId)).status;
  }, { key: adminKey, principalId: id });
  expect(still).toBe("active");
  await page.click("#deactivate-cancel");
  await page.click("#disconnect-button");
  await connect(page, adminKey);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
});
test("surfaces failed status update without false success", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  const id = await createActivePrincipal(page, adminKey, "s04");
  await connect(page, adminKey);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  await openDeactivate(page, id);
  await page.route("**/api/**/status", (route) => (route.request().method() === "PUT" ? route.abort("failed") : route.continue()));
  await page.click("#deactivate-submit");
  await expect(page.locator("#deactivate-error-title")).toHaveText("API unavailable", { timeout: 20_000 });
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1);
  await expect(page.locator("#live-region")).not.toContainText(`Principal ${id} deactivated.`);
  await expect(page.locator("#deactivate-dialog")).toBeVisible();
  await expect(page.locator("#deactivate-submit")).toBeEnabled();
  await page.unroute("**/api/**/status");
  await page.click("#deactivate-submit");
  await expect(page.locator("#live-region")).toContainText(`Principal ${id} deactivated.`, { timeout: 20_000 });
  await expect(page.locator(`[data-principal-detail='${id}']`)).toContainText("inactive");
});
test("clears the session before a held status response arrives", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  const id = await createActivePrincipal(page, adminKey, "s05");
  await connect(page, adminKey);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  await openDeactivate(page, id);
  let releasePut;
  const gate = new Promise((resolve) => { releasePut = resolve; });
  let puts = 0;
  let putHeld = false;
  const statusPut = (url) => url.pathname === `/api/v1/principals/${id}/status`;
  await page.route(statusPut, async (route) => {
    if (route.request().method() !== "PUT") return route.continue();
    puts += 1;
    putHeld = true;
    await gate;
    await route.continue();
  });
  await page.click("#deactivate-submit");
  await expect.poll(async () => putHeld).toBe(true);
  await expect(page.locator("#deactivate-submit")).toBeDisabled();
  await expect(page.locator("#deactivate-cancel")).toBeDisabled();
  // The open modal backdrop blocks pointer input, so Clear is dispatched
  // on the real handler instead of clicked through the modal.
  await page.locator("#disconnect-button").dispatchEvent("click");
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(0);
  await expect(page.locator("#principal-count")).toHaveText("Not loaded.");
  await expect(page.locator("#page-error")).toBeHidden();
  await expect(page.locator("#live-region")).toHaveText("Session cleared.");
  releasePut();
  await page.waitForTimeout(1000);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(0);
  await expect(page.locator("#principal-count")).toHaveText("Not loaded.");
  await expect(page.locator("#deactivate-dialog")).toBeHidden();
  await expect(page.locator("#live-region")).toHaveText("Session cleared.");
  await expect(page.locator("#live-region")).not.toContainText(`Principal ${id} deactivated.`);
  expect(puts).toBe(1);
  await page.unroute(statusPut);
});
test("drops a stale detail read that resolves after a confirmed deactivation", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  const id = await createActivePrincipal(page, adminKey, "s06");
  await connect(page, adminKey);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  let holdFirstGet = true;
  const detailGet = (url) => url.pathname === `/api/v1/principals/${id}`;
  const statusPut = (url) => url.pathname === `/api/v1/principals/${id}/status`;
  let puts = 0;
  await page.route(detailGet, async (route) => {
    if (route.request().method() === "GET" && holdFirstGet) {
      holdFirstGet = false;
      await new Promise((r) => setTimeout(r, 2500));
    }
    await route.continue();
  });
  await page.route(statusPut, async (route) => {
    if (route.request().method() !== "PUT") return route.continue();
    puts += 1;
    await route.continue();
  });
  await page.click(`[data-expand-principal='${id}']`);
  await page.click(`[data-expand-principal='${id}']`);
  await expect(page.locator(`[data-principal-detail='${id}']`)).toBeVisible({ timeout: 20_000 });
  await page.click(`[data-deactivate-principal='${id}']`);
  await expect(page.locator("#deactivate-dialog")).toBeVisible();
  await page.click("#deactivate-submit");
  await expect(page.locator("#live-region")).toContainText(`Principal ${id} deactivated.`, { timeout: 20_000 });
  await page.waitForTimeout(3000);
  await expect(page.locator(`[data-principal-detail='${id}']`)).toContainText("inactive");
  await expect(page.locator(`[data-deactivate-principal='${id}']`)).toHaveCount(0);
  expect(puts).toBe(1);
  await page.unroute(detailGet);
  await page.unroute(statusPut);
});
test("locks retry when the refresh after a real 409 fails", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  const id = await createActivePrincipal(page, adminKey, "s07");
  await connect(page, adminKey);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  await openDeactivate(page, id);
  await page.evaluate(async ({ key, principalId }) => {
    const { createAdministrativeApiClient, createMemoryCredentialStore } = await import("/public/api/client.js");
    const store = createMemoryCredentialStore();
    store.set(key);
    const client = createAdministrativeApiClient({ credentialStore: store });
    const fresh = await client.getPrincipal(principalId);
    await client.replacePrincipalStatus(principalId, { status: "active", expected_updated_at: fresh.updated_at });
  }, { key: adminKey, principalId: id });
  let puts = 0;
  const statusPut = (url) => url.pathname === `/api/v1/principals/${id}/status`;
  const detailGet = (url) => url.pathname === `/api/v1/principals/${id}`;
  await page.route(statusPut, async (route) => {
    if (route.request().method() !== "PUT") return route.continue();
    puts += 1;
    await route.continue();
  });
  await page.route(detailGet, (route) => {
    if (route.request().method() === "GET") return route.abort("failed");
    return route.continue();
  });
  await page.click("#deactivate-submit");
  await expect(page.locator("#deactivate-error-title")).toHaveText("API unavailable", { timeout: 20_000 });
  await expect(page.locator("#live-region")).toContainText("API unavailable");
  await expect(page.locator("#live-region")).not.toContainText(`Principal ${id} deactivated.`);
  await expect(page.locator("#deactivate-submit")).toBeDisabled();
  await expect(page.locator("#deactivate-cancel")).toBeEnabled();
  await expect(page.locator("#deactivate-dialog")).toBeVisible();
  await page.waitForTimeout(500);
  expect(puts).toBe(1);
  await page.unroute(detailGet);
  await page.click("#deactivate-cancel");
  await expect(page.locator("#deactivate-dialog")).toBeHidden();
  await page.click(`[data-expand-principal='${id}']`);
  await page.click(`[data-expand-principal='${id}']`);
  await expect(page.locator(`[data-principal-detail='${id}']`)).toContainText("active", { timeout: 20_000 });
  await page.click(`[data-deactivate-principal='${id}']`);
  await expect(page.locator("#deactivate-dialog")).toBeVisible();
  await page.click("#deactivate-submit");
  await expect(page.locator("#live-region")).toContainText(`Principal ${id} deactivated.`, { timeout: 20_000 });
  await expect(page.locator(`[data-principal-detail='${id}']`)).toContainText("inactive");
  expect(puts).toBe(2);
  await page.unroute(statusPut);
});
test("closes deactivate without retry when the refresh after 409 finds inactive", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  const id = await createActivePrincipal(page, adminKey, "s08");
  await connect(page, adminKey);
  await expect(page.locator(`[data-principal-row='${id}']`)).toHaveCount(1, { timeout: 20_000 });
  await openDeactivate(page, id);
  await page.evaluate(async ({ key, principalId }) => {
    const { createAdministrativeApiClient, createMemoryCredentialStore } = await import("/public/api/client.js");
    const store = createMemoryCredentialStore();
    store.set(key);
    const client = createAdministrativeApiClient({ credentialStore: store });
    const fresh = await client.getPrincipal(principalId);
    await client.replacePrincipalStatus(principalId, { status: "inactive", expected_updated_at: fresh.updated_at });
  }, { key: adminKey, principalId: id });
  let puts = 0;
  const statusPut = (url) => url.pathname === `/api/v1/principals/${id}/status`;
  await page.route(statusPut, async (route) => {
    if (route.request().method() !== "PUT") return route.continue();
    puts += 1;
    await route.continue();
  });
  await page.click("#deactivate-submit");
  await expect(page.locator("#live-region")).toContainText(`Principal ${id} is now inactive.`, { timeout: 20_000 });
  await expect(page.locator("#deactivate-dialog")).toBeHidden();
  await expect(page.locator(`[data-principal-detail='${id}']`)).toContainText("inactive");
  await expect(page.locator(`[data-deactivate-principal='${id}']`)).toHaveCount(0);
  await page.waitForTimeout(500);
  expect(puts).toBe(1);
  await page.unroute(statusPut);
});
