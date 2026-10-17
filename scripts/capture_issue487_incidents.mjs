// Incident-in-focus proof for issue #487 against the isolated triage stack (nginx CSP, real API,
// PostgreSQL). The inbox hands an alert to Triage inside the console, where the key is entered
// once, and its declaration opens the war room in the same session. The band then keeps a seeded
// incident and its run across War room, Decisiones and Postmortem with Back/Forward, reload and
// logout, and navigating never sends a command. A principal without run.read gets a 403 and no
// band. Keys come from the runner's environment and are never printed, stored or written.
//
// Containerized usage, on the stack of compose.triage23.yaml once inc-war-room-demo is seeded:
//   docker compose -f compose.triage23.yaml run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
//     -v "$PWD/scripts/capture_issue487_incidents.mjs:/e2e/capture.mjs:ro" \
//     -v "$PWD/docs/evidence:/evidence" e2e node /e2e/capture.mjs
import { writeFileSync } from "node:fs";
import { chromium } from "playwright";

const base = process.env.PLAYWRIGHT_BASE_URL ?? "http://web";
const evidence = process.env.EVIDENCE_DIR ?? "/evidence";
const operatorKey = process.env.E2E_TRIAGE_API_KEY;
const deniedKey = process.env.E2E_NOGRANT_API_KEY;
const SEEDED_INCIDENT = "inc-war-room-demo";
const SEEDED_RUN = "run_warroomdemo01";
const checks = [];
const check = (name, ok, detail = "") => {
  checks.push({ name, result: ok ? "PASS" : "FAIL", ...(detail ? { detail } : {}) });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` :: ${detail}` : ""}`);
};

if (!operatorKey || !deniedKey) {
  console.error("E2E_TRIAGE_API_KEY and E2E_NOGRANT_API_KEY are required from the seeded stack.");
  process.exit(2);
}

const browser = await chromium.launch();
// Reduced motion settles theme transitions before each screenshot.
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: "reduce" });
const pageErrors = [];
const apiCalls = [];

async function openTab() {
  const page = await context.newPage();
  page.on("pageerror", (error) => pageErrors.push(String(error?.message ?? error)));
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/")) apiCalls.push({ method: request.method(), path: url.pathname });
  });
  return page;
}

async function connectConsole(page, key) {
  await page.locator("#console-session").waitFor();
  await page.fill("#api-key", key);
  await page.click("#connect-button");
  await page.locator("#session-chip[data-phase='active']").waitFor({ timeout: 20_000 });
}

const text = async (locator) => ((await locator.textContent()) ?? "").trim();
const step = (page, label) => page.locator("#incident-focus-journey .console-journey__step", { hasText: label });
const writes = () => apiCalls.filter((call) => call.method !== "GET");

// 1. The inbox hands an alert to Triage inside the console, where the key is entered once; the
//    declaration is the only command of this proof.
const triage = await openTab();
const alertId = "alert-cart-004";
await triage.goto(`${base}/`);
await triage.locator("#alert-inbox[data-state='ready']").waitFor();
await triage.evaluate(() => {
  window.__sameDocument = true;
});
await triage.locator(`#alert-list [data-alert-id="${alertId}"]`).click();
await triage.locator("#start-triage").click();
await triage.waitForURL(`${base}/?view=triage&alert_id=${alertId}`);
check("the inbox hands its alert to Triage inside the console", (await triage.locator("#alert-id").inputValue()) === alertId);
await connectConsole(triage, operatorKey);
await triage.locator("#command-operation:not([disabled]) option[value='triage_declare']:not([disabled])").waitFor({
  state: "attached",
});
check(
  "Triage speaks the console's language",
  (await text(triage.locator("#triage-page h1"))) === "Triage" &&
    (await text(triage.locator("#submit-button"))) === "Enviar comando" &&
    (await text(triage.locator("#result-title"))) === "Resultado",
);
await triage.selectOption("#command-operation", "triage_declare");
await triage.fill("#command-reason", "Issue 487 console journey proof.");
await triage.selectOption("#command-severity", "sev3");
await triage.fill("#command-impact", "Synthetic cart errors for the console journey proof.");
await triage.fill("#alert-context-service", "cart-service");
await triage.fill("#alert-context-summary", "Synthetic cart errors for the console journey proof.");
await triage.fill("#alert-context-observed-at", "2026-10-15T20:00:00Z");
await triage.fill("#alert-context-source", "operator-confirmed synthetic report");
await triage.selectOption("#alert-context-severity", "sev3");
await triage.check("#alert-context-confirmed");
await triage.click("#submit-button");
await triage.locator("#result-status", { hasText: "declared" }).waitFor({ timeout: 20_000 });
const declared = await text(triage.locator("#result-incident"));
const commands = writes().map((call) => `${call.method} ${call.path}`);
check("triage declares the incident through the real API", /^inc-/.test(declared), declared);
check(
  "the declaration is the only command so far",
  commands.length === 1 && commands[0] === `POST /api/v1/alerts/${alertId}/triage/commands`,
  commands.join(", "),
);
// A tall viewport shows the whole view without stitching the console's sticky bars.
await triage.setViewportSize({ width: 1440, height: 1900 });
await triage.screenshot({ path: `${evidence}/issue-487-triage-declared.png` });
await triage.setViewportSize({ width: 1440, height: 1000 });
apiCalls.length = 0;

// 2. The decision's link opens that incident's war room in the same document and session.
await triage.click("#result-incident a");
await triage.waitForURL(`${base}/?view=war-room&incident_id=${declared}`);
await triage.locator("#war-room[data-state='ready']").waitFor();
check("the triage result opens the war room inside the console", true, new URL(triage.url()).search);
check(
  "the war room reuses the session: no second key and one document",
  apiCalls.every((call) => call.path !== "/api/v1/whoami") && (await triage.evaluate(() => window.__sameDocument)) === true,
);
check("the band shows the declared incident", (await text(triage.locator("#incident-focus-incident"))) === declared);
check("the band shows its authoritative state", (await text(triage.locator("#incident-focus-state"))) === "Activo");
check("the journey marks triage as declared", (await text(step(triage, "Triage"))).includes("Declarado"));
check("the journey keeps the inbox alert", (await text(step(triage, "Alerta"))).includes(alertId));
const declaredRun = await text(triage.locator("#incident-focus-run"));
check(
  "the declaration's run links Decisiones on the same incident",
  (await step(triage, "Decisión").getAttribute("href")) ===
    `/?view=decisions&incident_id=${declared}&run_id=${declaredRun}`,
  declaredRun,
);
await triage.screenshot({ path: `${evidence}/issue-487-triage-war-room.png` });
await triage.goBack();
await triage.locator("#result-summary", { hasText: "Recuperado del backend: declared" }).waitFor();
check("Back returns to Triage with the decision read again from the API", (await text(triage.locator("#result-incident"))) === declared);
await triage.close();

// 3. A seeded incident with a run: one tab, one key, the whole journey.
const tab = await openTab();
await tab.goto(`${base}/?view=war-room&incident_id=${SEEDED_INCIDENT}`);
await connectConsole(tab, operatorKey);
await tab.locator("#war-room[data-state='ready']").waitFor();
await tab.evaluate(() => {
  window.__sameDocument = true;
});
const whoamiBefore = apiCalls.filter((call) => call.path === "/api/v1/whoami").length;
check("the band keeps the run the war room read", (await text(tab.locator("#incident-focus-run"))) === SEEDED_RUN);
check("the run is kept in the address", new URL(tab.url()).searchParams.get("run_id") === SEEDED_RUN);
check(
  "the war room is the current step and the investigation stage",
  (await step(tab, "War room").getAttribute("aria-current")) === "page" &&
    (await step(tab, "War room").getAttribute("data-progress")) === "current",
);
const sidebarHref = await tab.locator("[data-console-nav='decisions']").getAttribute("href");
check(
  "the navigation opens Decisiones on the incident in focus",
  sidebarHref === `/?view=decisions&incident_id=${SEEDED_INCIDENT}&run_id=${SEEDED_RUN}`,
  sidebarHref,
);
await tab.screenshot({ path: `${evidence}/issue-487-incidents-war-room.png` });

await step(tab, "Decisión").click();
await tab.locator("#review[data-state='ready']").waitFor();
check(
  "Decisiones opens on the same incident and run",
  (await text(tab.locator("#fact-incident"))) === SEEDED_INCIDENT && (await text(tab.locator("#fact-run"))) === SEEDED_RUN,
);
check("an investigating run offers no review action", await tab.locator("#actions-empty").isVisible());
await step(tab, "Postmortem").click();
await tab.locator("#postmortem[data-state='ready']").waitFor();
check("Postmortem opens on the same incident", (await text(tab.locator("#fact-incident"))) === SEEDED_INCIDENT);

await tab.goBack();
await tab.locator("#review[data-state='ready']").waitFor();
await tab.goBack();
await tab.locator("#war-room[data-state='ready']").waitFor();
await tab.goForward();
await tab.locator("#review[data-state='ready']").waitFor();
check("Back and Forward restore each view in one document", (await tab.evaluate(() => window.__sameDocument)) === true);
check(
  "the key was entered once for the whole journey",
  apiCalls.filter((call) => call.path === "/api/v1/whoami").length === whoamiBefore,
);

// The capture waits for the dark theme to be applied and painted.
await tab.getByRole("button", { name: "Oscuro" }).click();
await tab.locator("html[data-theme='dark'] [data-theme-option='dark'][aria-pressed='true']").waitFor();
await tab.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
await tab.screenshot({ path: `${evidence}/issue-487-incidents-decisions-dark.png` });
await tab.getByRole("button", { name: "Claro" }).click();
await tab.locator("html[data-theme='light']").waitFor({ state: "attached" });

await tab.reload();
await connectConsole(tab, operatorKey);
await tab.locator("#review[data-state='ready']").waitFor();
check(
  "a reload restores Decisiones from the address after the key is entered again",
  (await text(tab.locator("#fact-run"))) === SEEDED_RUN && (await text(tab.locator("#incident-focus-run"))) === SEEDED_RUN,
);

await tab.locator("#session-chip").click();
await tab.locator("#disconnect-button").click();
await tab.locator("#session-chip[data-phase='anonymous']").waitFor();
check(
  "logout empties the band and the view",
  (await tab.locator("#incident-focus").isHidden()) &&
    (await text(tab.locator("#incident-focus-title"))) === "" &&
    (await tab.locator("#review").getAttribute("data-state")) === "auth",
);
const storage = await tab.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }));
check(
  "the key is absent from the address and Web Storage",
  !tab.url().includes(operatorKey) && !storage.includes(operatorKey),
);
await tab.close();

// 4. An identity without run.read: the view is denied, the band stays empty, the session stays.
const denied = await openTab();
await denied.goto(`${base}/?view=war-room&incident_id=${SEEDED_INCIDENT}`);
await connectConsole(denied, deniedKey);
await denied.locator("#war-room[data-state='error']").waitFor();
check("a principal without run.read gets the 403 state", await denied.locator("#error-403").isVisible());
check("the denied view shows no band", await denied.locator("#incident-focus").isHidden());
check(
  "the 403 does not end the session",
  (await denied.locator("#session-chip").getAttribute("data-phase")) === "active",
  await text(denied.locator("#session-principal")),
);
await denied.screenshot({ path: `${evidence}/issue-487-incidents-denied.png` });
await denied.close();

const navigationWrites = writes().map((call) => `${call.method} ${call.path}`);
check("navigating the console sent no command", navigationWrites.length === 0, navigationWrites.join(", "));
check("no page errors", pageErrors.length === 0, pageErrors.join(" | "));
await browser.close();

const failures = checks.filter((item) => item.result === "FAIL").map((item) => item.name);
writeFileSync(
  `${evidence}/issue-487-incidents-proof.json`,
  `${JSON.stringify(
    { issue: 487, base, incidents: { declared, seeded: SEEDED_INCIDENT, run: SEEDED_RUN }, checks, failures, pageErrors },
    null,
    2,
  )}\n`,
);
process.exit(failures.length ? 1 : 0);
