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
