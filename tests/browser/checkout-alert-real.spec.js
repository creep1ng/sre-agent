import { expect, request, test } from "@playwright/test";
import { createHash, createHmac, randomUUID } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { connectConsole } from "./support/console-session.mjs";

// Issue #721 against the REAL stack: the local OpenTelemetry Demo with its second service
// sre-checkout, the demo's collector and Prometheus, the governed Grafana MCP, FastAPI behind
// the web proxy, and the deploy-executor over docker-socket-proxy. Ways this can fail:
// 1. sre-checkout is not enrolled, or does not run demo/checkout:1.4.0 before the failure, or the
//    store's `checkout`, which a store rule also alerts on, is enrolled too (#722);
// 2. after `demo_env.py fail --service sre-checkout` it does not run 1.5.0, or 1.4.0 is not in
//    the image store to roll back to;
// 3. its alert is not in the inbox within 60 s of 1.5.0 starting, or the store's rule fires too;
// 4. the rollback, signed as the gateway will sign it (#722), does not bring back 1.4.0;
// 5. after the rollback the rule never evaluates `ok`, so the episode stays open in the inbox.
const ENABLED = process.env.CHECKOUT_ALERT_E2E === "1";
const DEMO_KEY = process.env.DEMO_HUMAN_API_KEY ?? "";
const SIGNING_KEY = process.env.DEPLOY_EXECUTOR_SIGNING_KEY ?? "";
const EXECUTOR = process.env.DEPLOY_EXECUTOR_URL ?? "http://deploy-executor:8000";
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://web";
const ARTIFACTS = process.env.CHECKOUT_ALERT_ARTIFACT_DIR ?? "test-results/issue-721";
const RULE = "checkout-orders-error-rate";
const SERVICE = "sre-checkout";
const ROLLBACK = "/v1/operations/deployment.rollback";

test.skip(!ENABLED || !DEMO_KEY, "requires CHECKOUT_ALERT_E2E=1 and a demo key inside the Compose stack");

const transcript = [];
const timings = {};
const note = (step, data) => (transcript.push({ step, at: new Date().toISOString(), ...data }), data);
// Written even when an assertion fails, so a red run still leaves its evidence.
test.afterEach(() => {
  mkdirSync(ARTIFACTS, { recursive: true });
  writeFileSync(`${ARTIFACTS}/transcript.json`, JSON.stringify({ timings, transcript }, null, 2));
});

// What the gateway will send (#722): v1 = HMAC-SHA256 over method, path, key, sha256(body), timestamp.
function signature(method, path, key, data) {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const digest = createHash("sha256").update(data).digest("hex");
  const mac = createHmac("sha256", SIGNING_KEY).update([method, path, key, digest, timestamp].join("\n")).digest("hex");
  return { "x-executor-timestamp": timestamp, "x-executor-signature": `v1=${mac}` };
}

test("the sre-checkout alert reaches the inbox within 60 s of 1.5.0 and closes after the rollback", async ({ page }) => {
  test.setTimeout(900_000);
  mkdirSync(ARTIFACTS, { recursive: true });
  const executor = await request.newContext();
  const web = await request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${DEMO_KEY}` } });
  const checkout = async () => (await executor.get(`${EXECUTOR}/v1/services/${SERVICE}`)).json();
  const alerts = async () => (await web.get(`${BASE}/api/v1/alerts`)).json();
  const ours = (body) => body.alerts.filter((alert) => alert.origin?.condition?.startsWith(`${RULE}:`));
  const card = page.locator("#alert-list button", { hasText: `${RULE}:` });

  // 1. Enrolled with both operations, on the healthy release, and nothing in the inbox for it.
  const { services } = await (await executor.get(`${EXECUTOR}/v1/catalog`)).json();
  const enrolled = note("catalog", { service: services.find((s) => s.service === SERVICE) });
  expect(enrolled.service.image_repository).toBe("demo/checkout");
  expect(enrolled.service.operations.map((o) => o.operation)).toEqual(["deployment.restart", "deployment.rollback"]);
  const store = await executor.get(`${EXECUTOR}/v1/services/checkout`);
  expect(note("store checkout", { status: store.status(), body: await store.json() }).body.error.code).toBe("service_not_enrolled");
  const healthy = note("checkout before", { response: await checkout() });
  expect(healthy.response.container).toMatchObject({ image: "demo/checkout:1.4.0", state: "running", health: "healthy" });
  await page.goto("/");
  await connectConsole(page, DEMO_KEY);
  await expect(page.locator("#alert-inbox")).toHaveAttribute("data-state", /^(empty|ready)$/, { timeout: 30_000 });
  await expect(card).toHaveCount(0);
  expect(ours(note("alerts before", { body: await alerts() }).body)).toEqual([]);

  // 2. The operator deploys the broken release; the image store keeps both tags.
  console.log("READY: run `demo_env.py fail --service sre-checkout` now");
  let broken;
  // While Compose recreates it the executor may answer 409 (no container, or two): keep polling.
  await expect.poll(async () => (broken = await checkout()).container?.image, { timeout: 600_000, intervals: [1_000] }).toBe("demo/checkout:1.5.0");
  note("checkout broken", { response: broken });
  expect(broken.available_tags).toEqual(expect.arrayContaining(["1.4.0", "1.5.0"]));
  const deployed = Date.parse(broken.container.started_at);
  timings.broken_started_at = broken.container.started_at;

  // 3. The inbox polls on its own every 15 s; the card must be there within a minute.
  await expect(card).toBeVisible({ timeout: Math.max(1_000, deployed + 60_000 - Date.now()) });
  timings.seconds_to_inbox = (Date.now() - deployed) / 1000;
  await card.click();
  await page.screenshot({ path: `${ARTIFACTS}/inbox-firing.png`, fullPage: true });
  const firing = note("alerts firing", { body: await alerts() });
  expect(ours(firing.body)).toEqual([expect.objectContaining({ service: SERVICE, severity: "sev2", status: "new" })]);
  expect(firing.body.rules.find((rule) => rule.rule_id === "checkout-payment-error-rate").state).not.toBe("firing");

  // 4. Rollback through the executor, signed as #722 will sign it.
  const key = randomUUID();
  const data = JSON.stringify({ service: SERVICE, to_tag: "1.4.0" });
  const response = await executor.fetch(`${EXECUTOR}${ROLLBACK}`, {
    method: "POST",
    headers: { "content-type": "application/json", "idempotency-key": key, ...signature("POST", ROLLBACK, key, data) },
    data,
  });
  const rollback = note("rollback 1.4.0", { status: response.status(), body: await response.json() });
  expect(rollback.status).toBe(200);
  expect(rollback.body).toMatchObject({ outcome: "rolled_back", before: { image: "demo/checkout:1.5.0" }, after: { image: "demo/checkout:1.4.0", state: "running" } });
  const rolledBack = Date.now();
  timings.rolled_back_at = new Date(rolledBack).toISOString();

  // 5. Once the window holds only the healthy release the rule is `ok` and the episode closes.
  await expect(card).toHaveCount(0, { timeout: 180_000 });
  timings.seconds_to_close = (Date.now() - rolledBack) / 1000;
  const after = note("alerts after rollback", { body: await alerts() });
  expect(after.body.rules.find((rule) => rule.rule_id === RULE).state).toBe("ok");
  expect(ours(after.body)).toEqual([]);
  await page.screenshot({ path: `${ARTIFACTS}/inbox-recovered.png`, fullPage: true });
  note("checkout after", { response: await checkout() });
  await page.goto(`${EXECUTOR}/v1/services/${SERVICE}`);
  await page.screenshot({ path: `${ARTIFACTS}/service-after-rollback.png`, fullPage: true });
  test.info().annotations.push({ type: "timings", description: JSON.stringify(timings) });
  expect(timings.seconds_to_inbox).toBeLessThan(60);
});
