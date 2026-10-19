import { expect, test } from "@playwright/test";
import { answerWhoAmI, connectConsole, logoutConsole } from "./support/console-session.mjs";

// The postmortem view reads the persisted artifact of the incident in focus (#43 over #335).
// Failure modes covered here, each with its own test below:
//  1. No incident in focus: nothing is read.
//  2. Incident read fails (401, 404 incident_not_found, 503): no artifact data is shown.
//  3. The postmortem read is denied (403): nothing of the incident is left on screen.
//  4. No artifact is persisted (404 postmortem_not_found): an honest empty state, never a fixture.
//  5. A reader without run.read_context gets the projection only: no text reaches the page.
//  6. Logging out removes the artifact content from the page.
const INCIDENT = "inc-demo";
const RUN = "run_demo0001";
const PM_RUN = "run_demopm0001";

function detailPayload(state = "postmortem") {
  const runs = [{ run_id: RUN, version: 6, status: "running", current_state: "resolved", updated_at: "2026-08-24T14:40:00Z" }];
  if (state === "postmortem") {
    runs.push({ run_id: PM_RUN, version: 1, status: "running", current_state: "postmortem", updated_at: "2026-08-24T14:45:00Z" });
  }
  return {
    incident_id: INCIDENT, workflow_version: "1.0.0", state, severity: "sev2", impact: "Checkout failing at payment.",
    alert: null, approvals: [], version: 9, updated_at: "2026-08-24T14:45:00Z", runs,
  };
}

const CONTENT = {
  summary: "Checkout payments failed for 14 minutes.",
  impact: "About 3% of checkouts failed.",
  timeline: [{ event_id: "evt_verified01", description: "Stability check passed." }],
  cause: { statement: "A config push removed the payment client timeout.", certainty: "probable" },
  strategy: "Roll back the config.",
  actions_taken: [{ event_id: "evt_applied001", description: "Mitigation approved by a human." }],
  verification: "Error rate below 1% for 15 minutes.",
  pending: ["Add a config lint for client timeouts."],
  unknowns: ["Exact revenue impact."],
};

function projection({ withContent = true, review = null } = {}) {
  const payload = {
    postmortem_id: "pm_demopayment", incident_id: INCIDENT, version: 2, run_ids: [RUN, PM_RUN],
    updated_by: "demo-human", created_at: "2026-08-24T14:46:00Z", updated_at: "2026-08-24T14:50:00Z",
    review: review ?? { status: "pending", reviewed_version: null, reviewer_id: null, reviewed_at: null },
    content_included: withContent,
  };
  if (withContent) {
    payload.content = CONTENT;
    payload.review = { ...payload.review, comment: null };
  }
  return payload;
}

const NOT_FOUND = { status: 404, json: { error: { code: "postmortem_not_found", message: "none" } } };

// Answers the incident and its postmortem; records every request to the incident API.
async function mockApi(page, { detail = () => detailPayload(), postmortem = () => ({ json: projection() }) } = {}) {
  const requests = [];
  await page.route("**/api/v1/incidents/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    requests.push({ method: request.method(), path });
    if (path.endsWith("/postmortem")) return route.fulfill(postmortem());
    const answer = detail();
    return route.fulfill(answer.status ? answer : { json: answer });
  });
  return requests;
}

async function openPostmortem(page, query = `incident_id=${INCIDENT}`, { active = true } = {}) {
  await answerWhoAmI(page);
  await page.goto(`/?view=postmortem&${query}`);
  if (active) return connectConsole(page);
  // A 401 ends the console session right after connecting, so "active" may never be observable.
  await page.locator("#api-key").fill("sre_demo_token_demo_0001");
  await page.locator("#connect-button").click();
}

test("sin incidente en foco no consulta nada", async ({ page }) => {
  const requests = await mockApi(page);
  await openPostmortem(page, "");

  await expect(page.locator("#error-missing-id")).toBeVisible();
  await expect(page.locator("#context-section")).toBeHidden();
  expect(requests).toHaveLength(0);
});

for (const [status, code, alert] of [
  [401, "authentication_failed", "#error-401"],
  [404, "incident_not_found", "#error-404"],
  [503, "storage_unavailable", "#error-503"],
]) {
  test(`un ${status} al leer el incidente no muestra artefacto`, async ({ page }) => {
    await mockApi(page, { detail: () => ({ status, json: { error: { code, message: "x" } } }) });
    await openPostmortem(page, `incident_id=${INCIDENT}`, { active: status !== 401 });

    await expect(page.locator(alert)).toBeVisible();
    for (const section of ["#context-section", "#empty-section", "#artifact-section"]) {
      await expect(page.locator(section)).toBeHidden();
    }
    // A 401 ends the console session instead: recovery is reconnecting, not refreshing.
    if (status !== 401) await expect(page.locator("#refresh-button")).toBeVisible();
  });
}

test("un 403 al leer el postmortem no deja nada del incidente", async ({ page }) => {
  await mockApi(page, { postmortem: () => ({ status: 403, json: { error: { code: "not_authorized", message: "x" } } }) });
  await openPostmortem(page);

  await expect(page.locator("#error-403")).toBeVisible();
  await expect(page.locator("#context-section")).toBeHidden();
  await expect(page.locator("#artifact-sections")).toBeEmpty();
});

test("sin artefacto persistido muestra un estado vacío honesto y ningún fixture", async ({ page }) => {
  await mockApi(page, { postmortem: () => NOT_FOUND });
  await openPostmortem(page);

  await expect(page.locator("#postmortem")).toHaveAttribute("data-state", "ready");
  await expect(page.locator("#empty-section")).toBeVisible();
  await expect(page.locator("#empty-detail")).toContainText("sin contenido persistido");
  await expect(page.locator("#fact-artifact")).toHaveText("Sin artefacto persistido");
  await expect(page.locator("#artifact-section")).toBeHidden();
  await expect(page.locator("#postmortem")).not.toContainText("pm_demo0001");
});

test("con run.read_context muestra versión, revisión, runs y el mínimo con sus citas", async ({ page }) => {
  await mockApi(page);
  await openPostmortem(page);

  await expect(page.locator("#fact-artifact")).toHaveText("pm_demopayment");
  await expect(page.locator("#fact-version")).toHaveText("2");
  await expect(page.locator("#fact-review")).toContainText("Pendiente de revisión");
  await expect(page.locator("#fact-runs")).toHaveText(`${RUN}, ${PM_RUN}`);
  const sections = page.locator("#artifact-sections");
  await expect(sections).toContainText(CONTENT.summary);
  await expect(sections).toContainText("certeza: Probable");
  await expect(sections).toContainText("evt_verified01");
  await expect(sections).toContainText("evt_applied001");
  await expect(sections).toContainText("Exact revenue impact.");
  await expect(page.locator("#content-restricted")).toBeHidden();
});

test("sin run.read_context muestra la proyección y ningún texto del postmortem", async ({ page }) => {
  await mockApi(page, { postmortem: () => ({ json: projection({ withContent: false }) }) });
  await openPostmortem(page);

  await expect(page.locator("#fact-version")).toHaveText("2");
  await expect(page.locator("#content-restricted")).toBeVisible();
  await expect(page.locator("#artifact-sections")).toBeEmpty();
  await expect(page.locator("#postmortem")).not.toContainText(CONTENT.summary);
});

test("cerrar sesión retira el contenido del postmortem", async ({ page }) => {
  await mockApi(page);
  await openPostmortem(page);
  await expect(page.locator("#artifact-sections")).toContainText(CONTENT.summary);

  await logoutConsole(page);
  await expect(page.locator("#error-401")).toBeVisible();
  await expect(page.locator("#artifact-sections")).toBeEmpty();
  await expect(page.locator("#postmortem")).not.toContainText(CONTENT.summary);
});
