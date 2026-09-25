import { expect, test } from "@playwright/test";

const connected = process.env.PLAYWRIGHT_PRODUCTION_TOPOLOGY === "1";
const ALIAS = "triage-agent";
const ALT_ASSIGNMENT = { concrete_model: "openai/gpt-5", router: "openrouter", inference_provider: "openai" };

async function seamGet(page, key, id) {
  return page.evaluate(
    async ({ key, id }) => {
      const { ApiClientError, createAdministrativeApiClient, createMemoryCredentialStore } =
        await import("/public/api/client.js");
      const store = createMemoryCredentialStore();
      store.set(key);
      try {
        return {
          ok: true,
          item: await createAdministrativeApiClient({ credentialStore: store }).getModelAlias(id),
        };
      } catch (error) {
        if (!(error instanceof ApiClientError)) throw error;
        return { ok: false, kind: error.kind, status: error.status, code: error.code };
      }
    },
    { key, id },
  );
}

async function seamPut(page, key, id, body) {
  return page.evaluate(
    async ({ key, id, body }) => {
      const { ApiClientError, createAdministrativeApiClient, createMemoryCredentialStore } =
        await import("/public/api/client.js");
      const store = createMemoryCredentialStore();
      store.set(key);
      try {
        return {
          ok: true,
          item: await createAdministrativeApiClient({ credentialStore: store }).replaceModelAliasAssignment(
            id,
            body,
          ),
        };
      } catch (error) {
        if (!(error instanceof ApiClientError)) throw error;
        return { ok: false, kind: error.kind, status: error.status, code: error.code };
      }
    },
    { key, id, body },
  );
}

async function openAssignmentEdit(page, id) {
  await page.click(`[data-detail-open='${id}']`);
  await expect(page.locator("[data-detail-field='alias']")).toHaveText(id);
  await expect(page.locator("#detail-edit-button")).toBeVisible();
  await page.click("#detail-edit-button");
  await expect(page.locator("#assignment-form")).toBeVisible();
}

async function restoreAssignment(page, key, id, original) {
  const fresh = await seamGet(page, key, id);
  expect(fresh.ok).toBe(true);
  const restored = await seamPut(page, key, id, {
    concrete_model: original.concrete_model,
    router: original.router,
    inference_provider: original.inference_provider,
    expected_updated_at: fresh.item.updated_at,
  });
  expect(restored.ok).toBe(true);
}

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

async function openTriageDetail(page) {
  await expect(page.locator(`[data-alias-row='${ALIAS}']`)).toHaveCount(1, { timeout: 20_000 });
  await openAssignmentEdit(page, ALIAS);
}

async function fillAssignment(page, assignment) {
  await page.fill("#edit-concrete-model", assignment.concrete_model);
  await page.fill("#edit-router", assignment.router);
  await page.fill("#edit-inference-provider", assignment.inference_provider);
}

test("admin opens assignment edit for triage-agent", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  const probe = await seamGet(page, adminKey, ALIAS);
  expect(probe.ok).toBe(true);
  await connect(page, adminKey);
  await expect(page.locator(`[data-alias-row='${ALIAS}']`)).toHaveCount(1, { timeout: 20_000 });
  await openAssignmentEdit(page, ALIAS);
  await expect(page.locator("#edit-concrete-model")).toHaveValue(probe.item.concrete_model);
  await expect(page.locator("#edit-router")).toHaveValue(probe.item.router);
  await expect(page.locator("#edit-inference-provider")).toHaveValue(probe.item.inference_provider);
});

test("reassigns triage-agent and persists the authoritative assignment", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
  const before = (await seamGet(page, adminKey, ALIAS)).item;
  try {
    await connect(page, adminKey);
    await expect(page.locator(`[data-alias-row='${ALIAS}']`)).toHaveCount(1, { timeout: 20_000 });
    await openAssignmentEdit(page, ALIAS);
    let putBody = null;
    await page.route(`**/api/v1/model-aliases/${ALIAS}/assignment`, async (route) => {
      if (route.request().method() === "PUT") putBody = route.request().postDataJSON();
      await route.continue();
    });
    await fillAssignment(page, ALT_ASSIGNMENT);
    await page.click("#assignment-save-button");
    // Valid PUT persists: authoritative 200, closed body, token matches V1.
    await expect(page.locator("#live-region")).toContainText(`Assignment updated for ${ALIAS}.`, {
      timeout: 20_000,
    });
    expect(Object.keys(putBody ?? {}).sort()).toEqual([
      "concrete_model",
      "expected_updated_at",
      "inference_provider",
      "router",
    ]);
    expect(putBody.expected_updated_at).toBe(before.updated_at);
    await expect(page.locator("[data-detail-field='concrete_model']")).toHaveText(
      ALT_ASSIGNMENT.concrete_model,
    );
    await expect(page.locator("[data-detail-field='updated_at']")).not.toHaveText(before.updated_at);
    const rowText = (await page.locator(`[data-alias-row='${ALIAS}']`).textContent()) ?? "";
    expect(rowText).toContain(ALT_ASSIGNMENT.concrete_model);
    // alias stays: logical identity unchanged by assignment mutation.
    await expect(page.locator("[data-detail-field='alias']")).toHaveText(ALIAS);
    await expect(page.locator("[data-detail-field='model_alias_id']")).toHaveText(ALIAS);
    // reload confirms persistence.
    await page.reload();
    await expect(page.locator("#model-aliases-page")).toHaveAttribute("data-state", "idle");
    await connect(page, adminKey);
    await expect(page.locator(`[data-alias-row='${ALIAS}']`)).toHaveCount(1, { timeout: 20_000 });
    await page.click(`[data-detail-open='${ALIAS}']`);
    await expect(page.locator("[data-detail-field='concrete_model']")).toHaveText(
      ALT_ASSIGNMENT.concrete_model,
    );
    await expect(page.locator("[data-detail-field='alias']")).toHaveText(ALIAS);
    await page.unroute(`**/api/v1/model-aliases/${ALIAS}/assignment`);
  } finally {
    await restoreAssignment(page, adminKey, ALIAS, before);
    await page.unrouteAll({ behavior: "wait" }).catch(() => {});
  }
});

for (const field of ["concrete_model", "router", "inference_provider"]) {
  test(`does not submit when ${field} is missing`, async ({ page }) => {
    test.skip(!connected, "requires the connected control-plane API");
    const adminKey = apiKey("ADMIN_HUMAN_API_KEY");
    const before = (await seamGet(page, adminKey, ALIAS)).item;
    await connect(page, adminKey);
    await openTriageDetail(page);
    let puts = 0;
    const predicate = (url) => url.pathname === `/api/v1/model-aliases/${ALIAS}/assignment`;
    await page.route(predicate, async (route) => {
      if (route.request().method() === "PUT") puts += 1;
      await route.continue();
    });
    const filled = { ...before, concrete_model: before.concrete_model, router: before.router, inference_provider: before.inference_provider };
    filled[field] = "";
    await page.fill("#edit-concrete-model", filled.concrete_model);
    await page.fill("#edit-router", filled.router);
    await page.fill("#edit-inference-provider", filled.inference_provider);
    await page.click("#assignment-save-button");
    await expect(page.locator("#detail-error-title")).toHaveText("Invalid assignment", {
      timeout: 20_000,
    });
    await expect(page.locator("#assignment-form")).toBeVisible();
    await page.waitForTimeout(500);
    expect(puts).toBe(0);
    const after = await seamGet(page, adminKey, ALIAS);
    expect(after.item.updated_at).toBe(before.updated_at);
    await page.unroute(predicate);
  });
}
