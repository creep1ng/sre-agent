import { expect, test } from "@playwright/test";

// C06 (issue #143): consumer drilldown to contract 2.8.0 readUsageRequests.
// Offline seam + DOM proof. No backend change. Navigation is unsupported per
// contract, so no incident/run links are ever rendered.
const CONSUMPTION_PATH = "/api/v1/usage/consumption";
const REQUESTS_PATH = "/api/v1/usage/requests";

const json = (status, body) => ({ status, contentType: "application/json", body });

function consumptionBody() {
  return JSON.stringify({
    filter: { request_id: "123e4567-e89b-12d3-a456-426614174000" },
    request_count: 1,
    incident_runs: 0,
    months: [{ month: "2026-10", request_count: 1 }],
    totals: { input_tokens: 5, output_tokens: 7, total_tokens: 12, cost: { amount: null, currency: null, nature: "billed", precision: null, price_versions: [] } },
    coverage: { status: "complete", known: 1, incomplete: 0, unknown: 0 },
  });
}

function requestsBody(items) {
  return JSON.stringify({ filter: { request_id: "123e4567-e89b-12d3-a456-426614174000" }, items });
}

function availableItem() {
  return {
    request_id: "123e4567-e89b-12d3-a456-426614174000",
    month: "2026-10",
    requested_assignment: { availability: "available", alias: "prod-chat", model: "openai/gpt-4o", provider: "openrouter", router: "openrouter" },
    credited_model: { availability: "available", value: "openai/gpt-4o-2024-08-06" },
    credited_provider: { availability: "available", value: "openrouter" },
    attribution_status: "available",
    consumption: null,
    navigation: { status: "unsupported" },
  };
}

function legacyItem() {
  return {
    request_id: "223e4567-e89b-12d3-a456-426614174001",
    month: "2026-10",
    requested_assignment: { availability: "unavailable", alias: null, model: null, provider: null, router: null },
    credited_model: { availability: "unavailable", value: null },
    credited_provider: { availability: "unavailable", value: null },
    attribution_status: "legacy",
    consumption: null,
    navigation: { status: "unsupported" },
  };
}

test("requests client seam requires exactly one selector and uses the bounded path", async ({ page }) => {
  await page.goto("/");
  const evidence = await page.evaluate(async () => {
    const { createAdministrativeApiClient, createMemoryCredentialStore } = await import("/public/api/client.js");
    const calls = [];
    const responseBody = { filter: { month: "2026-10" }, items: [] };
    const client = createAdministrativeApiClient({
      credentialStore: createMemoryCredentialStore(),
      fetchImplementation: async (url, init = {}) => {
        calls.push({ url: String(url), method: init.method ?? "GET" });
        return Response.json(responseBody);
      },
    });
    const failures = [];
    for (const args of [{}, { requestId: "a", incidentId: "b" }, { requestId: "a", month: "2026-10" }, { requestId: "" }, { incidentId: "" }, { month: "" }]) {
      try {
        await client.readUsageRequests(args);
        failures.push(JSON.stringify(args));
      } catch (error) {
        if (!(error instanceof TypeError)) throw error;
      }
    }
    const requestId = "123e4567-e89b-12d3-a456-426614174000";
    const byRequest = await client.readUsageRequests({ requestId });
    const byIncident = await client.readUsageRequests({ incidentId: "incident-a" });
    const byMonth = await client.readUsageRequests({ month: "2026-10" });
    return { calls, failures, byRequest, byIncident, byMonth, responseBody, requestId };
  });
  expect(evidence.failures).toEqual([]);
  expect(evidence.calls).toHaveLength(3);
  for (const call of evidence.calls) {
    expect(call.method).toBe("GET");
    expect(call.url).toContain("/api/v1/usage/requests?");
  }
  const names = (url) => [...new URL(url, "http://localhost").searchParams.keys()].sort();
  const valueOf = (url, name) => new URL(url, "http://localhost").searchParams.get(name);
  expect(names(evidence.calls[0].url)).toEqual(["request_id"]);
  expect(valueOf(evidence.calls[0].url, "request_id")).toBe(evidence.requestId);
  expect(names(evidence.calls[1].url)).toEqual(["incident_id"]);
  expect(names(evidence.calls[2].url)).toEqual(["month"]);
  for (const call of evidence.calls) {
    for (const forbidden of ["from=", "to=", "cursor", "page=", "offset", "continuation_token", "prompt", "output", "api_key", "limit="]) {
      expect(call.url).not.toContain(forbidden);
    }
  }
  expect(evidence.byRequest).toEqual(evidence.responseBody);
});

test("drilldown maps the aggregate selector and renders immutable attribution without links", async ({ page }) => {
  const observed = [];
  await page.route((url) => url.pathname === CONSUMPTION_PATH, (route) => {
    observed.push(new URL(route.request().url()));
    return route.fulfill(json(200, consumptionBody()));
  });
  await page.route((url) => url.pathname === REQUESTS_PATH, (route) => {
    observed.push(new URL(route.request().url()));
    return route.fulfill(json(200, requestsBody([availableItem(), legacyItem()])));
  });
  await page.goto("/public/admin/consumption.html");
  await page.fill("#api-key", "sre_admn_0123456789abcdefghijklmnop");
  await page.click("#connect-button");
  await page.fill("#request-id", "123e4567-e89b-12d3-a456-426614174000");
  await page.click("#query-submit");
  await expect(page.locator("#result-list")).toBeVisible();
  await expect(page.locator("#request-detail-list")).toBeVisible();
  await expect(page.locator("[data-request-row='123e4567-e89b-12d3-a456-426614174000']")).toContainText("prod-chat");
  await expect(page.locator("[data-request-row='123e4567-e89b-12d3-a456-426614174000']")).toContainText("openai/gpt-4o");
  await expect(page.locator("[data-request-row='123e4567-e89b-12d3-a456-426614174000']")).toContainText("openrouter");
  await expect(page.locator("[data-request-row='223e4567-e89b-12d3-a456-426614174001']")).toContainText("Historical unavailable");
  await expect(page.locator("#request-detail-list a")).toHaveCount(0);
  const bodyText = await page.locator("body").innerText();
  expect(bodyText).not.toContain("prompt");
  const requestsUrl = observed.find((url) => url.pathname === REQUESTS_PATH);
  expect(requestsUrl.searchParams.get("request_id")).toBe("123e4567-e89b-12d3-a456-426614174000");
  expect([...requestsUrl.searchParams.keys()].sort()).toEqual(["request_id"]);
  if (process.env.CONSUMPTION_DRILLDOWN_SCREENSHOT)
    await page.screenshot({ path: process.env.CONSUMPTION_DRILLDOWN_SCREENSHOT, fullPage: true });
});

test("drilldown reports auth and storage failures distinctly without inventing rows", async ({ page }) => {
  await page.route((url) => url.pathname === CONSUMPTION_PATH, (route) => route.fulfill(json(200, consumptionBody())));
  let status = 401;
  let body = "{}";
  await page.route((url) => url.pathname === REQUESTS_PATH, (route) => route.fulfill(json(status, body)));
  await page.goto("/public/admin/consumption.html");
  await page.fill("#api-key", "sre_admn_0123456789abcdefghijklmnop");
  await page.click("#connect-button");
  await page.fill("#request-id", "123e4567-e89b-12d3-a456-426614174000");
  await page.click("#query-submit");
  await expect(page.locator("#result-list")).toBeVisible();
  await expect(page.locator("#request-detail-status")).toContainText("Authentication required");
  await expect(page.locator("[data-request-row]")).toHaveCount(0);
  status = 503;
  body = JSON.stringify({ error: { code: "storage_unavailable", message: "unavailable" } });
  await page.click("#query-submit");
  await expect(page.locator("#request-detail-status")).toContainText("Consumption unavailable");
  await expect(page.locator("[data-request-row]")).toHaveCount(0);
});

// Consumption limits (issue #142). Failure modes covered: null shown as 0 or 0 sent as
// null; the typed value shown as accepted instead of the server's answer; a stale version
// overwriting the policy or hiding the conflict; invalid values sent or a 422 shown as
// saved; a 403 revealing a partial policy; a retry minting a new key or a changed payload
// reusing the old one; the previous session's policy left on screen.
const LIMITS_PATH = "/api/v1/consumption-limits";
const policy = (version, incident, monthly) => ({
  version, incident_token_limit: incident, monthly_usd_limit: monthly, updated_at: `2026-10-0${version}T00:00:00Z`,
});

async function connectLimits(page) {
  await page.goto("/public/admin/consumption.html");
  await page.fill("#api-key", "sre_admn_0123456789abcdefghijklmnop");
  await page.click("#connect-button");
}

test("limits panel shows the server policy and saves exactly what the contract defines", async ({ page }) => {
  const puts = [];
  let failNext = true;
  await page.route((url) => url.pathname === LIMITS_PATH, (route) => {
    const request = route.request();
    if (request.method() === "GET") return route.fulfill(json(200, JSON.stringify(policy(3, 0, null))));
    puts.push({ body: request.postDataJSON(), key: request.headers()["idempotency-key"] });
    if (failNext) {
      failNext = false;
      return route.abort("failed");
    }
    return route.fulfill(json(200, JSON.stringify(policy(4, null, "0.5"))));
  });
  await connectLimits(page);
  await expect(page.locator("#limits-incident")).toHaveText("0");
  await expect(page.locator("#limits-monthly")).toHaveText("Not configured");
  await expect(page.locator("#limits-version")).toHaveText("3");
  await expect(page.locator("#limits-incident-input")).toHaveValue("0");
  await expect(page.locator("#limits-monthly-input")).toHaveValue("");

  for (const [tokens, usd] of [["-1", ""], ["1.5", ""], ["", "1.1234567890123"], ["", "abc"]]) {
    await page.fill("#limits-incident-input", tokens);
    await page.fill("#limits-monthly-input", usd);
    await page.click("#limits-submit");
    await expect(page.locator("#limits-status")).toContainText("Nothing was sent");
  }
  expect(puts).toHaveLength(0);

  await page.fill("#limits-incident-input", "");
  await page.fill("#limits-monthly-input", "0.50");
  await page.click("#limits-submit");
  await expect(page.locator("#limits-status")).toContainText("Not saved: API unavailable");
  await expect(page.locator("#limits-monthly")).toHaveText("Not configured");
  await page.click("#limits-submit");
  await expect(page.locator("#limits-status")).toHaveText("Saved: policy version 4 applies to new gateway admissions.");
  await expect(page.locator("#limits-monthly")).toHaveText("0.5");
  await expect(page.locator("#limits-incident")).toHaveText("Not configured");
  expect(puts.map((put) => put.body)).toEqual([
    { expected_version: 3, incident_token_limit: null, monthly_usd_limit: "0.50" },
    { expected_version: 3, incident_token_limit: null, monthly_usd_limit: "0.50" },
  ]);
  expect(puts[0].key).toMatch(/^limits-[0-9a-f]{32}$/);
  expect(puts[1].key).toBe(puts[0].key);

  await page.fill("#limits-incident-input", "0");
  await page.click("#limits-submit");
  await expect(page.locator("#limits-status")).toContainText("Saved: policy version 4");
  expect(puts[2].body).toEqual({ expected_version: 4, incident_token_limit: 0, monthly_usd_limit: "0.5" });
  expect(puts[2].key).not.toBe(puts[0].key);

  await page.click("#disconnect-button");
  await expect(page.locator("#limits-current")).toBeHidden();
  await expect(page.locator("#limits-form")).toBeHidden();
  await expect(page.locator("#limits-status")).toHaveText("Connect to load the policy.");
});

test("limits panel reloads on a version conflict and keeps the policy on rejection", async ({ page }) => {
  let current = policy(5, 1000, "10");
  let putStatus = 409;
  await page.route((url) => url.pathname === LIMITS_PATH, (route) => {
    if (route.request().method() === "GET") return route.fulfill(json(200, JSON.stringify(current)));
    return route.fulfill(json(putStatus, JSON.stringify({ error: { code: putStatus === 409 ? "status_conflict" : "validation_error" } })));
  });
  await connectLimits(page);
  await expect(page.locator("#limits-version")).toHaveText("5");
  current = policy(6, 2000, "20");
  await page.fill("#limits-monthly-input", "15");
  await page.click("#limits-submit");
  await expect(page.locator("#limits-status")).toHaveText("The policy changed elsewhere (409). The current version is shown; nothing was overwritten.");
  await expect(page.locator("#limits-version")).toHaveText("6");
  await expect(page.locator("#limits-monthly")).toHaveText("20");
  putStatus = 422;
  await page.fill("#limits-monthly-input", "15");
  await page.click("#limits-submit");
  await expect(page.locator("#limits-status")).toHaveText("Invalid limits (rejected by the API). The active policy is unchanged.");
  await expect(page.locator("#limits-monthly")).toHaveText("20");
  await expect(page.locator("#page-error")).toBeHidden();
});

test("limits panel reveals nothing to an identity without access", async ({ page }) => {
  await page.route((url) => url.pathname === LIMITS_PATH, (route) =>
    route.fulfill(json(403, JSON.stringify({ error: { code: "resource_unavailable" } }))));
  await connectLimits(page);
  await expect(page.locator("#limits-status")).toHaveText("Consumption limits unavailable: Access unavailable.");
  await expect(page.locator("#limits-current")).toBeHidden();
  await expect(page.locator("#limits-form")).toBeHidden();
});

test("limits panel persists a real policy change and restores it", async ({ page, request }) => {
  test.skip(process.env.PLAYWRIGHT_PRODUCTION_TOPOLOGY !== "1", "requires the connected control-plane API");
  const admin = process.env.ADMIN_HUMAN_API_KEY;
  test.skip(!admin, "requires ADMIN_HUMAN_API_KEY");
  await page.goto("/public/admin/consumption.html");
  await page.fill("#api-key", admin);
  await page.click("#connect-button");
  await expect(page.locator("#limits-form")).toBeVisible({ timeout: 20_000 });
  const before = { tokens: await page.inputValue("#limits-incident-input"), usd: await page.inputValue("#limits-monthly-input") };
  const version = Number(await page.locator("#limits-version").innerText());
  await page.fill("#limits-incident-input", "123456");
  await page.fill("#limits-monthly-input", "7.25");
  await page.click("#limits-submit");
  await expect(page.locator("#limits-status")).toHaveText(`Saved: policy version ${version + 1} applies to new gateway admissions.`);
  if (process.env.CONSUMPTION_LIMITS_SCREENSHOT)
    await page.locator("#limits-panel").screenshot({ path: process.env.CONSUMPTION_LIMITS_SCREENSHOT });
  await page.reload();
  await page.fill("#api-key", admin);
  await page.click("#connect-button");
  await expect(page.locator("#limits-incident")).toHaveText("123456", { timeout: 20_000 });
  await expect(page.locator("#limits-monthly")).toHaveText("7.25");
  const stale = await request.put("/api/v1/consumption-limits", {
    headers: { Authorization: `Bearer ${admin}`, "Idempotency-Key": `limits-stale-${Date.now()}-check` },
    data: { expected_version: version, incident_token_limit: null, monthly_usd_limit: null },
  });
  expect(stale.status()).toBe(409);
  await page.fill("#limits-incident-input", before.tokens);
  await page.fill("#limits-monthly-input", before.usd);
  await page.click("#limits-submit");
  await expect(page.locator("#limits-status")).toHaveText(`Saved: policy version ${version + 2} applies to new gateway admissions.`);
  const restricted = process.env.RESTRICTED_HARNESS_API_KEY;
  if (restricted) {
    await page.click("#disconnect-button");
    await page.fill("#api-key", restricted);
    await page.click("#connect-button");
    await expect(page.locator("#limits-status")).toHaveText("Consumption limits unavailable: Access unavailable.", { timeout: 20_000 });
    await expect(page.locator("#limits-current")).toBeHidden();
  }
});
