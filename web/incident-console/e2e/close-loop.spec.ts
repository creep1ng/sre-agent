import { randomBytes } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { expect, request, test, type APIRequestContext, type Page } from "@playwright/test";

/*
 * #723 on the stack of compose.close-loop-e2e.yaml: API, database, investigator, web proxy and the
 * deploy-executor acting on this project's sre-checkout are real; the model and Grafana MCP are
 * scripted, and the verification is answered with real orders on sre-checkout. Ways it can fail:
 * 1. an approval that ran is never verified, and the incident waits in verifying;
 * 2. the verdict does not follow the release that runs: a restart that left 1.5.0 passes, or the
 *    rollback to 1.4.0 fails;
 * 3. a failed verification does not send the incident back to investigation, or the page does not
 *    say that Midnight measured it and what was expected;
 * 4. the system investigates again without learning what failed, and proposes the restart again;
 * 5. a measured recovery does not resolve the incident;
 * 6. an execution leaves no audit event an administrator can read.
 * Run with scripts/run_close_loop_e2e.sh; keys never reach disk.
 */

const enabled = process.env.CLOSE_LOOP_E2E === "1";
const API = `${process.env.BASE_URL ?? "http://127.0.0.1:8080"}/api/v1`;
const STAMP = randomBytes(4).toString("hex");
const DIR = "e2e/artifacts/close-loop";
// The marker makes the scripted model try a restart first (scripts/incident_console_upstreams.py).
const SUMMARY = "sre-checkout: 3 de cada 10 pedidos fallan con 500 [e2e:reinicio]";
const CHECK = "Los pedidos de sre-checkout dejan de fallar con 500.";
const DEMO = process.env.DEMO_HUMAN_API_KEY!;
const ADMIN = process.env.ADMIN_HUMAN_API_KEY!;

type Told = { at: string; actor: string; reference: string | null; summary: string };

// No trace: it would keep the keys' headers. A failure leaves its screenshot instead.
test.use({ video: "off", trace: "off", screenshot: "only-on-failure" });

const clients = new Map<string, APIRequestContext>();
async function client(key: string): Promise<APIRequestContext> {
  if (!clients.has(key)) clients.set(key, await request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${key}` } }));
  return clients.get(key)!;
}

async function read(path: string, key = DEMO) {
  const response = await (await client(key)).get(`${API}${path}`);
  expect(response.status(), `${path}: ${await response.text()}`).toBe(200);
  return response.json();
}

/** Every run's events, oldest first, in the API's own words and with who did each. */
async function story(incident: string): Promise<Told[]> {
  const told: Told[] = [];
  for (const { run_id } of (await read(`/incidents/${incident}`)).runs) {
    let page = await read(`/incidents/${incident}/runs/${run_id}/events?limit=200`);
    const events = [...page.events];
    while (page.has_more) {
      page = await read(`/incidents/${incident}/runs/${run_id}/events?limit=200&after=${page.next_cursor}`);
      events.push(...page.events);
    }
    for (const event of events) {
      told.push({ at: event.occurred_at, actor: event.actor.type, reference: event.actor.reference?.principal_id ?? null, summary: event.summary });
    }
  }
  return told.sort((a, b) => a.at.localeCompare(b.at));
}

const by = (told: Told[], summary: string) => told.filter((item) => item.summary === summary).map((item) => item.actor);

/** The receipt of the mitigation that just ran, as the incident keeps it (any run reads the incident's reasoning). */
async function receipt(incident: string) {
  const run = (await read(`/incidents/${incident}`)).runs[0].run_id;
  const ran = (await read(`/incidents/${incident}/runs/${run}/context`)).reasoning.mitigation_strategy.execution;
  return { execution_id: ran.execution_id, outcome: ran.outcome, before_image: ran.before_image, after_image: ran.after_image };
}

/** One Grafana Alerting delivery to intake (#765), as the contact point sends it with its secret. */
async function grafana(status: "firing" | "resolved", startsAt: string) {
  const alert = {
    status,
    labels: { alertname: "service-error-rate", service_name: "sre-checkout", severity: "critical" },
    annotations: { summary: SUMMARY },
    startsAt,
    endsAt: status === "resolved" ? new Date().toISOString() : "0001-01-01T00:00:00Z",
    fingerprint: `close-loop-${STAMP}`,
  };
  const intake = await client(process.env.ALERT_INTAKE_GRAFANA_SECRET!);
  const response = await intake.post(`${API}/alert-intake/grafana`, { data: { status, groupKey: `close-loop-${STAMP}`, alerts: [alert] } });
  expect(response.status(), await response.text()).toBe(200);
  return (await response.json()).episodes[0];
}

/** Opens a console path and connects a key, which lives only in this tab's memory. */
async function connect(page: Page, path: string, key = DEMO) {
  await page.addInitScript(() => localStorage.setItem("midnight-language", JSON.stringify({ state: { language: "es" }, version: 0 })));
  await page.goto(path);
  await page.getByRole("button", { name: "Conectar API" }).click();
  await page.getByRole("dialog").getByLabel("Clave de API").fill(key);
  await page.getByRole("dialog").getByRole("button", { name: "Conectar", exact: true }).click();
}

/** The person approves the plan the page proposes, and the receipt of what ran comes back. */
async function approve(page: Page, plan: string, ran: string) {
  await expect(page.getByRole("heading", { level: 2, name: plan })).toBeVisible({ timeout: 120_000 });
  await page.getByRole("button", { name: "Aprobar", exact: true }).click();
  const decided = page.getByRole("region", { name: "Decisiones tomadas" });
  await expect(decided.locator("[data-receipt]", { hasText: ran })).toHaveCount(1, { timeout: 60_000 });
}

async function shoot(page: Page, name: string) {
  await page.mouse.move(0, 0);
  await page.screenshot({ path: `${DIR}/${name}.png`, fullPage: true });
}

async function journey(page: Page, report: Record<string, unknown>) {
  // The setup grants the agent the rollback only; an administrator grants the restart too.
  const resource = { resource_type: "service_operation", resource_id: "sre-checkout:deployment.restart" };
  const grant = { grant_id: `grant-close-loop-restart-${STAMP}`, principal_id: "incident-harness", action: "mitigation.execute", resource, effect: "allow" };
  const granted = await (await client(ADMIN)).post(`${API}/grants`, { data: grant, headers: { "idempotency-key": `e2e-723-${STAMP}` } });
  expect(granted.status(), await granted.text()).toBe(201);

  // Grafana's rule fires: intake declares the incident and the investigation starts, nobody at the console.
  const startsAt = new Date(Date.now() - 120_000).toISOString();
  const incident: string = (await grafana("firing", startsAt)).incident_id;
  report.incident = incident;

  // A person approves the first proposal: the restart runs, and sre-checkout stays on 1.5.0.
  await connect(page, `incidentes/${incident}`);
  await approve(page, "Reiniciar sre-checkout", "Se ejecutó deployment.restart en sre-checkout: reiniciado");
  await shoot(page, "1-reinicio-aprobado");
  const executions = [await receipt(incident)];
  report.executions = executions;

  // Ten seconds later the agent places real orders: they still fail, it says so, and the incident goes back to investigation.
  await expect.poll(async () => by(await story(incident), "Verification failed; returned to investigating."), { timeout: 120_000 }).toEqual(["agent"]);
  expect(by(await story(incident), "Verification found the service had not recovered.")).toEqual(["agent"]);
  await connect(page, `incidentes/${incident}`);
  const step = page.locator("#step-verification");
  await expect(step).toContainText("Verificación · la señal no se recuperó", { timeout: 30_000 });
  await expect(step).toContainText("Midnight · La verificación falló; se vuelve a investigar");
  await expect(step).toContainText(`No se cumplió lo esperado: ${CHECK}`);
  await step.scrollIntoViewIfNeeded();
  await step.screenshot({ path: `${DIR}/2-verificacion-fallida.png` });

  // Midnight investigates again on its own, told the restart ran and failed: it proposes the rollback instead.
  const rolledBack = "Se ejecutó deployment.rollback en sre-checkout: revertido (midnight-e2e/checkout:1.5.0 → midnight-e2e/checkout:1.4.0)";
  await approve(page, "Volver sre-checkout a la 1.4.0", rolledBack);
  executions.push(await receipt(incident));
  expect(executions).toMatchObject([
    { outcome: "restarted" },
    { outcome: "rolled_back", before_image: "midnight-e2e/checkout:1.5.0", after_image: "midnight-e2e/checkout:1.4.0" },
  ]);
  const running = await (await request.newContext()).get("http://sre-checkout:8080/");
  expect((await running.json()).version).toBe("1.4.0");

  // The agent measures again: every order goes through, and the incident resolves without anyone saying so.
  await expect.poll(async () => (await read(`/incidents/${incident}`)).state, { timeout: 120_000 }).toMatch(/^(resolved|postmortem)$/);
  const told = await story(incident);
  report.story = told;
  expect(by(told, "Verification found the service recovered.")).toEqual(["agent"]);
  expect(by(told, "Service verified stable.")).toEqual(["agent"]);
  const approvals = told.filter((item) => item.summary.startsWith("Mitigation approved; the deploy-executor ran"));
  expect(approvals.map((item) => [item.actor, item.reference])).toEqual([["human", "demo-human"], ["human", "demo-human"]]);
  await connect(page, `incidentes/${incident}`);
  await expect(page.locator("#step-verification")).toContainText("Midnight · Servicio verificado estable", { timeout: 30_000 });
  await shoot(page, "3-resuelto");

  // The audit an administrator reads: each execution is a mitigation.execute event of the agent, correlated with the incident.
  const audit = (await read(`/audit-events?incident_id=${incident}&limit=100`, ADMIN)).items;
  const executed = audit.filter((item: { operation?: string }) => item.operation === "mitigation.execute");
  const operations: Record<string, number> = {};
  for (const item of audit) operations[item.operation] = (operations[item.operation] ?? 0) + 1;
  report.audit = { operations, "mitigation.execute": executed };
  expect(executed.map((item: { outcome?: string }) => item.outcome)).toEqual(["success", "success"]);
  const ranBy = (await read(`/audit-events?incident_id=${incident}&principal_id=incident-harness&limit=100`, ADMIN)).items;
  expect(ranBy.filter((item: { operation?: string }) => item.operation === "mitigation.execute")).toHaveLength(2);
  // Who approved each run, as the action catalog joins its audit event with the run.
  type Run = Record<string, unknown> & { incident_id?: string };
  const catalog: { services: { operations: { operation: string; executions: Run[] }[] }[] } = await read("/action-catalog");
  const approved = catalog.services
    .flatMap((service) => service.operations.flatMap((item) => item.executions.map((run) => ({ operation: item.operation, ...run }))))
    .filter((run) => run.incident_id === incident)
    .sort((a, b) => a.operation.localeCompare(b.operation));
  report.approved = approved;
  expect(approved).toMatchObject([
    { operation: "deployment.restart", outcome: "succeeded", approved_by: { principal_id: "demo-human" } },
    { operation: "deployment.rollback", outcome: "succeeded", approved_by: { principal_id: "demo-human" } },
  ]);

  const audits = await page.context().newPage();
  await connect(audits, "admin/auditoria", ADMIN);
  await audits.getByLabel("ID de incidente").fill(incident);
  await audits.getByRole("button", { name: "Aplicar filtros" }).click();
  await expect(audits.locator("td", { hasText: "mitigation.execute" })).toHaveCount(2, { timeout: 30_000 });
  await shoot(audits, "4-auditoria");

  // Grafana stops alerting once the service recovered.
  expect((await grafana("resolved", startsAt)).status).toBe("resolved");
}

test.describe("cerrar el ciclo contra la API real (#723)", () => {
  test.skip(!enabled, "Requiere CLOSE_LOOP_E2E=1 y la pila de compose.close-loop-e2e.yaml");
  test.beforeAll(() => mkdirSync(DIR, { recursive: true }));

  test("lo aprobado se ejecuta, el agente lo verifica y el incidente se resuelve o vuelve a investigarse", async ({ page }) => {
    test.setTimeout(480_000);
    const report: Record<string, unknown> = { sanitized: true, stamp: STAMP };
    try {
      await journey(page, report);
    } finally {
      writeFileSync(`${DIR}/report.json`, JSON.stringify(report, null, 2));
    }
  });
});
