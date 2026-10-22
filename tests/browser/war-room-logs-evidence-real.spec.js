import { expect, request, test } from "@playwright/test";
import { connectConsole } from "./support/console-session.mjs";

// Issue #716 against the REAL stack: web proxy, FastAPI, PostgreSQL, the local OpenTelemetry Demo
// with paymentUnreachable on, Grafana MCP and the paid investigator model. Ways this can fail:
// 1. the log query asks for `service.name`, which the index does not have, and finds 0 documents;
// 2. it finds documents of another service (an unquoted hyphenated name matches by token);
// 3. the logs evidence is collected after the hypothesis, or never reaches the model's input.
// The operator's summary carries no field hint: the investigator has only its tool schema.
const DEMO_KEY = process.env.DEMO_HUMAN_API_KEY ?? "";
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://web";
const ARTIFACTS = process.env.LIVE_INVESTIGATION_ARTIFACT_DIR ?? "test-results/issue-716";
const LIVE = process.env.LIVE_INVESTIGATION === "1" && Boolean(DEMO_KEY);

test.skip(!LIVE, "requires LIVE_INVESTIGATION=1, the OTel Demo failure and a demo key");

async function declareCheckoutIncident() {
  const api = await request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${DEMO_KEY}` } });
  const path = `${BASE}/api/v1/alerts/al-716-${Date.now().toString(36)}/triage`;
  const post = (data) =>
    api.post(`${path}/commands`, { data, headers: { "idempotency-key": `i716-${Math.random()}` } });
  expect((await post({ operation: "open_triage", expected_version: 1 })).status()).toBe(200);
  const version = (await (await api.get(path)).json()).expected_version;
  const declared = await post({
    operation: "triage_declare",
    expected_version: version,
    severity: "sev1",
    reason: "Checkout cannot charge payments",
    impact: "Customers cannot place orders",
    alert_context: {
      service: "checkout",
      summary: "Customers report checkout payments failing",
      observed_at: new Date().toISOString(),
      source: "operator",
      severity: "sev1",
    },
  });
  expect(declared.status()).toBe(201);
  return { api, incident: (await declared.json()).incident_id };
}

test("the logs evidence brings checkout or payment documents into the hypothesis", async ({ page }) => {
  test.setTimeout(600_000);
  const { api, incident } = await declareCheckoutIncident();
  await page.goto(`/public/incident-ui/war-room.html?incident_id=${incident}`);
  await connectConsole(page, DEMO_KEY);
  await page.locator("#run-start").click();

  // The war room refreshes itself while the agent investigates.
  await expect(page.locator("#hypothesis-block")).toBeVisible({ timeout: 540_000 });
  const runId = await page.locator("#run-select").inputValue();
  const logs = page.locator("#evidence-list li", { hasText: "query_elasticsearch" }).first();
  await expect(logs.locator(".reasoning__query")).toContainText("resource.service.name");
  await expect(logs.locator(".reasoning__result")).toHaveText(/^[1-9]\d* documentos?/);
  await page.screenshot({ path: `${ARTIFACTS}/war-room-logs-evidence.png`, fullPage: true });

  // The turns are stored when the dispatch ends, after the hypothesis is shown.
  let context;
  let proposal;
  await expect
    .poll(async () => {
      const url = `${BASE}/api/v1/incidents/${incident}/runs/${runId}/context`;
      context = await (await api.get(url)).json();
      proposal = context.turns.find((turn) => turn.model_output.includes('"propose_hypothesis"'));
      return Boolean(proposal);
    }, { timeout: 120_000 })
    .toBe(true);
  const evidence = context.reasoning.evidence.filter((item) => item.tool === "query_elasticsearch");
  const found = evidence.find((item) => /"service\.name":"(checkout|payment)"/.test(item.summary));
  expect(found, "a log document of checkout or payment").toBeTruthy();
  expect(found.query).not.toMatch(/(^|[^.\w])service\.name:/);
  expect(proposal.assembled_input).toContain(found.evidence_id);
  const cited = context.reasoning.hypotheses.some((h) => h.supporting_evidence.includes(found.evidence_id));
  test.info().annotations.push(
    { type: "incident", description: incident },
    { type: "logs query", description: found.query },
    { type: "logs cited by the hypothesis", description: String(cited) },
  );
});
