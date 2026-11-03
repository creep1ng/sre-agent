import { randomBytes } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { expect, request, test, type Page } from "@playwright/test";

/*
 * The RC-2 action catalog against the real API (#870, #722), on the stack of
 * compose.action-catalog-e2e.yaml: API, database, investigator, web proxy and the deploy-executor
 * acting on this project's sre-checkout are real; the model and Grafana MCP are scripted. A
 * person approves the proposed rollback on the incident page, the executor runs it, and the run
 * appears on the catalog. The second journey runs once the script stops the executor.
 * Run with scripts/run_action_catalog_e2e.sh; keys never reach disk.
 */

const enabled = process.env.ACTION_CATALOG_E2E === "1";
const API = `${process.env.BASE_URL ?? "http://127.0.0.1:8080"}/api/v1`;
const STAMP = randomBytes(4).toString("hex");
const DIR = "e2e/artifacts/action-catalog";
const AMBER = ["rgb(242, 180, 90)", "rgb(166, 90, 0)"];
const PLAN = "Volver sre-checkout a la 1.4.0";
const LEAD = "Las operaciones que Midnight puede ejecutar en tus servicios. Su agente ejecuta cada una solo después de que una persona la aprueba.";

test.use({ video: "off", trace: "off" });
test.describe.configure({ mode: "serial" });

async function api(path: string, data?: unknown) {
  const demo = await request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${process.env.DEMO_HUMAN_API_KEY}` } });
  const response = data
    ? await demo.post(`${API}${path}`, { data, headers: { "idempotency-key": `e2e-870-catalog-${randomBytes(12).toString("hex")}` } })
    : await demo.get(`${API}${path}`);
  return { status: response.status(), body: await response.json(), text: await response.text() };
}

/** Opens a page of the console in a language and connects the key, which lives only in the tab. */
async function open(page: Page, path: string, language: "es" | "en" = "es") {
  await page.addInitScript((value) => localStorage.setItem("midnight-language", JSON.stringify({ state: { language: value }, version: 0 })), language);
  await page.goto(path);
  await page.getByRole("button", { name: language === "es" ? "Conectar API" : "Connect API" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Clave de API").fill(process.env.DEMO_HUMAN_API_KEY!);
  await dialog.getByRole("button", { name: "Conectar", exact: true }).click();
}

const operation = (page: Page, name: string) => page.locator(`[data-operation="sre-checkout:${name}"]`);

function amber(page: Page) {
  return page.evaluate((colours) => {
    const found: string[] = [];
    for (const element of document.querySelectorAll("body *")) {
      const style = getComputedStyle(element);
      if ([style.color, style.backgroundColor, style.borderTopColor].some((value) => colours.includes(value))) found.push(element.outerHTML.slice(0, 80));
    }
    return found;
  }, AMBER);
}

async function shoot(page: Page, name: string, language: "es" | "en") {
  for (const scheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    // The theme's colours ease in, as in theme.spec.ts: wait for them before the capture.
    await page.mouse.move(0, 0);
    await page.waitForTimeout(600);
    await page.screenshot({ path: `${DIR}/${name}-${scheme === "dark" ? "noche" : "dia"}-${language}.png`, fullPage: true });
  }
}

test.describe("catálogo de acciones RC-2 contra la API real", () => {
  test.skip(!enabled, "Requiere ACTION_CATALOG_E2E=1 y la pila de compose.action-catalog-e2e.yaml");
  test.beforeAll(() => mkdirSync(DIR, { recursive: true }));

  test("las acciones de Midnight, una aprobación real y su ejecución en el catálogo", async ({ page }) => {
    const record: Record<string, unknown> = { sanitized: true, stamp: STAMP };
    await open(page, "acciones");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Acciones");
    await expect(page.getByText(LEAD)).toBeVisible();
    // Who runs an operation is said once, in the lead; the old promise line is gone.
    await expect(page.getByText(/Nada fuera de esta lista|La ejecuta el agente de Midnight/)).toHaveCount(0);
    await expect(page.getByRole("heading", { level: 2 })).toHaveText(["sre-checkout"]);
    const service = page.locator('[data-service="sre-checkout"]');
    await expect(service.locator("header")).toContainText("2 acciones · sin ejecuciones");
    const rollback = operation(page, "deployment.rollback");
    await expect(rollback.getByRole("heading", { level: 3 })).toHaveText("Volver a una versión anterior");
    await expect(rollback.locator("h3 + code")).toHaveText("deployment.rollback");
    await expect(rollback.locator("dt")).toHaveText(["to_tag"]);
    await expect(rollback.locator("dd code")).toContainText(["1.4.0"]);
    // No runs: the summary line says it and there is no empty disclosure.
    await expect(rollback).toContainText("Nunca se ha ejecutado.");
    await expect(rollback.locator("details")).toHaveCount(0);
    await expect(operation(page, "deployment.restart")).toContainText("Nadie puede ejecutarla: ningún permiso la cubre.");
    await expect(operation(page, "deployment.restart").locator("dl")).toHaveCount(0);
    expect(await amber(page)).toEqual([]);
    await shoot(page, "catalogo-antes", "es");
    const englishBefore = await page.context().newPage();
    await open(englishBefore, "acciones", "en");
    await expect(englishBefore.getByRole("heading", { level: 1 })).toHaveText("Actions");
    await expect(englishBefore.locator('[data-service="sre-checkout"] header')).toContainText("2 actions · no runs yet");
    await expect(operation(englishBefore, "deployment.rollback")).toContainText("It has never run.");
    await shoot(englishBefore, "catalogo-antes", "en");
    await englishBefore.close();
    const before = await api("/action-catalog");
    expect(before.status).toBe(200);
    record.before = before.body;

    // A checkout alert declared as the demo human; the server starts the investigation (#858).
    const alert = `alt-e2e870cat-${STAMP}`;
    const declared = await api(`/alerts/${alert}/triage/commands`, {
      operation: "triage_declare",
      expected_version: 1,
      reason: "Los cobros fallan",
      severity: "sev2",
      impact: "Los clientes no pueden pagar sus pedidos.",
      alert_context: { service: "sre-checkout", severity: "sev2", source: "e2e-870", summary: "sre-checkout no puede cobrar", observed_at: new Date().toISOString() },
    });
    expect(declared.status, declared.text).toBe(201);
    const incident: string = declared.body.incident_id;
    record.incident = incident;

    // The person approves in the console, inside the SPA, so the key stays connected.
    await page.goto(`incidentes/${incident}`);
    await page.getByRole("button", { name: "Conectar API" }).click();
    await page.getByRole("dialog").getByLabel("Clave de API").fill(process.env.DEMO_HUMAN_API_KEY!);
    await page.getByRole("dialog").getByRole("button", { name: "Conectar", exact: true }).click();
    await expect(page.getByRole("heading", { level: 2, name: PLAN })).toBeVisible({ timeout: 120_000 });
    await page.getByRole("button", { name: "Aprobar" }).click();
    // The card says it, or once the RC-2 feedback (#928) is in, «Decisiones tomadas» takes it in.
    const decided = page.getByRole("region", { name: /^(Propuesta de mitigación|Decisiones tomadas)$/ });
    await expect(decided.filter({ hasText: /Aprobada/ })).toHaveCount(1, { timeout: 90_000 });
    await expect.poll(async () => (await api(`/incidents/${incident}`)).body.state, { timeout: 90_000 }).toBe("verifying");

    await page.getByRole("complementary").getByRole("link", { name: "Acciones" }).click();
    // The runs stay folded until asked for; the summary carries the count.
    const runs = rollback.locator("details");
    await expect(runs.locator("summary")).toHaveText("Ejecuciones recientes (1)", { timeout: 20_000 });
    await expect(runs).not.toHaveAttribute("open");
    await expect(service.locator("header")).toContainText(/2 acciones · última ejecución \d{2}:\d{2}/);
    await runs.locator("summary").click();
    await expect(rollback.getByRole("listitem")).toHaveCount(1);
    await expect(rollback).toContainText(/\d{2}:\d{2}\s*Se ejecutó\s*aprobó Demo human\s*Ver el incidente/);
    await expect(rollback.getByRole("link", { name: "Ver el incidente" })).toHaveAttribute("href", `/app/incidentes/${incident}`);
    expect(await amber(page)).toEqual([]);
    await shoot(page, "catalogo-despues", "es");

    const after = await api("/action-catalog");
    expect(after.status).toBe(200);
    expect(after.body.executor_status).toBe("available");
    const ran = after.body.services[0].operations.find((item: { operation: string }) => item.operation === "deployment.rollback");
    expect(ran.runner.principal_id).toBe("incident-harness");
    expect(ran.executions[0]).toMatchObject({ outcome: "succeeded", reason_code: null, incident_id: incident, approved_by: { principal_id: "demo-human", display_name: "Demo human" } });
    // Nothing about how the gateway reaches or signs the executor reaches the browser.
    expect(after.text).not.toMatch(/deploy-executor|:8000|signature|signing|https?:/i);
    record.after = after.body;

    // The link opens the incident the run belongs to.
    await rollback.getByRole("link", { name: "Ver el incidente" }).click();
    await expect(page).toHaveURL(new RegExp(`/app/incidentes/${incident}$`));
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("sre-checkout no puede cobrar");

    // The same page in English, after the run.
    const english = await page.context().newPage();
    await open(english, "acciones", "en");
    await expect(english.getByRole("heading", { level: 1 })).toHaveText("Actions");
    await operation(english, "deployment.rollback").getByText("Recent runs (1)", { exact: true }).click();
    await expect(operation(english, "deployment.rollback")).toContainText(/Ran\s*approved by Demo human\s*Open the incident/);
    await expect(operation(english, "deployment.restart")).toContainText("No one can run it: no grant covers it.");
    await shoot(english, "catalogo-despues", "en");
    writeFileSync(`${DIR}/verification.json`, JSON.stringify(record, null, 2));
  });

  test("con el ejecutor detenido, el catálogo dice que nada puede ejecutarse", async ({ page }) => {
    await open(page, "acciones");
    await expect(page.getByRole("status")).toHaveText(
      "El ejecutor no responde: nada puede ejecutarse hasta que vuelva. Estas son las operaciones registradas.",
    );
    const rollback = operation(page, "deployment.rollback");
    await expect(rollback.locator("h3 + code")).toHaveText("deployment.rollback");
    await expect(rollback).toContainText("parámetros desconocidos");
    await rollback.getByText("Ejecuciones recientes (1)", { exact: true }).click();
    await expect(rollback).toContainText(/Se ejecutó\s*aprobó Demo human/);
    await shoot(page, "catalogo-sin-ejecutor", "es");
    const unavailable = await api("/action-catalog");
    expect(unavailable.status).toBe(200);
    expect(unavailable.body.executor_status).toBe("unavailable");
    writeFileSync(`${DIR}/verification-executor-down.json`, JSON.stringify({ sanitized: true, catalog: unavailable.body }, null, 2));
  });
});
