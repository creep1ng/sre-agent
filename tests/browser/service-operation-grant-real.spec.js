import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { expect, request, test } from "@playwright/test";

// Who may run an enrolled service operation (#722, first cut), against the REAL stack (web proxy,
// FastAPI, PostgreSQL) after scripts/provision_demo.py; nothing is mocked. Ways this can fail:
// 1. setup leaves incident-harness without mitigation.execute on sre-checkout:deployment.rollback,
//    so approving the demo's rollback would be denied;
// 2. setup gives the agent more than that: sre-checkout:deployment.restart stays an enrolled
//    resource the agent may not run, the denial case of the approval cut; or it catalogs an
//    operation of the store's `checkout`, which has no catalog (#722);
// 3. the console offers another action on a service operation;
// 4. a grant naming an operation outside the catalog, or an action the type does not admit, is
//    stored instead of refused;
// 5. a revoked authority comes back by itself, or cannot be granted again (#759): granting it
//    again is a new active grant (201), a duplicate active grant answers 409 grant_conflict and
//    reusing the revoked grant's id answers 409 grant_id_conflict.
const ADMIN_KEY = process.env.ADMIN_HUMAN_API_KEY ?? "";
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://web";
const ARTIFACTS = process.env.SERVICE_OPERATION_ARTIFACT_DIR ?? "";
const REAL = process.env.SERVICE_OPERATION_E2E === "1" && Boolean(ADMIN_KEY);
const ROLLBACK = "sre-checkout:deployment.rollback";
const RESTART = "sre-checkout:deployment.restart";
// A principal of its own per run: the spec revokes and grants again only its own authority,
// never the demo's.
const STAMP = Date.now().toString(36);
const PROBE = `operation-probe-${STAMP}`;
const transcript = [];
let api;

test.skip(!REAL, "requires SERVICE_OPERATION_E2E=1 and the admin key");
test.describe.configure({ mode: "serial" });

test.beforeAll(async () => {
  api = await request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${ADMIN_KEY}` } });
  const created = await call("POST", "/v1/principals", {
    principal_id: PROBE,
    kind: "agent",
    display_name: "Operation probe",
  });
  expect(created.status).toBe(201);
});

test.afterAll(async () => {
  await api?.dispose();
  if (ARTIFACTS) {
    mkdirSync(ARTIFACTS, { recursive: true });
    writeFileSync(join(ARTIFACTS, "transcript.json"), `${JSON.stringify(transcript, null, 2)}\n`);
  }
});

// Every API call the spec makes, with its status and body; headers and keys are never kept.
async function call(method, path, data) {
  const headers = data ? { "idempotency-key": `service-operation-e2e-${STAMP}-${transcript.length}` } : {};
  const response = await api.fetch(`${BASE}/api${path}`, { method, data, headers });
  const body = await response.json().catch(() => null);
  transcript.push({ method, path, ...(data ? { request: data } : {}), status: response.status(), response: body });
  return { status: response.status(), body };
}

function grant(id, action, resourceId) {
  return {
    grant_id: id,
    principal_id: PROBE,
    action,
    resource: { resource_type: "service_operation", resource_id: resourceId },
    effect: "allow",
  };
}

// The console's Permissions page (/app/admin/permisos), in Spanish, connected with the admin key.
async function connect(page) {
  await page.addInitScript(() =>
    localStorage.setItem("midnight-language", JSON.stringify({ state: { language: "es" }, version: 0 })),
  );
  await page.goto("/app/admin/permisos");
  await page.getByRole("button", { name: "Conectar con la API" }).click();
  await page.locator("#api-key").fill(ADMIN_KEY);
  await page.locator("#api-key").press("Enter");
  await expect(page.getByRole("button", { name: "Conceder permiso" })).toBeEnabled();
}

async function capture(page, name) {
  if (!ARTIFACTS) return;
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await page.screenshot({ path: join(ARTIFACTS, name), fullPage: true });
}

test("setup lets the agent roll sre-checkout back, and nothing else", async ({ page }) => {
  const agent = await call("GET", "/v1/grants?principal_id=incident-harness");
  expect(agent.status).toBe(200);
  // On sre-checkout the agent may only roll back. Other services' operations (the OTel demo's
  // flag.set on payment and checkout, #724) are setup grants of their own and not this case.
  const sreCheckout = (item) => item.resource_id.startsWith("sre-checkout:");
  const operations = agent.body.items.filter(
    (item) => item.resource.resource_type === "service_operation" && sreCheckout(item.resource),
  );
  expect(operations.map((item) => [item.action, item.resource.resource_id, item.status])).toEqual([
    ["mitigation.execute", ROLLBACK, "active"],
  ]);
  const catalog = await call("GET", "/v1/catalog/resources?resource_type=service_operation&limit=100");
  expect(catalog.status).toBe(200);
  expect(catalog.body.items.filter(sreCheckout).map((item) => [item.resource_id, item.status]).sort()).toEqual([
    [RESTART, "active"],
    [ROLLBACK, "active"],
  ]);
  await connect(page);
  await page.selectOption("#grants-principal", "incident-harness");
  const row = page.locator("[data-grant-row]", { hasText: ROLLBACK });
  await expect(row).toContainText("mitigation.execute");
  await expect(row).toContainText("Activo");
  await capture(page, "agent-grant.png");
});

test("the console offers only mitigation.execute, and a revoked grant is granted again anew", async ({ page }) => {
  await connect(page);
  await page.getByRole("button", { name: "Conceder permiso" }).click();
  await page.selectOption("#grant-resource", `service_operation/${RESTART}`);
  const actions = await page
    .locator("#grant-action option")
    .evaluateAll((options) => options.map((option) => option.value).filter(Boolean));
  expect(actions).toEqual(["mitigation.execute"]);
  await page.fill("#grant-id", `grant-${PROBE}`);
  await page.selectOption("#grant-principal", PROBE);
  await page.selectOption("#grant-action", "mitigation.execute");
  await page.getByRole("button", { name: "Conceder", exact: true }).click();
  const row = page.locator(`[data-grant-row='grant-${PROBE}']`);
  await expect(row).toContainText(RESTART);
  await expect(row).toContainText("Activo");
  await row.getByRole("button", { name: `Revocar grant-${PROBE}` }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Revocar" }).click();
  await expect(row).toContainText("Revocado");
  await capture(page, "probe-revoked.png");
  const again = await call("POST", "/v1/grants", grant(`grant-${PROBE}-again`, "mitigation.execute", RESTART));
  expect(again.status).toBe(201);
  const duplicate = await call("POST", "/v1/grants", grant(`grant-${PROBE}-twice`, "mitigation.execute", RESTART));
  const reused = await call("POST", "/v1/grants", grant(`grant-${PROBE}`, "mitigation.execute", RESTART));
  expect([duplicate, reused].map(({ status, body }) => [status, body?.error?.code])).toEqual([
    [409, "grant_conflict"],
    [409, "grant_id_conflict"],
  ]);
  const probe = await call("GET", `/v1/grants?principal_id=${PROBE}`);
  expect(probe.body.items.map((item) => [item.grant_id, item.status]).sort()).toEqual([
    [`grant-${PROBE}`, "revoked"],
    [`grant-${PROBE}-again`, "active"],
  ]);
});

test("an operation outside the catalog, or another action on one, is refused", async () => {
  const outside = await call(
    "POST",
    "/v1/grants",
    grant(`grant-${PROBE}-scale`, "mitigation.execute", "sre-checkout:deployment.scale"),
  );
  expect(outside.status).toBe(404);
  const foreign = await call("POST", "/v1/grants", grant(`grant-${PROBE}-approve`, "run.approve", ROLLBACK));
  expect(foreign.status).toBe(422);
  const stored = await call("GET", `/v1/grants?principal_id=${PROBE}`);
  expect(stored.status).toBe(200);
  const ids = stored.body.items.map((item) => item.grant_id);
  expect(ids).not.toContain(`grant-${PROBE}-scale`);
  expect(ids).not.toContain(`grant-${PROBE}-approve`);
});
