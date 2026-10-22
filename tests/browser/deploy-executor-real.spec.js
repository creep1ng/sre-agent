import { expect, request, test } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";

// Issue #720 against the REAL deploy-executor, docker-socket-proxy and Docker Engine inside
// Compose, with demo/probe:1.1.0 running and demo/probe:1.0.0 in the image store. Ways this
// can fail, written before the runtime (schemas/executor/1.0.0/deploy-executor.yaml):
// 1. a negative fixture is not rejected with its status and error code, or it touches the probe;
// 2. the proxy answers anything but 403 outside the containers and images families;
// 3. the rollback leaves the probe on the old image, or the probe does not answer its new version;
// 4. the same key sent twice executes twice, or a key reused with another payload is accepted;
// 5. a rollback to the running tag moves the container; a restart changes the container id;
// 6. the journal does not list the executions.
const ENABLED = process.env.DEPLOY_EXECUTOR_E2E === "1";
const EXECUTOR = process.env.DEPLOY_EXECUTOR_URL ?? "http://deploy-executor:8000";
const PROXY = process.env.DOCKER_SOCKET_PROXY_URL ?? "http://docker-socket-proxy:2375";
const PROBE = process.env.PROBE_URL ?? "http://probe:8080";
const ARTIFACTS = process.env.DEPLOY_EXECUTOR_ARTIFACT_DIR ?? "test-results/issue-720";
const FIXTURES = "schemas/executor/1.0.0/fixtures/negative";
const DENIED_FAMILIES = ["/info", "/networks", "/volumes", "/version", "/events", "/exec/any/start"];

test.skip(!ENABLED, "requires DEPLOY_EXECUTOR_E2E=1 inside the Compose stack");

const transcript = [];
async function call(api, method, url, { key, body } = {}) {
  const headers = { "content-type": "application/json", ...(key ? { "idempotency-key": key } : {}) };
  const response = await api.fetch(url, { method, headers, data: body === undefined ? undefined : JSON.stringify(body) });
  const text = await response.text();
  let parsed;
  try { parsed = JSON.parse(text); } catch { parsed = text; }
  return { status: response.status(), body: parsed };
}
function note(step, request_, response) {
  transcript.push({ step, at: new Date().toISOString(), request: request_, response });
  return response;
}
const untouched = (a, b) => ["container_id", "image", "started_at"].every((f) => a.container[f] === b.container[f]);

test("rollback and restart run once per key, rejections touch nothing, the proxy denies the rest", async ({ page }) => {
  test.setTimeout(300_000);
  mkdirSync(ARTIFACTS, { recursive: true });
  const api = await request.newContext();
  const executor = (method, path, options) => call(api, method, `${EXECUTOR}${path}`, options);
  const probeVersion = async () => (await call(api, "GET", `${PROBE}/`)).body.version;

  expect(note("ready", "GET /health/ready", await executor("GET", "/health/ready")).status).toBe(200);
  const catalog = note("catalog", "GET /v1/catalog", await executor("GET", "/v1/catalog")).body;
  expect(catalog.services.map((s) => [s.service, s.operations.map((o) => o.operation)])).toEqual([
    ["probe", ["deployment.restart", "deployment.rollback"]],
    ["web", ["deployment.restart"]],
  ]);
  const before = note("probe before", "GET /v1/services/probe", await executor("GET", "/v1/services/probe")).body;
  expect(before.container.image).toBe("demo/probe:1.1.0");
  expect(before.container.state).toBe("running");
  expect(before.available_tags).toEqual(expect.arrayContaining(["1.0.0", "1.1.0"]));
  expect(await probeVersion()).toBe("1.1.0");
  await page.goto(`${EXECUTOR}/v1/services/probe`);
  await page.screenshot({ path: `${ARTIFACTS}/service-before.png`, fullPage: true });

  // 2. The proxy forwards only the containers and images families.
  for (const path of DENIED_FAMILIES) {
    const method = path.endsWith("/start") ? "POST" : "GET";
    expect(note("proxy denies", `${method} ${path}`, await call(api, method, `${PROXY}${path}`)).status, path).toBe(403);
  }
  expect(note("proxy allows", "GET /containers/json", await call(api, "GET", `${PROXY}/containers/json`)).status).toBe(200);
  expect(note("proxy allows", "GET /images/json", await call(api, "GET", `${PROXY}/images/json`)).status).toBe(200);
  await page.goto(`${PROXY}/info`);
  await page.screenshot({ path: `${ARTIFACTS}/proxy-denies-info.png` });

  // 1. Every negative fixture of the contract, then the probe is exactly as it was.
  const fixtures = readdirSync(FIXTURES).sort().map((name) => JSON.parse(readFileSync(`${FIXTURES}/${name}`, "utf8")));
  const rollbackKey = randomUUID();
  for (const { scenario_id, data } of fixtures) {
    if (data.request.idempotency_key === "previous") continue; // needs the rollback below first
    const key = data.request.idempotency_key === "fresh" ? randomUUID() : undefined;
    const response = note(`fixture ${scenario_id}`, data.request, await executor(data.request.method, data.request.path, { key, body: data.request.body }));
    expect(response.status, scenario_id).toBe(data.expected.status);
    expect(response.body.error.code, scenario_id).toBe(data.expected.error_code);
  }
  expect(untouched(before, (await executor("GET", "/v1/services/probe")).body), "rejections touched the probe").toBe(true);

  // 3. The rollback replaces the container and the probe answers its old version.
  const rollback = note("rollback 1.0.0", "POST deployment.rollback", await executor("POST", "/v1/operations/deployment.rollback", { key: rollbackKey, body: { service: "probe", to_tag: "1.0.0" } }));
  expect(rollback.status).toBe(200);
  expect(rollback.body).toMatchObject({ outcome: "rolled_back", replayed: false, before: { image: "demo/probe:1.1.0" }, after: { image: "demo/probe:1.0.0", state: "running" } });
  expect(rollback.body.after.container_id).not.toBe(before.container.container_id);
  await expect.poll(probeVersion, { timeout: 15_000 }).toBe("1.0.0");
  await page.goto(`${PROBE}/`);
  await page.screenshot({ path: `${ARTIFACTS}/probe-after-rollback.png` });

  // 4. Same key: replayed, not re-executed. Same key, other payload: conflict.
  const replay = note("rollback replay", "POST deployment.rollback (same key)", await executor("POST", "/v1/operations/deployment.rollback", { key: rollbackKey, body: { service: "probe", to_tag: "1.0.0" } }));
  expect(replay.body).toMatchObject({ execution_id: rollback.body.execution_id, replayed: true });
  const afterRollback = (await executor("GET", "/v1/services/probe")).body;
  expect(afterRollback.container.container_id).toBe(rollback.body.after.container_id);
  const reused = fixtures.find((f) => f.data.request.idempotency_key === "previous").data;
  const conflict = note("fixture key-reused-with-other-payload", reused.request, await executor(reused.request.method, reused.request.path, { key: rollbackKey, body: reused.request.body }));
  expect(conflict.status).toBe(reused.expected.status);
  expect(conflict.body.error.code).toBe(reused.expected.error_code);

  // 5. Idempotent by state: the running tag is a no-op. A restart keeps the container.
  const again = note("rollback 1.0.0 again", "POST deployment.rollback (new key)", await executor("POST", "/v1/operations/deployment.rollback", { key: randomUUID(), body: { service: "probe", to_tag: "1.0.0" } }));
  expect(again.body.outcome).toBe("already_at_target");
  expect(untouched(afterRollback, (await executor("GET", "/v1/services/probe")).body)).toBe(true);
  const restartKey = randomUUID();
  const restart = note("restart", "POST deployment.restart", await executor("POST", "/v1/operations/deployment.restart", { key: restartKey, body: { service: "probe" } }));
  expect(restart.body).toMatchObject({ outcome: "restarted", after: { container_id: afterRollback.container.container_id, state: "running" } });
  expect(restart.body.after.started_at > restart.body.before.started_at).toBe(true);
  const restartReplay = note("restart replay", "POST deployment.restart (same key)", await executor("POST", "/v1/operations/deployment.restart", { key: restartKey, body: { service: "probe" } }));
  expect(restartReplay.body).toMatchObject({ execution_id: restart.body.execution_id, replayed: true });
  expect((await executor("GET", "/v1/services/probe")).body.container.started_at).toBe(restart.body.after.started_at);

  // Roll forward, so the stack is left as found and the journey repeats.
  const forward = note("rollback 1.1.0", "POST deployment.rollback", await executor("POST", "/v1/operations/deployment.rollback", { key: randomUUID(), body: { service: "probe", to_tag: "1.1.0" } }));
  expect(forward.body).toMatchObject({ outcome: "rolled_back", after: { image: "demo/probe:1.1.0" } });
  await expect.poll(probeVersion, { timeout: 15_000 }).toBe("1.1.0");

  // 6. The journal lists what ran, in order.
  const executions = note("executions", "GET /v1/executions", await executor("GET", "/v1/executions")).body.executions;
  const ran = [rollback, again, restart, forward].map((r) => r.body.execution_id);
  expect(executions.filter((e) => ran.includes(e.execution_id)).map((e) => e.outcome)).toEqual(["rolled_back", "already_at_target", "restarted", "rolled_back"]);
  await page.goto(`${EXECUTOR}/v1/executions`);
  await page.screenshot({ path: `${ARTIFACTS}/executions.png`, fullPage: true });
  writeFileSync(`${ARTIFACTS}/transcript.json`, JSON.stringify(transcript, null, 2));
  test.info().annotations.push({ type: "executions", description: ran.join(",") });
});

// Socket down: run after `docker compose stop docker-socket-proxy`.
test("with the socket proxy stopped, readiness and operations answer 503 and nothing runs", async () => {
  test.skip(process.env.DEPLOY_EXECUTOR_SOCKET_DOWN !== "1", "requires DEPLOY_EXECUTOR_SOCKET_DOWN=1");
  mkdirSync(ARTIFACTS, { recursive: true });
  const api = await request.newContext();
  const steps = [];
  const ready = await call(api, "GET", `${EXECUTOR}/health/ready`);
  steps.push({ step: "ready", response: ready });
  expect(ready.status).toBe(503);
  const rollback = await call(api, "POST", `${EXECUTOR}/v1/operations/deployment.rollback`, { key: randomUUID(), body: { service: "probe", to_tag: "1.0.0" } });
  steps.push({ step: "rollback", response: rollback });
  expect(rollback.status).toBe(503);
  expect(rollback.body.error.code).toBe("docker_unavailable");
  writeFileSync(`${ARTIFACTS}/socket-down.json`, JSON.stringify(steps, null, 2));
});
