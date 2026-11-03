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

/** The incident's version and its investigation run: a declaration's triage run stays `active` and may list last. */
async function investigation(incident: string): Promise<{ version: number; run: string }> {
  const { version, runs } = await read(`/incidents/${incident}`);
  const run = runs.findLast((item: { current_state: string }) => item.current_state !== "active" && item.current_state !== "triage") ?? runs.at(-1);
  return { version, run: run.run_id };
}

/** Declares an incident from a checkout alert (or another service's) as the demo human. */
async function declare(summary: string, service = "checkout"): Promise<string> {
  const demo = await client(process.env.DEMO_HUMAN_API_KEY!);
  const alert = `alt-e2e870-${STAMP}-${randomBytes(3).toString("hex")}`;
  const context = { service, severity: "sev2", source: "e2e-870", summary, observed_at: new Date().toISOString() };
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

/** The annotations of demo/grafana/alerting/midnight.yaml's error rule as Grafana expanded them in the walkthrough (2026-11-02). */
const WALKTHROUGH = {
  summary: "checkout: 19.05% of spans failed over the last 2 min (threshold 5%).",
  description:
    'Evidence: Prometheus datasource webstore-metrics, metric traces_span_metrics_calls_total with service_name="checkout" and status_code="STATUS_CODE_ERROR" for the errors, span_name for the failing operation; logs in datasource webstore-logs, index otel-logs-*, field resource.service.name:"checkout".',
};

/** One Grafana Alerting delivery to intake (#765), as the contact point sends it with its secret. */
async function grafana(service: string, status: "firing" | "resolved", startsAt: string, annotations: Record<string, string> = { summary: `${service} no puede cobrar a payment` }) {
  const intake = await client(process.env.ALERT_INTAKE_GRAFANA_SECRET!);
  const alert = {
    status,
    labels: { alertname: "service-error-rate", service_name: service, severity: "critical" },
    annotations,
    startsAt,
    endsAt: status === "resolved" ? new Date().toISOString() : "0001-01-01T00:00:00Z",
    fingerprint: `service-error-rate-${service}`,
  };
  const response = await intake.post(`${API}/alert-intake/grafana`, { data: { status, groupKey: service, alerts: [alert] } });
  expect(response.status(), await response.text()).toBe(200);
  return (await response.json()).episodes[0];
}

/** Opens the incident in a language; the key lives only in this tab's memory, so it is connected each time. */
async function open(page: Page, incident: string, language: "es" | "en" = "es") {
  await page.addInitScript((value) => localStorage.setItem("midnight-language", JSON.stringify({ state: { language: value }, version: 0 })), language);
  await page.goto(`incidentes/${incident}`);
  await page.getByRole("button", { name: language === "es" ? "Conectar API" : "Connect API" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Clave de API").fill(process.env.DEMO_HUMAN_API_KEY!);
  await dialog.getByRole("button", { name: "Conectar", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/checkout/i);
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

/** Element and themed captures: night and day, with the language in the name. */
async function capture(page: Page, name: string, target?: ReturnType<Page["locator"]>) {
  for (const scheme of ["dark", "light"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    const path = `${DIR}/${name}-${scheme === "dark" ? "noche" : "dia"}.png`;
    await (target ? target.screenshot({ path }) : page.screenshot({ path, fullPage: true }));
  }
  await page.emulateMedia({ colorScheme: "dark" });
}

/** The meta row's last update: said in words, the timeline's time format and the full date on hover; returns its instant. */
async function lastUpdate(page: Page, name: string, full: RegExp): Promise<number> {
  const updated = page.locator("[data-meta=updated]");
  const stamp = updated.locator("time");
  await expect(stamp).toHaveText(/^\d{2}:\d{2}$/);
  await expect(updated).toHaveText(/^(Actualizado|Updated) \d{2}:\d{2}$/);
  await stamp.hover();
  await expect(page.getByRole("tooltip")).toHaveText(full);
  for (const scheme of ["dark", "light"] as const) {
    await page.emulateMedia({ colorScheme: scheme });
    await page.screenshot({ path: `${DIR}/${name}-${scheme === "dark" ? "noche" : "dia"}.png`, clip: { x: 0, y: 0, width: 1440, height: 260 } });
  }
  await page.emulateMedia({ colorScheme: "dark" });
  await page.mouse.move(0, 0);
  return Date.parse((await stamp.getAttribute("datetime"))!);
}

/** Opens one evidence disclosure by its label, checks the stored query and captures its step. */
async function disclosure(page: Page, label: string, query: RegExp, name: string) {
  const summary = page.locator("details > summary", { hasText: label });
  await expect(summary).toHaveCount(1);
  await summary.click();
  await expect(summary.locator("xpath=..").locator("pre")).toHaveText(query);
  await summary.scrollIntoViewIfNeeded();
  await capture(page, name, summary.locator("xpath=ancestor::li[1]"));
}

async function noTechnicalIds(page: Page) {
  expect(await page.locator("article").innerText()).not.toMatch(TECHNICAL);
}

test.describe("incidente RC-2 contra la API real", () => {
  test.skip(!enabled, "Requiere LIVE_INCIDENT=1 y la pila de compose.incident-console-e2e.yaml");
  test.beforeAll(() => mkdirSync(DIR, { recursive: true }));
  test.afterAll(() => writeFileSync(`${DIR}/verification.json`, JSON.stringify(record, null, 2)));

  // First, so its Grafana alert for `checkout` opens an incident instead of joining a declared one.
  test("la página se lee: título corto, hipótesis en partes, etapas con hora, resultados de las consultas y nada se sale", async ({ browser }) => {
    test.setTimeout(420_000);
    const incident = (await grafana("checkout", "firing", new Date(Date.now() - 120_000).toISOString(), WALKTHROUGH)).incident_id;
    expect(incident).toBeTruthy();
    record.page = { incident, widths: {} };
    const widths = (record.page as { widths: Record<string, unknown> }).widths;
    for (const language of ["es", "en"] as const) {
      const es = language === "es";
      for (const width of [1280, 390]) {
        const page = await browser.newPage({ viewport: { width, height: 900 } });
        await open(page, incident, language);
        await expect(page.getByRole("region", { name: es ? "Propuesta de mitigación" : "Mitigation proposal" })).toBeVisible({ timeout: 120_000 });

        // The title: the rule's own text in the page's language; the alert's hint behind its disclosure.
        const title = page.getByRole("heading", { level: 1 });
        await expect(title).toHaveText(es ? "Errores en checkout (19\u00a0% de spans, umbral 5\u00a0%)" : "Errors in checkout (19% of spans, threshold 5%)");
        expect(parseFloat(await title.evaluate((element) => getComputedStyle(element).fontSize))).toBeLessThanOrEqual(44);
        const alert = page.locator("article details", { hasText: es ? "Alerta de Grafana" : "Grafana alert" }).first();
        await alert.locator("summary").click();
        await expect(alert).toContainText("Evidence: Prometheus datasource webstore-metrics");

        // The meta row says what each time is; severity is a coloured pill, never amber.
        await expect(page.locator("[data-meta=declared]")).toHaveText(new RegExp(`^${es ? "Declarado" : "Declared"} \\d{2}:\\d{2}$`));
        await expect(page.locator("[data-meta=updated]")).toHaveText(new RegExp(`^${es ? "Actualizado" : "Updated"} \\d{2}:\\d{2}$`));
        const severity = page.locator("[data-severity=sev1]");
        await expect(severity).toHaveText("SEV1");

        // The hypothesis in labelled lines at body size; its evidence listed under it, one line each.
        const hypothesis = page.locator("#hypothesis");
        await expect(hypothesis.locator("dt")).toHaveText(["Causa", "Mecanismo", "La refutaría"]);
        const body = await hypothesis.locator("dd").first().evaluate((element) => ({ size: parseFloat(getComputedStyle(element).fontSize), font: getComputedStyle(element).fontFamily }));
        expect(body.size).toBeLessThanOrEqual(18);
        expect(body.font).not.toMatch(/Fraunces/);
        await expect(hypothesis.locator("ol > li")).toHaveCount(3);
        await expect(hypothesis.locator("ol > li").first()).toContainText(es ? "apoya" : "supports");

        // The timeline's hypothesis shows its cause and folds the rest.
        const step = page.locator("li[id^=step-hyp_]");
        await expect(step.locator("dt").first()).toHaveText("Causa");
        await expect(step.locator("dt", { hasText: "La refutaría" })).toBeHidden();
        await step.locator("summary").click();
        await expect(step.locator("dt", { hasText: "La refutaría" })).toBeVisible();

        // Each reached stage tells when, with the full date on hover; the rest tell nothing.
        const stages = page.getByRole("list", { name: es ? "Progreso del incidente" : "Incident progress" }).locator("li");
        await expect(stages).toHaveCount(6);
        for (const index of [0, 1, 2]) await expect(stages.nth(index).locator("time")).toHaveText(/^\d{2}:\d{2}$/);
        for (const index of [3, 4, 5]) await expect(stages.nth(index).locator("time")).toHaveCount(0);
        await stages.nth(1).locator("time").hover();
        await expect(page.getByRole("tooltip")).toHaveText(es ? /de 20\d\d/ : /, 20\d\d/);
        await page.mouse.move(0, 0);

        // What each query returned, readable: the vector as a table, the logs as hits and lines.
        const metrics = page.locator("li[id^=step-ev_]", { hasText: es ? "Métricas de checkout" : "checkout metrics" }).locator("[data-result]");
        await expect(metrics.locator("tr")).toHaveCount(2);
        await expect(metrics.locator("tr").first()).toContainText(es ? /oteldemo\.\S+\s*9,76/ : /oteldemo\.\S+\s*9\.76/);
        const logs = page.locator("li[id^=step-ev_]", { hasText: es ? "Logs de checkout" : "checkout logs" }).locator("[data-result]");
        await expect(logs).toContainText(es ? "20 resultados" : "20 hits");
        await expect(logs.locator("li")).toHaveCount(5);
        await expect(logs.locator("li").first()).toContainText(/\d{2}:\d{2}:\d{2}\s*ERROR\s*checkout\s*.*context deadline/);
        for (const summary of await page.locator("li[id^=step-ev_] details > summary").all()) await summary.click();

        // Nothing leaves the page or its column, in either theme.
        const overflow = await page.evaluate(() => {
          const article = document.querySelector("article")!.getBoundingClientRect();
          const outside = [...document.querySelectorAll("article *")]
            .filter((element) => element.getBoundingClientRect().width > 0 && element.getBoundingClientRect().right > article.right + 1)
            .map((element) => element.outerHTML.slice(0, 80));
          // What reaches past the window, named in the failure.
          const wide = [...document.querySelectorAll("body *")]
            .filter((element) => element.getBoundingClientRect().right > window.innerWidth + 1)
            .map((element) => element.outerHTML.slice(0, 120));
          return { page: document.documentElement.scrollWidth - window.innerWidth, outside, wide };
        });
        expect(overflow.page, JSON.stringify(overflow.wide)).toBeLessThanOrEqual(0);
        expect(overflow.outside).toEqual([]);
        expect(await amberOutsideDecision(page)).toEqual([]);
        const contrast: Record<string, number> = {};
        for (const scheme of ["dark", "light"] as const) {
          await page.emulateMedia({ colorScheme: scheme });
          contrast[scheme] = await severity.evaluate((element) => {
            const rgb = (value: string) => value.match(/[\d.]+/g)!.slice(0, 3).map(Number);
            const luminance = (value: string) => {
              const [r, g, b] = rgb(value).map((channel) => (channel / 255 <= 0.03928 ? channel / 255 / 12.92 : ((channel / 255 + 0.055) / 1.055) ** 2.4));
              return 0.2126 * r + 0.7152 * g + 0.0722 * b;
            };
            const style = getComputedStyle(element);
            const [a, b] = [luminance(style.color), luminance(style.backgroundColor)].sort((x, y) => y - x);
            return (a + 0.05) / (b + 0.05);
          });
          expect(contrast[scheme]).toBeGreaterThanOrEqual(4.5);
          expect(AMBER).not.toContain(await severity.evaluate((element) => getComputedStyle(element).backgroundColor));
          await page.screenshot({ path: `${DIR}/pagina-${language}-${width}-${scheme === "dark" ? "noche" : "dia"}.png`, fullPage: true });
        }
        widths[`${language}-${width}`] = { overflow, severityContrast: contrast, title: await title.innerText() };
        await page.close();
      }
    }
  });

  test("las afirmaciones de la hipótesis muestran su evidencia y llevan a su paso; aprobar envía el comando gobernado", async ({ page }) => {
    const incident = await declare("checkout no puede cobrar a payment");
    record.approved = incident;
    await open(page, incident);
    await investigate(page);

    const hypothesis = page.locator("#hypothesis");
    await expect(hypothesis.locator("dt")).toHaveText(["Causa", "Mecanismo", "La refutaría"]);
    await expect(hypothesis.locator("dd").first()).toHaveText("el despliegue de checkout 1.5.0 rompió los cobros contra payment.");
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

    // `checkout` has no catalog: the plan says nobody will execute it.
    await expect(page.getByRole("region", { name: "Propuesta de mitigación" })).toContainText("Texto libre: no es una operación del catálogo y nadie la ejecutará.");

    // Each disclosure names what the agent asked: no generic label on measured evidence.
    await expect(page.locator("details > summary", { hasText: /^Ver la consulta$/ })).toHaveCount(0);
    await disclosure(page, "Ver la búsqueda de logs", /query_elasticsearch · .*\nresource\.service\.name:"checkout"/, "evidencia-logs-es");
    await disclosure(page, "Ver la consulta de métricas", /query_prometheus · .*\n.*traces_span_metrics_calls_total/, "evidencia-metricas-es");
    record.disclosures = await page.locator("details > summary").allInnerTexts();

    // The last update is the newest recorded event: a poll with nothing new leaves it as it is.
    await page.evaluate(() => window.scrollTo(0, 0));
    const before = await lastUpdate(page, "actualizado-es", /de 20\d\d/);
    await page.waitForTimeout(17_000);
    expect(Date.parse((await page.locator("[data-meta=updated] time").getAttribute("datetime"))!)).toBe(before);

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

    // Decided, the proposal is no longer a proposal: it is a decision taken, out of amber.
    const decisions = page.getByRole("region", { name: "Decisiones tomadas" });
    await expect(decisions).toContainText(PLAN);
    await expect(decisions).toContainText(/Aprobada · Tú · \d{2}:\d{2}/);
    await expect(page.getByRole("region", { name: "Propuesta de mitigación" })).toHaveCount(0);
    await expect(timeline.getByText("Tú · Aprobaste la mitigación")).toBeVisible();
    await decisions.scrollIntoViewIfNeeded();
    await capture(page, "decisiones-es", decisions);
    await expect(page.getByRole("button", { name: "Aprobar" })).toHaveCount(0);
    expect(await amberOutsideDecision(page)).toEqual([]);
    expect(await page.locator("[data-decision]").count()).toBe(0);
    const events = (await read(`/incidents/${incident}/runs/${(await investigation(incident)).run}/events?limit=200`)).events;
    const approved = events.find((event: { summary: string }) => event.summary === "Mitigation approved.");
    expect(approved.actor).toMatchObject({ type: "human", reference: { principal_id: "demo-human" } });
    record.approvedBy = approved.actor.reference.principal_id;
    // The decision moved the report forward to at least the approval.
    await page.evaluate(() => window.scrollTo(0, 0));
    const after = await lastUpdate(page, "actualizado-decidido-es", /de 20\d\d/);
    expect(after).toBeGreaterThan(before);
    expect(after).toBeGreaterThanOrEqual(Math.floor(Date.parse(approved.occurred_at) / 1000) * 1000);
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
    const decisions = page.getByRole("region", { name: "Decisiones tomadas" });
    await expect(decisions).toContainText(/Rechazada · Tú · \d{2}:\d{2}/);
    await expect(page.getByRole("list", { name: "Línea de tiempo del incidente" }).getByText("Tú · Rechazaste la mitigación")).toBeVisible();
    const reasoning = await read(`/incidents/${incident}/runs/${(await investigation(incident)).run}/context`);
    record.rejectedStatus = reasoning.reasoning.mitigation_strategy.approval_status;
    expect(record.rejectedStatus).toBe("rejected");

    // A rejection ends the run; a retry proposes again, amber returns above the decision taken.
    await page.getByRole("button", { name: "Reintentar la investigación" }).click();
    await expect(page.getByRole("heading", { level: 2, name: PLAN })).toBeVisible({ timeout: 90_000 });
    const proposal = page.getByRole("region", { name: "Propuesta de mitigación" });
    await expect(proposal).toBeVisible();
    await expect(decisions.getByRole("listitem")).toHaveCount(1);
    expect(await amberOutsideDecision(page)).toEqual([]);
    await page.getByRole("button", { name: "Aprobar" }).click();
    await expect(proposal).toHaveCount(0);
    const items = decisions.getByRole("listitem");
    await expect(items).toHaveCount(2);
    await expect(items.nth(0)).toContainText(/Una propuesta anterior\s*Rechazada · Tú · \d{2}:\d{2}/);
    // The decision taken names the cause it acted on, its mechanism folded.
    await expect(items.nth(1)).toContainText(new RegExp(`${PLAN}\\s*Causa\\s*el despliegue de checkout 1\\.5\\.0[\\s\\S]*Aprobada · Tú · \\d{2}:\\d{2}`));
    expect(await page.locator("[data-decision]").count()).toBe(0);
    await decisions.scrollIntoViewIfNeeded();
    await capture(page, "decisiones-rechazo-y-aprobacion-es", decisions);
    record.decisionsAfterRetry = await items.allInnerTexts();
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

    const { version, run } = await investigation(incident);
    await send(await client(key), `/incidents/${incident}/runs/${run}/commands`, {
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
    const decisions = page.getByRole("region", { name: "Decisions taken" });
    await expect(decisions).toContainText(/Approved · Ana · \d{2}:\d{2}/, { timeout: 30_000 });
    await expect(decisions).toContainText(PLAN);
    await expect(page.getByRole("list", { name: "Incident timeline" }).getByText("Ana · Approved the mitigation")).toBeVisible();
    await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(0);
    await page.screenshot({ path: `${DIR}/decidido-en-otro-canal-en.png`, fullPage: true });
    await decisions.scrollIntoViewIfNeeded();
    await capture(page, "decisiones-en", decisions);
    await disclosure(page, "See the log search", /query_elasticsearch · /, "evidencia-logs-en");
    await disclosure(page, "See the metrics query", /query_prometheus · /, "evidencia-metricas-en");
    await page.evaluate(() => window.scrollTo(0, 0));
    await lastUpdate(page, "actualizado-en", /, 20\d\d/);
  });

  test("tras aprobar, la verificación cuenta cuándo Grafana dejó de alertar", async ({ page }) => {
    // An alert of its own service, so intake declares a new incident instead of joining another.
    const service = `checkout-${STAMP}`;
    const startsAt = new Date(Date.now() - 60_000).toISOString();
    const incident = (await grafana(service, "firing", startsAt)).incident_id;
    expect(incident).toBeTruthy();
    record.verified = incident;
    await open(page, incident);
    await expect(page.getByText("SEV1", { exact: true })).toBeVisible();
    await investigate(page);
    await page.getByRole("button", { name: "Aprobar" }).click();

    // Approved while Grafana still alerts: the step waits, in no amber, it is not a decision.
    const step = page.locator("#step-verification");
    await expect(step).toContainText("Verificación · en espera");
    await expect(step).toContainText("Grafana sigue alertando.");
    expect(await amberOutsideDecision(page)).toEqual([]);

    // Grafana resolves its alert: the step tells when and how long after the approval.
    const resolved = await grafana(service, "resolved", startsAt);
    expect(resolved).toMatchObject({ status: "resolved", incident_id: incident });
    await expect(step).toContainText(/Verificación · la señal se recuperó/, { timeout: 30_000 });
    await expect(step).toContainText(/Grafana dejó de alertar a las \d{2}:\d{2}, \d+ (s|min) después de aprobar la mitigación\./);
    await expect(step.locator("svg[role=img]")).toHaveCount(0);
    record.resolvedText = await step.innerText();

    // A person confirms the service is stable through the governed command; the step folds it in.
    const { version, run } = await investigation(incident);
    await send(await client(process.env.DEMO_HUMAN_API_KEY!), `/incidents/${incident}/runs/${run}/commands`, {
      command: "verification_passed",
      expected_incident_version: version,
      actor: "human",
      actor_reference: { reference_version: "1.0.0", principal_id: "demo-human" },
      turn_id: null,
      disposition: null,
      comment: null,
      authorization: { action: "run.command", resource: { type: "incident_workflow", id: "incident-response" } },
    }, 202);
    await expect(step).toContainText("Tú · Servicio verificado estable", { timeout: 30_000 });
    await expect(page.getByRole("list", { name: "Línea de tiempo del incidente" }).getByText("Servicio verificado estable")).toHaveCount(1);
    await step.scrollIntoViewIfNeeded();
    await capture(page, "verificacion-es", step);
    await capture(page, "verificacion-pagina-es");
    record.verifiedText = await step.innerText();

    const english = await page.context().newPage();
    await open(english, incident, "en");
    const stepEn = english.locator("#step-verification");
    await expect(stepEn).toContainText("Verification · the signal recovered");
    await expect(stepEn).toContainText(/Grafana stopped alerting at \d{2}:\d{2}, \d+ (s|min) after the mitigation was approved\./);
    await stepEn.scrollIntoViewIfNeeded();
    await capture(english, "verificacion-en", stepEn);
  });

  test("la propuesta nombra su operación del catálogo; una aprobación rechazada no mueve nada y la que corre deja su recibo", async ({ page }) => {
    // sre-checkout is the one service the journeys' deploy-executor enrols (incident_console_catalog.yaml).
    const service = "sre-checkout";
    const incident = (await grafana(service, "firing", new Date(Date.now() - 60_000).toISOString())).incident_id;
    expect(incident).toBeTruthy();
    record.executed = incident;
    await open(page, incident);
    await expect(page.getByText("Investigando…")).toBeVisible();
    const plan = "Volver sre-checkout a la 1.4.0";
    await expect(page.getByRole("heading", { level: 2, name: plan })).toBeVisible({ timeout: 90_000 });
    const proposal = page.getByRole("region", { name: "Propuesta de mitigación" });
    await expect(proposal).toContainText('deployment.rollback(service="sre-checkout", to_tag="1.4.0")');
    await expect(proposal).toContainText("del catálogo");
    await capture(page, "catalogo-propuesta-es", proposal);
    const englishProposal = await page.context().newPage();
    await open(englishProposal, incident, "en");
    const proposalEn = englishProposal.getByRole("region", { name: "Mitigation proposal" });
    await expect(proposalEn).toContainText("from the catalog");
    await expect(englishProposal.getByRole("heading", { level: 2, name: "Roll sre-checkout back to 1.4.0" })).toBeVisible();
    await capture(englishProposal, "catalogo-propuesta-en", proposalEn);
    await englishProposal.close();

    // Without the agent's mitigation.execute grant the gateway refuses the approval (#919, #923).
    const admin = await client(process.env.ADMIN_HUMAN_API_KEY!);
    const grant = "grant-setup-agent-sre-checkout-deployment-rollback";
    expect((await admin.delete(`${API}/grants/${grant}`)).status()).toBeLessThan(300);
    const before = await read(`/incidents/${incident}`);
    await page.getByRole("button", { name: "Aprobar" }).click();
    const timeline = page.getByRole("list", { name: "Línea de tiempo del incidente" });
    const refused = timeline.getByText(/Tú · Tu aprobación no se aplicó: el agente no tiene permiso para ejecutar esa operación\. El incidente sigue esperando tu decisión\./);
    await expect(refused).toBeVisible({ timeout: 30_000 });
    // The incident stays where it was: still waiting, the proposal still in amber, no decision taken.
    const after = await read(`/incidents/${incident}`);
    expect(after.state).toBe("mitigating");
    expect(after.state).toBe(before.state);
    await expect(proposal).toBeVisible();
    await expect(proposal.getByRole("alert")).toHaveText("No se aplicó; la línea de tiempo dice por qué.");
    await expect(page.getByRole("region", { name: "Decisiones tomadas" })).toHaveCount(0);
    await refused.scrollIntoViewIfNeeded();
    await capture(page, "aprobacion-no-aplicada-es", refused.locator("xpath=ancestor::li[1]"));
    record.refusedState = after.state;

    // With the grant back, approving runs the rollback through the deploy-executor.
    const workflow = { resource_type: "service_operation", resource_id: "sre-checkout:deployment.rollback" };
    await send(admin, "/grants", { grant_id: `${grant}-${STAMP}`, principal_id: "incident-harness", action: "mitigation.execute", resource: workflow, effect: "allow" }, 201);
    await page.getByRole("button", { name: "Aprobar" }).click();
    const decisions = page.getByRole("region", { name: "Decisiones tomadas" });
    const receipt = decisions.locator("[data-receipt]");
    await expect(receipt).toHaveText(
      "Se ejecutó deployment.rollback en sre-checkout: revertido (midnight-e2e/checkout:1.5.0 → midnight-e2e/checkout:1.4.0).",
      { timeout: 60_000 },
    );
    await expect(timeline.locator("#step-execution")).toContainText("Se ejecutó deployment.rollback en sre-checkout: revertido");
    await expect(timeline.locator("#step-execution")).toContainText("por deploy-executor");
    await decisions.getByText("Detalle de la ejecución").click();
    await expect(decisions).toContainText(/Ejecución\s*exe_[0-9a-f]{16}/);
    await expect(decisions).toContainText(/Duración\s*\d+\.\d s/);
    await decisions.scrollIntoViewIfNeeded();
    await capture(page, "recibo-decisiones-es", decisions);
    await timeline.locator("#step-execution").scrollIntoViewIfNeeded();
    await capture(page, "recibo-linea-de-tiempo-es", timeline.locator("#step-execution"));

    // The receipt is the one the incident keeps, and the service really runs the release it names.
    const context = await read(`/incidents/${incident}/runs/${(await investigation(incident)).run}/context`);
    const execution = context.reasoning.mitigation_strategy.execution;
    expect(execution).toMatchObject({ outcome: "rolled_back", before_image: "midnight-e2e/checkout:1.5.0", after_image: "midnight-e2e/checkout:1.4.0" });
    await expect(decisions).toContainText(execution.execution_id);
    const running = await (await request.newContext()).get("http://sre-checkout:8080/");
    expect((await running.json()).version).toBe("1.4.0");
    record.execution = { id: execution.execution_id, outcome: execution.outcome, before: execution.before_image, after: execution.after_image, durationMs: execution.duration_ms, running: "1.4.0" };

    const english = await page.context().newPage();
    await open(english, incident, "en");
    const decisionsEn = english.getByRole("region", { name: "Decisions taken" });
    await expect(decisionsEn.locator("[data-receipt]")).toHaveText("Ran deployment.rollback on sre-checkout: rolled back (midnight-e2e/checkout:1.5.0 → midnight-e2e/checkout:1.4.0).");
    await expect(english.getByRole("list", { name: "Incident timeline" })).toContainText("Your approval was not applied: the agent may not run that operation. The incident still waits for your decision.");
    await decisionsEn.getByText("Execution detail").click();
    await decisionsEn.scrollIntoViewIfNeeded();
    await capture(english, "recibo-decisiones-en", decisionsEn);
    await capture(english, "recibo-pagina-en");
  });

  /** An sre-checkout incident whose approved restart the deploy-executor ran: it waits for a verdict (#710). */
  async function executed(page: Page, summary: string) {
    // The setup grants the agent the rollback only; the restart is granted once, as an administrator would.
    if (!record.restartGranted) {
      const resource = { resource_type: "service_operation", resource_id: "sre-checkout:deployment.restart" };
      const grant = { grant_id: `grant-agent-restart-${STAMP}`, principal_id: "incident-harness", action: "mitigation.execute", resource, effect: "allow" };
      await send(await client(process.env.ADMIN_HUMAN_API_KEY!), "/grants", grant, 201);
      record.restartGranted = true;
    }
    const incident = await declare(summary, "sre-checkout");
    await open(page, incident);
    await expect(page.getByRole("heading", { level: 2, name: "Reiniciar sre-checkout" })).toBeVisible({ timeout: 90_000 });
    await page.getByRole("button", { name: "Aprobar" }).click();
    await expect(page.getByRole("region", { name: "Decisiones tomadas" }).locator("[data-receipt]")).toContainText("Se ejecutó deployment.restart en sre-checkout: reiniciado", { timeout: 60_000 });
    const check = page.getByRole("region", { name: "Verificación de la recuperación" });
    await expect(check.getByRole("heading", { level: 2 })).toHaveText("¿El servicio se recuperó?");
    await expect(check).toContainText("Lo esperado: Las llamadas con error de checkout vuelven a cero.");
    // A verdict is a decision: amber on the question, its stage and the status, nowhere else.
    expect(await amberOutsideDecision(page)).toEqual([]);
    await expect(page.locator("[data-decision]")).toHaveCount(3);
    await expect(page.getByRole("list", { name: "Progreso del incidente" }).locator("li[aria-current=step]")).toHaveAttribute("data-decision", "");
    return { incident, check, version: (await read(`/incidents/${incident}`)).version as number };
  }

  /** Sends one verdict from the question and checks the governed command it became. */
  async function verdict(page: Page, button: string, command: string, version: number) {
    const sent = page.waitForRequest((request) => request.url().includes("/commands") && request.method() === "POST");
    await page.getByRole("button", { name: button }).click();
    const request = await sent;
    const body = request.postDataJSON();
    expect(body).toMatchObject({ command, expected_incident_version: version, actor: "human", authorization: { action: "run.command" } });
    expect(request.headers()["idempotency-key"]).toMatch(new RegExp(`^console-${command}-[0-9a-f]{32}$`));
    expect((await request.response())?.status()).toBe(202);
    await expect(page.getByRole("region", { name: "Verificación de la recuperación" })).toHaveCount(0);
    expect(await page.locator("[data-decision]").count()).toBe(0);
  }

  test("tras ejecutar la mitigación, «Sigue fallando» devuelve el incidente a investigación y la línea de tiempo dice qué falló", async ({ page }) => {
    const { incident, check, version } = await executed(page, "sre-checkout sigue sin cobrar [e2e:reinicio]");
    record.failing = incident;
    await check.scrollIntoViewIfNeeded();
    await capture(page, "verificar-pregunta-es", check);
    const english = await page.context().newPage();
    await english.setViewportSize({ width: 390, height: 900 });
    await open(english, incident, "en");
    const checkEn = english.getByRole("region", { name: "Recovery check" });
    await expect(checkEn.getByRole("button", { name: "Still failing" })).toBeVisible();
    await expect(checkEn.getByRole("button", { name: "The service is stable" })).toBeVisible();
    await checkEn.scrollIntoViewIfNeeded();
    await capture(english, "verificar-pregunta-en-390", checkEn);

    await verdict(page, "Sigue fallando", "verification_failed", version);
    const step = page.locator("#step-verification");
    await expect(step).toContainText("Verificación · la señal no se recuperó", { timeout: 30_000 });
    await expect(step).toContainText("Tú · La verificación falló; se vuelve a investigar");
    await expect(step).toContainText(
      "No se cumplió lo esperado: Las llamadas con error de checkout vuelven a cero. El incidente vuelve a investigación; Midnight investiga de nuevo cuando se lo pidas.",
    );
    expect((await read(`/incidents/${incident}`)).state).toBe("investigating");
    await expect(page.getByRole("button", { name: "Reintentar la investigación" })).toBeVisible();
    await noTechnicalIds(page);
    await step.scrollIntoViewIfNeeded();
    await capture(page, "verificacion-fallida-es", step);
    await capture(page, "verificacion-fallida-pagina-es");
    record.failingText = await step.innerText();

    await open(english, incident, "en");
    const stepEn = english.locator("#step-verification");
    await expect(stepEn).toContainText("Verification · the signal did not recover");
    await expect(stepEn).toContainText("Not met: Las llamadas con error de checkout vuelven a cero. The incident is back under investigation; Midnight investigates again when you ask it to.");
    await stepEn.scrollIntoViewIfNeeded();
    await capture(english, "verificacion-fallida-en-390", stepEn);
  });

  test("tras ejecutar la mitigación, «El servicio está estable» resuelve el incidente", async ({ page }) => {
    const { incident, version } = await executed(page, "sre-checkout no cobra tras desplegar [e2e:reinicio]");
    record.stable = incident;
    await verdict(page, "El servicio está estable", "verification_passed", version);
    const step = page.locator("#step-verification");
    await expect(step).toContainText("Verificación · la señal se recuperó", { timeout: 30_000 });
    await expect(step).toContainText("Tú · Servicio verificado estable");
    expect((await read(`/incidents/${incident}`)).state).toBe("resolved");
    await noTechnicalIds(page);
    await step.scrollIntoViewIfNeeded();
    await capture(page, "verificacion-estable-es", step);
    await capture(page, "verificacion-estable-pagina-es");
    record.stableText = await step.innerText();

    // Resolved, the agent opens the postmortem with its draft (#711): under 90 s, as the server stamps both.
    const demo = await client(process.env.DEMO_HUMAN_API_KEY!);
    let draft: { version: number; created_at: string; updated_by: string; content: { timeline: unknown[]; cause: { statement: string } } } | null = null;
    await expect
      .poll(async () => {
        const response = await demo.get(`${API}/incidents/${incident}/postmortem`);
        draft = response.status() === 200 ? await response.json() : null;
        return draft?.version;
      }, { timeout: 90_000, intervals: [1_000] })
      .toBe(1);
    const runs: { run_id: string }[] = (await read(`/incidents/${incident}`)).runs;
    const events = (await Promise.all(runs.map(async (run) => (await read(`/incidents/${incident}/runs/${run.run_id}/events?limit=200`)).events))).flat();
    const stable = events.find((event: { summary: string }) => event.summary === "Service verified stable.");
    const seconds = (Date.parse(draft!.created_at) - Date.parse(stable.occurred_at)) / 1000;
    expect(seconds).toBeLessThan(90);
    expect(draft!.updated_by).toBe("incident-harness");
    expect(draft!.content.cause.statement).toContain("1.5.0");
    expect((await read(`/incidents/${incident}`)).state).toBe("postmortem");
    record.draft = { seconds, timeline: draft!.content.timeline.length, by: draft!.updated_by };
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
