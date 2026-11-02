import { expect, request, test } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";

// GET /v1/incidents (#870) against the REAL stack: the web proxy, FastAPI and PostgreSQL. The
// incidents come from scripts/seed_verification_close_demo.py through the real runtime:
// inc-vc-<SEED_STAMP> waits for a mitigation decision and inc-vc-<RESOLVED_STAMP> was approved
// and verified over HTTP (scripts/run_real_journeys.sh). Ways this can fail, written first:
// 1. a caller without a key, or without run.read, gets rows instead of 401/403;
// 2. the incident awaiting approval is missing from `open`, or its row does not say which run
//    waits, for what, since when, and with which incident version a command must be sent;
// 3. the row leaks the mitigation's words, which only run.read_context may read;
// 4. the incident version in the row is not one the command endpoint accepts, or the row still
//    reports a pending decision once the human has decided;
// 5. a recovered incident reports a pending decision, or its latest run loses its ending cause;
// 6. bad parameters are guessed instead of refused, or `since` keeps older incidents.
const STAMP = process.env.SEED_STAMP ?? "";
const RESOLVED = process.env.RESOLVED_STAMP ?? "";
const DEMO_KEY = process.env.DEMO_HUMAN_API_KEY ?? "";
const ADMIN_KEY = process.env.ADMIN_HUMAN_API_KEY ?? "";
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://web";
const ARTIFACTS = process.env.INCIDENT_LIST_ARTIFACT_DIR ?? "/artifacts/incident-list";
const REAL = process.env.SRE_REAL_BACKEND === "1" && Boolean(DEMO_KEY && ADMIN_KEY && STAMP && RESOLVED);
const PENDING = `inc-vc-${STAMP}`;
const RUN = `run_vc${STAMP.replaceAll("-", "")}`;
const DONE = `inc-vc-${RESOLVED}`;
const MITIGATION_TEXT = "Turn the paymentFailure feature flag off.";

test.skip(!REAL, "requires SRE_REAL_BACKEND=1, demo/admin keys, SEED_STAMP and RESOLVED_STAMP");
test.describe.configure({ mode: "serial" });

const transcript = [];
test.afterAll(() => {
  mkdirSync(ARTIFACTS, { recursive: true });
  writeFileSync(`${ARTIFACTS}/transcript.json`, JSON.stringify(transcript, null, 2));
});

async function list(key, query) {
  const headers = key ? { authorization: `Bearer ${key}` } : {};
  const api = await request.newContext({ extraHTTPHeaders: headers });
  const response = await api.get(`${BASE}/api/v1/incidents${query}`);
  const body = await response.json();
  transcript.push({ query: `GET /v1/incidents${query}`, status: response.status(), body });
  return { status: response.status(), body };
}

const row = (body, id) => body.incidents?.find((item) => item.incident_id === id);

test("callers without a key or without run.read read no incident", async () => {
  expect((await list("", "?status=open")).status).toBe(401);
  // A human with a credential and no grant, created through the governed API.
  const admin = await request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${ADMIN_KEY}` } });
  const id = `list-stranger-${STAMP}`;
  const post = (path, data) => admin.post(`${BASE}/api${path}`, { data, headers: { "idempotency-key": randomUUID() } });
  expect((await post("/v1/principals", { principal_id: id, kind: "human", display_name: "Stranger" })).status()).toBe(201);
  const issued = await post(`/v1/principals/${id}/credentials`, { expires_at: "2031-01-01T00:00:00Z" });
  const denied = await list((await issued.json()).key, "?status=open");
  expect(denied.status).toBe(403);
  expect(denied.body.incidents).toBeUndefined();
});

test("the incident awaiting approval leads with its pending decision, without the proposal's words", async () => {
  const { status, body } = await list(DEMO_KEY, "?status=open&limit=100");
  expect(status).toBe(200);
  const pending = row(body, PENDING);
  expect(pending).toMatchObject({
    state: "mitigating",
    severity: "sev2",
    service: "paymentservice",
    summary: "Elevated error rate on paymentservice.",
    impact: "Checkout failing at payment.",
    latest_run: { run_id: RUN, status: "awaiting_human", pending_command: "approve_mitigation" },
    pending_decision: {
      command: "approve_mitigation",
      run_id: RUN,
      incident_version: pending?.version,
      mitigation_id: "mit_disable_payment_flag",
    },
  });
  expect(Date.parse(pending.pending_decision.waiting_since)).not.toBeNaN();
  expect(JSON.stringify(body)).not.toContain(MITIGATION_TEXT);
  // Most recently updated first.
  const times = body.incidents.map((item) => Date.parse(item.updated_at));
  expect(times).toEqual([...times].sort((a, b) => b - a));
});

test("a recovered incident is listed with its ending, and no decision", async () => {
  const { body } = await list(DEMO_KEY, "?status=recent&limit=100");
  expect(row(body, DONE)).toMatchObject({
    state: "resolved",
    pending_decision: null,
    latest_run: { status: "running", terminated_reason: null },
  });
});

test("the row's incident version is the one the decision command accepts", async () => {
  const before = row((await list(DEMO_KEY, "?status=open&limit=100")).body, PENDING);
  const api = await request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${DEMO_KEY}` } });
  const sent = await api.post(`${BASE}/api/v1/incidents/${PENDING}/runs/${RUN}/commands`, {
    headers: { "idempotency-key": `list-approve-${STAMP}-0001` },
    data: {
      command: "approve_mitigation",
      expected_incident_version: before.pending_decision.incident_version,
      actor: "human",
      actor_reference: { reference_version: "1.0.0", principal_id: "demo-human" },
    },
  });
  transcript.push({ command: "approve_mitigation", status: sent.status() });
  expect(sent.status()).toBe(202);
  let after;
  await expect
    .poll(async () => (after = row((await list(DEMO_KEY, "?status=open&limit=100")).body, PENDING))?.state, { timeout: 30_000 })
    .toBe("verifying");
  expect(after.pending_decision).toBeNull();
  expect(after.version).toBeGreaterThan(before.version);
});

test("bad parameters are refused and since leaves older incidents out", async () => {
  for (const query of ["?status=closed", "?limit=0", "?limit=101", "?since=2026-10-31T00:00:00", "?since=yesterday"]) {
    expect((await list(DEMO_KEY, query)).status, query).toBe(422);
  }
  const ahead = encodeURIComponent(new Date(Date.now() + 60 * 60_000).toISOString());
  expect((await list(DEMO_KEY, `?since=${ahead}`)).body).toEqual({ incidents: [], has_more: false });
  const page = await list(DEMO_KEY, "?status=recent&limit=1");
  expect(page.body.incidents).toHaveLength(1);
  expect(page.body.has_more).toBe(true);
});
