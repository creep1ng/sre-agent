import { expect, test } from "@playwright/test";

const connected = process.env.PLAYWRIGHT_PRODUCTION_TOPOLOGY === "1";
const LIST_PATH = "/api/v1/audit-events";

function apiKey(name) {
  const value = process.env[name];
  test.skip(!value, `requires ${name}`);
  return value;
}

function eventItem(id) {
  return {
    event_id: id, occurred_at: "2026-09-20T10:00:00Z", operation: "responses.create",
    outcome: "success", identity: { principal_kind: "human" }, content_state: "absent",
  };
}

const json = (status, body) => ({ status, contentType: "application/json", body });

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
  await page.goto("/public/admin/audit-events.html");
  await expect(page.locator("#audit-events-page")).toHaveAttribute("data-state", "idle");
});

test.afterEach(async ({ page }) => {
  expect(page.context()["__consoleErrors"] ?? []).toEqual([]);
});

test("renders a list with only contract parameters and reports empty results", async ({ page }) => {
  let observed = null;
  let items = [eventItem("evt-alpha-01"), eventItem("evt-alpha-02")];
  await page.route((url) => url.pathname === LIST_PATH, (route) => {
    observed = new URL(route.request().url());
    return route.fulfill(json(200, JSON.stringify({ items })));
  });
  await page.fill("#filter-decision", "allow");
  await page.fill("#filter-limit", "");
  await page.fill("#api-key", "sre_admn_0123456789abcdefghijklmnop");
  await page.click("#connect-button");
  await expect(page.locator("#audit-events-page")).toHaveAttribute("data-state", "ready");
  await expect(page.locator("[data-event-row]")).toHaveCount(2);
  await expect(page.locator("[data-event-row='evt-alpha-01']")).toContainText("2026-09-20");
  expect(observed.searchParams.get("decision")).toBe("allow");
  expect(observed.searchParams.get("limit")).toBe("100");
  for (const forbidden of ["page", "offset", "continuation_token", "next", "content", "include_content"])
    expect(observed.searchParams.has(forbidden)).toBe(false);
  expect(observed.search).not.toContain("cursor");
  items = [];
  await page.click("#apply-button");
  await expect(page.locator("#audit-events-page")).toHaveAttribute("data-state", "empty");
  await expect(page.locator("#event-count")).toHaveText("No audit events.");
  await expect(page.locator("#page-error")).toBeHidden();
});

test("renders authentication, authorization, validation and outage failures distinctly", async ({ page }) => {
  let status = 401;
  let body = "{}";
  await page.route((url) => url.pathname === LIST_PATH, (route) => route.fulfill(json(status, body)));
  for (const [next, code, title] of [[401, null, "Authentication required"], [403, null, "Access unavailable"], [422, "validation_error", "Invalid request"], [503, "audit_unavailable", "Service unavailable"]]) {
    status = next;
    body = code === null ? "{}" : JSON.stringify({ error: { code, message: title } });
    await page.click("#apply-button");
    await expect(page.locator("#page-error-title")).toHaveText(title);
    await expect(page.locator("[data-event-row]")).toHaveCount(0);
  }
});

test("opens metadata-only detail and reports a missing event as not found", async ({ page }) => {
  await page.route((url) => url.pathname.startsWith(LIST_PATH), (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === LIST_PATH)
      return route.fulfill(json(200, JSON.stringify({ items: [eventItem("evt-detail-01"), eventItem("evt-gone-01")] })));
    if (path === `${LIST_PATH}/evt-detail-01`)
      return route.fulfill(json(200, JSON.stringify({ ...eventItem("evt-detail-01"),
        redacted_content: "MARKER-EXCLUDED-CONTENT", tool_schema_version: "MARKER-EXCLUDED-VERSION" })));
    return route.fulfill(json(404, "{}"));
  });
  await page.fill("#filter-principal-id", "admin-human");
  await page.fill("#api-key", "sre_admn_0123456789abcdefghijklmnop");
  await page.click("#connect-button");
  await expect(page.locator("[data-event-row='evt-detail-01']")).toBeVisible();
  await page.click("[data-expand-event='evt-detail-01']");
  const detail = page.locator("[data-event-detail='evt-detail-01']");
  await expect(detail).toBeVisible();
  await expect(detail).toContainText("responses.create");
  const bodyText = await page.locator("body").innerText();
  expect(bodyText).not.toContain("MARKER-EXCLUDED-CONTENT");
  expect(bodyText).not.toContain("MARKER-EXCLUDED-VERSION");
  const source = await page.evaluate(() => fetch("/public/admin/audit-events.js").then((r) => r.text()));
  expect(source).not.toContain("redacted_content");
  expect(source).not.toContain("tool_schema_version");
  await page.click("[data-expand-event='evt-gone-01']");
  await expect(page.locator("#page-error-title")).toHaveText("Audit event not found");
});

test("lists through the connected API with contract parameters", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  let observed = null;
  await page.route((url) => url.pathname === LIST_PATH, async (route) => {
    observed = new URL(route.request().url());
    await route.continue();
  });
  await page.fill("#filter-decision", "allow");
  await page.fill("#api-key", apiKey("ADMIN_HUMAN_API_KEY"));
  await page.click("#connect-button");
  await expect(page.locator("#audit-events-page")).toHaveAttribute("data-state", /^(ready|empty)$/, { timeout: 20_000 });
  expect(observed.searchParams.get("decision")).toBe("allow");
  expect(observed.searchParams.get("limit")).toBe("100");
  expect(observed.search).not.toContain("cursor");
});
