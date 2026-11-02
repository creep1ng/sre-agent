import { randomBytes } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { expect, request, test, type APIRequestContext, type Page } from "@playwright/test";

/*
 * The RC-2 incident page against the real API (#870, #708, #709), on the stack of
 * compose.incident-console-e2e.yaml: the API, database, investigator and web proxy are real; the
 * model and Grafana MCP are scripted (scripts/incident_console_upstreams.py). Nothing is routed or
 * mocked in the browser. Run with scripts/run_incident_console_e2e.sh; keys never reach disk.
 */

const enabled = process.env.LIVE_INCIDENT === "1";
const API = `${process.env.BASE_URL ?? "http://127.0.0.1:8080"}/api/v1`;
const STAMP = randomBytes(4).toString("hex");
const DIR = "e2e/artifacts/incident-live";
const record: Record<string, unknown> = { sanitized: true, stamp: STAMP };
// Run, event and request ids and UUIDs stay inside the technical details.
const TECHNICAL = /\brun_|\bevt_|\bev_|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/;
const AMBER = ["rgb(242, 180, 90)", "rgb(166, 90, 0)"];
const PLAN = "Volver checkout a la 1.4.0";

test.use({ video: "off", trace: "off" });
test.describe.configure({ mode: "serial" });

async function client(key: string): Promise<APIRequestContext> {
  return request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${key}` } });
}

async function send(api: APIRequestContext, path: string, data: unknown, expected: number) {
  const response = await api.post(`${API}${path}`, { data, headers: { "idempotency-key": `e2e-870-${randomBytes(12).toString("hex")}` } });
  expect(response.status(), `${path}: ${await response.text()}`).toBe(expected);
  return response.json();
}

async function read(path: string) {
  return (await (await client(process.env.DEMO_HUMAN_API_KEY!)).get(`${API}${path}`)).json();
}

/** Declares an incident from a checkout alert as the demo human. */
async function declare(summary: string): Promise<string> {
  const demo = await client(process.env.DEMO_HUMAN_API_KEY!);
  const alert = `alt-e2e870-${STAMP}-${randomBytes(3).toString("hex")}`;
  const context = { service: "checkout", severity: "sev2", source: "e2e-870", summary, observed_at: new Date().toISOString() };
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

/** Opens the incident in a language; the key lives only in this tab's memory, so it is connected each time. */
async function open(page: Page, incident: string, language: "es" | "en" = "es") {
  await page.addInitScript((value) => localStorage.setItem("midnight-language", JSON.stringify({ state: { language: value }, version: 0 })), language);
  await page.goto(`incidentes/${incident}`);
  await page.getByRole("button", { name: language === "es" ? "Conectar API" : "Connect API" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Clave de API").fill(process.env.DEMO_HUMAN_API_KEY!);
  await dialog.getByRole("button", { name: "Conectar", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/checkout/);
}

/** Declaring starts the investigation on the server (#858): the page follows it to the proposal. */
async function investigate(page: Page) {
  await expect(page.getByText("Investigando…")).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: PLAN })).toBeVisible({ timeout: 90_000 });
}

/** Painted colours outside the elements a pending decision owns. */
function amberOutsideDecision(page: Page) {
  return page.evaluate((amber) => {
    const found: string[] = [];
    for (const element of document.querySelectorAll("body *")) {
      const style = getComputedStyle(element);
      const painted = [style.color, style.backgroundColor, style.borderTopColor, style.borderLeftColor];
      if (painted.some((value) => amber.includes(value)) && !element.closest("[data-decision]")) found.push(element.outerHTML.slice(0, 80));
    }
    return found;
  }, AMBER);
}

async function noTechnicalIds(page: Page) {
  expect(await page.locator("article").innerText()).not.toMatch(TECHNICAL);
}

test.describe("incidente RC-2 contra la API real", () => {
  test.skip(!enabled, "Requiere LIVE_INCIDENT=1 y la pila de compose.incident-console-e2e.yaml");
  test.beforeAll(() => mkdirSync(DIR, { recursive: true }));
  test.afterAll(() => writeFileSync(`${DIR}/verification.json`, JSON.stringify(record, null, 2)));

  test("las afirmaciones de la hipótesis muestran su evidencia y llevan a su paso; aprobar envía el comando gobernado", async ({ page }) => {
    const incident = await declare("checkout no puede cobrar a payment");
    record.approved = incident;
    await open(page, incident);
    await investigate(page);

    const hypothesis = page.locator("#hypothesis");
    await expect(hypothesis).toContainText("El despliegue de checkout 1.5.0 rompió los cobros contra payment.");
    await expect(hypothesis.locator("code", { hasText: "1.5.0" }).first()).toHaveCSS("font-family", /JetBrains Mono/);
    const claims = hypothesis.getByRole("link");
    expect(await claims.count()).toBeGreaterThanOrEqual(2);
    record.claims = await claims.count();

    // Hover: the evidence card with its verdict, time, finding and source.
    const claim = claims.filter({ hasText: "Los cobros fallan con context deadline exceeded" });
    const card = page.locator(`#${await claim.getAttribute("aria-describedby")}`);
    await expect(card).toBeHidden();
    await claim.hover();
    await expect(card).toBeVisible();
    await expect(card).toContainText("apoya");
    await expect(card).toContainText("Logs de checkout");
    await expect(card).toContainText(/\d{2}:\d{2}/);
    await page.screenshot({ path: `${DIR}/afirmacion-evidencia.png` });
    // Focus opens it too.
    await page.mouse.move(0, 0);
    await expect(card).toBeHidden();
    await claim.focus();
    await expect(card).toBeVisible();

    // Click: its step in the timeline.
    await claim.click();
    const step = (await claim.getAttribute("href"))!;
    expect(page.url()).toContain(step);
    await expect(page.locator(step)).toBeInViewport();
    await expect(page.locator(step)).toContainText("Logs de checkout");

    const timeline = page.getByRole("list", { name: "Línea de tiempo del incidente" });
    for (const text of ["Tú · Declaraste el incidente", "Tú · Pediste la investigación", "Midnight · Empezó a investigar", "Midnight · Métricas de checkout", "Midnight · Propone una hipótesis", "Midnight · Propone una mitigación", "Midnight espera tu decisión"]) {
      await expect(timeline.getByText(text, { exact: true })).toBeVisible();
    }
    await noTechnicalIds(page);
    expect(await amberOutsideDecision(page)).toEqual([]);

    // Night and day follow the system theme; the screenshots go to docs/evidence/issue-870/incident.
    await page.evaluate(() => window.scrollTo(0, 0));
    for (const scheme of ["dark", "light"] as const) {
      await page.emulateMedia({ colorScheme: scheme });
      await page.screenshot({ path: `${DIR}/incidente-${scheme === "dark" ? "noche" : "dia"}-es.png`, fullPage: true });
    }
    await page.emulateMedia({ colorScheme: "dark" });

    const detail = await read(`/incidents/${incident}`);
    const sent = page.waitForRequest((request) => request.url().includes("/commands") && request.method() === "POST");
    await page.getByRole("button", { name: "Aprobar" }).click();
    const command = await sent;
    const body = command.postDataJSON();
    expect(body.command).toBe("approve_mitigation");
    expect(body.expected_incident_version).toBe(detail.version);
    expect(body.authorization.action).toBe("run.approve");
    expect(command.headers()["idempotency-key"]).toMatch(/^console-approve_mitigation-[0-9a-f]{32}$/);
    expect((await command.response())?.status()).toBe(202);

    const proposal = page.getByRole("region", { name: "Propuesta de mitigación" });
    await expect(proposal).toContainText(/Aprobada · Tú · \d{2}:\d{2}/);
    await expect(timeline.getByText("Tú · Aprobaste la mitigación")).toBeVisible();
    await expect(page.getByRole("button", { name: "Aprobar" })).toHaveCount(0);
    expect(await amberOutsideDecision(page)).toEqual([]);
    expect(await page.locator("[data-decision]").count()).toBe(0);
    const runs = (await read(`/incidents/${incident}`)).runs;
    const events = (await read(`/incidents/${incident}/runs/${runs.at(-1).run_id}/events?limit=200`)).events;
    const approved = events.find((event: { summary: string }) => event.summary === "Mitigation approved.");
    expect(approved.actor).toMatchObject({ type: "human", reference: { principal_id: "demo-human" } });
    record.approvedBy = approved.actor.reference.principal_id;
  });

  test("rechazar envía reject_mitigation y la historia lo registra", async ({ page }) => {
    const incident = await declare("checkout rechaza los pagos");
    record.rejected = incident;
    await open(page, incident);
    await investigate(page);
    const sent = page.waitForRequest((request) => request.url().includes("/commands") && request.method() === "POST");
    await page.getByRole("button", { name: "Rechazar" }).click();
    const command = await sent;
    expect(command.postDataJSON().command).toBe("reject_mitigation");
    expect((await command.response())?.status()).toBe(202);
    await expect(page.getByRole("region", { name: "Propuesta de mitigación" })).toContainText(/Rechazada · Tú/);
    await expect(page.getByRole("list", { name: "Línea de tiempo del incidente" }).getByText("Tú · Rechazaste la mitigación")).toBeVisible();
    const reasoning = await read(`/incidents/${incident}/runs/${(await read(`/incidents/${incident}`)).runs.at(-1).run_id}/context`);
    record.rejectedStatus = reasoning.reasoning.mitigation_strategy.approval_status;
    expect(record.rejectedStatus).toBe("rejected");
  });

  test("una decisión tomada en otro canal aparece con quién decidió, en inglés", async ({ page }) => {
    // Another person with run.approve decides through the same governed command, as Telegram does (#767).
    const admin = await client(process.env.ADMIN_HUMAN_API_KEY!);
    const person = `ana-${STAMP}`;
    await send(admin, "/principals", { principal_id: person, kind: "human", display_name: "Ana" }, 201);
    const key = (await send(admin, `/principals/${person}/credentials`, {}, 201)).key;
    const workflow = { resource_type: "incident_workflow", resource_id: "incident-response" };
    await send(admin, "/grants", { grant_id: `grant-${person}-approve`, principal_id: person, action: "run.approve", resource: workflow, effect: "allow" }, 201);

    const incident = await declare("checkout cannot charge payment");
    record.decidedElsewhere = incident;
    await open(page, incident, "en");
    await expect(page.getByRole("heading", { level: 2, name: PLAN })).toBeVisible({ timeout: 90_000 });
    await expect(page.getByRole("button", { name: "Approve" })).toBeVisible();
    for (const scheme of ["dark", "light"] as const) {
      await page.emulateMedia({ colorScheme: scheme });
      await page.screenshot({ path: `${DIR}/incidente-${scheme === "dark" ? "noche" : "dia"}-en.png`, fullPage: true });
    }

    const { version, runs } = await read(`/incidents/${incident}`);
    await send(await client(key), `/incidents/${incident}/runs/${runs.at(-1).run_id}/commands`, {
      command: "approve_mitigation",
      expected_incident_version: version,
      actor: "human",
      actor_reference: { reference_version: "1.0.0", principal_id: person, display_name: "Ana" },
      turn_id: null,
      disposition: null,
      comment: null,
      authorization: { action: "run.approve", resource: { type: "incident_workflow", id: "incident-response" } },
    }, 202);
    // No reload: the page polls and shows the outcome with the person who decided.
    const proposal = page.getByRole("region", { name: "Mitigation proposal" });
    await expect(proposal).toContainText(/Approved · Ana · \d{2}:\d{2}/, { timeout: 30_000 });
    await expect(page.getByRole("list", { name: "Incident timeline" }).getByText("Ana · Approved the mitigation")).toBeVisible();
    await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(0);
    await page.screenshot({ path: `${DIR}/decidido-en-otro-canal-en.png`, fullPage: true });
  });

  test("un despacho fallido muestra su causa y solo una persona lo reintenta", async ({ page }) => {
    const incident = await declare("checkout no puede cobrar a payment [e2e:falla]");
    record.retried = incident;
    await open(page, incident);
    const timeline = page.getByRole("list", { name: "Línea de tiempo del incidente" });
    await expect(timeline.getByText("La investigación se detuvo: el modelo respondió en un formato no válido.")).toBeVisible({ timeout: 90_000 });
    await expect(page.getByText("detenido", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Reintentar la investigación" }).click();
    await expect(page.getByRole("heading", { level: 2, name: PLAN })).toBeVisible({ timeout: 90_000 });
    await expect(timeline.getByText("Tú · Reintentaste la investigación")).toBeVisible();
    await noTechnicalIds(page);
    await page.screenshot({ path: `${DIR}/reintento-es.png`, fullPage: true });
  });
});
