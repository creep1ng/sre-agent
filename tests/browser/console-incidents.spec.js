import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { answerWhoAmI, connectConsole, logoutConsole } from "./support/console-session.mjs";

// The incident in focus (#487): War room, Decisiones and Postmortem open inside the console on one
// incident and run, under a band that shows what the view read and links the whole journey.
const connected = process.env.PLAYWRIGHT_PRODUCTION_TOPOLOGY === "1";
const INCIDENT = "inc-demo";
const RUN = "run_demo0001";

test.beforeEach(async ({ page }) => {
  const errors = [];
  page.on("console", (message) => {
    // Nginx's CSP blocks third-party fonts, and denied reads log a resource error on purpose.
    const text = message.text();
    if (
      message.type() === "error" &&
      !text.includes("Content Security Policy") &&
      !text.startsWith("Failed to load resource") &&
      !text.startsWith("War room failed")
    )
      errors.push(text);
  });
  page.on("pageerror", (error) => errors.push(String(error?.message ?? error)));
  page.context()["__errors"] = errors;
});

test.afterEach(async ({ page }) => {
  expect(page.context()["__errors"]).toEqual([]);
});

function detailPayload({ state = "mitigating", runs } = {}) {
  return {
    incident_id: INCIDENT,
    workflow_version: "1.0.0",
    state,
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
    version: 7,
    updated_at: "2026-08-24T14:20:00Z",
    runs: runs ?? [
      { run_id: RUN, version: 7, status: "awaiting_human", current_state: state, updated_at: "2026-08-24T14:20:00Z" },
    ],
  };
}

// Answers every incident read; `deny` turns the reads of one view's request shape into a 403.
async function mockIncident(page, { detail = detailPayload(), deny = () => false } = {}) {
  const reads = [];
  await page.route("**/api/v1/incidents/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    reads.push(`${request.method()} ${url.pathname}`);
    if (deny(url)) {
      await route.fulfill({ status: 403, json: { error: { code: "not_authorized", message: "denied" } } });
      return;
    }
    if (url.pathname.endsWith("/timeline")) {
      await route.fulfill({ json: { events: [], next_cursor: "seq:-1", has_more: false } });
      return;
    }
    if (url.pathname.endsWith("/snapshot")) {
      await route.fulfill({ status: 404, json: { error: { code: "snapshot_absent", message: "none" } } });
      return;
    }
    await route.fulfill({ json: detail });
  });
  return reads;
}

async function countWhoAmI(page) {
  const calls = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/api/v1/whoami")) calls.push(request.url());
  });
  return calls;
}

async function openWarRoom(page, query = `incident_id=${INCIDENT}`) {
  await answerWhoAmI(page);
  await page.goto(`/?view=war-room&${query}`);
  await connectConsole(page);
  await expect(page.locator("#war-room")).toHaveAttribute("data-state", "ready");
}

const band = (page) => page.locator("#incident-focus");
const step = (page, label) => page.locator("#incident-focus-journey .console-journey__step", { hasText: label });

test("el war room muestra el incidente en foco con su recorrido y la ubicación", async ({ page }) => {
  await mockIncident(page);
  await openWarRoom(page);

  await expect(band(page)).toBeVisible();
  await expect(page.locator("#incident-focus-title")).toHaveText("Elevated error rate on paymentservice.");
  await expect(page.locator("#incident-focus-severity")).toHaveText("sev2");
  await expect(page.locator("#incident-focus-state")).toHaveText("Mitigando");
  await expect(page.locator("#incident-focus-incident")).toHaveText(INCIDENT);
  await expect(page.locator("#incident-focus-run")).toHaveText(RUN);
  await expect(page.locator("#incident-focus-version")).toHaveText("7");

  const steps = page.locator("#incident-focus-journey .console-journey__label");
  await expect(steps).toHaveText(["Alerta", "Triage", "War room", "Decisión", "Postmortem"]);
  await expect(step(page, "War room")).toHaveAttribute("aria-current", "page");
  for (const [label, progress] of [
    ["Alerta", "done"],
    ["Triage", "done"],
    ["War room", "done"],
    ["Decisión", "current"],
    ["Postmortem", "pending"],
  ]) {
    await expect(step(page, label)).toHaveAttribute("data-progress", progress);
  }
  await expect(step(page, "Decisión")).toContainText("Decisión pendiente");
  await expect(step(page, "Decisión")).toHaveAttribute(
    "href",
    `/?view=decisions&incident_id=${INCIDENT}&run_id=${RUN}`,
  );
  // The Triage step hands the view the alert of this incident.
  await expect(step(page, "Triage")).toHaveAttribute("href", "/?view=triage&alert_id=alt-payment-error-rate");
  await expect(page).toHaveURL(`/?view=war-room&incident_id=${INCIDENT}&run_id=${RUN}`);
  for (const view of ["war-room", "decisions", "postmortem"]) {
    await expect(page.locator(`[data-console-nav="${view}"]`)).toHaveAttribute(
      "href",
      `/?view=${view}&incident_id=${INCIDENT}&run_id=${RUN}`,
    );
  }
});

test("el recorrido conserva incidente, run y sesión entre War room, Decisiones y Postmortem", async ({ page }) => {
  const whoami = await countWhoAmI(page);
  const reads = await mockIncident(page);
  await openWarRoom(page);
  await page.evaluate(() => {
    window.__sameDocument = true;
  });

  await step(page, "Decisión").click();
  await expect(page).toHaveURL(`/?view=decisions&incident_id=${INCIDENT}&run_id=${RUN}`);
  await expect(page.locator("#review")).toHaveAttribute("data-state", "ready");
  await expect(page.locator("#fact-run")).toHaveText(RUN);
  await expect(page.locator("#review h1")).toBeFocused();
  await expect(step(page, "Decisión")).toHaveAttribute("aria-current", "page");
  await expect(page.locator("[data-console-nav][aria-current='page']")).toHaveText("Decisiones");

  await step(page, "Postmortem").click();
  await expect(page).toHaveURL(`/?view=postmortem&incident_id=${INCIDENT}&run_id=${RUN}`);
  await expect(page.locator("#postmortem")).toHaveAttribute("data-state", "ready");
  await expect(page.locator("#incident-focus-run")).toHaveText(RUN);

  await page.goBack();
  await expect(page.locator("#review")).toHaveAttribute("data-state", "ready");
  await page.goBack();
  await expect(page.locator("#war-room")).toHaveAttribute("data-state", "ready");
  await page.goForward();
  await expect(page.locator("#review")).toHaveAttribute("data-state", "ready");

  expect(await page.evaluate(() => window.__sameDocument)).toBe(true);
  await expect(page.locator("#session-principal")).toHaveText("demo-human");
  expect(whoami).toHaveLength(1);
  // Navigating only reads: no command or mutation reached the incident API.
  expect(reads.every((entry) => entry.startsWith("GET "))).toBe(true);
});

test("cerrar sesión retira la franja y los datos del incidente", async ({ page }) => {
  await mockIncident(page);
  await openWarRoom(page);
  await expect(band(page)).toBeVisible();

  await logoutConsole(page);
  await expect(band(page)).toBeHidden();
  await expect(page.locator("#incident-focus-title")).toBeEmpty();
  await expect(page.locator("#incident-focus-journey li")).toHaveCount(0);
  await expect(page.locator("#war-room")).toHaveAttribute("data-state", "auth");
  await expect(page.locator("#error-401")).toBeVisible();
  await expect(page.locator("#summary-section")).toBeHidden();
  await expect(page.locator("#console-session")).toBeVisible();
});

test("un 403 en una vista retira la franja sin cerrar la sesión", async ({ page }) => {
  // Decisiones reads the same incident, but this identity cannot: only that view is denied.
  let denyNext = false;
  await mockIncident(page, { deny: () => denyNext });
  await openWarRoom(page);
  await expect(band(page)).toBeVisible();

  denyNext = true;
  await step(page, "Decisión").click();
  await expect(page.locator("#error-403")).toBeVisible();
  await expect(band(page)).toBeHidden();
  await expect(page.locator("#session-chip")).toHaveAttribute("data-phase", "active");
  await expect(page.locator("#context-section")).toBeHidden();
});

test("sin incidente en foco, la vista explica cómo llegar sin dictar direcciones", async ({ page }) => {
  let fetched = false;
  await page.route("**/api/v1/**", async (route) => {
    fetched = true;
    await route.abort();
  });
  await page.goto("/?view=war-room");

  await expect(page.locator("#error-missing-id")).toBeVisible();
  await expect(page.locator("#error-missing-id")).not.toContainText("?incident_id");
  await expect(band(page)).toBeHidden();
  await page.locator("#error-missing-id").getByRole("link", { name: "Ir a Alertas" }).click();
  await expect(page.locator("#alert-inbox")).toHaveAttribute("data-state", "ready");
  expect(fetched).toBe(false);
});

test("un incidente sin run no ofrece Decisión ni inventa un run", async ({ page }) => {
  await mockIncident(page, { detail: detailPayload({ state: "active", runs: [] }) });
  await openWarRoom(page);

  await expect(page.locator("#incident-focus-run")).toHaveText("Sin run");
  await expect(step(page, "Decisión")).toHaveAttribute("aria-disabled", "true");
  await expect(step(page, "Decisión")).not.toHaveAttribute("href", /.*/);
  await expect(step(page, "Decisión")).toContainText("Sin run");
  await expect(step(page, "War room")).toHaveAttribute("data-progress", "current");
  await expect(step(page, "Triage")).toContainText("Declarado");
  await expect(page).toHaveURL(`/?view=war-room&incident_id=${INCIDENT}`);
});

test("la consola con un incidente en foco no tiene violaciones WCAG A/AA detectables", async ({ page }) => {
  await mockIncident(page);
  await openWarRoom(page);
  await expect(band(page)).toBeVisible();
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    // The palette's measured contrast baseline is tracked by the design-system smoke.
    .disableRules(["color-contrast"])
    .analyze();
  expect(results.violations).toEqual([]);
});

test("con el stack real, un incidente sin permiso de lectura no muestra datos y la sesión sigue", async ({
  page,
}) => {
  test.skip(!connected || !process.env.ADMIN_HUMAN_API_KEY, "requires the production topology");
  await page.goto(`/?view=war-room&incident_id=${INCIDENT}`);
  await connectConsole(page, process.env.ADMIN_HUMAN_API_KEY);
  await expect(page.locator("#war-room")).toHaveAttribute("data-state", "error");
  await expect(page.locator("#error-403")).toBeVisible();
  await expect(band(page)).toBeHidden();
  await expect(page.locator("#session-principal")).toHaveText("admin-human");
});
