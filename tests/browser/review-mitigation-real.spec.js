import { expect, request, test } from "@playwright/test";
import { connectConsole } from "./support/console-session.mjs";

// Decisiones shows the recorded mitigation before the human decides, against the REAL stack
// (web proxy, FastAPI, PostgreSQL); nothing is mocked. The incident comes from
// scripts/seed_verification_close_demo.py (SEED_STAMP): a run in `mitigating` with a pending
// mitigation based on one hypothesis. Ways this can fail, written before the view:
// 1. the operator approves without seeing the description, steps, risk, verification check,
//    execution mode and the hypothesis it is based on;
// 2. showing it changes the decision flow: approving must still go through the same panel and
//    reach `verifying`, where the approved mitigation and its check stay readable;
// 3. a human without run.read_context gets the text, or a broken page instead of a refusal.
const STAMP = process.env.SEED_STAMP ?? "";
const DEMO_KEY = process.env.DEMO_HUMAN_API_KEY ?? "";
const ADMIN_KEY = process.env.ADMIN_HUMAN_API_KEY ?? "";
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://web";
const REAL = process.env.SRE_REAL_BACKEND === "1" && Boolean(DEMO_KEY && ADMIN_KEY && STAMP);
const INCIDENT = `inc-vc-${STAMP}`;
const RUN = `run_vc${STAMP.replaceAll("-", "")}`;
const DESCRIPTION = "Turn the paymentFailure feature flag off.";
const REVIEW = `/public/incident-ui/review.html?incident_id=${INCIDENT}&run_id=${RUN}`;

test.skip(!REAL, "requires SRE_REAL_BACKEND=1, demo/admin keys and a SEED_STAMP seed");

// A human allowed to follow runs (run.read) and nothing else, created through the governed API.
async function watcherKey() {
  const api = await request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${ADMIN_KEY}` } });
  const id = `mitigation-watcher-${STAMP}`;
  const post = (path, data, key) =>
    api.post(`${BASE}/api${path}`, { data, headers: { "idempotency-key": `${key}-${STAMP}-0001` } });
  await post("/v1/principals", { principal_id: id, kind: "human", display_name: "Watcher" }, "mw-p");
  const issued = await post(`/v1/principals/${id}/credentials`, { expires_at: "2031-01-01T00:00:00Z" }, "mw-c");
  expect(issued.status()).toBe(201);
  const granted = await post("/v1/grants", {
    grant_id: `grant-${id}-run-read`,
    principal_id: id,
    action: "run.read",
    resource: { resource_type: "incident_workflow", resource_id: "incident-response" },
    effect: "allow",
  }, "mw-g");
  expect(granted.status()).toBe(201);
  return (await issued.json()).key;
}

test.describe.configure({ mode: "serial" });

test("without run.read_context the refusal replaces the mitigation text", async ({ page }) => {
  const key = await watcherKey();
  await page.goto(REVIEW);
  await connectConsole(page, key);

  await expect(page.locator("#mitigation-forbidden")).toBeVisible();
  await expect(page.locator("#context-section")).toBeVisible();
  await expect(page.locator("#actions-list button")).toHaveCount(3);
  await expect(page.locator("body")).not.toContainText(DESCRIPTION);
});

test("the operator reads the whole mitigation, approves it and still reads it while verifying", async ({ page }) => {
  await page.goto(REVIEW);
  await connectConsole(page, DEMO_KEY);

  const mitigation = page.locator("#mitigation-section");
  await expect(page.locator("#mitigation-title")).toHaveText("Mitigación propuesta");
  await expect(mitigation).toContainText(DESCRIPTION);
  await expect(mitigation).toContainText("The operator sets paymentFailure to off in the flag service.");
  await expect(mitigation).toContainText("Riesgo bajo");
  await expect(mitigation).toContainText("Pendiente de decisión humana");
  await expect(mitigation).toContainText("paymentservice error rate below 1% for ten minutes.");
  await expect(mitigation).toContainText("Humana: la aplica una persona fuera de la consola.");
  await expect(mitigation).toContainText("The paymentFailure feature flag makes PaymentService/Charge fail.");
  // The mitigation comes before the actions that decide it.
  const order = await page.evaluate(() => {
    const section = document.getElementById("mitigation-section");
    return Boolean(section.compareDocumentPosition(document.getElementById("actions-section")) & 4);
  });
  expect(order).toBe(true);

  await page.locator('#actions-list button[data-command="approve_mitigation"]').click();
  await page.locator("#decision-submit").click();
  await expect(page.locator("#receipt-line")).toContainText("verifying");
  await page.locator("#refresh-button").click();
  await expect(page.locator("#mitigation-title")).toHaveText("Mitigación aprobada y su verificación");
  await expect(mitigation).toContainText("Aprobada");
  await expect(mitigation).toContainText("paymentservice error rate below 1% for ten minutes.");
  await expect(page.locator('#actions-list button[data-command="verification_passed"]')).toBeVisible();
});
