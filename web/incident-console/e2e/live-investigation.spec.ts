import { randomBytes } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { expect, request, test, type APIRequestContext, type Page } from "@playwright/test";

/*
 * The incident page against the real API (#708), on the stack of compose.console-e2e.yaml: the
 * API, database, investigator and web proxy are real; the model and Grafana MCP are scripted
 * (scripts/console_investigation_upstreams.py). Nothing is routed or mocked in the browser.
 * Run with scripts/run_console_journeys.sh; the keys never reach disk.
 */

const enabled = process.env.LIVE_INVESTIGATION === "1";
const API = `${process.env.BASE_URL ?? "http://127.0.0.1:8080"}/api/v1`;
const STAMP = randomBytes(4).toString("hex");
const DIR = "e2e/artifacts/live-investigation";
const record: Record<string, unknown> = { sanitized: true, stamp: STAMP };
// Run, event and request ids and UUIDs stay inside «Detalles técnicos».
const TECHNICAL = /\brun_|\bevt_|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|Snapshot v1/;

test.use({ video: "off", trace: "off" });
test.describe.configure({ mode: "serial" });

async function client(key: string): Promise<APIRequestContext> {
  return request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${key}` } });
}

async function send(api: APIRequestContext, path: string, data: unknown, expected: number) {
  const response = await api.post(`${API}${path}`, { data, headers: { "idempotency-key": `e2e-708-${randomBytes(12).toString("hex")}` } });
  expect(response.status(), `${path}: ${await response.text()}`).toBe(expected);
  return response.json();
}

/** Declares an incident from an alert of checkout, as the operator does from the inbox. */
async function declare(summary: string): Promise<string> {
  const demo = await client(process.env.DEMO_HUMAN_API_KEY!);
  const alert = `alt-e2e708-${STAMP}-${randomBytes(3).toString("hex")}`;
  const context = { service: "checkout", severity: "sev2", source: "e2e-708", summary, observed_at: new Date().toISOString() };
  const declared = await send(demo, `/alerts/${alert}/triage/commands`, {
    operation: "triage_declare",
    expected_version: 1,
    reason: "Los cobros fallan",
    severity: "sev2",
    impact: "Los clientes no pueden pagar sus pedidos.",
    alert_context: context,
  }, 201);
  return declared.incident_id;
}

async function runCount(incident: string): Promise<number> {
  const demo = await client(process.env.DEMO_HUMAN_API_KEY!);
  const detail = await (await demo.get(`${API}/incidents/${incident}`)).json();
  return detail.runs.length;
}

async function open(page: Page, incident: string) {
  await page.goto(`incidentes/${incident}`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Conecta una credencial");
  await page.getByRole("button", { name: "Conectar API" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Clave de API").fill(process.env.DEMO_HUMAN_API_KEY!);
  await dialog.getByRole("button", { name: "Conectar", exact: true }).click();
}

async function noTechnicalIds(page: Page) {
  expect(await page.locator("body").innerText()).not.toMatch(TECHNICAL);
}

test.describe("investigación en vivo contra la API real", () => {
  test.skip(!enabled, "Requiere LIVE_INVESTIGATION=1 y la pila de compose.console-e2e.yaml");
  test.beforeAll(() => mkdirSync(DIR, { recursive: true }));
  test.afterAll(() => writeFileSync(`${DIR}/verification.json`, JSON.stringify(record, null, 2)));

  test("la hipótesis, la evidencia con su veredicto y el cambio reciente aparecen sin recargar", async ({ page }) => {
    // An integration records the deploy that broke checkout a few minutes earlier (#770).
    const admin = await client(process.env.ADMIN_HUMAN_API_KEY!);
    const integration = `gha-checkout-${STAMP}`;
    await send(admin, "/principals", { principal_id: integration, kind: "agent", display_name: "GitHub Actions checkout" }, 201);
    const { key } = await send(admin, `/principals/${integration}/credentials`, {}, 201);
    const workflow = { resource_type: "incident_workflow", resource_id: "incident-response" };
    await send(admin, "/grants", { grant_id: `grant-${integration}-change-write`, principal_id: integration, action: "change.write", resource: workflow, effect: "allow" }, 201);
    const deploy = {
      source: "github-actions", external_id: `${STAMP}-deploy`, service: "checkout", kind: "deploy",
      version: "1.5.0", author: "ana", occurred_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    };
    await send(await client(key), "/changes", deploy, 201);

    const incident = await declare("checkout no puede cobrar a payment");
    record.investigated = incident;
    await open(page, incident);
    await expect(page.getByRole("heading", { level: 2, name: "Sin investigar" })).toBeVisible();
    const story = page.getByRole("complementary", { name: "Historia del incidente" });
    // A rerun on the same database also lists the deploys of earlier runs.
    await expect(story.getByText("Despliegue de checkout 1.5.0").first()).toBeVisible();

    await page.getByRole("button", { name: "Investigar" }).click();
    await expect(page.getByText("Investigando…").first()).toBeVisible();
    await expect(story.getByText("Empezó a investigar")).toBeVisible();
    await page.screenshot({ path: `${DIR}/1-investigando.png`, fullPage: true });

    await expect(page.getByRole("heading", { level: 2, name: "Esperando tu decisión" })).toBeVisible({ timeout: 90_000 });
    await expect(page.getByText("El despliegue de checkout 1.5.0 rompió los cobros contra payment.").first()).toBeVisible();
    for (const text of ["Consultó las métricas", "Consultó los logs", "Revisó los cambios recientes de checkout", "Propuso una hipótesis", "Propuso una mitigación", "Terminó de investigar"]) {
      await expect(story.getByText(text, { exact: true })).toBeVisible();
    }
    // Each cited evidence shows the verdict and the finding the investigator recorded (#707),
    // and none when the API records no verdict.
    const runs = (await (await (await client(process.env.DEMO_HUMAN_API_KEY!)).get(`${API}/incidents/${incident}`)).json()).runs;
    const context = await (await client(process.env.DEMO_HUMAN_API_KEY!)).get(`${API}/incidents/${incident}/runs/${runs.at(-1).run_id}/context`);
    const judged = (await context.json()).reasoning.evidence.filter((item: { verdict?: string }) => item.verdict).length;
    record.evidenceWithVerdict = judged;
    await expect(story.getByText("Respalda la hipótesis")).toHaveCount(judged);
    if (judged > 0) await expect(story.getByText("checkout desplegó la versión 1.5.0 minutos antes de la alerta.")).toBeVisible();
    await noTechnicalIds(page);
    await story.getByRole("button", { name: "Ver la consulta" }).first().click();
    await expect(story.getByText(/traces_span_metrics_calls_total/)).toBeVisible();
    await page.screenshot({ path: `${DIR}/2-hipotesis-y-evidencia.png`, fullPage: true });
    record.investigatedRuns = await runCount(incident);
  });

  test("un despacho fallido muestra su causa y solo una persona lo reintenta", async ({ page }) => {
    const incident = await declare("checkout no puede cobrar a payment [e2e:falla]");
    record.retried = incident;
    await open(page, incident);
    await page.getByRole("button", { name: "Investigar" }).click();

    const stopped = page.getByRole("heading", { level: 2, name: "Detenido: El modelo respondió en un formato no válido" });
    await expect(stopped).toBeVisible({ timeout: 90_000 });
    const story = page.getByRole("complementary", { name: "Historia del incidente" });
    await expect(story.getByText("La investigación se detuvo")).toBeVisible();
    await expect(story.getByText("Causa: el modelo respondió en un formato no válido.")).toBeVisible();
    await noTechnicalIds(page);
    await page.screenshot({ path: `${DIR}/3-detenido.png`, fullPage: true });

    // Nothing retries on its own: after a few polls the incident still has the same runs.
    const before = await runCount(incident);
    await page.waitForTimeout(8_000);
    expect(await runCount(incident)).toBe(before);
    await expect(stopped).toBeVisible();

    await page.getByRole("button", { name: "Reintentar investigación" }).click();
    await expect(page.getByText("Investigando…").first()).toBeVisible();
    await expect(page.getByRole("heading", { level: 2, name: "Esperando tu decisión" })).toBeVisible({ timeout: 90_000 });
    await expect(story.getByText("La investigación se detuvo")).toBeVisible();
    await expect(story.getByText("Terminó de investigar")).toBeVisible();
    await page.screenshot({ path: `${DIR}/4-reintento.png`, fullPage: true });
    record.retriedRuns = { beforeRetry: before, afterRetry: await runCount(incident) };
  });
});
