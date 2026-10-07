import { expect, test } from "@playwright/test";

const BASE = process.env.E2E_BASE_URL ?? "http://web";

function requiredKey(name) {
  const value = process.env[name];
  test.skip(!value, `requires ${name} from a seeded isolated stack`);
  return value;
}

function alertId(prefix) {
  return `al-${prefix}-${Date.now().toString(36)}`;
}

async function postCommand(request, key, id, body) {
  const response = await request.post(
    `${BASE}/api/v1/alerts/${encodeURIComponent(id)}/triage/commands`,
    {
      headers: {
        Authorization: `Bearer ${key}`,
        "Idempotency-Key": `t23-2-${crypto.randomUUID()}`,
      },
      data: body,
    },
  );
  return { response, body: await response.json() };
}

async function connect(page, key, id) {
  await page.goto(`${BASE}/public/admin/triage.html?alert_id=${encodeURIComponent(id)}`);
  await page.locator("#api-key").fill(key);
  await page.locator("#connect-button").click();
  await expect(page.locator("#command-operation")).toBeEnabled();
}

async function expectRecoveryRead(page, previousCount) {
  await expect.poll(() => page.context()["__triageRequests"].length).toBeGreaterThan(previousCount);
  await expect.poll(() => page.context()["__triageRequests"].at(-1)?.pathname.endsWith("/triage/context")).toBe(true);
}

test.beforeEach(async ({ page }) => {
  const requests = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (/\/api\/v1\/alerts\/[^/]+\/triage(?:\/commands|\/context)?$/.test(url.pathname)) {
      requests.push({ method: request.method(), pathname: url.pathname });
    }
  });
  page.context()["__triageRequests"] = requests;
});

test("stale command reads the winning version before explicit resubmission", async ({ page, request }) => {
  const key = requiredKey("E2E_TRIAGE_API_KEY");
  const raceAlert = alertId("t23-race");
  const targetIncident = "inc-0000-t23-linkable";

  const initial = await postCommand(request, key, raceAlert, {
    operation: "open_triage",
    expected_version: 1,
  });
  expect(initial.response.status()).toBe(200);
  expect(initial.body.expected_version).toBe(1);

  await connect(page, key, raceAlert);
  await expect(page.locator("#result-version")).toHaveText("1");
  await expect(page.locator("#command-operation")).toBeEnabled();
  await page.locator("#command-operation").selectOption("triage_link");
  await page.locator("#command-reason").fill("Link after reviewing the current alert.");
  await expect(page.locator(`#command-target option[value="${targetIncident}"]`)).toHaveCount(1);
  await page.locator("#command-target").selectOption(targetIncident);

  const beforeStaleSubmit = page.context()["__triageRequests"].length;
  const winner = await postCommand(request, key, raceAlert, {
    operation: "open_triage",
    expected_version: 1,
  });
  expect(winner.response.status()).toBe(200);
  expect(winner.body.expected_version).toBe(2);

  await page.locator("#submit-button").click();
  await expect(page.locator("#page-error-title")).toHaveText("Conflict");
  await expectRecoveryRead(page, beforeStaleSubmit);
  await expect(page.locator("#result-status")).toHaveText("open");
  await expect(page.locator("#result-origin")).toHaveText("Manual");
  await expect(page.locator("#result-version")).toHaveText("2");
  await expect(page.locator("#expected-version")).toHaveValue("2");
  await expect(page.locator("#result-summary")).toContainText("Recovered from backend");
  await expect(page.locator("#alert-id")).toHaveValue(raceAlert);
  await expect(page.locator("#command-operation")).toHaveValue("triage_link");
  await expect(page.locator("#command-reason")).toHaveValue("Link after reviewing the current alert.");
  await expect(page.locator("#command-target")).toHaveValue(targetIncident);
  if (process.env.T23_2_ARTIFACT_DIR) {
    await page.locator("#submit-button").evaluate((button) => button.blur());
    await page.screenshot({
      path: `${process.env.T23_2_ARTIFACT_DIR}/recovery.png`,
      fullPage: true,
    });
  }

  const beforeExplicitRetry = page.context()["__triageRequests"].length;
  await page.waitForTimeout(150);
  expect(page.context()["__triageRequests"]).toHaveLength(beforeExplicitRetry);
  expect(page.context()["__triageRequests"].filter(({ method }) => method === "POST")).toHaveLength(1);

  await page.locator("#submit-button").click();
  await expect(page.locator("#result-status")).toHaveText("linked");
  await expect(page.locator("#result-incident")).toHaveText(targetIncident);
  await expect(page.locator("#result-version")).toHaveText("3");
  expect(page.context()["__triageRequests"].filter(({ method }) => method === "POST")).toHaveLength(2);
});

test("stale declaration preserves selected severity for an explicit retry", async ({ page, request }) => {
  const key = requiredKey("E2E_TRIAGE_API_KEY");
  const id = alertId("t23-severity");
  const initial = await postCommand(request, key, id, {
    operation: "open_triage",
    expected_version: 1,
  });
  expect(initial.response.status()).toBe(200);
  expect(initial.body.expected_version).toBe(1);

  await connect(page, key, id);
  await expect(page.locator("#result-version")).toHaveText("1");
  await expect(page.locator("#command-operation")).toBeEnabled();
  await page.locator("#command-operation").selectOption("triage_declare");
  await page.locator("#command-reason").fill("Declare after reconciling fresh state.");
  await page.locator("#command-severity").selectOption("sev3");
  await page.locator("#command-impact").fill("Operators report that new orders cannot be paid.");
  await page.locator("#alert-context-service").fill("checkout-api");
  await page.locator("#alert-context-summary").fill("Payment attempts return errors.");
  await page.locator("#alert-context-observed-at").fill("2026-10-07T17:30:00Z");
  await page.locator("#alert-context-source").fill("operator-confirmed monitoring report");
  await page.locator("#alert-context-severity").selectOption("sev3");
  await page.locator("#alert-context-confirmed").check();
  const beforeStaleSubmit = page.context()["__triageRequests"].length;
  const winner = await postCommand(request, key, id, {
    operation: "open_triage",
    expected_version: 1,
  });
  expect(winner.response.status()).toBe(200);
  expect(winner.body.expected_version).toBe(2);

  await page.locator("#submit-button").click();
  await expect(page.locator("#page-error-title")).toHaveText("Conflict");
  await expectRecoveryRead(page, beforeStaleSubmit);
  await expect(page.locator("#expected-version")).toHaveValue("2");
  await expect(page.locator("#command-operation")).toHaveValue("triage_declare");
  await expect(page.locator("#command-reason")).toHaveValue("Declare after reconciling fresh state.");
  await expect(page.locator("#command-severity")).toHaveValue("sev3");
  await expect(page.locator("#command-impact")).toHaveValue("Operators report that new orders cannot be paid.");
  await expect(page.locator("#alert-context-service")).toHaveValue("checkout-api");
  await expect(page.locator("#alert-context-summary")).toHaveValue("Payment attempts return errors.");
  await expect(page.locator("#alert-context-observed-at")).toHaveValue("2026-10-07T17:30:00Z");
  await expect(page.locator("#alert-context-source")).toHaveValue("operator-confirmed monitoring report");
  await expect(page.locator("#alert-context-severity")).toHaveValue("sev3");
  await expect(page.locator("#alert-context-confirmed")).toBeChecked();

  await page.locator("#submit-button").click();
  await expect(page.locator("#result-status")).toHaveText("declared");
  await expect(page.locator("#result-version")).toHaveText("3");
  await expect(page.locator("#command-severity")).toHaveValue("sev3");
});

test("stale-version recovery preserves the draft when a context reread is denied", async ({ page, request }) => {
  const fullKey = requiredKey("E2E_TRIAGE_API_KEY");
  const id = alertId("t23-noread");

  const initial = await postCommand(request, fullKey, id, {
    operation: "open_triage",
    expected_version: 1,
  });
  expect(initial.response.status()).toBe(200);
  expect(initial.body.expected_version).toBe(1);
  const winner = await postCommand(request, fullKey, id, {
    operation: "open_triage",
    expected_version: 1,
  });
  expect(winner.response.status()).toBe(200);
  expect(winner.body.expected_version).toBe(2);

  let contextReads = 0;
  await page.route((url) => url.pathname.endsWith("/triage/context"), async (route) => {
    contextReads += 1;
    if (contextReads === 2)
      return route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ error: { code: "not_authorized" } }) });
    return route.continue();
  });
  await page.goto(`${BASE}/public/admin/triage.html`);
  await page.locator("#api-key").fill(fullKey);
  await page.locator("#connect-button").click();
  await page.locator("#alert-id").fill(id);
  await expect(page.locator("#command-operation")).toBeEnabled();
  await page.locator("#expected-version").fill("1");
  await page.locator("#command-operation").selectOption("triage_dismiss");
  await page.locator("#command-reason").fill("Preserve operator context after denied read.");

  await page.locator("#submit-button").click();
  await expect(page.locator("#page-error-title")).toHaveText("Conflict");
  await expect.poll(() =>
    page.context()["__triageRequests"].filter(({ pathname }) => pathname.endsWith("/triage/context")).length,
  ).toBe(2);
  await expect(page.locator("#page-error-detail")).toContainText("read");
  await expect(page.locator("#result-summary")).toHaveText(
    "Current state could not be verified; no command was confirmed.",
  );
  await expect(page.locator("#result-status")).toHaveText("—");
  await expect(page.locator("#result-origin")).toHaveText("—");
  await expect(page.locator("#result-responsible-system")).toHaveText("—");
  await expect(page.locator("#result-version")).toHaveText("—");
  await expect(page.locator("#expected-version")).toHaveValue("1");
  await expect(page.locator("#alert-id")).toHaveValue(id);
  await expect(page.locator("#command-operation")).toHaveValue("triage_dismiss");
  await expect(page.locator("#command-reason")).toHaveValue("Preserve operator context after denied read.");
  await expect(page.locator("#triage-page")).toHaveAttribute("data-state", "error");
  expect(page.context()["__triageRequests"].filter(({ method }) => method === "POST")).toHaveLength(1);
  expect(page.context()["__triageRequests"].filter(({ pathname }) => pathname.endsWith("/triage/context"))).toHaveLength(2);
});

test("reconnecting with the same credential releases only the new generation while an old response is held", async ({ page }) => {
  const fullKey = requiredKey("E2E_TRIAGE_API_KEY");
  const reconnectingKey = fullKey;
  const alertA = alertId("t23-switch-a");
  const alertB = alertId("t23-switch-b");

  await page.addInitScript(() => {
    const nativeFetch = globalThis.fetch.bind(globalThis);
    globalThis.__triageGate = { enabled: false, held: [], releases: {} };
    globalThis.fetch = async (input, init = {}) => {
      const response = await nativeFetch(input, init);
      const url = new URL(typeof input === "string" ? input : input.url, location.href);
      if (
        globalThis.__triageGate.enabled &&
        init.method === "POST" &&
        url.pathname.endsWith("/triage/commands")
      ) {
        const id = decodeURIComponent(url.pathname.split("/").at(-3));
        globalThis.__triageGate.held.push(id);
        await new Promise((resolve) => {
          globalThis.__triageGate.releases[id] = resolve;
        });
      }
      return response;
    };
  });

  await page.goto(`${BASE}/public/admin/triage.html`);
  await page.locator("#api-key").fill(fullKey);
  await page.locator("#connect-button").click();
  await page.evaluate(() => { globalThis.__triageGate.enabled = true; });

  try {
    await page.locator("#alert-id").fill(alertA);
    await expect(page.locator("#command-operation")).toBeEnabled();
    await page.locator("#command-operation").selectOption("open_triage");
    await page.locator("#submit-button").click();
    await expect.poll(() => page.evaluate(() => globalThis.__triageGate.held)).toContain(alertA);

    await page.locator("#api-key").fill(reconnectingKey);
    await page.locator("#connect-button").click();
    await expect(page.locator("#submit-button")).toBeDisabled();
    await page.locator("#alert-id").fill(alertB);
    await expect(page.locator("#command-operation")).toBeEnabled();
    await page.locator("#command-operation").selectOption("triage_dismiss");
    await page.locator("#command-reason").fill("Independent switched-session command.");
    await page.locator("#submit-button").click();
    await expect.poll(() => page.evaluate(() => globalThis.__triageGate.held)).toContain(alertB);

    await page.evaluate((id) => globalThis.__triageGate.releases[id](), alertA);
    await expect(page.locator("#triage-page")).toHaveAttribute("data-state", "loading");
    await expect(page.locator("#submit-button")).toBeDisabled();
    await expect(page.locator("#alert-id")).toHaveValue(alertB);
    await expect(page.locator("#command-reason")).toHaveValue("Independent switched-session command.");
    await expect(page.locator("#result-status")).toHaveText("—");

    await page.evaluate((id) => globalThis.__triageGate.releases[id](), alertB);
    await expect(page.locator("#result-status")).toHaveText("dismissed");
    await expect(page.locator("#triage-state")).toContainText(alertB);
    await expect(page.locator("#triage-page")).toHaveAttribute("data-state", "ready");
  } finally {
    await page.evaluate(([a, b]) => {
      globalThis.__triageGate.releases[a]?.();
      globalThis.__triageGate.releases[b]?.();
    }, [alertA, alertB]);
  }
});
