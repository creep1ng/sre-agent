import { expect, test } from "@playwright/test";
test.use({ video: "on" });

const WEB = process.env.E2E_BASE_URL ?? "http://web";
const API = process.env.E2E_API_BASE_URL ?? "http://api:8000";
const ELIGIBLE_PATH = /\/api\/v1\/alerts\/[^/]+\/triage\/eligible-incidents$/;
const LINK_TARGET = "inc-0000-t23-linkable";
const DECLARATION_CONTEXT = {
  service: "checkout-api",
  summary: "Payment attempts return errors.",
  observed_at: "2026-10-07T17:30:00Z",
  source: "operator-confirmed monitoring report",
  severity: "sev2",
};
const INBOX_JOURNEYS = [
  {
    name: "dismiss",
    alertId: "alert-payment-002",
    operation: "triage_dismiss",
    reason: "The payment alert was reviewed and is not actionable.",
    status: "dismissed",
  },
  {
    name: "link",
    alertId: "alert-checkout-001",
    operation: "triage_link",
    reason: "The checkout alert belongs to the active checkout incident.",
    status: "linked",
    incidentId: LINK_TARGET,
  },
  {
    name: "declare",
    alertId: "alert-frontend-003",
    operation: "triage_declare",
    reason: "The catalog signal requires coordinated investigation.",
    impact: "Customers cannot load product recommendations from the catalog.",
    severity: "sev2",
    status: "declared",
  },
];

function requiredKey(name) {
  const value = process.env[name];
  if (!value) throw new Error(`requires ${name} from the isolated triage fixture`);
  return value;
}

function alertId(label) {
  return `al-t23-18-${label}-${Date.now().toString(36)}`;
}

async function connect(page, id, key) {
  await page.goto(`${WEB}/public/admin/triage.html?alert_id=${encodeURIComponent(id)}`);
  await page.locator("#api-key").fill(key);
  await page.locator("#connect-button").click();
  await expect(page.locator("#command-operation")).toBeEnabled();
}

async function selectLinkAndWait(page) {
  const response = page.waitForResponse((item) =>
    item.request().method() === "GET" && ELIGIBLE_PATH.test(new URL(item.url()).pathname),
  );
  await page.locator("#command-operation").selectOption("triage_link");
  return response;
}

async function beginInboxJourney(page, alertId, key) {
  const commandPosts = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/triage/commands"))
      commandPosts.push(request.postDataJSON());
  });
  await page.goto(`${WEB}/public/incident-ui/alerts.html`);
  await expect(page.locator("#alert-inbox")).toHaveAttribute("data-state", "ready");
  await page.locator(`#alert-list [data-alert-id="${alertId}"]`).click();
  await page.locator("#start-triage").click();
  await expect(page).toHaveURL(`${WEB}/public/admin/triage.html?alert_id=${alertId}`);
  await expect(page.locator("#alert-id")).toHaveValue(alertId);
  expect(commandPosts).toHaveLength(0);
  await page.locator("#api-key").fill(key);
  await page.locator("#connect-button").click();
  await expect(page.locator("#command-operation")).toBeEnabled();
  await expect(page.locator("#api-key")).toHaveValue("");
  return commandPosts;
}

async function saveProofScreens(page, name, expectedStatus, expectedIncident) {
  if (process.env.T23_18_ARTIFACT_DIR) {
    await page.screenshot({ path: `${process.env.T23_18_ARTIFACT_DIR}/inbox-${name}-after-command.png`, fullPage: true });
  }
  await page.reload();
  const key = requiredKey("E2E_TRIAGE_API_KEY");
  await page.locator("#api-key").fill(key);
  await page.locator("#connect-button").click();
  await expect(page.locator("#api-key")).toHaveValue("");
  await expect(page.locator("#result-status")).toHaveText(expectedStatus);
  if (expectedIncident) await expect(page.locator("#result-incident")).toHaveText(expectedIncident);
  if (process.env.T23_18_ARTIFACT_DIR) {
    await page.screenshot({ path: `${process.env.T23_18_ARTIFACT_DIR}/inbox-${name}-after-reload.png`, fullPage: true });
  }
}

test.describe("real inbox-to-triage operator journeys", () => {
  for (const journey of INBOX_JOURNEYS) {
    test(`inbox ${journey.name} applies and reloads the same alert decision`, async ({ page, request }) => {
      const key = requiredKey("E2E_TRIAGE_API_KEY");
      const commandPosts = await beginInboxJourney(page, journey.alertId, key);
      await page.locator("#command-operation").selectOption(journey.operation);
      if (journey.operation === "triage_link") {
        await page.locator("#command-target").selectOption(LINK_TARGET);
      }
      await page.locator("#command-reason").fill(journey.reason);
      if (journey.operation === "triage_declare") {
        await page.locator("#command-severity").selectOption(journey.severity);
        await page.locator("#command-impact").fill(journey.impact);
        await page.locator("#alert-context-service").fill(DECLARATION_CONTEXT.service);
        await page.locator("#alert-context-summary").fill(DECLARATION_CONTEXT.summary);
        await page.locator("#alert-context-observed-at").fill(DECLARATION_CONTEXT.observed_at);
        await page.locator("#alert-context-source").fill(DECLARATION_CONTEXT.source);
        await page.locator("#alert-context-severity").selectOption(DECLARATION_CONTEXT.severity);
        await page.locator("#alert-context-confirmed").check();
      }
      await expect(page.locator("#api-key")).toHaveValue("");
      await page.locator("#submit-button").click();
      await expect(page.locator("#result-status")).toHaveText(journey.status);
      await expect(page.locator("#result-actor")).toHaveText("op-e2e");
      await expect(page.locator("#result-reason")).toHaveText(journey.reason);
      await expect(page.locator("#result-decided")).toContainText(/20\d\d/);
      if (journey.incidentId) await expect(page.locator("#result-incident")).toHaveText(journey.incidentId);
      const confirmedIncidentId = journey.operation === "triage_declare"
        ? (await page.locator("#result-incident").textContent()).trim()
        : journey.incidentId;
      if (journey.operation === "triage_declare") {
        expect(confirmedIncidentId).toMatch(/^inc-/);
      }
      expect(commandPosts).toEqual([expect.objectContaining({ operation: journey.operation })]);
      await saveProofScreens(page, journey.name, journey.status, confirmedIncidentId);
      await expect(page.locator("#result-status")).toHaveText(journey.status);
      await expect(page.locator("#result-actor")).toHaveText("op-e2e");
      await expect(page.locator("#result-reason")).toHaveText(journey.reason);
      await expect(page.locator("#result-decided")).toContainText(/20\d\d/);
      if (confirmedIncidentId) await expect(page.locator("#result-incident")).toHaveText(confirmedIncidentId);
      const stored = await request.get(`${API}/v1/alerts/${encodeURIComponent(journey.alertId)}/triage`, {
        headers: { Authorization: `Bearer ${key}` },
      });
      expect(stored.status()).toBe(200);
      const decision = await stored.json();
      expect(decision).toMatchObject({ status: journey.status, reason: journey.reason, actor: "op-e2e" });
      expect(decision.decided_at).toEqual(expect.any(String));
      if (confirmedIncidentId) expect(decision.incident_id).toBe(confirmedIncidentId);
      if (journey.operation === "triage_declare") {
        const incident = await request.get(`${API}/v1/incidents/${encodeURIComponent(decision.incident_id)}`, {
          headers: { Authorization: `Bearer ${key}` },
        });
        expect(incident.status()).toBe(200);
        expect((await incident.json()).impact).toBe(journey.impact);
      }
    });
  }
});

test("inbox event deep-links the same alert id and sends no triage command", async ({ page }) => {
  const commandPosts = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/triage/commands"))
      commandPosts.push(request.url());
  });

  await page.goto(`${WEB}/public/incident-ui/alerts.html`);
  await expect(page.locator("#alert-inbox")).toHaveAttribute("data-state", "ready");
  await page.locator('#alert-list [data-alert-id="alert-checkout-001"]').click();
  await page.locator("#start-triage").click();

  await expect(page).toHaveURL(
    `${WEB}/public/admin/triage.html?alert_id=alert-checkout-001`,
  );
  await expect(page.locator("#alert-id")).toHaveValue("alert-checkout-001");
  await expect.poll(() => commandPosts).toHaveLength(0);
});

test("real bounded eligible list selects and links an incident from the UI", async ({ page, request }) => {
  const key = requiredKey("E2E_TRIAGE_API_KEY");
  const id = alertId("real-link");
  const posts = [];
  page.on("request", (item) => {
    if (item.method() === "POST" && item.url().includes("/triage/commands"))
      posts.push(item.postDataJSON());
  });

  await connect(page, id, key);
  const listResponse = await selectLinkAndWait(page);
  expect(listResponse.status()).toBe(200);
  const { items } = await listResponse.json();
  expect(items.length).toBeGreaterThan(0);
  expect(items.length).toBeLessThanOrEqual(100);
  expect(items[0]).toEqual({ incident_id: LINK_TARGET, state: "active" });
  await expect(page.locator("#target-list-status")).toContainText(/up to 100/i);
  await expect(page.locator("#target-list-status")).toContainText(/may be incomplete/i);
  await expect(page.locator(`#command-target option[value="${LINK_TARGET}"]`)).toHaveCount(1);
  await page.locator("#command-target").selectOption(LINK_TARGET);
  await page.locator("#command-reason").fill("Link after choosing the backend-listed destination.");

  if (process.env.T23_18_ARTIFACT_DIR) {
    await page.screenshot({
      path: `${process.env.T23_18_ARTIFACT_DIR}/eligible-target-selected.png`,
      fullPage: true,
    });
  }
  await page.locator("#submit-button").click();
  await expect(page.locator("#result-status")).toHaveText("linked");
  await expect(page.locator("#result-incident")).toHaveText(LINK_TARGET);
  expect(posts).toEqual([{
    operation: "triage_link",
    expected_version: 1,
    reason: "Link after choosing the backend-listed destination.",
    target_incident_id: LINK_TARGET,
  }]);

  const stored = await request.get(`${API}/v1/alerts/${encodeURIComponent(id)}/triage`, {
    headers: { Authorization: `Bearer ${key}` },
  });
  expect(stored.status()).toBe(200);
  expect(await stored.json()).toMatchObject({ status: "linked", incident_id: LINK_TARGET });
});

test("empty and failed eligible reads fail closed without hiding other permitted actions", async ({ page }) => {
  let response = { status: 200, body: { items: [] }, message: /no eligible/i };
  const posts = [];
  page.on("request", (item) => {
    if (item.method() === "POST" && item.url().includes("/triage/commands")) posts.push(item.url());
  });
  await page.route((url) => ELIGIBLE_PATH.test(url.pathname), (route) =>
    route.fulfill({
      status: response.status,
      contentType: "application/json",
      body: JSON.stringify(response.body),
    }),
  );
  const key = requiredKey("E2E_TRIAGE_API_KEY");
  await page.goto(WEB + "/public/admin/triage.html");
  await page.locator("#api-key").fill(key);
  await page.locator("#connect-button").click();

  const failures = [
    { status: 200, body: { items: [] }, message: /no eligible/i },
    { status: 403, body: { error: { code: "not_authorized", message: "Denied." } }, message: /could not load|access unavailable/i },
    { status: 503, body: { error: { code: "storage_unavailable", message: "Unavailable." } }, message: /could not load|unavailable/i },
    { status: 200, body: { items: [{ incident_id: "BAD ID", state: "closed" }] }, message: /invalid|could not load/i },
  ];
  for (const failure of failures) {
    response = failure;
    const id = alertId(`read-${failure.status}-${Date.now().toString(36)}`);
    await page.locator("#alert-id").fill(id);
    await expect(page.locator("#command-operation")).toBeEnabled();
    await selectLinkAndWait(page);
    await expect(page.locator("#target-list-status")).toContainText(failure.message);
    await expect(page.locator("#command-target")).toBeDisabled();
    await expect(page.locator("#submit-button")).toBeDisabled();
    await expect(page.locator("#result-status")).toHaveText("—");
    await expect(page.locator("#result-summary")).toHaveText("No recorded decision for this alert.");
    await page.locator("#command-operation").selectOption("triage_declare");
    await expect(page.locator("#command-operation")).toBeEnabled();
  }
  expect(posts).toHaveLength(0);
});

test("late target lists cannot cross alert or session generations", async ({ page }) => {
  const full = requiredKey("E2E_TRIAGE_API_KEY");
  const reader = requiredKey("E2E_TRIAGE_READONLY_API_KEY");
  const alertA = alertId("held-list");
  const alertB = alertId("current-list");
  let releaseA;
  let seenA = false;
  await page.route((url) => ELIGIBLE_PATH.test(url.pathname), async (route) => {
    const id = decodeURIComponent(new URL(route.request().url()).pathname.split("/").at(-3));
    if (id === alertA) {
      seenA = true;
      const body = await new Promise((resolve) => { releaseA = resolve; });
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [{ incident_id: "inc-current-list", state: "active" }] }),
    });
  });

  await page.goto(WEB + "/public/admin/triage.html");
  await page.locator("#api-key").fill(full);
  await page.locator("#connect-button").click();
  await page.locator("#alert-id").fill(alertA);
  await expect(page.locator("#command-operation")).toBeEnabled();
  const pendingA = page.waitForResponse((item) =>
    item.request().method() === "GET" && ELIGIBLE_PATH.test(new URL(item.url()).pathname),
  );
  await page.locator("#command-operation").selectOption("triage_link");
  await expect.poll(() => seenA).toBe(true);

  await page.locator("#alert-id").fill(alertB);
  await expect(page.locator("#command-operation")).toBeEnabled();
  await page.locator("#command-operation").selectOption("open_triage");
  await selectLinkAndWait(page);
  await expect(page.locator('#command-target option[value="inc-current-list"]')).toHaveCount(1);
  await expect(page.locator('#command-target option[value="inc-held-list"]')).toHaveCount(0);

  await page.locator("#disconnect-button").click();
  await page.locator("#api-key").fill(reader);
  await page.locator("#connect-button").click();
  await page.locator("#alert-id").fill(alertB);
  await expect(page.locator("#command-operation")).toBeDisabled();
  releaseA({ items: [{ incident_id: "inc-held-list", state: "active" }] });
  await pendingA;
  await expect(page.locator('#command-target option[value="inc-held-list"]')).toHaveCount(0);
  await expect(page.locator("#command-target")).toBeDisabled();
  await expect(page.locator("#result-status")).toHaveText("—");
});

test("mocked destination_ineligible refresh shows no false link or automatic retry", async ({ page }) => {
  const key = requiredKey("E2E_TRIAGE_API_KEY");
  const reader = requiredKey("E2E_TRIAGE_READONLY_API_KEY");
  const id = alertId("destination-closed");
  let listReads = 0;
  let eligibleRequests = 0;
  let holdThirdRefresh = false;
  let thirdRefreshStarted = false;
  let releaseThirdRefresh;
  let commandPosts = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/triage/commands")) commandPosts += 1;
  });
  page.on("response", (response) => {
    if (response.request().method() === "GET" && ELIGIBLE_PATH.test(new URL(response.url()).pathname)) listReads += 1;
  });
  await page.route((url) => ELIGIBLE_PATH.test(url.pathname), async (route) => {
    eligibleRequests += 1;
    if (holdThirdRefresh && eligibleRequests === 3) {
      thirdRefreshStarted = true;
      const body = await new Promise((resolve) => { releaseThirdRefresh = resolve; });
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    }
    return route.continue();
  });
  await page.route((url) => url.pathname.endsWith("/triage/commands"), (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "destination_ineligible", message: "Destination is no longer eligible." } }),
    }),
  );

  await connect(page, id, key);
  const listed = await selectLinkAndWait(page);
  expect(listed.status()).toBe(200);
  await page.locator("#command-target").selectOption(LINK_TARGET);
  await page.locator("#command-reason").fill("Do not link after the destination closes.");
  await page.locator("#submit-button").click();
  await expect(page.locator("#page-error-title")).toHaveText("Conflict");
  await expect(page.locator("#result-status")).toHaveText("—");
  await expect.poll(() => listReads).toBe(2);
  await expect(page.locator("#command-target")).toBeEnabled();
  await expect(page.locator("#command-target")).toHaveValue("");
  await expect(page.locator("#command-reason")).toHaveValue("Do not link after the destination closes.");
  await expect(page.locator("#submit-button")).toBeDisabled();
  await page.waitForTimeout(200);
  expect(commandPosts).toBe(1);

  await page.locator("#command-target").selectOption(LINK_TARGET);
  await page.locator("#command-reason").fill("A second command is denied during a session transition.");
  holdThirdRefresh = true;
  const heldRefreshResponse = page.waitForResponse((response) =>
    response.request().method() === "GET" && ELIGIBLE_PATH.test(new URL(response.url()).pathname),
  );
  await page.locator("#submit-button").click();
  await expect.poll(() => commandPosts).toBe(2);
  await expect.poll(() => thirdRefreshStarted).toBe(true);

  await page.locator("#disconnect-button").click();
  await page.locator("#api-key").fill(reader);
  await page.locator("#connect-button").click();
  const nextSessionAlert = alertId("new-session");
  await page.locator("#alert-id").fill(nextSessionAlert);
  await expect(page.locator("#actions-status")).toHaveText(
    "The backend currently permits no triage operations for this alert.",
  );
  await expect(page.locator("#triage-state")).toContainText(
    `Alert ${nextSessionAlert} has no recorded decision yet.`,
  );
  releaseThirdRefresh({ items: [{ incident_id: LINK_TARGET, state: "active" }] });
  await heldRefreshResponse;
  await page.waitForTimeout(100);
  await expect(page.locator("#alert-id")).toHaveValue(nextSessionAlert);
  await expect(page.locator("#page-error")).toBeHidden();
  await expect(page.locator("#result-status")).toHaveText("—");
  expect(commandPosts).toBe(2);
});
