import { expect, test } from "@playwright/test";

const COMMANDS_PATH = "/api/v1/alerts/al-journey-01/triage/commands";

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
  await expect(page.locator("#result-origin")).toHaveText("—");
  await expect(page.locator("#result-responsible-system")).toHaveText("—");
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

test("sends the operator impact exactly with declaration and shows the created incident", async ({ page }) => {
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
  const impact = "  Checkout stopped accepting payments for new orders.  ";
  await send(page, "triage_declare", {
    "#command-reason": "Declaring.", "#command-severity": "sev2", "#command-impact": impact,
  });
  const body = await observed.postDataJSON();
  expect(body).toEqual({
    operation: "triage_declare", expected_version: 1, reason: "Declaring.", severity: "sev2", impact,
  });
  expect(body).not.toHaveProperty("actor");
  const key = observed.headers()["idempotency-key"];
  expect(key).toMatch(/^triage-[0-9a-f]{32}$/);
  await expect(page.locator("#result-status")).toHaveText("declared");
  await expect(page.locator("#result-incident")).toHaveText("inc-created-01");
  await expect(page.locator("#result-summary")).toContainText("inc-created-01");
});

test("rejects a declaration without operator impact before sending", async ({ page }) => {
  let requests = 0;
  await page.route((url) => url.pathname === COMMANDS_PATH, (route) => {
    requests += 1;
    return route.fulfill(json(201, JSON.stringify(stateResult("declared", "inc-created-01"))));
  });
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await page.selectOption("#command-operation", "triage_declare");
  await page.fill("#command-reason", "Declaring.");
  await page.selectOption("#command-severity", "sev2");
  for (const value of ["", "   "]) {
    await page.fill("#command-impact", value);
    await page.click("#submit-button");
    await expect(page.locator("#page-error-title")).toHaveText("Invalid request");
    await expect(page.locator("#page-error-detail")).toContainText(/impact/i);
  }
  expect(requests).toBe(0);
});

test("does not send impact for operations other than declaration", async ({ page }) => {
  const seen = [];
  await page.route((url) => url.pathname === COMMANDS_PATH, (route) => {
    seen.push(route.request().postDataJSON());
    return route.fulfill(json(200, JSON.stringify(stateResult("open"))));
  });
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await page.fill("#command-impact", "Only applies to a declared incident.");
  await send(page, "open_triage");
  expect(seen[0]).toEqual({ operation: "open_triage", expected_version: 1 });
});

test("renders a missing severity as an invalid request", async ({ page }) => {
  await page.route((url) => url.pathname === COMMANDS_PATH, (route) =>
    route.fulfill(json(422, JSON.stringify({ error: { code: "invalid_severity" } }))));
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await send(page, "triage_declare", {
    "#command-reason": "Declaring.", "#command-impact": "Checkout stopped accepting payments.",
  });
  await expect(page.locator("#page-error-title")).toHaveText("Invalid request");
});

test("switching operations drops stale fields before sending", async ({ page }) => {
  const seen = [];
  await page.route((url) => url.pathname === COMMANDS_PATH, (route) => {
    seen.push(route.request().postDataJSON());
    const operation = seen[seen.length - 1].operation;
    const status = operation === "triage_link" ? "linked" : "declared";
    const incident = operation === "triage_link" ? "inc-target-01" : "inc-created-01";
    const code = operation === "triage_link" ? 200 : 201;
    return route.fulfill(json(code, JSON.stringify(stateResult(status, incident))));
  });
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await send(page, "triage_link", {
    "#command-reason": "Same incident.",
    "#command-target": "inc-target-01",
  });
  await send(page, "triage_declare", {
    "#command-reason": "Declaring.", "#command-severity": "sev2",
    "#command-impact": "Checkout stopped accepting payments.",
  });
  expect(seen[1]).toEqual({
    operation: "triage_declare", expected_version: 2, reason: "Declaring.", severity: "sev2",
    impact: "Checkout stopped accepting payments.",
  });
  expect(seen[1]).not.toHaveProperty("target_incident_id");
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
    [503, "storage_unavailable", "Service unavailable"],
  ];
  for (const [next, code, title] of cases) {
    status = next;
    body = code === null ? "{}" : JSON.stringify({ error: { code, message: `server says ${code}` } });
    await page.fill("#alert-id", "al-journey-01");
    await page.click("#submit-button");
    await expect(page.locator("#page-error-title")).toHaveText(title);
  }
  await expect(page.locator("#page-error-detail")).toContainText("server says storage_unavailable");
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

test("reload shows idle without invented state", async ({ page }) => {
  await page.route((url) => url.pathname === COMMANDS_PATH, (route) =>
    route.fulfill(json(200, JSON.stringify(stateResult("dismissed")))));
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await send(page, "triage_dismiss", { "#command-reason": "Not actionable." });
  await expect(page.locator("#result-status")).toHaveText("dismissed");
  await page.reload();
  await expect(page.locator("#triage-page")).toHaveAttribute("data-state", "idle");
  await expect(page.locator("#result-summary")).toHaveText("No command sent yet.");
  await expect(page.locator("#page-error")).toBeHidden();
  await expect(page.locator("#expected-version")).toHaveValue("1");
});

test("stale version recovers with the current version", async ({ page }) => {
  let attempt = 0;
  await page.route((url) => url.pathname === COMMANDS_PATH, (route) => {
    attempt += 1;
    if (attempt === 1)
      return route.fulfill(json(409, JSON.stringify({ error: { code: "stale_version" } })));
    return route.fulfill(json(200, JSON.stringify(stateResult("dismissed"))));
  });
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await send(page, "triage_dismiss", { "#command-reason": "Not actionable." });
  await expect(page.locator("#page-error-title")).toHaveText("Conflict");
  await expect(page.locator("#result-status")).toHaveText("—");
  await page.fill("#expected-version", "2");
  await page.click("#submit-button");
  await expect(page.locator("#result-status")).toHaveText("dismissed");
  expect(attempt).toBe(2);
});

test("forbidden leaves no trace and reconnect recovers", async ({ page }) => {
  let mode = "deny";
  await page.route((url) => url.pathname === COMMANDS_PATH, (route) => {
    if (mode === "deny") return route.fulfill(json(403, JSON.stringify({})));
    return route.fulfill(json(200, JSON.stringify(stateResult("open"))));
  });
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await send(page, "open_triage");
  await expect(page.locator("#page-error-title")).toHaveText("Access unavailable");
  await expect(page.locator("#result-status")).toHaveText("—");
  await page.click("#disconnect-button");
  mode = "allow";
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await send(page, "open_triage");
  await expect(page.locator("#result-status")).toHaveText("open");
});

test("late response cannot overwrite a newer result", async ({ page }) => {
  const seen = [];
  await page.route((url) => url.pathname === COMMANDS_PATH, async (route) => {
    seen.push(route.request().postDataJSON());
    if (seen.length === 1) await new Promise((resolve) => setTimeout(resolve, 1500));
    return route.fulfill(json(200, JSON.stringify(stateResult("open"))));
  });
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await page.locator("#submit-button").click();
  await expect(page.locator("#triage-page")).toHaveAttribute("data-state", "loading");
  await page.click("#disconnect-button");
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await page.click("#submit-button");
  await expect(page.locator("#result-status")).toHaveText("open");
  await page.waitForTimeout(2000);
  await expect(page.locator("#result-status")).toHaveText("open");
  await expect(page.locator("#page-error")).toBeHidden();
  expect(seen).toHaveLength(2);
});

test("exposes impact only for declaration and no actor or timestamp inputs", async ({ page }) => {
  await expect(page.locator('[name="impact"]')).toHaveCount(1);
  await expect(page.locator('[name="impact"]')).toHaveAttribute("maxlength", "2000");
  await expect(page.locator('[name="impact"]')).toHaveAttribute("aria-required", "false");
  await page.selectOption("#command-operation", "triage_declare");
  await expect(page.locator('[name="impact"]')).toHaveAttribute("aria-required", "true");
  await page.selectOption("#command-operation", "open_triage");
  await expect(page.locator('[name="impact"]')).toHaveAttribute("aria-required", "false");
  await expect(page.locator('[name="actor"]')).toHaveCount(0);
  await expect(page.locator('[name="timestamp"]')).toHaveCount(0);
});
