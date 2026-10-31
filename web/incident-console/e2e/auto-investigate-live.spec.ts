import { mkdirSync, writeFileSync } from "node:fs";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

/*
 * Issue #704 against the real stack, declaring from the new console (#703): OTel demo with the
 * checkout failure injected, setup_sre.py, the web proxy, FastAPI and PostgreSQL. No route is
 * answered by the test. Ways this can fail:
 * 1. the declaration does not open an `investigate` run, or opens it as someone else;
 * 2. the run is still `pending` (or missing) 5 s after the operator sent the declaration, or
 *    the first declaration opens more than one investigating run;
 * 3. replaying the exact request the console sent opens a second run or a second start;
 * 4. a declarant without run.start loses the declaration, or the timeline says nothing about
 *    why no investigation started, or a run appears anyway.
 * One run decides one episode (AUTO_INVESTIGATE=granted|no-grant): the next scenario needs
 * `demo_env.py reset` and `fail` for a new alert.
 */

const SCENARIO = process.env.AUTO_INVESTIGATE ?? "";
const DEMO_KEY = process.env.DEMO_HUMAN_API_KEY ?? "";
const ADMIN_KEY = process.env.ADMIN_HUMAN_API_KEY ?? "";
const BASE = process.env.BASE_URL ?? "http://127.0.0.1:8080";
const STAMP = Date.now().toString(36);
const WORKFLOW = { resource_type: "incident_workflow", resource_id: "incident-response" };

test.use({ video: "off", trace: "off" });

interface Run {
  run_id: string;
  status: string | null;
  current_state: string | null;
}

// A human who may see and declare live alerts but not start runs, created through the governed API.
async function declarerWithoutRunStart(admin: APIRequestContext): Promise<string> {
  const id = `declarer-no-run-${STAMP}`;
  const post = (path: string, data: unknown, key: string) =>
    admin.post(`${BASE}/api${path}`, { data, headers: { "Idempotency-Key": `e2e-704-${key}-${STAMP}-0001` } });
  expect((await post("/v1/principals", { principal_id: id, kind: "human", display_name: "Declarer" }, "p")).status()).toBe(201);
  const issued = await post(`/v1/principals/${id}/credentials`, { expires_at: "2031-01-01T00:00:00Z" }, "c");
  expect(issued.status()).toBe(201);
  const grants: Array<[string, unknown]> = [
    ["alert.read", WORKFLOW],
    ["incident.declare", WORKFLOW],
    ["mcp.discovery", { resource_type: "mcp_server", resource_id: "grafana-mcp" }],
    ["mcp.invoke", { resource_type: "mcp_tool", resource_id: "query_prometheus" }],
  ];
  for (const [index, [action, resource]] of grants.entries()) {
    const granted = await post(
      "/v1/grants",
      { grant_id: `grant-${id}-${index}`, principal_id: id, action, resource, effect: "allow" },
      `g${index}`,
    );
    expect(granted.status()).toBe(201);
  }
  return ((await issued.json()) as { key: string }).key;
}

async function declareFromCard(page: Page, key: string) {
  await page.goto("./");
  await page.getByRole("button", { name: "Conectar API" }).click();
  await page.getByRole("dialog").getByLabel("Clave de API").fill(key);
  await page.getByRole("dialog").getByRole("button", { name: "Conectar", exact: true }).click();
  const card = page.locator("article").filter({ hasText: "Nueva" }).first();
  await expect(card).toBeVisible({ timeout: 300_000 });
  const alertId = (await card.getAttribute("data-alert-id"))!;
  await card.getByRole("button", { name: "Declarar incidente" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("¿Qué notan tus clientes?").fill("Los clientes no pueden completar el pago en checkout.");
  const posted = page.waitForResponse(
    (response) => response.url().endsWith("/triage/commands") && response.request().method() === "POST",
  );
  // The 5 s bound counts from the operator's click, not from the 201.
  const sentAt = Date.now();
  await dialog.getByRole("button", { name: /Declarar e investigar/ }).click();
  const response = await posted;
  expect(response.status()).toBe(201);
  const request = response.request();
  return {
    alertId,
    sentAt,
    incidentId: ((await response.json()) as { incident_id: string }).incident_id,
    body: request.postDataJSON() as unknown,
    idempotencyKey: (await request.allHeaders())["idempotency-key"],
    responseBody: (await response.json()) as unknown,
  };
}

test.describe("declarar inicia la investigación contra la pila real", () => {
  test.skip(
    !["granted", "no-grant"].includes(SCENARIO) || !DEMO_KEY || (SCENARIO === "no-grant" && !ADMIN_KEY),
    "Requiere AUTO_INVESTIGATE=granted|no-grant, DEMO_HUMAN_API_KEY (y ADMIN_HUMAN_API_KEY sin grant)",
  );

  test(`la declaración desde la consola nueva (${SCENARIO})`, async ({ page, playwright }) => {
    test.setTimeout(420_000);
    const dir = `e2e/artifacts/auto-investigate-${SCENARIO}`;
    mkdirSync(dir, { recursive: true });
    const reader = await playwright.request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${DEMO_KEY}` } });
    let key = DEMO_KEY;
    if (SCENARIO === "no-grant") {
      const admin = await playwright.request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${ADMIN_KEY}` } });
      key = await declarerWithoutRunStart(admin);
      await admin.dispose();
    }

    const declared = await declareFromCard(page, key);
    const detailOf = async () => {
      const response = await reader.get(`${BASE}/api/v1/incidents/${declared.incidentId}`);
      expect(response.status()).toBe(200);
      return (await response.json()) as { runs: Run[] };
    };
    // Poll before waiting for the route or taking a screenshot, so neither counts against 5 s.
    let investigation: Run | undefined;
    let observedMs: number | undefined;
    if (SCENARIO === "granted") {
      await expect
        .poll(
          async () => {
            investigation = (await detailOf()).runs.find((run) => run.current_state === "investigating");
            return investigation?.status ?? "missing";
          },
          { timeout: 5_000, intervals: [100, 250, 500] },
        )
        .not.toMatch(/^(missing|pending)$/);
      observedMs = Date.now() - declared.sentAt;
      expect(observedMs).toBeLessThan(5_000);
      expect(investigation!.status).not.toBe("pending");
      const investigating = (await detailOf()).runs.filter((run) => run.current_state === "investigating");
      expect(investigating).toHaveLength(1);
    }

    // Since #703 the console lands on the declared incident's route.
    await expect(page).toHaveURL(new RegExp(`/incidentes/${declared.incidentId}$`));
    await page.screenshot({ path: `${dir}/incident-route.png`, fullPage: true });

    if (SCENARIO === "granted") {
      const events = await reader.get(
        `${BASE}/api/v1/incidents/${declared.incidentId}/runs/${investigation!.run_id}/events`,
      );
      expect(events.status()).toBe(200);
      const starts = ((await events.json()) as { events: Array<Record<string, any>> }).events.filter(
        (event) => event.summary === "Investigation started.",
      );
      expect(starts).toHaveLength(1);
      expect(starts[0].actor.reference.principal_id).toBe("demo-human");
      const runsBefore = (await detailOf()).runs.length;

      // The exact request the console sent, replayed: same key, same body, same answer, no new run.
      const replay = await reader.post(`${BASE}/api/v1/alerts/${encodeURIComponent(declared.alertId)}/triage/commands`, {
        headers: { "Idempotency-Key": declared.idempotencyKey },
        data: declared.body,
      });
      expect(replay.status()).toBe(201);
      expect(await replay.json()).toEqual(declared.responseBody);
      const after = await detailOf();
      expect(after.runs).toHaveLength(runsBefore);
      const replayEvents = await reader.get(
        `${BASE}/api/v1/incidents/${declared.incidentId}/runs/${investigation!.run_id}/events`,
      );
      const startsAfter = ((await replayEvents.json()) as { events: Array<{ summary: string }> }).events.filter(
        (event) => event.summary === "Investigation started.",
      );
      expect(startsAfter).toHaveLength(1);

      writeFileSync(
        `${dir}/verification.json`,
        JSON.stringify(
          {
            sanitized: true,
            scenario: SCENARIO,
            alertId: declared.alertId,
            incidentId: declared.incidentId,
            runObservedNotPendingWithinMs: observedMs,
            investigation,
            startEvent: { event_id: starts[0].event_id, actor: starts[0].actor.reference.principal_id },
            runs: after.runs.map(({ run_id, status, current_state }) => ({ run_id, status, current_state })),
            replay: { status: replay.status(), sameBody: true, runsBefore, runsAfter: after.runs.length },
          },
          null,
          2,
        ),
      );
    } else {
      const detail = await detailOf();
      expect(detail.runs.some((run) => run.current_state === "investigating")).toBe(false);
      const timeline = await reader.get(`${BASE}/api/v1/incidents/${declared.incidentId}/timeline`);
      expect(timeline.status()).toBe(200);
      const events = ((await timeline.json()) as { events: Array<Record<string, any>> }).events;
      const blocked = events.filter((event) => event.reason_code === "run_start_not_authorized");
      expect(blocked).toHaveLength(1);
      // The dispatch-cause catalogue of #705 words it (src/sre_agent/incident/reasons.py).
      expect(blocked[0].summary).toContain("Cause: the declarant lacks the run.start grant");
      writeFileSync(
        `${dir}/verification.json`,
        JSON.stringify(
          {
            sanitized: true,
            scenario: SCENARIO,
            alertId: declared.alertId,
            incidentId: declared.incidentId,
            runs: detail.runs.map(({ run_id, status, current_state }) => ({ run_id, status, current_state })),
            timeline: events.map(({ event_id, kind, summary, reason_code }) => ({ event_id, kind, summary, reason_code })),
          },
          null,
          2,
        ),
      );
    }

    await reader.dispose();
  });
});
