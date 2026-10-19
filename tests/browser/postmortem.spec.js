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
//  7. Only a resolved incident offers to open the postmortem; other states explain why not.
//  8. Opening it is refused (409 run_conflict, 403): the reason shows and nothing changes.
//  9. A draft cites only events the incident really stored; saving creates version 1 from 0.
// 10. A stale save (409 postmortem_version_conflict), invalid content (422) or a writer without
//     run.command (403) shows the backend reason and keeps the draft in the form.
// 11. Without the text (no run.read_context) or outside the postmortem state there is no editor.
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

// Events the incident stored, per run; the draft may cite only these.
const EVENTS = {
  [RUN]: [
    // Triage writes its declaration as evt-…, which the postmortem citation contract (evt_…) refuses.
    { event_id: "evt-declared00000001", kind: "state_change", state: "active", summary: "Incident declared." },
    { event_id: "evt_started0001", kind: "state_change", state: "investigating", summary: "Investigation started." },
    { event_id: "evt_dispatch001", kind: "dispatch_receipt", state: "investigating", summary: "Investigation dispatch started." },
    { event_id: "evt_proposed001", kind: "state_change", state: "mitigating", summary: "Mitigation proposed." },
    { event_id: "evt_applied001", kind: "state_change", state: "verifying", summary: "Mitigation approved." },
    { event_id: "evt_verified01", kind: "state_change", state: "resolved", summary: "Service verified stable." },
  ],
  [PM_RUN]: [{ event_id: "evt_pmstart001", kind: "state_change", state: "postmortem", summary: "Postmortem started." }],
};

// Answers the incident, its postmortem, its timeline, run starts and writes; records every request.
async function mockApi(page, { detail = () => detailPayload(), postmortem = () => ({ json: projection() }), start, put } = {}) {
  const requests = [];
  await page.route("**/api/v1/incidents/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    requests.push({ method: request.method(), path, headers: request.headers(), body: request.postDataJSON() });
    if (path.endsWith("/runs") && request.method() === "POST") return route.fulfill(start());
    if (path.endsWith("/postmortem") && request.method() === "PUT") return route.fulfill(put());
    if (path.endsWith("/timeline")) {
      const events = EVENTS[url.searchParams.get("run_id")] ?? [];
      return route.fulfill({ json: { events, next_cursor: "seq:9", has_more: false } });
    }
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

test("solo un incidente resuelto ofrece abrir el postmortem", async ({ page }) => {
  let state = "investigating";
  await mockApi(page, { detail: () => detailPayload(state), postmortem: () => NOT_FOUND });
  await openPostmortem(page);
  await expect(page.locator("#empty-detail")).toContainText("Investigando");
  await expect(page.locator("#start-postmortem")).toBeHidden();

  state = "resolved";
  await page.locator("#refresh-button").click();
  await expect(page.locator("#start-postmortem")).toBeVisible();
  await expect(page.locator("#empty-detail")).toContainText("start_postmortem");
});

test("abrir el postmortem pide objective postmortem con clave de idempotencia y relee", async ({ page }) => {
  let state = "resolved";
  const requests = await mockApi(page, {
    detail: () => detailPayload(state),
    postmortem: () => NOT_FOUND,
    start: () => {
      state = "postmortem";
      return { status: 201, json: { run_id: PM_RUN, incident_id: INCIDENT, current_state: "postmortem" } };
    },
  });
  await openPostmortem(page);
  await page.locator("#start-postmortem").click();

  await expect(page.locator("#fact-state")).toHaveText("En postmortem");
  await expect(page.locator("#start-postmortem")).toBeHidden();
  const starts = requests.filter((entry) => entry.method === "POST");
  expect(starts).toHaveLength(1);
  expect(starts[0].path).toBe(`/api/v1/incidents/${INCIDENT}/runs`);
  expect(starts[0].body).toEqual({ workflow_version: "1.0.0", objective: "postmortem" });
  expect(starts[0].headers["idempotency-key"]).toMatch(/^\S{8,200}$/);
});

for (const [status, code, text] of [
  [409, "run_conflict", "cambió de estado"],
  [403, "not_authorized", "no está autorizada"],
]) {
  test(`abrir el postmortem rechazado con ${status} muestra el motivo y no cambia nada`, async ({ page }) => {
    await mockApi(page, {
      detail: () => detailPayload("resolved"),
      postmortem: () => NOT_FOUND,
      start: () => ({ status, json: { error: { code, message: "x" } } }),
    });
    await openPostmortem(page);
    await page.locator("#start-postmortem").click();

    await expect(page.locator("#start-status")).toContainText(`HTTP ${status}`);
    await expect(page.locator("#start-status")).toContainText(text);
    await expect(page.locator("#fact-state")).toHaveText("Resuelto");
    await expect(page.locator("#start-postmortem")).toBeEnabled();
  });
}

test("el borrador cita solo eventos guardados y guardar crea la versión 1", async ({ page }) => {
  let stored = null;
  const requests = await mockApi(page, {
    postmortem: () => (stored ? { json: stored } : NOT_FOUND),
    put: () => {
      stored = { ...projection(), version: 1 };
      return { status: 201, json: { ...projection({ withContent: false }), version: 1 } };
    },
  });
  await openPostmortem(page);
  await expect(page.locator("#editor-basis")).toContainText("versión 1");
  await expect(page.locator("#pm-timeline")).toHaveValue(/evt_verified01 \| /);
  await expect(page.locator("#pm-timeline")).not.toHaveValue(/evt_dispatch001/);
  await page.locator("#pm-pending").fill("Add a config lint for client timeouts.");
  await page.locator("#save-postmortem").click();

  await expect(page.locator("#save-status")).toContainText("Versión 1 guardada");
  await expect(page.locator("#fact-version")).toHaveText("1");
  const [write] = requests.filter((entry) => entry.method === "PUT");
  expect(write.path).toBe(`/api/v1/incidents/${INCIDENT}/postmortem`);
  expect(write.body.expected_version).toBe(0);
  const cited = [...write.body.content.timeline, ...write.body.content.actions_taken].map((entry) => entry.event_id);
  const known = Object.values(EVENTS).flat().map((event) => event.event_id);
  expect(cited.every((id) => known.includes(id) && /^evt_[a-z0-9_-]{1,60}$/.test(id))).toBe(true);
  expect(write.body.content.actions_taken).toEqual([expect.objectContaining({ event_id: "evt_applied001" })]);
  expect(write.body.content.cause.certainty).toBe("hypothesis");
  expect(write.body.content.pending).toEqual(["Add a config lint for client timeouts."]);
});

test("editar la versión mostrada envía expected_version con esa versión", async ({ page }) => {
  const requests = await mockApi(page, { put: () => ({ status: 200, json: { ...projection({ withContent: false }), version: 3 } }) });
  await openPostmortem(page);
  await expect(page.locator("#pm-summary")).toHaveValue(CONTENT.summary);
  await page.locator("#pm-summary").fill("Checkout payments failed for 14 minutes after a config push.");
  await page.locator("#save-postmortem").click();

  await expect.poll(() => requests.filter((entry) => entry.method === "PUT").length).toBe(1);
  const [write] = requests.filter((entry) => entry.method === "PUT");
  expect(write.body.expected_version).toBe(2);
  expect(write.body.content.timeline).toEqual(CONTENT.timeline);
});

for (const [status, code, message, text] of [
  [409, "postmortem_version_conflict", "The postmortem changed; reload the current version.", "cambió"],
  [422, "invalid_postmortem", "timeline requires at least one cited event", "timeline requires at least one cited event"],
  [422, "unknown_event_reference", "A cited event does not exist in this incident.", "no corresponde"],
  [403, "not_authorized", "denied", "no está autorizada"],
]) {
  test(`guardar con ${status} ${code} muestra el motivo y conserva el borrador`, async ({ page }) => {
    const requests = await mockApi(page, { put: () => ({ status, json: { error: { code, message } } }) });
    await openPostmortem(page);
    await page.locator("#pm-summary").fill("Texto local del borrador.");
    await page.locator("#save-postmortem").click();

    await expect(page.locator("#save-status")).toContainText(`HTTP ${status}`);
    await expect(page.locator("#save-status")).toContainText(text);
    await expect(page.locator("#pm-summary")).toHaveValue("Texto local del borrador.");
    await expect(page.locator("#fact-version")).toHaveText("2");
    expect(requests.filter((entry) => entry.method === "PUT")).toHaveLength(1);
  });
}

test("sin el texto o fuera de postmortem no hay editor", async ({ page }) => {
  let restricted = true;
  let state = "postmortem";
  await mockApi(page, { detail: () => detailPayload(state), postmortem: () => ({ json: projection({ withContent: !restricted }) }) });
  await openPostmortem(page);
  await expect(page.locator("#fact-version")).toHaveText("2");
  await expect(page.locator("#editor-section")).toBeHidden();

  restricted = false;
  state = "closed";
  await page.locator("#refresh-button").click();
  await expect(page.locator("#artifact-sections")).toContainText(CONTENT.summary);
  await expect(page.locator("#editor-section")).toBeHidden();
});
