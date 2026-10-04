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

function kindsPage() {
  const base = (sequence, kind, summary, actor) => ({
    event_id: `evt_kinds00${sequence}`,
    kind,
    sequence,
    state: "investigating",
    summary,
    actor,
    turn_id: null,
    task_id: null,
    request_id: null,
    occurred_at: "2026-08-24T14:12:00Z",
  });
  const human = { type: "human", reference: { reference_version: "1.0.0", principal_id: "demo-human" } };
  return {
    events: [
      base(0, "human_command", "Approved the flag rollback.", human),
      base(1, "mitigation_proposed", "Proposed the flag rollback.", { type: "agent", reference: null }),
      base(2, "denial", "Denied the risky restart.", human),
      base(3, "state_change", "Executed successfully.", { type: "system", reference: null }),
    ],
    next_cursor: "seq:3",
    has_more: false,
  };
}

test("labels execution state per contractual event kind", async ({ page }) => {
  await mockApi(page, { pages: [kindsPage()], snapshot: snapshotPayload() });
  await openWarRoom(page);

  const items = page.locator(".war-room__event");
  await expect(items).toHaveCount(4);
  await expect(items.nth(0)).toContainText("Executed");
  await expect(items.nth(0)).toContainText("demo-human");
  await expect(items.nth(1)).toContainText("Proposed · Not executed");
  await expect(items.nth(2)).toContainText("Blocked · Denied");
  await expect(items.nth(3)).toContainText("Record");
  await expect(items.nth(3).locator(".ma-badge").nth(1)).toHaveText("Record");
});

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

// Holds only the next paged timeline request; later ones pass through. Lets
// a test forget, refresh or re-authenticate while that response is in flight,
// then releases it.
async function holdAfter(page) {
  let release = () => {};
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  let held = false;
  await page.route("**/api/v1/incidents/**", async (route) => {
    const url = new URL(route.request().url());
    if (!held && url.pathname.endsWith("/timeline") && url.searchParams.get("after")) {
      held = true;
      await gate;
    }
    await route.fallback();
  });
  return release;
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

test("two sessions render the same mocked version (shared persistence converges on the backend)", async ({
  browser,
}) => {
  // Render consistency only: both pages share one mocked backend here, so this
  // cannot prove shared persistence. Real convergence across recreated services
  // is covered by test_snapshot_stays_historical_after_advance_and_recreate in
  // tests/test_incident_query_timeline.py; triage entry and persisted comments
  // still depend on issue #23.
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

test("pins the selected run across pages when a new run appears", async ({ page }) => {
  // run B exists server-side as the new latest: any read without an explicit
  // run_id falls through to B's page. The view must keep paging run A.
  const seen = [];
  await page.route("**/api/v1/incidents/**", async (route) => {
    const url = new URL(route.request().url());
    seen.push(`run=${url.searchParams.get("run_id")}|after=${url.searchParams.get("after")}`);
    if (url.pathname.endsWith("/snapshot")) return route.fulfill({ json: snapshotPayload() });
    if (url.pathname.endsWith("/timeline")) {
      if (!url.searchParams.get("after")) return route.fulfill({ json: pageOne });
      if (url.searchParams.get("run_id") === "run_demo0001") {
        return route.fulfill({ json: pageTwo });
      }
      return route.fulfill({
        json: {
          events: [eventPayload(9, "Other run event.")],
          next_cursor: "seq:9",
          has_more: false,
        },
      });
    }
    return route.fulfill({ json: detailPayload() });
  });
  await openWarRoom(page);
  await expect(page.locator(".war-room__event")).toHaveCount(2);
  await page.locator("#load-more").click();
  await expect(page.locator(".war-room__event")).toHaveCount(3);
  await expect(page.locator(".war-room__event").last()).toContainText("Evidence collected.");
  expect(
    seen.some((entry) => entry.includes("run=run_demo0001") && entry.includes("after=seq:1")),
  ).toBe(true);
});

test("denied loadMore clears protected content without partials", async ({ page }) => {
  const cases = [
    [401, "authentication_failed", "#error-401", true],
    [403, "not_authorized", "#error-403", false],
  ];
  for (const [http, code, selector, canReauth] of cases) {
    await page.unroute("**/api/v1/incidents/**");
    await mockApi(page, { pages: [pageOne, pageTwo], snapshot: snapshotPayload() });
    await openWarRoom(page);
    await expect(page.locator(".war-room__event")).toHaveCount(2);
    await page.route("**/api/v1/incidents/**", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname.endsWith("/timeline") && url.searchParams.get("after")) {
        await route.fulfill({ status: http, json: errorPayload(code, "denied during paging") });
        return;
      }
      await route.fallback();
    });
    await page.locator("#load-more").click();
    await expect(page.locator(selector)).toBeVisible();
    await expect(page.locator("#summary-section")).toBeHidden();
    if (canReauth) {
      await expect(page.locator("#credential-section")).toBeVisible();
      await page.unroute("**/api/v1/incidents/**");
      await mockApi(page, { pages: [pageOne, pageTwo], snapshot: snapshotPayload() });
      await authenticate(page);
      await expect(page.locator(".war-room__event")).toHaveCount(2);
    } else {
      await expect(page.locator("#forget-credential")).toBeVisible();
    }
  }
});

test("recovers the view after a 503 during loadMore", async ({ page }) => {
  await mockApi(page, { pages: [pageOne, pageTwo], snapshot: snapshotPayload() });
  await openWarRoom(page);
  await expect(page.locator(".war-room__event")).toHaveCount(2);
  await page.route("**/api/v1/incidents/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/timeline") && url.searchParams.get("after")) {
      await route.fulfill({
        status: 503,
        json: errorPayload("storage_unavailable", "store down"),
      });
      return;
    }
    await route.fallback();
  });
  await page.locator("#load-more").click();
  await expect(page.locator("#error-503")).toBeVisible();
  await expect(page.locator("#refresh-button")).toBeVisible();
  await page.unroute("**/api/v1/incidents/**");
  await mockApi(page, { pages: [pageOne, pageTwo], snapshot: snapshotPayload() });
  await page.locator("#refresh-button").click();
  await expect(page.locator("#error-503")).toBeHidden();
  await expect(page.locator(".war-room__event")).toHaveCount(2);
});

test("drops a stale delayed response after forgetting the credential", async ({ page }) => {
  await mockApi(page, { pages: [pageOne, pageTwo], snapshot: snapshotPayload() });
  await openWarRoom(page);
  await expect(page.locator(".war-room__event")).toHaveCount(2);
  const release = await holdAfter(page);
  await page.locator("#load-more").click();
  await page.locator("#forget-credential").click();
  await expect(page.locator("#credential-section")).toBeVisible();
  const staleArrived = page.waitForResponse(
    (response) =>
      response.url().includes("/timeline") &&
      new URL(response.url()).searchParams.get("after") === "seq:1",
  );
  release();
  await staleArrived;
  await expect(page.locator("#credential-section")).toBeVisible();
  await expect(page.locator("#timeline-section")).toBeHidden();
  await expect(page.locator(".war-room__event")).toHaveCount(0);
});

test("a newer session paginates while the old request is still pending", async ({ page }) => {
  await mockApi(page, { pages: [pageOne, pageTwo], snapshot: snapshotPayload() });
  await openWarRoom(page);
  await expect(page.locator(".war-room__event")).toHaveCount(2);
  const release = await holdAfter(page);
  await page.locator("#load-more").click();
  await page.locator("#forget-credential").click();
  await authenticate(page);
  await expect(page.locator(".war-room__event")).toHaveCount(2);
  // The new session must page while the old request is still held: the race
  // stays open, so this cannot pass by resolving the old request first.
  const isPagedTimeline = (response) =>
    response.url().includes("/timeline") &&
    new URL(response.url()).searchParams.get("after") === "seq:1";
  const newPageArrived = page.waitForResponse(isPagedTimeline);
  await page.locator("#load-more").click();
  await newPageArrived;
  await expect(page.locator(".war-room__event")).toHaveCount(3);
  // Only now release the old request: state and paging lock must not change.
  const staleArrived = page.waitForResponse(isPagedTimeline);
  release();
  await staleArrived;
  await expect(page.locator(".war-room__event")).toHaveCount(3);
  await expect(page.locator("#version-line")).toContainText("Versión 4");
  await expect(page.locator("#load-more")).toBeHidden();
  await expect(page.locator("#load-more")).toBeEnabled();
});

test("shows an explicit no-snapshot state instead of failing", async ({ page }) => {
  await mockApi(page, { pages: [pageOne, pageTwo] });
  await openWarRoom(page);

  await expect(page.locator("#summary-section")).toBeVisible();
  await expect(page.locator("#fact-snapshot")).toHaveText("Sin snapshot todavía");
});

test("shows a recoverable 503 state when the network fails", async ({ page }) => {
  await page.route("**/api/v1/incidents/**", async (route) => route.abort());
  await page.goto(`/public/incident-ui/war-room.html?incident_id=${INCIDENT}`);
  await authenticate(page);

  await expect(page.locator("#error-503")).toBeVisible();
  await expect(page.locator("#refresh-button")).toBeVisible();
});

test("refresh re-derives the latest run when a new run appears", async ({ page }) => {
  await mockApi(page, { pages: [pageOne, pageTwo], snapshot: snapshotPayload() });
  await openWarRoom(page);
  await expect(page.locator(".war-room__event")).toHaveCount(2);

  const pageNew = {
    events: [eventPayload(0, "New run started."), eventPayload(1, "New run continued.")],
    next_cursor: "seq:1",
    has_more: false,
  };
  await page.unroute("**/api/v1/incidents/**");
  await page.route("**/api/v1/incidents/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/timeline")) return route.fulfill({ json: pageNew });
    if (url.pathname.endsWith("/snapshot")) return route.fulfill({ json: snapshotPayload() });
    const detail = detailPayload();
    detail.runs.push({
      run_id: "run_demo0002",
      version: 1,
      status: "running",
      current_state: "triage",
      updated_at: "2026-08-24T14:20:00Z",
    });
    return route.fulfill({ json: detail });
  });
  await page.locator("#refresh-button").click();
  await expect(page.locator(".war-room__event")).toHaveCount(2);
  await expect(page.locator(".war-room__event").first()).toContainText("New run started.");
});

test("renders approvals as responsible persons", async ({ page }) => {
  const detail = detailPayload();
  detail.approvals = [
    {
      approval_id: "apr_demo0001",
      subject_id: "demo-human",
      granted: true,
      decided_at: "2026-08-24T14:20:00Z",
    },
  ];
  await mockApi(page, { detail, pages: [pageOne, pageTwo], snapshot: snapshotPayload() });
  await openWarRoom(page);

  await expect(page.locator("#approvals-list")).toContainText("demo-human");
  await expect(page.locator("#approvals-list")).toContainText("Aprobado");
  await expect(page.locator("#approvals-empty")).toBeHidden();
});

// HU-OPS-05 slice #40a: explicit run selection over the existing timeline.
function detailWithRuns(...runIds) {
  const detail = detailPayload();
  detail.runs = runIds.map((runId, index) => ({
    run_id: runId,
    version: 4,
    status: "running",
    current_state: index === 0 ? "investigating" : "triage",
    updated_at: "2026-08-24T14:20:00Z",
  }));
  return detail;
}

function runPage(prefix, sequences, cursor, hasMore) {
  return {
    events: sequences.map((sequence) =>
      eventPayload(sequence, `${prefix} event ${sequence}.`),
    ),
    next_cursor: cursor,
    has_more: hasMore,
  };
}

async function mockRuns(page, { detail, runPages, snapshot }) {
  const seen = [];
  await page.route("**/api/v1/incidents/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/snapshot")) {
      return route.fulfill({ json: snapshot ?? snapshotPayload() });
    }
    if (url.pathname.endsWith("/timeline")) {
      const runId = url.searchParams.get("run_id");
      seen.push(`run=${runId}|after=${url.searchParams.get("after")}`);
      const pages = runPages[runId] ?? runPages.__default;
      const pageBody = url.searchParams.get("after") ? pages[1] : pages[0];
      return route.fulfill({ json: pageBody });
    }
    return route.fulfill({ json: detail });
  });
  return seen;
}

test("lists incident runs and switches the timeline to the chosen run", async ({ page }) => {
  const detail = detailWithRuns("run_demo0001", "run_demo0002");
  const runPages = {
    run_demo0001: [runPage("Alpha", [0, 1], "seq:1", false)],
    run_demo0002: [runPage("Beta", [0, 1], "seq:1", false)],
    __default: [runPage("Alpha", [0, 1], "seq:1", false)],
  };
  const seen = await mockRuns(page, { detail, runPages });
  await openWarRoom(page);

  await expect(page.locator("#run-select option")).toHaveCount(2);
  await expect(page.locator("#run-select")).toHaveValue("run_demo0002");
  await expect(page.locator(".war-room__event").first()).toContainText("Beta event 0.");

  await page.locator("#run-select").selectOption("run_demo0001");
  await expect(page.locator(".war-room__event").first()).toContainText("Alpha event 0.");
  await expect(page.locator("#run-current")).toContainText("run_demo0001");
  expect(seen.some((entry) => entry.startsWith("run=run_demo0001"))).toBe(true);
  const body = (await page.locator("#timeline-list").textContent()) ?? "";
  expect(body).not.toContain("Beta event");
});

test("keeps the explicit run across pagination and reload", async ({ page }) => {
  const detail = detailWithRuns("run_demo0001", "run_demo0002");
  const runPages = {
    run_demo0001: [runPage("Alpha", [0, 1], "seq:1", true), runPage("Alpha", [2], "seq:2", false)],
    run_demo0002: [runPage("Beta", [0], "seq:0", false)],
    __default: [runPage("Alpha", [0, 1], "seq:1", true)],
  };
  const seen = await mockRuns(page, { detail, runPages });
  await openWarRoom(page);

  await page.locator("#run-select").selectOption("run_demo0001");
  await expect(page.locator(".war-room__event").first()).toContainText("Alpha event 0.");
  await page.locator("#load-more").click();
  await expect(page.locator(".war-room__event")).toHaveCount(3);
  expect(
    seen.some((entry) => entry.includes("run=run_demo0001") && entry.includes("after=seq:1")),
  ).toBe(true);

  await page.unroute("**/api/v1/incidents/**");
  const grown = detailWithRuns("run_demo0001", "run_demo0002", "run_demo0003");
  await mockRuns(page, { detail: grown, runPages });
  await page.locator("#refresh-button").click();
  await expect(page.locator("#run-select option")).toHaveCount(3);
  await expect(page.locator("#run-select")).toHaveValue("run_demo0001");
  await expect(page.locator(".war-room__event").first()).toContainText("Alpha event 0.");
});

test("escapes untrusted summaries and hides out-of-projection fields", async ({ page }) => {
  const hostile = {
    ...eventPayload(0, '<img src="x" onerror="window.__pwned=1"> Fiscaliza.'),
    arguments: { cmd: "MARKER-ARGS" },
    raw_output: "MARKER-RAW",
    prompt: "MARKER-PROMPT",
  };
  await mockRuns(page, {
    detail: detailWithRuns("run_demo0001"),
    runPages: {
      run_demo0001: [{ events: [hostile], next_cursor: "seq:0", has_more: false }],
      __default: [{ events: [hostile], next_cursor: "seq:0", has_more: false }],
    },
  });
  await openWarRoom(page);

  await expect(page.locator(".war-room__event img")).toHaveCount(0);
  await expect(page.locator(".war-room__event")).toContainText("Fiscaliza.");
  expect(await page.evaluate(() => window.__pwned)).toBeUndefined();
  const body = (await page.locator("#timeline-list").textContent()) ?? "";
  for (const marker of ["MARKER-ARGS", "MARKER-RAW", "MARKER-PROMPT"]) {
    expect(body).not.toContain(marker);
  }
  await expect(page.locator(".war-room__event")).toContainText("estado investigating");
});

test("exposes no slice-40b controls on the read-only timeline", async ({ page }) => {
  await mockRuns(page, {
    detail: detailWithRuns("run_demo0001"),
    runPages: { run_demo0001: [pageOne, pageTwo], __default: [pageOne, pageTwo] },
  });
  await openWarRoom(page);

  for (const selector of ["#postmortem", "#mitigation", "#run-command", "#transition"]) {
    await expect(page.locator(selector)).toHaveCount(0);
  }
  const labels = await page.locator("button").allTextContents();
  for (const label of labels) {
    expect(label).not.toMatch(/postmortem|mitigat|command|transition|start|close/i);
  }
});
