import { expect, test } from "@playwright/test";

const INCIDENT = "inc-demo";

function detailPayload() {
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
    version: 4,
    updated_at: "2026-08-24T14:20:00Z",
    runs: [
      { run_id: "run_demo0001", version: 4, status: "running", current_state: "investigating", updated_at: "2026-08-24T14:20:00Z" },
    ],
  };
}

async function openPostmortem(page, status = 200) {
  await page.route("**/api/v1/incidents/**", async (route) => {
    if (status === 200) return route.fulfill({ json: detailPayload() });
    return route.fulfill({ status, json: { error: { code: "not_authorized" } } });
  });
  await page.goto(`/public/incident-ui/postmortem.html?incident_id=${INCIDENT}`);
  await page.locator("#credential-input").fill("sre_demo_token_demo_0001");
  await page.locator("#credential-form button[type=submit]").click();
}

test("renders the minimum sections with explicit unknowns", async ({ page }) => {
  await openPostmortem(page);

  await expect(page.locator("#fact-incident")).toHaveText(INCIDENT);
  await expect(page.locator("#fact-state")).toHaveText("investigating");
  await expect(page.locator("#fact-artifact")).toContainText("pm_demo0001");
  await expect(page.locator("#fact-artifact")).toContainText("draft");
  await expect(page.locator("#fixture-banner")).toContainText("#335");
  for (const section of ["Resumen", "Impacto conocido", "Hipotesis o causa", "Certeza", "Estrategia", "Verificacion", "Pendientes"]) {
    await expect(page.locator("#artifact-sections")).toContainText(section);
  }
  await expect(page.locator("#artifact-sections")).toContainText("Desconocido");
  await expect(page.locator("#artifact-sections")).toContainText("Pendiente");
});

test("reloads the same fixture and never closes", async ({ page }) => {
  await openPostmortem(page);
  await expect(page.locator("#artifact-sections")).toContainText("Resumen");

  await page.reload();
  await expect(page.locator("#credential-section")).toBeVisible();
  await expect(page.locator("#close-incident")).toHaveCount(0);
  const labels = await page.locator("button").allTextContents();
  for (const label of labels) {
    expect(label).not.toMatch(/close|cierre/i);
  }
});

test("shows the forbidden state without content", async ({ page }) => {
  await openPostmortem(page, 403);

  await expect(page.locator("#error-403")).toBeVisible();
  await expect(page.locator("#context-section")).toBeHidden();
  await expect(page.locator("#artifact-section")).toBeHidden();
});

function detailTwoRuns() {
  const detail = detailPayload();
  detail.runs.push(
    { run_id: "run_demo0002", version: 1, status: "running", current_state: "triage", updated_at: "2026-08-24T14:21:00Z" },
  );
  return detail;
}

function timelineFor(prefix) {
  return {
    events: [
      { event_id: "evt_x1", kind: "state_change", sequence: 0, state: "investigating", summary: `${prefix} record one.`, actor: { type: "system", reference: null }, turn_id: null, task_id: null, request_id: null, occurred_at: "2026-08-24T14:12:00Z" },
    ],
    next_cursor: "seq:0",
    has_more: false,
  };
}

async function openProvenance(page, { hostile = false } = {}) {
  await page.route("**/api/v1/incidents/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/timeline")) {
      const runId = url.searchParams.get("run_id") ?? "run_demo0002";
      const payload = timelineFor(runId === "run_demo0001" ? "Alpha" : "Beta");
      if (hostile) payload.events[0].summary = '<img src="x" onerror="window.__pwned=1"> Fiscaliza.';
      return route.fulfill({ json: payload });
    }
    return route.fulfill({ json: detailTwoRuns() });
  });
  await page.goto(`/public/incident-ui/postmortem.html?incident_id=${INCIDENT}`);
  await page.locator("#credential-input").fill("sre_demo_token_demo_0001");
  await page.locator("#credential-form button[type=submit]").click();
}

test("keeps run provenance without mixing runs", async ({ page }) => {
  await openProvenance(page);

  await expect(page.locator("#run-select option")).toHaveCount(2);
  await expect(page.locator("#provenance-list")).toContainText("run run_demo0002");
  await page.locator("#run-select").selectOption("run_demo0001");
  await expect(page.locator("#provenance-list")).toContainText("Alpha record one.");
  const body = (await page.locator("#provenance-list").textContent()) ?? "";
  expect(body).not.toContain("Beta record");
  expect(body).not.toMatch(/applied|aplicada|ejecutada/i);
});

test("hides restricted content and escapes untrusted records", async ({ page }) => {
  await openProvenance(page, { hostile: true });

  await expect(page.locator("#provenance-list")).toContainText("Fiscaliza.");
  await expect(page.locator("#provenance-list img")).toHaveCount(0);
  expect(await page.evaluate(() => window.__pwned)).toBeUndefined();
  const body = (await page.locator("#postmortem").textContent()) ?? "";
  expect(body).not.toContain("MARKER-RESTRICTED");
});

test("drops a late timeline reply for a deselected run", async ({ page }) => {
  let releaseRun1;
  const gate = new Promise((resolve) => {
    releaseRun1 = resolve;
  });
  await page.route("**/api/v1/incidents/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/timeline")) {
      const runId = url.searchParams.get("run_id") ?? "run_demo0002";
      if (runId === "run_demo0001") await gate;
      const payload = timelineFor(runId === "run_demo0001" ? "Alpha" : "Beta");
      return route.fulfill({ json: payload });
    }
    return route.fulfill({ json: detailTwoRuns() });
  });
  await page.goto(`/public/incident-ui/postmortem.html?incident_id=${INCIDENT}`);
  await page.locator("#credential-input").fill("sre_demo_token_demo_0001");
  await page.locator("#credential-form button[type=submit]").click();
  await expect(page.locator("#provenance-list")).toContainText("run run_demo0002");
  await page.locator("#run-select").selectOption("run_demo0001");
  const run2reply = page.waitForResponse(
    (response) =>
      response.url().includes("/timeline") && response.url().includes("run_demo0002"),
  );
  await page.locator("#run-select").selectOption("run_demo0002");
  await run2reply;
  releaseRun1();
  await page.waitForTimeout(300);
  const body = (await page.locator("#provenance-list").textContent()) ?? "";
  expect(body).toContain("run run_demo0002");
  expect(body).not.toContain("Alpha record");
});

test("keeps review session-only without persistence or close", async ({ page }) => {
  await openProvenance(page);
  await expect(page.locator("#review-section")).toBeVisible();

  await page.locator("#review-note").fill("Sesión local.");
  await page.locator("#review-form button[type=submit]").click();
  await expect(page.locator("#review-saved")).toBeVisible();
  await page.reload();
  await expect(page.locator("#credential-section")).toBeVisible();
  await expect(page.locator("#close-incident")).toHaveCount(0);
  expect(await page.evaluate(() => window.localStorage.length)).toBe(0);
  const labels = await page.locator("button").allTextContents();
  for (const label of labels) {
    expect(label).not.toMatch(/close|cierre/i);
  }
});
