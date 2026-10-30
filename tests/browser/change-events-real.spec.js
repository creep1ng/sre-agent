import { expect, request, test } from "@playwright/test";
import { spawnSync } from "node:child_process";
import { createHash, createHmac, randomBytes, randomUUID } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";

// Issue #770 against the REAL stack: FastAPI and PostgreSQL behind the web proxy, fed by the
// reusable GitHub Actions step's own script (.github/actions/record-change/record_change.py)
// after a deploy and after a red CI run. Ways this can fail:
// 1. an integration credential with only change.write cannot record a deploy, or the stored
//    event loses its service, version, commit, author, ref, link or time;
// 2. resending the same run (the step retries, or a job runs it twice) adds a second event, or
//    the same key with another payload is answered "already recorded" and silently dropped;
// 3. a red CI run on main is refused, stored as a success, or needs more than change.write;
// 4. the integration key can read the history, or a reader without change.write can write;
// 5. the history is not newest first, or holds events of another service;
// 6. an event dated well in the future is stored and stays first in every history;
// 7. a rollback through the deploy-executor leaves no change event, or one without its image.
const ENABLED = process.env.SRE_REAL_BACKEND === "1";
const ADMIN_KEY = process.env.ADMIN_HUMAN_API_KEY ?? "";
const DEMO_KEY = process.env.DEMO_HUMAN_API_KEY ?? "";
const STAMP = process.env.SEED_STAMP ?? randomBytes(5).toString("hex");
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://web";
const ARTIFACTS = process.env.CHANGE_EVENTS_ARTIFACT_DIR ?? "/artifacts/change-events";
const ACTION = process.env.RECORD_CHANGE_SCRIPT ?? "/e2e/actions/record-change/record_change.py";
const SERVICE = "sre-checkout";
const WORKFLOW = { resource_type: "incident_workflow", resource_id: "incident-response" };

// The rollback case runs in executor-e2e, with the executor holding a change.write credential.
const EXECUTOR_CHANGES = process.env.DEPLOY_EXECUTOR_CHANGES_E2E === "1";
const EXECUTOR = process.env.DEPLOY_EXECUTOR_URL ?? "http://deploy-executor:8000";
const SIGNING_KEY = process.env.DEPLOY_EXECUTOR_SIGNING_KEY ?? "";

const transcript = [];
const note = (step, data) => (transcript.push({ step, at: new Date().toISOString(), ...data }), data);
test.afterEach(({}, testInfo) => {
  // A skipped case (the other runner's, or outside the stack) writes nothing: /artifacts may not exist.
  if (testInfo.status === "skipped") return;
  mkdirSync(ARTIFACTS, { recursive: true });
  writeFileSync(`${ARTIFACTS}/transcript.json`, JSON.stringify(transcript, null, 2));
});

// One job of a workflow run, as the GitHub step keys it (action.yml): run, attempt, job and kind.
const runEvent = (run, extra) => {
  const event = { source: "github-actions", service: SERVICE, kind: "deploy", ...extra };
  return {
    external_id: `creep1ng/sre-agent/actions/runs/${run}/attempts/1/jobs/${event.kind === "ci" ? "test" : "release"}/${event.kind}`,
    commit_sha: createHash("sha1").update(run).digest("hex"),
    ref: "main",
    author: "octo-dev",
    url: `https://github.com/creep1ng/sre-agent/actions/runs/${run}`,
    ...event,
  };
};

// What the GitHub step does: its own script, with the env that action.yml gives it.
function send(key, run, extra = {}) {
  const event = runEvent(run, extra);
  const env = {
    PATH: process.env.PATH,
    MIDNIGHT_URL: `${BASE}/api`,
    MIDNIGHT_API_KEY: key,
    FAIL_ON_ERROR: "true",
    CHANGE_SOURCE: event.source,
    CHANGE_EXTERNAL_ID: event.external_id,
    CHANGE_SERVICE: event.service,
    CHANGE_KIND: event.kind,
    CHANGE_STATUS: event.status ?? "",
    CHANGE_VERSION: event.version ?? "",
    CHANGE_COMMIT: event.commit_sha,
    CHANGE_REF: event.ref,
    CHANGE_AUTHOR: event.author,
    CHANGE_URL: event.url,
  };
  const step = spawnSync("python3", [ACTION], { env, encoding: "utf8" });
  const output = `${step.stdout}${step.stderr}`.trim();
  const [, state, change_id, status] = output.match(/(already recorded|recorded) (chg_[0-9a-f]{16}) \((\d{3})\)/) ?? [];
  return { status: Number(status ?? output.match(/answered (\d{3})/)?.[1]), change_id, created: state && state === "recorded" };
}

test("a deploy and a red CI run are recorded once each and read back newest first", async ({ browser }) => {
  test.skip(!ENABLED || !ADMIN_KEY || !DEMO_KEY, "requires SRE_REAL_BACKEND=1 and the seeded keys inside the Compose stack");
  const started = new Date(Date.now() - 1_000).toISOString();
  const admin = await request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${ADMIN_KEY}` } });
  const reader = await request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${DEMO_KEY}` } });
  const control = async (path, data) => {
    const response = await admin.post(`${BASE}/api${path}`, { data, headers: { "idempotency-key": randomUUID() } });
    expect(response.status(), `${path}: ${await response.text()}`).toBe(201);
    return response.json();
  };

  // The integration: an agent principal with a credential and change.write only; demo-human
  // reads with the change.read grant of scripts/provision_demo.py.
  const integration = `gha-checkout-${STAMP}`;
  await control("/v1/principals", { principal_id: integration, kind: "agent", display_name: "GitHub Actions sre-checkout" });
  const { key } = await control(`/v1/principals/${integration}/credentials`, {});
  await control("/v1/grants", { grant_id: `grant-${integration}-change-write`, principal_id: integration, action: "change.write", resource: WORKFLOW, effect: "allow" });

  // 1. The deploy of the broken release, then the same run sent again.
  const deployRun = `${Date.now()}1`;
  const deploy = { version: "demo/checkout:1.5.0" };
  const first = note("deploy", send(key, deployRun, deploy));
  expect(first).toMatchObject({ status: 201, created: true, change_id: expect.stringMatching(/^chg_[0-9a-f]{16}$/) });
  const resent = note("deploy resent", send(key, deployRun, deploy));
  expect(resent).toEqual({ ...first, status: 200, created: false });
  const clash = note("deploy resent with another version", send(key, deployRun, { version: "demo/checkout:1.6.0" }));
  expect(clash.status).toBe(409);
  const writer = await request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${key}` } });
  const ahead = runEvent(`${Date.now()}4`, { occurred_at: new Date(Date.now() + 10 * 60_000).toISOString() });
  expect(note("dated 10 min ahead", { status: (await writer.post(`${BASE}/api/v1/changes`, { data: ahead })).status() }).status).toBe(422);

  // 2. A red CI job on main in the same run (post-deploy checks): its own failed change, not
  // "already recorded" under the deploy's key, with the same credential.
  const ci = note("ci failed", send(key, deployRun, { kind: "ci", status: "failed" }));
  expect(ci).toMatchObject({ status: 201, created: true });

  // 3. Each side holds one action only.
  const integrationRead = await request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${key}` } });
  const denied = note("integration reads", { status: (await integrationRead.get(`${BASE}/api/v1/changes`)).status() });
  expect(denied.status).toBe(403);
  expect(note("reader writes", send(DEMO_KEY, `${Date.now()}3`)).status).toBe(403);

  // 4. The history of sre-checkout since this test began: two events, newest first.
  const query = `service=${SERVICE}&since=${encodeURIComponent(started)}`;
  const history = note("history", { body: await (await reader.get(`${BASE}/api/v1/changes?${query}`)).json() });
  expect(history.body.changes).toEqual([
    expect.objectContaining({ change_id: ci.change_id, kind: "ci", status: "failed", ref: "main", recorded_by: integration }),
    expect.objectContaining({
      change_id: first.change_id,
      source: "github-actions",
      service: SERVICE,
      kind: "deploy",
      status: "succeeded",
      version: "demo/checkout:1.5.0",
      commit_sha: createHash("sha1").update(deployRun).digest("hex"),
      author: "octo-dev",
      ref: "main",
      url: `https://github.com/creep1ng/sre-agent/actions/runs/${deployRun}`,
      occurred_at: expect.stringMatching(/Z$/),
    }),
  ]);

  // The same read in a browser, as the evidence screenshot.
  const context = await browser.newContext({ extraHTTPHeaders: { authorization: `Bearer ${DEMO_KEY}` } });
  const page = await context.newPage();
  await page.goto(`${BASE}/api/v1/changes?${query}`);
  await expect(page.locator("body")).toContainText("demo/checkout:1.5.0");
  mkdirSync(ARTIFACTS, { recursive: true });
  await page.screenshot({ path: `${ARTIFACTS}/history.png`, fullPage: true });
});

test("a rollback through the deploy-executor records its own change", async ({ browser }) => {
  test.skip(!EXECUTOR_CHANGES || !DEMO_KEY || !SIGNING_KEY, "requires DEPLOY_EXECUTOR_CHANGES_E2E=1, the executor and its keys");
  test.setTimeout(300_000);
  const executor = await request.newContext();
  const reader = await request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${DEMO_KEY}` } });
  // Signed as the gateway signs it (#743): method, path, key, sha256(body), timestamp.
  const rollback = async (tag) => {
    const path = "/v1/operations/deployment.rollback";
    const key = randomUUID();
    const data = JSON.stringify({ service: "probe", to_tag: tag });
    const timestamp = String(Math.floor(Date.now() / 1000));
    const digest = createHash("sha256").update(data).digest("hex");
    const mac = createHmac("sha256", SIGNING_KEY).update(["POST", path, key, digest, timestamp].join("\n")).digest("hex");
    const headers = { "content-type": "application/json", "idempotency-key": key, "x-executor-timestamp": timestamp, "x-executor-signature": `v1=${mac}` };
    const response = await executor.fetch(`${EXECUTOR}${path}`, { method: "POST", headers, data });
    return note(`rollback ${tag}`, { status: response.status(), body: await response.json() });
  };
  const done = await rollback("1.0.0");
  expect(done).toMatchObject({ status: 200, body: { outcome: "rolled_back", after: { image: "demo/probe:1.0.0" } } });
  // The executor records it after answering, so the event may land a moment later.
  const recorded = async () => (await (await reader.get(`${BASE}/api/v1/changes?service=probe&limit=5`)).json()).changes ?? [];
  await expect.poll(async () => (await recorded()).map((change) => change.external_id), { timeout: 15_000 }).toContain(done.body.execution_id);
  const history = note("probe history", { changes: await recorded() });
  expect(history.changes.find((change) => change.external_id === done.body.execution_id)).toMatchObject({
    source: "deploy-executor", kind: "rollback", status: "succeeded", version: "demo/probe:1.0.0", recorded_by: "deploy-executor",
  });
  const page = await (await browser.newContext({ extraHTTPHeaders: { authorization: `Bearer ${DEMO_KEY}` } })).newPage();
  await page.goto(`${BASE}/api/v1/changes?service=probe&limit=1`);
  await expect(page.locator("body")).toContainText(done.body.execution_id);
  mkdirSync(ARTIFACTS, { recursive: true });
  await page.screenshot({ path: `${ARTIFACTS}/executor-rollback.png`, fullPage: true });
  // Leave the probe on the release the executor journey expects.
  expect((await rollback("1.1.0")).status).toBe(200);
});
