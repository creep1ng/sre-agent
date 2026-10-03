import { expect, test } from "@playwright/test";

// S1 foundation for issue #21 [HU-ADM-03A]. The grants/catalog reads are
// blocked by backend issue #423 (no seed grants cover grants.list/catalog),
// so render paths fulfill synthetic payloads at the HTTP seam while every
// request URL asserted below is issued by the real page + client code.
const connected = process.env.PLAYWRIGHT_PRODUCTION_TOPOLOGY === "1";

function apiKey(name) {
  const value = process.env[name];
  test.skip(!value, `requires ${name}`);
  return value;
}

async function storageContents(page) {
  return page.evaluate(() => ({ local: { ...window.localStorage }, session: { ...window.sessionStorage } }));
}

function grantPayload(items) {
  return { items, limit: 100, truncated: false };
}

function grantItem(overrides = {}) {
  return {
    grant_id: "grant-admin-human-admin-read-principals",
    principal_id: "admin-human",
    action: "admin.read",
    resource: { resource_type: "administrative_control", resource_id: "principals" },
    effect: "allow",
    status: "active",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function principalsPayload() {
  return {
    items: [
      { principal_id: "admin-human", kind: "human", display_name: "Admin human", status: "active" },
      { principal_id: "incident-harness", kind: "agent", display_name: "Incident harness", status: "active" },
      { principal_id: "retired-harness", kind: "agent", display_name: "Retired", status: "inactive" },
    ],
    limit: 100,
    truncated: false,
  };
}

function catalogPayload() {
  return {
    items: [
      {
        resource_type: "llm_model",
        resource_id: "triage-agent",
        owner_id: "triage-agent",
        status: "active",
        source: "model_alias",
        source_ref: "triage-agent",
        // Assignment-plane fields the grants UI must never read nor render.
        concrete_model: "concrete-model-should-never-render",
        router: "router-should-never-render",
        inference_provider: "provider-should-never-render",
        discoverability: { display_name: "Triage agent", visibility: "private", description: "", tags: [] },
      },
      {
        resource_type: "administrative_control",
        resource_id: "grants",
        owner_id: "admin-human",
        status: "active",
        source: "admin",
        source_ref: "grants",
        discoverability: { display_name: "Grants", visibility: "private", description: "", tags: [] },
      },
      {
        resource_type: "llm_model",
        resource_id: "retired-model",
        owner_id: "triage-agent",
        status: "inactive",
        source: "model_alias",
        source_ref: "retired-model",
        discoverability: { display_name: "Retired model", visibility: "private", description: "", tags: [] },
      },
    ],
    limit: 100,
    truncated: false,
  };
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
  await page.goto("/public/admin/grants.html");
  await expect(page.locator("#grants-page")).toHaveAttribute("data-state", "idle");
});

test.afterEach(async ({ page }) => {
  expect(page.context()["__consoleErrors"] ?? []).toEqual([]);
});

test("client refuses bare or dual-filter grants GETs without touching the network", async ({ page }) => {
  const result = await page.evaluate(async () => {
    const { createAdministrativeApiClient, createMemoryCredentialStore } =
      await import("/public/api/client.js");
    let calls = 0;
    const client = createAdministrativeApiClient({
      credentialStore: createMemoryCredentialStore(),
      fetchImplementation: async () => {
        calls += 1;
        return Response.json({ items: [], limit: 100, truncated: false });
      },
    });
    const failures = [];
    for (const args of [{}, { principalId: "a", resourceId: "b" }, { principalId: "" }, { limit: 5 }]) {
      try {
        await client.listGrants(args);
        failures.push(JSON.stringify(args));
      } catch (error) {
        if (!(error instanceof TypeError)) throw error;
      }
    }
    const url = await client.listGrants({ principalId: "admin-human" }).then(
      () => null,
      () => null,
    );
    return { calls, failures, url };
  });
  expect(result.failures).toEqual([]);
  expect(result.calls).toBe(1);
});

test("principal filter loads grants over an exactly-one-filter GET and renders them", async ({ page }) => {
  const grantUrls = [];
  await page.route("**/api/v1/principals?limit=100", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(principalsPayload()) }),
  );
  await page.route("**/api/v1/catalog/resources**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalogPayload()) }),
  );
  await page.route("**/api/v1/grants**", async (route) => {
    grantUrls.push(route.request().url());
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        grantPayload([
          grantItem(),
          grantItem({ grant_id: "grant-revoked-1", status: "revoked" }),
        ]),
      ),
    });
  });
  await page.fill("#api-key", "sre_s1_placeholder_key_for_seam_fulfillment");
  await page.click("#connect-button");
  await expect(page.locator("#principal-filter option[value='admin-human']")).toHaveCount(1);
  // Inactive principals stay queryable for history; active ones are creation candidates.
  await expect(page.locator("#principal-filter option[value='retired-harness']")).toHaveCount(1);
  expect(await page.locator("#principal-filter option[value='admin-human']").getAttribute("data-creation-candidate")).toBe("true");
  await page.selectOption("#principal-filter", "admin-human");
  await expect(page.locator("[data-grant-row]")).toHaveCount(2);
  expect(grantUrls.length).toBeGreaterThan(0);
  for (const url of grantUrls) {
    expect(url).toContain("principal_id=admin-human");
    expect(url).not.toContain("resource_id=");
  }
  const firstRow = await page.locator("[data-grant-row]").first().textContent();
  expect(firstRow).toContain("grant-admin-human-admin-read-principals");
  expect(firstRow).toContain("admin-human");
  expect(firstRow).toContain("admin.read");
  expect(firstRow).toContain("administrative_control/principals");
  await expect(page.locator("[data-grant-row='grant-revoked-1']")).toContainText("revoked");
  await expect(page.locator("#resource-filter")).toHaveValue("");
  await expect(page.locator("#create-grant-button")).toBeVisible();
  await expect(page.locator("#create-grant-button")).toBeEnabled();
  expect(await page.locator("#grant-count").textContent()).toMatch(/grant/);
  expect(await storageContents(page)).toEqual({ local: {}, session: {} });
  const leak = await page.evaluate(() => ({ href: location.href, body: document.body.textContent ?? "" }));
  expect(leak.href).not.toContain("sre_s1_placeholder");
  expect(leak.body).not.toContain("sre_s1_placeholder");
  expect(/\bsre_[A-Za-z0-9_-]{24,128}\b/.test(leak.body)).toBe(false);
});

test("resource filter replaces the principal filter and preserves XOR", async ({ page }) => {
  const grantUrls = [];
  await page.route("**/api/v1/principals?limit=100", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(principalsPayload()) }),
  );
  await page.route("**/api/v1/catalog/resources**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalogPayload()) }),
  );
  await page.route("**/api/v1/grants**", async (route) => {
    const url = route.request().url();
    grantUrls.push(url);
    const items = url.includes("resource_id=")
      ? [grantItem({ grant_id: "grant-incident-harness-invoke-triage-agent", principal_id: "incident-harness", action: "invoke", resource: { resource_type: "llm_model", resource_id: "triage-agent" } })]
      : [grantItem()];
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(grantPayload(items)) });
  });
  await page.fill("#api-key", "sre_s1_placeholder_key_for_seam_fulfillment");
  await page.click("#connect-button");
  await expect(page.locator("#resource-filter option[value='triage-agent']")).toHaveCount(1);
  await expect(page.locator("#resource-filter")).toContainText("llm_model/triage-agent");
  await page.selectOption("#principal-filter", "admin-human");
  await expect(page.locator("[data-grant-row='grant-admin-human-admin-read-principals']")).toHaveCount(1);
  await page.selectOption("#resource-filter", "triage-agent");
  await expect(page.locator("#principal-filter")).toHaveValue("");
  await expect(page.locator("[data-grant-row='grant-incident-harness-invoke-triage-agent']")).toHaveCount(1);
  await expect(page.locator("[data-grant-row='grant-admin-human-admin-read-principals']")).toHaveCount(0);
  const resourceUrls = grantUrls.filter((url) => url.includes("resource_id=triage-agent"));
  expect(resourceUrls.length).toBeGreaterThan(0);
  for (const url of resourceUrls) expect(url).not.toContain("principal_id=");
  await expect(page.locator("[data-grant-row='grant-incident-harness-invoke-triage-agent']")).toContainText("llm_model/triage-agent");
  const pageText = (await page.locator("#grants-page").textContent()) ?? "";
  expect(pageText).not.toContain("concrete-model-should-never-render");
  expect(pageText).not.toContain("router-should-never-render");
  expect(pageText).not.toContain("provider-should-never-render");
});

test("absence is an explicit deny and failures clear stale rows", async ({ page }) => {
  await page.route("**/api/v1/principals?limit=100", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(principalsPayload()) }),
  );
  await page.route("**/api/v1/grants**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(grantPayload([])) }),
  );
  await page.fill("#api-key", "sre_s1_placeholder_key_for_seam_fulfillment");
  await page.click("#connect-button");
  await expect(page.locator("#principal-filter option[value='admin-human']")).toHaveCount(1);
  await page.selectOption("#principal-filter", "admin-human");
  await expect(page.locator("#grants-page")).toHaveAttribute("data-state", "empty");
  await expect(page.locator("#list-empty-title")).toHaveText("No active grant matches.");
  await expect(page.locator("#list-empty-detail")).toContainText("Absent grant implies deny");
  await expect(page.locator("#page-error")).toBeHidden();
  await expect(page.locator("[data-grant-row]")).toHaveCount(0);

  await page.unrouteAll({ behavior: "wait" });
  await page.route("**/api/v1/grants**", (route) =>
    route.fulfill({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "validation_error", message: "Invalid grant filter." } }),
    }),
  );
  await page.selectOption("#principal-filter", "");
  await page.selectOption("#principal-filter", "admin-human");
  await expect(page.locator("#page-error-title")).toHaveText("Invalid grant filter");
  await expect(page.locator("[data-grant-row]")).toHaveCount(0);

  await page.unrouteAll({ behavior: "wait" });
  await page.route("**/api/v1/grants**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(grantPayload([grantItem()])) }),
  );
  await page.selectOption("#principal-filter", "");
  await page.selectOption("#principal-filter", "admin-human");
  await expect(page.locator("[data-grant-row]")).toHaveCount(1);
  const stale = await page.locator("[data-grant-row]").first().textContent();

  await page.unrouteAll({ behavior: "wait" });
  await page.route("**/api/v1/grants**", (route) => route.abort("failed"));
  await page.selectOption("#principal-filter", "");
  await page.selectOption("#principal-filter", "admin-human");
  await expect(page.locator("#page-error-title")).toHaveText("API unavailable");
  await expect(page.locator("[data-grant-row]")).toHaveCount(0);
  expect(await page.locator("#grant-rows").textContent()).not.toContain(stale);
});

test("restricted identity and invalid keys see no rows", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  await page.fill("#api-key", "sre_admn_0123456789abcdefghij");
  await page.click("#connect-button");
  await expect(page.locator("#page-error-title")).toHaveText("Authentication required", { timeout: 20_000 });
  await expect(page.locator("[data-grant-row]")).toHaveCount(0);
  await page.click("#disconnect-button");
  await page.fill("#api-key", apiKey("RESTRICTED_HARNESS_API_KEY"));
  await page.click("#connect-button");
  await expect(page.locator("#page-error-title")).toHaveText("Access unavailable", { timeout: 20_000 });
  await expect(page.locator("[data-grant-row]")).toHaveCount(0);
  await expect(page.locator("#grant-count")).toHaveText("Not loaded.");
});

async function connectWithGrantRoutes(page, postStatus) {
  await page.route("**/api/v1/principals?limit=100", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(principalsPayload()) }),
  );
  await page.route("**/api/v1/catalog/resources**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(catalogPayload()) }),
  );
  const posted = [];
  let createdSeen = false;
  const createdGrant = () =>
    grantItem({
      grant_id: "grant-incident-harness-invoke-triage-agent",
      principal_id: "incident-harness",
      action: "invoke",
      resource: { resource_type: "llm_model", resource_id: "triage-agent" },
    });
  await page.route("**/api/v1/grants**", async (route) => {
    if (route.request().method() === "POST") {
      posted.push({
        body: JSON.parse(route.request().postData() ?? "{}"),
        idempotencyKey: await route.request().headerValue("idempotency-key"),
      });
      if (postStatus === 201) {
        createdSeen = true;
        await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(createdGrant()) });
      } else {
        await route.fulfill({
          status: 409,
          contentType: "application/json",
          body: JSON.stringify({ error: { code: "idempotency_conflict", message: "Grant already exists." } }),
        });
      }
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(grantPayload(createdSeen ? [createdGrant()] : [])),
    });
  });
  await page.fill("#api-key", "sre_s1_placeholder_key_for_seam_fulfillment");
  await page.click("#connect-button");
  await expect(page.locator("#create-grant-button")).toBeEnabled();
  return { posted };
}

test("create flow posts a real grant body, announces 201 and refreshes without reload", async ({ page }) => {
  const { posted } = await connectWithGrantRoutes(page, 201);
  await expect(page.locator("#create-principal option[value='incident-harness']")).toHaveCount(1);
  await expect(page.locator("#create-principal option[value='retired-harness']")).toHaveCount(0);
  await expect(page.locator("#create-resource option[value='llm_model/triage-agent']")).toHaveCount(1);
  await expect(page.locator("#create-resource option[value='administrative_control/grants']")).toHaveCount(1);
  await expect(page.locator("#create-resource option[value='llm_model/retired-model']")).toHaveCount(0);
  await expect(page.locator("#create-action option")).toHaveCount(8);
  await page.click("#create-grant-button");
  await expect(page.locator("#create-dialog")).toBeVisible();
  await page.fill("#create-grant-id", "grant-incident-harness-invoke-triage-agent");
  await page.selectOption("#create-principal", "incident-harness");
  await page.selectOption("#create-action", "invoke");
  await page.selectOption("#create-resource", "llm_model/triage-agent");
  await page.click("#create-submit");
  await expect(page.locator("#live-region")).toContainText(
    "Grant grant-incident-harness-invoke-triage-agent ready (201 created or stable replay).",
  );
  await expect(page.locator("#create-dialog")).toBeHidden();
  await expect(page.locator("[data-grant-row='grant-incident-harness-invoke-triage-agent']")).toHaveCount(1);
  expect(posted).toHaveLength(1);
  expect(posted[0].body).toEqual({
    grant_id: "grant-incident-harness-invoke-triage-agent",
    principal_id: "incident-harness",
    action: "invoke",
    resource: { resource_type: "llm_model", resource_id: "triage-agent" },
    effect: "allow",
  });
  expect(posted[0].idempotencyKey).toMatch(/^grant-create-[0-9a-f]{32}$/);
  const pageText = (await page.locator("#grants-page").textContent()) ?? "";
  expect(pageText).not.toContain("concrete-model-should-never-render");
  expect(pageText).not.toContain("router-should-never-render");
  expect(pageText).not.toContain("provider-should-never-render");
});

test("duplicate grant keeps the dialog with 409 wording and adds no row", async ({ page }) => {
  await connectWithGrantRoutes(page, 409);
  await page.click("#create-grant-button");
  await expect(page.locator("#create-dialog")).toBeVisible();
  await page.fill("#create-grant-id", "grant-admin-human-admin-read-grants");
  await page.selectOption("#create-principal", "admin-human");
  await page.selectOption("#create-action", "admin.read");
  await page.selectOption("#create-resource", "administrative_control/grants");
  await page.click("#create-submit");
  await expect(page.locator("#create-error-title")).toHaveText("Grant already exists (409 duplicate)");
  await expect(page.locator("#create-dialog")).toBeVisible();
  await expect(page.locator("#create-grant-id")).toHaveValue("grant-admin-human-admin-read-grants");
  await expect(page.locator("[data-grant-row]")).toHaveCount(0);
});
