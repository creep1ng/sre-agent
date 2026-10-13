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

test("drops a stale first reply after reselecting the same run", async ({ page }) => {
  let releaseFirst;
  const gate = new Promise((resolve) => {
    releaseFirst = resolve;
  });
  let run1calls = 0;
  await page.route("**/api/v1/incidents/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/timeline")) {
      const runId = url.searchParams.get("run_id") ?? "run_demo0002";
      if (runId === "run_demo0001") {
        run1calls += 1;
        const marker = run1calls === 1 ? "Alpha stale." : "Alpha current.";
        if (run1calls === 1) await gate;
        return route.fulfill({ json: timelineFor(marker) });
      }
      return route.fulfill({ json: timelineFor("Beta") });
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
  const run1again = page.waitForResponse(
    (response) =>
      response.url().includes("/timeline") && response.url().includes("run_demo0001"),
  );
  await page.locator("#run-select").selectOption("run_demo0001");
  await run1again;
  await expect(page.locator("#provenance-list")).toContainText("Alpha current.");
  releaseFirst();
  await page.waitForTimeout(300);
  const body = (await page.locator("#provenance-list").textContent()) ?? "";
  expect(body).toContain("Alpha current.");
  expect(body).not.toContain("Alpha stale.");
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

test("forgetting the credential clears the session review note", async ({ page }) => {
  await openProvenance(page);
  await page.locator("#review-note").fill("Nota confidencial del operador A.");
  await page.locator("#review-form button[type=submit]").click();
  await expect(page.locator("#review-saved")).toBeVisible();

  await page.locator("#forget-credential").click();
  await expect(page.locator("#credential-section")).toBeVisible();
  await expect(page.locator("#review-note")).toHaveValue("");
  await expect(page.locator("#review-saved")).toBeHidden();

  await page.locator("#credential-input").fill("sre_demo_token_demo_0002");
  await page.locator("#credential-form button[type=submit]").click();
  await expect(page.locator("#review-note")).toHaveValue("");
  await expect(page.locator("#review-saved")).toBeHidden();
  const reviewBody = (await page.locator("#review-section").textContent()) ?? "";
  expect(reviewBody).not.toContain("Nota confidencial del operador A.");
});

function pagedTimeline(prefix, start, count, cursor, hasMore) {
  return {
    events: Array.from({ length: count }, (_, index) => ({
      event_id: `evt_${prefix}_${start + index}`,
      kind: "state_change",
      sequence: start + index,
      state: "investigating",
      summary: `${prefix} record ${start + index}.`,
      actor: { type: "system", reference: null },
      turn_id: null,
      task_id: null,
      request_id: null,
      occurred_at: "2026-08-24T14:12:00Z",
    })),
    next_cursor: cursor,
    has_more: hasMore,
  };
}

async function mockPagedRuns(page, runPages) {
  const seen = [];
  await page.route("**/api/v1/incidents/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/timeline")) {
      const runId = url.searchParams.get("run_id") ?? "run_demo0002";
      const after = url.searchParams.get("after");
      seen.push(`run=${runId}|after=${after ?? "-"}`);
      const pages = runPages[runId] ?? runPages.__default;
      const body = after ? (pages[1] ?? { events: [], next_cursor: after, has_more: false }) : pages[0];
      return route.fulfill({ json: body });
    }
    return route.fulfill({ json: detailTwoRuns() });
  });
  return seen;
}

async function openPagedProvenance(page, runPages) {
  const seen = await mockPagedRuns(page, runPages);
  await page.goto(`/public/incident-ui/postmortem.html?incident_id=${INCIDENT}`);
  await page.locator("#credential-input").fill("sre_demo_token_demo_0001");
  await page.locator("#credential-form button[type=submit]").click();
  await expect(page.locator("#provenance-list")).not.toBeEmpty();
  return seen;
}

test("loads continuation pages without duplicates and in contractual order", async ({ page }) => {
  const runPages = {
    run_demo0002: [
      pagedTimeline("Beta", 0, 50, "seq:49", true),
      pagedTimeline("Beta", 50, 15, "seq:64", false),
    ],
    __default: [pagedTimeline("Beta", 0, 50, "seq:49", true)],
  };
  const seen = await openPagedProvenance(page, runPages);

  await expect(page.locator("#provenance-list > li")).toHaveCount(50);
  await expect(page.locator("#load-more")).toBeVisible();
  await page.locator("#load-more").click();
  await expect(page.locator("#provenance-list > li")).toHaveCount(65);
  await expect(page.locator("#load-more")).toBeHidden();
  await expect(page.locator("#timeline-count")).toContainText("65");

  expect(seen).toContain("run=run_demo0002|after=-");
  expect(seen).toContain("run=run_demo0002|after=seq:49");
  const ids = await page.locator("#provenance-list > li").evaluateAll((nodes) =>
    nodes.map((node) => node.textContent ?? ""),
  );
  expect(new Set(ids).size).toBe(65);
  expect(ids[0]).toContain("Beta record 0.");
  expect(ids[64]).toContain("Beta record 64.");
});

test("drops a late continuation page for a deselected run", async ({ page }) => {
  let releaseAlpha = () => {};
  const gate = new Promise((resolve) => {
    releaseAlpha = resolve;
  });
  const runPages = {
    run_demo0001: [pagedTimeline("Alpha", 0, 50, "seq:49", true), pagedTimeline("Alpha", 50, 5, "seq:54", false)],
    run_demo0002: [pagedTimeline("Beta", 0, 2, "seq:1", false)],
    __default: [pagedTimeline("Beta", 0, 2, "seq:1", false)],
  };
  const seen = [];
  await page.route("**/api/v1/incidents/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/timeline")) {
      const runId = url.searchParams.get("run_id") ?? "run_demo0002";
      const after = url.searchParams.get("after");
      seen.push(`run=${runId}|after=${after ?? "-"}`);
      if (runId === "run_demo0001" && after) {
        await gate;
        return route.fulfill({ json: runPages.run_demo0001[1] });
      }
      const pages = runPages[runId] ?? runPages.__default;
      return route.fulfill({ json: after ? (pages[1] ?? pages[0]) : pages[0] });
    }
    return route.fulfill({ json: detailTwoRuns() });
  });
  await page.goto(`/public/incident-ui/postmortem.html?incident_id=${INCIDENT}`);
  await page.locator("#credential-input").fill("sre_demo_token_demo_0001");
  await page.locator("#credential-form button[type=submit]").click();
  await expect(page.locator("#provenance-list")).not.toBeEmpty();

  await page.locator("#run-select").selectOption("run_demo0001");
  await expect(page.locator("#provenance-list > li")).toHaveCount(50);
  // Dispatch directly: the button hides as soon as the run changes, which a
  // waiting click would never survive; the handler is already running then.
  const held = page.locator("#load-more").dispatchEvent("click");
  await page.locator("#run-select").selectOption("run_demo0002");
  await expect(page.locator("#provenance-list > li").first()).toContainText("Beta record 0.");
  releaseAlpha();
  await held.catch(() => {});
  await page.waitForTimeout(300);
  const body = (await page.locator("#provenance-list").textContent()) ?? "";
  expect(body).toContain("Beta record 0.");
  expect(body).not.toContain("Alpha record 50.");
});

test("a failing continuation page surfaces an error instead of a complete list", async ({ page }) => {
  await page.route("**/api/v1/incidents/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/timeline")) {
      const after = url.searchParams.get("after");
      if (after) {
        return route.fulfill({ status: 503, json: { error: { code: "storage_unavailable", message: "store down" } } });
      }
      return route.fulfill({ json: pagedTimeline("Beta", 0, 50, "seq:49", true) });
    }
    return route.fulfill({ json: detailTwoRuns() });
  });
  await page.goto(`/public/incident-ui/postmortem.html?incident_id=${INCIDENT}`);
  await page.locator("#credential-input").fill("sre_demo_token_demo_0001");
  await page.locator("#credential-form button[type=submit]").click();
  await expect(page.locator("#provenance-list > li")).toHaveCount(50);

  await page.locator("#load-more").click();
  await expect(page.locator("#error-503")).toBeVisible();
  await expect(page.locator("#provenance-section")).toBeHidden();
  await expect(page.locator("#refresh-button")).toBeVisible();
});
