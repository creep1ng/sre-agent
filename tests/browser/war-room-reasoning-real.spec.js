import { expect, request, test } from "@playwright/test";
import { connectConsole } from "./support/console-session.mjs";

// The agent's recorded reasoning in the war room, against the REAL stack (web proxy, FastAPI,
// PostgreSQL); nothing is mocked. The incident comes from scripts/seed_verification_close_demo.py
// (SEED_STAMP): a run in `mitigating` whose incident holds one cited hypothesis and one labelled
// evidence item. Ways this can fail, written before the view:
// 1. the operator (run.read_context) does not see the hypothesis, its confidence or the evidence
//    the agent gathered (tool, datasource, query, result, governed request id);
// 2. a principal that may follow the run (run.read) but not read its context gets the text, or
//    the view breaks instead of an explicit "sin permiso" state beside a working timeline;
// 3. a failed or refused reasoning read hides the summary or the run strip.
const STAMP = process.env.SEED_STAMP ?? "";
const DEMO_KEY = process.env.DEMO_HUMAN_API_KEY ?? "";
const ADMIN_KEY = process.env.ADMIN_HUMAN_API_KEY ?? "";
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://web";
const REAL = process.env.SRE_REAL_BACKEND === "1" && Boolean(DEMO_KEY && ADMIN_KEY && STAMP);
const INCIDENT = `inc-vc-${STAMP}`;
const STATEMENT = "The paymentFailure feature flag makes PaymentService/Charge fail.";

test.skip(!REAL, "requires SRE_REAL_BACKEND=1, demo/admin keys and a SEED_STAMP seed");

// A human allowed to follow runs (run.read) and nothing else, created through the governed API.
async function watcherKey() {
  const api = await request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${ADMIN_KEY}` } });
  const id = `reasoning-watcher-${STAMP}`;
  const post = (path, data, key) =>
    api.post(`${BASE}/api${path}`, { data, headers: { "idempotency-key": `${key}-${STAMP}-0001` } });
  await post("/v1/principals", { principal_id: id, kind: "human", display_name: "Watcher" }, "rw-p");
  const issued = await post(`/v1/principals/${id}/credentials`, { expires_at: "2031-01-01T00:00:00Z" }, "rw-c");
  expect(issued.status()).toBe(201);
  const granted = await post("/v1/grants", {
    grant_id: `grant-${id}-run-read`,
    principal_id: id,
    action: "run.read",
    resource: { resource_type: "incident_workflow", resource_id: "incident-response" },
    effect: "allow",
  }, "rw-g");
  expect(granted.status()).toBe(201);
  return (await issued.json()).key;
}

test("the operator reads the recorded hypothesis and the evidence behind it", async ({ page }) => {
  await page.goto(`/public/incident-ui/war-room.html?incident_id=${INCIDENT}`);
  await connectConsole(page, DEMO_KEY);

  const panel = page.locator("#reasoning-section");
  await expect(panel).toBeVisible();
  await expect(page.locator("#hypothesis-block")).toContainText(STATEMENT);
  await expect(page.locator("#hypothesis-block")).toContainText("Confianza media");
  await expect(page.locator("#evidence-title")).toHaveText("Evidencia recolectada (1)");
  const evidence = page.locator("#evidence-list li");
  await expect(evidence).toContainText("query_prometheus");
  await expect(evidence).toContainText("webstore-metrics");
  await expect(evidence).toContainText("traces_span_metrics_calls_total");
  await expect(evidence).toContainText("Citada por la hipótesis");
  await expect(evidence).toContainText("Solicitud MCP: sin registrar");
  await expect(page.locator("#reasoning-forbidden")).toBeHidden();
  await expect(page.locator("#run-decide")).toBeVisible();
});

test("following the run without run.read_context shows an honest refusal", async ({ page }) => {
  const key = await watcherKey();
  await page.goto(`/public/incident-ui/war-room.html?incident_id=${INCIDENT}`);
  await connectConsole(page, key);

  await expect(page.locator("#reasoning-forbidden")).toBeVisible();
  await expect(page.locator("#reasoning-forbidden")).toContainText("Sin permiso para ver el razonamiento");
  await expect(page.locator("#summary-section")).toBeVisible();
  await expect(page.locator("#timeline-list li").first()).toBeVisible();
  await expect(page.locator("#hypothesis-block")).toBeHidden();
  await expect(page.locator("#evidence-block")).toBeHidden();
  await expect(page.locator("body")).not.toContainText(STATEMENT);
});
