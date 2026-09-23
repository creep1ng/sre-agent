import { expect, test } from "@playwright/test";

const INCIDENT = "inc-demo";

function detailPayload(version = 4) {
  return {
    incident_id: INCIDENT,
    workflow_version: "1.0.0",
    state: "investigating",
    severity: "sev2",
    impact: "Checkout failing at payment.",
    alert: {
      alert_id: "alt-payment-error-rate",
      service: "paymentservice",
      severity: "sev2",
      status: "triaged",
      observed_at: "2026-08-24T14:05:00Z",
      summary: "Elevated error rate on paymentservice.",
      source: "grafana-alerting",
    },
    approvals: [],
    version,
    updated_at: "2026-08-24T14:20:00Z",
    runs: [
      {
        run_id: "run_demo0001",
        version,
        status: "running",
        current_state: "investigating",
        updated_at: "2026-08-24T14:20:00Z",
      },
    ],
  };
}

function eventPayload(sequence, summary, actor = { type: "system", reference: null }) {
  return {
    event_id: `evt_demo00${sequence}`,
    kind: "state_change",
    sequence,
    state: "investigating",
    summary,
    actor,
    turn_id: null,
    task_id: null,
    request_id: null,
    occurred_at: "2026-08-24T14:12:00Z",
  };
}

function snapshotPayload(version = 4) {
  const detail = detailPayload(version);
  return {
    snapshot_id: "snap_demo0001",
    incident_id: INCIDENT,
    run_id: "run_demo0001",
    version,
    event_sequence: 1,
    incident: detail,
    run: detail.runs[0],
    created_at: "2026-08-24T14:20:00Z",
  };
}

function errorPayload(code, message) {
  return {
    error: { code, message },
    request_id: "00000000-0000-4000-8000-000000000000",
    retryable: false,
  };
}

async function mockApi(page, { detail, pages, snapshot, failure = null } = {}) {
  const first = pages?.[0] ?? { events: [], next_cursor: "seq:-1", has_more: false };
  const second = pages?.[1] ?? { events: [], next_cursor: "seq:-1", has_more: false };
  await page.route("**/api/v1/incidents/**", async (route) => {
    const url = new URL(route.request().url());
    if (failure) {
      await route.fulfill({
        status: failure.http,
        json: errorPayload(failure.code, failure.message),
      });
      return;
    }
    if (url.pathname.endsWith("/timeline")) {
      const after = url.searchParams.get("after");
      await route.fulfill({ json: after ? second : first });
      return;
    }
    if (url.pathname.endsWith("/snapshot")) {
      if (!snapshot) {
        await route.fulfill({
          status: 404,
          json: errorPayload("snapshot_absent", "No snapshot exists for this run yet."),
        });
        return;
      }
      await route.fulfill({ json: snapshot });
      return;
    }
    await route.fulfill({ json: detail ?? detailPayload() });
  });
}

async function authenticate(page) {
  await page.locator("#credential-input").fill("sre_demo_token_demo_0001");
  await page.locator("#credential-form button[type=submit]").click();
}

async function openWarRoom(page, incidentId = INCIDENT) {
  await page.goto(`/public/incident-ui/war-room.html?incident_id=${incidentId}`);
  await expect(page.locator("#credential-section")).toBeVisible();
  await authenticate(page);
}

const pageOne = {
  events: [eventPayload(0, "Triage declared an incident."), eventPayload(1, "Investigation started.")],
  next_cursor: "seq:1",
  has_more: true,
};

const pageTwo = {
  events: [eventPayload(2, "Evidence collected.")],
  next_cursor: "seq:2",
  has_more: false,
};

test("renders the persisted summary, version and first timeline page", async ({ page }) => {
  await mockApi(page, { pages: [pageOne, pageTwo], snapshot: snapshotPayload() });
  await openWarRoom(page);

  await expect(page.locator("#incident-title")).toHaveText("Elevated error rate on paymentservice.");
  await expect(page.locator("#version-line")).toContainText("Versión 4");
  await expect(page.locator("#fact-snapshot")).toContainText("v4 (seq 1)");
  await expect(page.locator(".war-room__event")).toHaveCount(2);
  await expect(page.locator("#timeline-count")).toHaveText("2 eventos");
});

test("loads the second page without duplicating events", async ({ page }) => {
  await mockApi(page, { pages: [pageOne, pageTwo], snapshot: snapshotPayload() });
  await openWarRoom(page);

  await page.locator("#load-more").click();
  await expect(page.locator(".war-room__event")).toHaveCount(3);
  await expect(page.locator("#timeline-count")).toHaveText("3 eventos");
  await expect(page.locator("#load-more")).toBeHidden();
});

test("refresh reconciles to the new backend version", async ({ page }) => {
  await mockApi(page, { pages: [pageOne, pageTwo], snapshot: snapshotPayload(4) });
  await openWarRoom(page);
  await expect(page.locator("#version-line")).toContainText("Versión 4");

  await page.unroute("**/api/v1/incidents/**");
  await mockApi(page, {
    detail: detailPayload(5),
    pages: [pageOne, pageTwo],
    snapshot: snapshotPayload(5),
  });
  await page.locator("#refresh-button").click();
  await expect(page.locator("#version-line")).toContainText("Versión 5");
  await expect(page.locator(".war-room__event")).toHaveCount(2);
});

test("shows the empty timeline state without errors", async ({ page }) => {
  await mockApi(page, { snapshot: snapshotPayload() });
  await openWarRoom(page);

  await expect(page.locator("#timeline-empty")).toBeVisible();
  await expect(page.locator("#load-more")).toBeHidden();
});

test("missing incident_id explains without fetching", async ({ page }) => {
  let fetched = false;
  await page.route("**/api/v1/**", async (route) => {
    fetched = true;
    await route.abort();
  });
  await page.goto("/public/incident-ui/war-room.html");

  await expect(page.locator("#error-missing-id")).toBeVisible();
  expect(fetched).toBe(false);
});

test("distinguishes 401, 403, 404 and 503 states", async ({ page }) => {
  const cases = [
    ["authentication_failed", 401, "#error-401"],
    ["not_authorized", 403, "#error-403"],
    ["incident_not_found", 404, "#error-404"],
    ["storage_unavailable", 503, "#error-503"],
  ];
  for (const [code, http, selector] of cases) {
    await page.unroute("**/api/v1/incidents/**");
    await mockApi(page, { failure: { http, code, message: `${code} message` } });
    await page.goto(`/public/incident-ui/war-room.html?incident_id=${INCIDENT}`);
    await authenticate(page);
    await expect(page.locator(selector)).toBeVisible();
    await expect(page.locator("#summary-section")).toBeHidden();
  }
});

test("exposes no lifecycle or harness controls", async ({ page }) => {
  await mockApi(page, { pages: [pageOne, pageTwo], snapshot: snapshotPayload() });
  await openWarRoom(page);

  await expect(page.locator("#refresh-button")).toBeVisible();
  const buttons = await page.locator("button").allTextContents();
  for (const label of buttons) {
    expect(label).not.toMatch(/triage|approv|harness|mitigat|lifecycle/i);
  }
});

test("two authorized sessions converge on the same version", async ({ browser }) => {
  const first = await browser.newPage();
  const second = await browser.newPage();
  for (const page of [first, second]) {
    await mockApi(page, { pages: [pageOne, pageTwo], snapshot: snapshotPayload() });
    await openWarRoom(page);
    await expect(page.locator('#war-room[data-state="ready"]')).toBeAttached();
  }
  const expected = (await second.locator("#version-line").textContent()) ?? "";
  await expect(first.locator("#version-line")).toHaveText(expected);
  await first.close();
  await second.close();
});
