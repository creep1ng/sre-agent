import { expect, test } from "@playwright/test";

const connected = process.env.PLAYWRIGHT_PRODUCTION_TOPOLOGY === "1";
const COMMANDS_PATH = "/api/v1/alerts/al-journey-01/triage/commands";

function apiKey(name) {
  const value = process.env[name];
  test.skip(!value, `requires ${name}`);
  return value;
}

function stateResult(status, incident = null) {
  return {
    alert_id: "al-journey-01",
    status,
    incident_id: incident,
    expected_version: 2,
    actor: "op-human",
    decided_at: "2026-09-20T10:00:00Z",
  };
}

const json = (status, body) => ({ status, contentType: "application/json", body });

async function connect(page) {
  await page.fill("#api-key", "sre_admn_0123456789abcdefghijklmnop");
  await page.click("#connect-button");
}

async function send(page, operation, configure = {}) {
  await page.selectOption("#command-operation", operation);
  for (const [selector, value] of Object.entries(configure)) {
    if (selector === "#command-severity") await page.selectOption(selector, value);
    else await page.fill(selector, value);
  }
  await page.click("#submit-button");
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
  await page.goto("/public/admin/triage.html");
  await expect(page.locator("#triage-page")).toHaveAttribute("data-state", "idle");
});

test.afterEach(async ({ page }) => {
  expect(page.context()["__consoleErrors"] ?? []).toEqual([]);
});

test("sends open_triage without reason and syncs state", async ({ page }) => {
  let observed = null;
  await page.route(
    (url) => url.pathname === COMMANDS_PATH,
    (route) => {
      observed = route.request();
      return route.fulfill(json(200, JSON.stringify(stateResult("open"))));
    },
  );
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await page.fill("#command-reason", "");
  await send(page, "open_triage");
  expect(await observed.postDataJSON()).toEqual({ operation: "open_triage", expected_version: 1 });
  await expect(page.locator("#result-status")).toHaveText("open");
  await expect(page.locator("#expected-version")).toHaveValue("2");
  await expect(page.locator("#triage-state")).toContainText("al-journey-01 is open (version 2).");
});

test("sends dismiss and link with exact bodies", async ({ page }) => {
  const seen = [];
  await page.route((url) => url.pathname === COMMANDS_PATH, (route) => {
    seen.push(route.request().postDataJSON());
    const operation = seen[seen.length - 1].operation;
    const status = operation === "triage_dismiss" ? "dismissed" : "linked";
    const incident = operation === "triage_link" ? "inc-target-01" : null;
    return route.fulfill(json(200, JSON.stringify(stateResult(status, incident))));
  });
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await send(page, "triage_dismiss", { "#command-reason": "Not actionable." });
  await send(page, "triage_link", {
    "#command-reason": "Same incident.",
    "#command-target": "inc-target-01",
  });
  expect(seen[0]).toEqual({ operation: "triage_dismiss", expected_version: 1, reason: "Not actionable." });
  expect(seen[1]).toEqual({
    operation: "triage_link", expected_version: 2, reason: "Same incident.",
    target_incident_id: "inc-target-01",
  });
  await expect(page.locator("#result-incident")).toHaveText("inc-target-01");
});

test("sends declare with severity and shows the created incident", async ({ page }) => {
  let observed = null;
  await page.route(
    (url) => url.pathname === COMMANDS_PATH,
    (route) => {
      observed = route.request();
      return route.fulfill(json(201, JSON.stringify(stateResult("declared", "inc-created-01"))));
    },
  );
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await send(page, "triage_declare", { "#command-reason": "Declaring.", "#command-severity": "sev2" });
  const body = await observed.postDataJSON();
  expect(body).toEqual({
    operation: "triage_declare", expected_version: 1, reason: "Declaring.", severity: "sev2",
  });
  expect(body).not.toHaveProperty("impact");
  expect(body).not.toHaveProperty("actor");
  const key = observed.headers()["idempotency-key"];
  expect(key).toMatch(/^triage-[0-9a-f]{32}$/);
  await expect(page.locator("#result-status")).toHaveText("declared");
  await expect(page.locator("#result-incident")).toHaveText("inc-created-01");
  await expect(page.locator("#result-summary")).toContainText("inc-created-01");
});

test("renders a missing severity as an invalid request", async ({ page }) => {
  await page.route((url) => url.pathname === COMMANDS_PATH, (route) =>
    route.fulfill(json(422, JSON.stringify({ error: { code: "invalid_severity" } }))));
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await send(page, "triage_declare", { "#command-reason": "Declaring." });
  await expect(page.locator("#page-error-title")).toHaveText("Invalid request");
});

test("renders authentication, authorization, conflict and outage failures distinctly", async ({ page }) => {
  let status = 401;
  let body = "{}";
  await page.route((url) => url.pathname === COMMANDS_PATH, (route) =>
    route.fulfill(json(status, body)));
  const cases = [
    [401, null, "Authentication required"],
    [403, null, "Access unavailable"],
    [404, null, "Not found"],
    [409, "stale_version", "Conflict"],
    [503, "audit_unavailable", "Service unavailable"],
  ];
  for (const [next, code, title] of cases) {
    status = next;
    body = code === null ? "{}" : JSON.stringify({ error: { code, message: `server says ${code}` } });
    await page.fill("#alert-id", "al-journey-01");
    await page.click("#submit-button");
    await expect(page.locator("#page-error-title")).toHaveText(title);
  }
  await expect(page.locator("#page-error-detail")).toContainText("server says audit_unavailable");
});

test("surfaces network failure as offline without false state", async ({ page }) => {
  await page.route((url) => url.pathname === COMMANDS_PATH, (route) => route.abort("failed"));
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await send(page, "open_triage");
  await expect(page.locator("#triage-page")).toHaveAttribute("data-state", "offline");
  await expect(page.locator("#page-error-title")).toHaveText("API unavailable");
  await expect(page.locator("#result-status")).toHaveText("—");
});

test("ignores a double submit while a command is in flight", async ({ page }) => {
  let requests = 0;
  await page.route((url) => url.pathname === COMMANDS_PATH, async (route) => {
    requests += 1;
    await new Promise((resolve) => setTimeout(resolve, 1200));
    return route.fulfill(json(200, JSON.stringify(stateResult("open"))));
  });
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await page.selectOption("#command-operation", "open_triage");
  await page.$eval("#command-form", (form) => form.requestSubmit());
  await page.$eval("#command-form", (form) => form.requestSubmit());
  await expect(page.locator("#result-status")).toHaveText("open", { timeout: 10_000 });
  expect(requests).toBe(1);
});

test("exposes no impact, actor or timestamp inputs", async ({ page }) => {
  await expect(page.locator('[name="impact"]')).toHaveCount(0);
  await expect(page.locator('[name="actor"]')).toHaveCount(0);
  await expect(page.locator('[name="timestamp"]')).toHaveCount(0);
  const source = await page.evaluate(() => fetch("/public/admin/triage.js").then((r) => r.text()));
  expect(source).not.toContain("impact");
});

test("renders a real 401 as authentication required", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  await page.fill("#alert-id", "al-journey-01");
  await page.fill("#api-key", "sre_admn_0123456789abcdefghij");
  await page.click("#connect-button");
  await send(page, "open_triage");
  await expect(page.locator("#page-error-title")).toHaveText("Authentication required", {
    timeout: 20_000,
  });
});

test("renders a real 403 for an identity without triage grants", async ({ page }) => {
  test.skip(!connected, "requires the connected control-plane API");
  let observed = null;
  await page.route((url) => url.pathname === COMMANDS_PATH, async (route) => {
    observed = route.request();
    await route.continue();
  });
  await page.fill("#api-key", apiKey("ADMIN_HUMAN_API_KEY"));
  await page.click("#connect-button");
  await page.fill("#alert-id", "al-journey-01");
  await send(page, "open_triage");
  await expect(page.locator("#page-error-title")).toHaveText("Access unavailable", {
    timeout: 20_000,
  });
  expect(observed.method()).toBe("POST");
  expect(observed.headers()["idempotency-key"]).toMatch(/^triage-[0-9a-f]{32}$/);
  expect(await observed.postDataJSON()).toEqual({ operation: "open_triage", expected_version: 1 });
});
