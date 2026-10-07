import { expect, test } from "@playwright/test";

const COMMANDS_PATH = "/api/v1/alerts/al-journey-01/triage/commands";
const CONTEXT_PATH = "/api/v1/alerts/al-journey-01/triage/context";
const ELIGIBLE_PATH = "/api/v1/alerts/al-journey-01/triage/eligible-incidents";
const ALL_ACTIONS = ["open_triage", "triage_dismiss", "triage_link", "triage_declare"];
const DECLARATION_CONTEXT = {
  service: "checkout-api",
  summary: "Payment attempts return errors.",
  observed_at: "2026-10-07T17:30:00Z",
  source: "operator-confirmed monitoring report",
  severity: "sev4",
};

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
  await expect(page.locator("#command-operation")).toBeEnabled();
  await page.selectOption("#command-operation", operation);
  for (const [selector, value] of Object.entries(configure)) {
    if (selector === "#alert-context-confirmed") {
      await page.locator(selector).check();
    } else if (
      selector === "#command-severity" || selector === "#command-target" ||
      selector === "#alert-context-severity"
    ) {
      await expect(page.locator(`${selector} option[value=\"${value}\"]`)).toHaveCount(1);
      await page.selectOption(selector, value);
    }
    else await page.fill(selector, value);
  }
  await page.click("#submit-button");
}

test.beforeEach(async ({ page }) => {
  const consoleErrors = [];
  let mockedState = null;
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
  page.on("response", (response) => {
    const request = response.request();
    if (request.method() !== "POST" || !request.url().includes("/triage/commands") || !response.ok()) return;
    const body = request.postDataJSON();
    const operation = body.operation;
    mockedState = {
      alert_id: decodeURIComponent(new URL(request.url()).pathname.split("/").at(-3)),
      status: { open_triage: "open", triage_dismiss: "dismissed", triage_link: "linked", triage_declare: "declared" }[operation],
      expected_version: body.expected_version + 1,
      incident_id: operation === "triage_declare" ? "inc-created-01" : operation === "triage_link" ? body.target_incident_id : null,
      actor: "op-human", reason: body.reason ?? null, decided_at: "2026-09-20T10:00:00Z",
    };
  });
  await page.route((url) => url.pathname === ELIGIBLE_PATH, (route) =>
    route.fulfill(json(200, JSON.stringify({
      items: [{ incident_id: "inc-target-01", state: "active" }],
    }))),
  );
  await page.route((url) => url.pathname === CONTEXT_PATH, (route) =>
    route.fulfill(json(200, JSON.stringify({
      alert_id: "al-journey-01", triage_state: mockedState, allowed_actions: ALL_ACTIONS,
    }))),
  );
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
  await expect(page.locator("#triage-state")).toContainText("al-journey-01 is open (version 2), read from the API.");
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
    "#alert-context-service": DECLARATION_CONTEXT.service,
    "#alert-context-summary": DECLARATION_CONTEXT.summary,
    "#alert-context-observed-at": DECLARATION_CONTEXT.observed_at,
    "#alert-context-source": DECLARATION_CONTEXT.source,
    "#alert-context-severity": DECLARATION_CONTEXT.severity,
    "#alert-context-confirmed": "yes",
  });
  const body = await observed.postDataJSON();
  expect(body).toEqual({
    operation: "triage_declare", expected_version: 1, reason: "Declaring.", severity: "sev2", impact,
    alert_context: DECLARATION_CONTEXT,
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
  await expect(page.locator("#command-operation")).toBeEnabled();
  await page.selectOption("#command-operation", "triage_declare");
  await page.fill("#command-reason", "Declaring.");
  await page.selectOption("#command-severity", "sev2");
  await page.locator("#alert-context-service").fill(DECLARATION_CONTEXT.service);
  await page.locator("#alert-context-summary").fill(DECLARATION_CONTEXT.summary);
  await page.locator("#alert-context-observed-at").fill(DECLARATION_CONTEXT.observed_at);
  await page.locator("#alert-context-source").fill(DECLARATION_CONTEXT.source);
  await page.locator("#alert-context-severity").selectOption(DECLARATION_CONTEXT.severity);
  await page.locator("#alert-context-confirmed").check();
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
    "#alert-context-service": DECLARATION_CONTEXT.service,
    "#alert-context-summary": DECLARATION_CONTEXT.summary,
    "#alert-context-observed-at": DECLARATION_CONTEXT.observed_at,
    "#alert-context-source": DECLARATION_CONTEXT.source,
    "#alert-context-severity": DECLARATION_CONTEXT.severity,
    "#alert-context-confirmed": "yes",
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
    "#alert-context-service": DECLARATION_CONTEXT.service,
    "#alert-context-summary": DECLARATION_CONTEXT.summary,
    "#alert-context-observed-at": DECLARATION_CONTEXT.observed_at,
    "#alert-context-source": DECLARATION_CONTEXT.source,
    "#alert-context-severity": DECLARATION_CONTEXT.severity,
    "#alert-context-confirmed": "yes",
  });
  expect(seen[1]).toEqual({
    operation: "triage_declare", expected_version: 2, reason: "Declaring.", severity: "sev2",
    impact: "Checkout stopped accepting payments.", alert_context: DECLARATION_CONTEXT,
  });
  expect(seen[1]).not.toHaveProperty("target_incident_id");
});

test("renders authentication, authorization, conflict and outage failures distinctly", async ({ page }) => {
  let status = 401;
  let body = "{}";
  await page.route((url) => url.pathname === COMMANDS_PATH, (route) =>
    route.fulfill(json(status, body)));
  await connect(page);
  const cases = [
    [401, null, "Authentication required"],
    [403, null, "Access unavailable"],
    [404, null, "Not found"],
    [409, "stale_version", "Conflict"],
    [503, "storage_unavailable", "Service unavailable"],
  ];
  for (let index = 0; index < cases.length; index += 1) {
    const [next, code, title] = cases[index];
    status = next;
    body = code === null ? "{}" : JSON.stringify({ error: { code, message: `server says ${code}` } });
    await page.fill("#alert-id", "al-journey-01");
    await expect(page.locator("#command-operation")).toBeEnabled();
    await page.click("#submit-button");
    await expect(page.locator("#page-error-title")).toHaveText(title);
    if (index < cases.length - 1) {
      await page.fill("#alert-id", "");
      await page.fill("#alert-id", "al-journey-01");
    }
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

test("context denial, storage failure and malformed projection fail closed without POST", async ({ page }) => {
  let mode = "denied";
  await page.route((url) => url.pathname === CONTEXT_PATH, (route) => {
    if (mode === "denied") return route.fulfill(json(403, JSON.stringify({ error: { code: "not_authorized" } })));
    if (mode === "unavailable") return route.fulfill(json(503, JSON.stringify({ error: { code: "storage_unavailable" } })));
    return route.fulfill(json(200, JSON.stringify({
      alert_id: "al-journey-01", triage_state: null, allowed_actions: ["invented_action"],
    })));
  });
  let posts = 0;
  await page.route((url) => url.pathname === COMMANDS_PATH, (route) => {
    posts += 1;
    return route.fulfill(json(200, JSON.stringify(stateResult("open"))));
  });
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await expect(page.locator("#submit-button")).toBeDisabled();
  await expect(page.locator("#page-error-title")).toHaveText("Access unavailable");
  await page.locator("#command-form").evaluate((form) =>
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
  );
  expect(posts).toBe(0);

  for (const [nextMode, title] of [["unavailable", "Service unavailable"], ["malformed", "Request failed"]]) {
    mode = nextMode;
    await page.fill("#alert-id", "");
    await page.fill("#alert-id", "al-journey-01");
    await expect(page.locator("#page-error-title")).toHaveText(title);
    await expect(page.locator("#submit-button")).toBeDisabled();
    await page.locator("#command-form").evaluate((form) =>
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })),
    );
    expect(posts).toBe(0);
  }
});

test("a successful command refresh displays the newer authoritative context", async ({ page }) => {
  let reads = 0;
  await page.route((url) => url.pathname === CONTEXT_PATH, (route) => {
    reads += 1;
    const state = reads === 1 ? null : {
      alert_id: "al-journey-01", status: "open", expected_version: 3,
      incident_id: null, reason: null, actor: "op-human", decided_at: "2026-09-20T10:00:01Z",
    };
    return route.fulfill(json(200, JSON.stringify({
      alert_id: "al-journey-01", triage_state: state, allowed_actions: ALL_ACTIONS,
    })));
  });
  await page.route((url) => url.pathname === COMMANDS_PATH, (route) =>
    route.fulfill(json(200, JSON.stringify(stateResult("open")))),
  );
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await send(page, "open_triage");
  await expect(page.locator("#result-version")).toHaveText("3");
  await expect(page.locator("#expected-version")).toHaveValue("3");
  await expect(page.locator("#result-summary")).toContainText("Recovered from backend: open");
  expect(reads).toBe(2);
});

test("a confirmed command with a null refresh context keeps its result but disables further operations", async ({ page }) => {
  let reads = 0;
  await page.route((url) => url.pathname === CONTEXT_PATH, (route) => {
    reads += 1;
    return route.fulfill(json(200, JSON.stringify({
      alert_id: "al-journey-01", triage_state: null, allowed_actions: ALL_ACTIONS,
    })));
  });
  await page.route((url) => url.pathname === COMMANDS_PATH, (route) =>
    route.fulfill(json(200, JSON.stringify(stateResult("open")))),
  );
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await send(page, "open_triage");
  await expect(page.locator("#result-status")).toHaveText("open");
  await expect(page.locator("#result-summary")).toContainText("open");
  await expect(page.locator("#submit-button")).toBeDisabled();
  await expect(page.locator("#page-error")).toBeVisible();
  await expect(page.locator("#page-error-title")).toHaveText("Request failed");
  await expect(page.locator("#page-error-detail")).toContainText("confirmed");
  expect(reads).toBe(2);
});

test("changing alert invalidates prior projection and ignores a late context response", async ({ page }) => {
  let releaseA;
  let firstA = true;
  await page.route((url) => url.pathname.endsWith("/triage/context"), async (route) => {
    const id = decodeURIComponent(new URL(route.request().url()).pathname.split("/").at(-3));
    if (id === "al-context-a" && firstA) {
      firstA = false;
      await new Promise((resolve) => { releaseA = resolve; });
    }
    const allowed = id === "al-context-b" ? ["triage_dismiss"] : ALL_ACTIONS;
    return route.fulfill(json(200, JSON.stringify({ alert_id: id, triage_state: null, allowed_actions: allowed })));
  });
  await connect(page);
  await page.fill("#alert-id", "al-context-a");
  await expect.poll(() => Boolean(releaseA)).toBe(true);
  await page.fill("#alert-id", "al-context-b");
  await expect(page.locator("#command-operation option[value='open_triage']")).toBeDisabled();
  await expect(page.locator("#command-operation option[value='triage_dismiss']")).toBeEnabled();
  await expect(page.locator("#command-operation")).toHaveValue("open_triage");
  await expect(page.locator("#submit-button")).toBeDisabled();
  releaseA();
  await expect(page.locator("#command-operation option[value='open_triage']")).toBeDisabled();
  await expect(page.locator("#command-operation")).toHaveValue("open_triage");
  await expect(page.locator("#submit-button")).toBeDisabled();
  await expect(page.locator("#command-operation")).toBeEnabled();
  await page.selectOption("#command-operation", "triage_dismiss");
  await expect(page.locator("#submit-button")).toBeEnabled();
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
  await expect(page.locator("#command-operation")).toBeEnabled();
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
  await connect(page);
  await page.fill("#alert-id", "al-journey-01");
  await expect(page.locator('[name="impact"]')).toHaveCount(1);
  await expect(page.locator('[name="impact"]')).toHaveAttribute("maxlength", "2000");
  await expect(page.locator('[name="impact"]')).toHaveAttribute("aria-required", "false");
  await expect(page.locator("#command-operation")).toBeEnabled();
  await page.selectOption("#command-operation", "triage_declare");
  await expect(page.locator('[name="impact"]')).toHaveAttribute("aria-required", "true");
  await page.selectOption("#command-operation", "open_triage");
  await expect(page.locator('[name="impact"]')).toHaveAttribute("aria-required", "false");
  await expect(page.locator('[name="actor"]')).toHaveCount(0);
  await expect(page.locator('[name="timestamp"]')).toHaveCount(0);
});
