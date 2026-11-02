import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { expect, test, type APIRequestContext } from "@playwright/test";
import { freshEpisodes } from "./live-faults";

/*
 * Issue #704: a declaration's investigation that loses its dispatcher still ends, against the
 * live-triage stack (compose.live-triage-e2e.yaml: real API, PostgreSQL and web proxy; stand-in
 * model and Grafana MCP). DISPATCH_RECOVERY picks the step:
 * - `interrupt`: declare with the stand-in model held (`$FAULT_DIR/model-delay`) and stop once the
 *   dispatch intent is pending; the host then kills and restarts the API;
 * - `interrupted`: after the restart, the run that lost its dispatcher;
 * - `handoff-failure`: the host breaks the investigator's agent identity first, so the hand-off
 *   fails before it can claim the run.
 * Ways this can fail:
 * 1. after the restart the run stays `running` forever, or is redispatched automatically;
 * 2. it ends without `needs_human` or without `producer_interrupted` on its receipt;
 * 3. a person's retry is still refused beside the dead run;
 * 4. a hand-off failing before the claim leaves the run `running`, with no reason.
 */

const STEP = process.env.DISPATCH_RECOVERY ?? "";
const KEY = process.env.DEMO_HUMAN_API_KEY ?? "";
const BASE = process.env.BASE_URL ?? "http://127.0.0.1:8080";
const FAULT_DIR = process.env.FAULT_DIR ?? "";
const DIR = "e2e/artifacts/dispatch-recovery";
const STATE = `${DIR}/interrupt.json`;

test.use({ video: "off", trace: "off" });

interface Run {
  run_id: string;
  status: string | null;
  current_state: string | null;
  terminated_reason?: string | null;
}
type Event = { event_id: string; kind: string; summary: string; reason_code: string | null };

async function declare(api: APIRequestContext) {
  const [alertId] = await freshEpisodes(api, BASE, ["checkout-payment-error-rate"]);
  const response = await api.post(`${BASE}/api/v1/alerts/${alertId}/triage/commands`, {
    headers: { "Idempotency-Key": `e2e-704-recovery-${STEP}-${Date.now().toString(36)}` },
    data: {
      operation: "triage_declare",
      expected_version: 1,
      reason: "Declarada para probar la recuperación del despacho.",
      severity: "sev2",
      impact: "Los clientes no pueden completar el pago.",
      alert_context: {
        service: "checkout",
        summary: "Errores de pago en checkout",
        observed_at: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
        source: "grafana",
        severity: "sev2",
      },
    },
  });
  expect(response.status()).toBe(201);
  return { alertId, incidentId: ((await response.json()) as { incident_id: string }).incident_id };
}

async function investigation(api: APIRequestContext, incidentId: string) {
  const detail = await api.get(`${BASE}/api/v1/incidents/${incidentId}`);
  expect(detail.status()).toBe(200);
  const runs = ((await detail.json()) as { runs: Run[] }).runs;
  return { runs, run: runs.find((run) => run.current_state === "investigating") };
}

async function events(api: APIRequestContext, incidentId: string, runId: string): Promise<Event[]> {
  const response = await api.get(`${BASE}/api/v1/incidents/${incidentId}/runs/${runId}/events`);
  expect(response.status()).toBe(200);
  return ((await response.json()) as { events: Event[] }).events;
}

async function ended(api: APIRequestContext, incidentId: string, runId: string) {
  await expect
    .poll(async () => (await investigation(api, incidentId)).runs.find((run) => run.run_id === runId)?.status, {
      timeout: 60_000,
    })
    .toBe("terminated");
  const state = await api.get(`${BASE}/api/v1/incidents/${incidentId}/runs/${runId}`);
  expect(state.status()).toBe(200);
  return (await state.json()) as Run;
}

test.describe("una investigación sin despachador termina con una causa", () => {
  test.skip(
    !["interrupt", "interrupted", "handoff-failure"].includes(STEP) || !KEY || !FAULT_DIR,
    "Requiere DISPATCH_RECOVERY=interrupt|interrupted|handoff-failure, DEMO_HUMAN_API_KEY y FAULT_DIR",
  );

  test(`recuperación del despacho (${STEP})`, async ({ page, playwright }) => {
    test.setTimeout(240_000);
    mkdirSync(DIR, { recursive: true });
    const api = await playwright.request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${KEY}` } });
    const shot = async (incidentId: string, runId: string, file: string) => {
      await page.setExtraHTTPHeaders({ authorization: `Bearer ${KEY}` });
      await page.goto(`${BASE}/api/v1/incidents/${incidentId}/runs/${runId}/events`);
      await page.screenshot({ path: `${DIR}/${file}`, fullPage: true });
    };

    if (STEP === "interrupt") {
      writeFileSync(`${FAULT_DIR}/model-delay`, "150");
      const { alertId, incidentId } = await declare(api);
      let runId = "";
      await expect
        .poll(async () => {
          runId = (await investigation(api, incidentId)).run?.run_id ?? "";
          return runId ? (await events(api, incidentId, runId)).map((event) => event.summary) : [];
        })
        .toContain("Investigation dispatch started.");
      expect((await investigation(api, incidentId)).run?.status).toBe("running");
      writeFileSync(STATE, JSON.stringify({ alertId, incidentId, runId }));
      await api.dispose();
      return;
    }

    let incidentId: string;
    let runId: string;
    if (STEP === "interrupted") {
      ({ incidentId, runId } = JSON.parse(readFileSync(STATE, "utf8")) as { incidentId: string; runId: string });
      rmSync(`${FAULT_DIR}/model-delay`, { force: true });
    } else {
      ({ incidentId } = await declare(api));
      await expect.poll(async () => (await investigation(api, incidentId)).run?.run_id ?? "").not.toBe("");
      runId = (await investigation(api, incidentId)).run!.run_id;
    }
    const run = await ended(api, incidentId, runId);
    expect(run.terminated_reason).toBe("needs_human");
    const timeline = await events(api, incidentId, runId);
    const reason = STEP === "interrupted" ? "producer_interrupted" : "investigator_failed";
    const outcome = timeline.filter((event) => event.kind === "dispatch_receipt" && event.reason_code === reason);
    expect(outcome).toHaveLength(1);
    expect(timeline.filter((event) => event.kind === "run_terminated")).toHaveLength(1);
    // Nothing redispatched it: still one investigation run, and one dispatch intent at most.
    const runs = (await investigation(api, incidentId)).runs;
    expect(runs.filter((item) => item.current_state === "investigating")).toHaveLength(1);
    expect(timeline.filter((event) => event.summary === "Investigation dispatch started.").length).toBeLessThanOrEqual(1);

    let retry: number | null = null;
    if (STEP === "interrupted") {
      // A person may retry now: the dead run no longer blocks a new one.
      const response = await api.post(`${BASE}/api/v1/incidents/${incidentId}/runs`, {
        headers: { "Idempotency-Key": `e2e-704-retry-${Date.now().toString(36)}` },
        data: { workflow_version: "1.0.0", objective: "investigate" },
      });
      retry = response.status();
      expect(retry).toBe(201);
    }
    await shot(incidentId, runId, `${STEP}-run-events-api.png`);
    writeFileSync(
      `${DIR}/${STEP}-verification.json`,
      JSON.stringify(
        {
          sanitized: true,
          step: STEP,
          incidentId,
          runId,
          run: { status: run.status, terminated_reason: run.terminated_reason },
          events: timeline.map(({ kind, summary, reason_code }) => ({ kind, summary, reason_code })),
          humanRetryStatus: retry,
        },
        null,
        2,
      ),
    );
    await api.dispose();
  });
});
