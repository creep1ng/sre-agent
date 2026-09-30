import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { createServer as createNetServer } from "node:net";
import { mkdtemp, symlink, rm } from "node:fs/promises";
import { once } from "node:events";
import { join, resolve } from "node:path";
import test from "node:test";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

const SCRIPT = resolve(fileURLToPath(new URL("../scripts/demo_mcp_probe.mjs", import.meta.url)));
const PRIVATE_MARKER = "service-ip-private-response-marker";
const BASE_ENV = { PATH: process.env.PATH };

function runCli(overrides = {}, script = SCRIPT) {
  return new Promise((resolveRun, rejectRun) => {
    const child = spawn(process.execPath, [script], {
      env: { ...BASE_ENV, ...overrides },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8").on("data", (chunk) => { stdout += chunk; });
    child.stderr.setEncoding("utf8").on("data", (chunk) => { stderr += chunk; });
    const timeout = setTimeout(() => child.kill("SIGKILL"), 20_000);
    child.on("error", rejectRun);
    child.on("close", (status) => {
      clearTimeout(timeout);
      resolveRun({ status, stdout, stderr });
    });
  });
}

test("CLI invocation through a symlink still emits a bounded report", async (t) => {
  const directory = await mkdtemp(join(tmpdir(), "issue45-cli-link-"));
  const link = join(directory, "probe.mjs");
  try {
    await symlink(SCRIPT, link);
    const result = await runCli({}, link);
    assert.equal(result.status, 2);
    const output = report(result);
    assert.equal(output.status, "unverified");
    assert.deepEqual(output.failures, ["target_inventory_missing"]);
    assert.deepEqual(output.targets, []);
    t.diagnostic(`Symlink CLI invocation emitted status=${output.status}; exit=${result.status}; no target contacted`);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

function report(result) {
  assert.equal(result.stderr, "");
  return JSON.parse(result.stdout);
}

async function freePort() {
  const server = createNetServer();
  server.listen(0, "::1");
  await once(server, "listening");
  const { port } = server.address();
  await new Promise((done) => server.close(done));
  return port;
}

async function listenHttp(handler) {
  const server = createServer(handler);
  server.listen(0, "::1");
  await once(server, "listening");
  return server;
}

async function close(server) {
  server.closeAllConnections();
  await new Promise((done) => server.close(done));
}

function directTargets(port, overrides = {}) {
  return {
    MCP_PROBE_HOST: "localhost",
    MCP_PROBE_PORT: String(port),
    MCP_IPS: "::1",
    MCP_PUBLISHED_ENDPOINTS: `http://[::1]:${port}`,
    ...overrides,
  };
}

test("supplied service and IP health targets fail closed without leaking response data", async (t) => {
  const requests = [];
  const server = await listenHttp((request, response) => {
    requests.push({ url: request.url, authorization: request.headers.authorization ?? null });
    response.writeHead(503);
    response.end(PRIVATE_MARKER);
  });
  try {
    const result = await runCli(directTargets(server.address().port, {
      GRAFANA_MCP_TOKEN: "must-not-be-used",
      MCP_GRAFANA_SERVER_TOKEN: "must-not-be-used",
    }));
    assert.equal(result.status, 1);
    const output = report(result);
    assert.equal(output.status, "fail");
    assert.equal(output.coverage, "supplied-targets-only");
    assert.equal(output.full_boundary, "pending");
    assert.deepEqual(output.failures, ["direct_mcp_path_reachable"]);
    assert.deepEqual(output.targets, [
      { kind: "service-name", status: "reachable", http_status: 503 },
      { kind: "direct-ip", status: "reachable", http_status: 503 },
      { kind: "published-port", status: "reachable", http_status: 503 },
    ]);
    assert.deepEqual(requests, [
      { url: "/healthz", authorization: null },
      { url: "/healthz", authorization: null },
      { url: "/healthz", authorization: null },
    ]);
    assert.ok(!result.stdout.includes(PRIVATE_MARKER));
    assert.ok(!result.stdout.includes(String(server.address().port)));
    t.diagnostic(`Supplied targets=${output.targets.length}; reachable=3; status=${output.status}; response marker exposed=false`);
  } finally {
    await close(server);
  }
});

test("blocked service and IP targets remain unverified, never an isolation pass", async (t) => {
  const result = await runCli(directTargets(await freePort()));
  assert.equal(result.status, 2);
  const output = report(result);
  assert.equal(output.status, "unverified");
  assert.equal(output.coverage, "supplied-targets-only");
  assert.equal(output.full_boundary, "pending");
  assert.deepEqual(output.failures, ["direct_targets_unavailable"]);
  assert.deepEqual(output.targets, [
    { kind: "service-name", status: "blocked", http_status: null },
    { kind: "direct-ip", status: "blocked", http_status: null },
    { kind: "published-port", status: "blocked", http_status: null },
  ]);
  t.diagnostic(`Blocked supplied targets: status=${output.status}; full_boundary=${output.full_boundary}; no isolation pass claimed`);
});

test("missing or invalid direct inventory is unverified before contact", async (t) => {
  let requests = 0;
  const server = await listenHttp((_request, response) => {
    requests += 1;
    response.end(PRIVATE_MARKER);
  });
  const port = server.address().port;
  const invalid = [
    { MCP_PUBLISHED_ENDPOINTS: `http://${PRIVATE_MARKER}@[::1]:${port}` },
    { MCP_PUBLISHED_ENDPOINTS: `http://[::1]:${port}/private` },
    { MCP_PUBLISHED_ENDPOINTS: `http://[::1]:${port}/?token=${PRIVATE_MARKER}` },
    { MCP_PUBLISHED_ENDPOINTS: `http://[::1]:${port}/#${PRIVATE_MARKER}` },
    { MCP_PROBE_HOST: "localhost/private" },
    { MCP_PROBE_PORT: "65536" },
    { MCP_IPS: "not-an-ip" },
    { MCP_IPS: Array(17).fill("::1").join(",") },
  ];
  try {
    const missing = await runCli();
    assert.equal(missing.status, 2);
    assert.equal(report(missing).status, "unverified");
    for (const overrides of invalid) {
      const result = await runCli(directTargets(port, overrides));
      assert.equal(result.status, 2);
      const output = report(result);
      assert.equal(output.status, "unverified");
      assert.deepEqual(output.failures, ["target_inventory_invalid"]);
      assert.deepEqual(output.targets, []);
      assert.ok(!result.stdout.includes(PRIVATE_MARKER));
      assert.ok(!result.stdout.includes(String(port)));
    }
    assert.equal(requests, 0);
    t.diagnostic(`Invalid inventory cases=${invalid.length}; status=unverified; contacted_targets=${requests}; marker exposed=false`);
  } finally {
    await close(server);
  }
});

test("missing published-origin inventory is unverified before direct-target contact", async (t) => {
  let requests = 0;
  const server = await listenHttp((_request, response) => {
    requests += 1;
    response.end(PRIVATE_MARKER);
  });
  const port = server.address().port;
  const inventory = directTargets(port);
  delete inventory.MCP_PUBLISHED_ENDPOINTS;
  try {
    const result = await runCli(inventory);
    assert.equal(result.status, 2);
    const output = report(result);
    assert.equal(output.status, "unverified");
    assert.deepEqual(output.failures, ["target_inventory_missing"]);
    assert.deepEqual(output.targets, []);
    assert.equal(requests, 0);
    assert.ok(!result.stdout.includes(PRIVATE_MARKER));
    assert.ok(!result.stdout.includes(String(port)));
    t.diagnostic(`Missing published inventory: status=${output.status}; targets=${output.targets.length}; contacted_targets=${requests}`);
  } finally {
    await close(server);
  }
});

test("redirect responses are reachable but never followed", async (t) => {
  let alternateRequests = 0;
  const alternate = await listenHttp((_request, response) => {
    alternateRequests += 1;
    response.end(PRIVATE_MARKER);
  });
  const alternateUrl = `http://[::1]:${alternate.address().port}/healthz`;
  const redirect = await listenHttp((_request, response) => {
    response.writeHead(302, { Location: alternateUrl });
    response.end(PRIVATE_MARKER);
  });
  try {
    const port = redirect.address().port;
    const result = await runCli(directTargets(port));
    assert.equal(result.status, 1);
    const output = report(result);
    assert.equal(output.status, "fail");
    assert.equal(output.targets.length, 3);
    assert.ok(output.targets.every((target) => target.status === "reachable" && target.http_status === 302));
    assert.equal(alternateRequests, 0);
    assert.ok(!result.stdout.includes(PRIVATE_MARKER));
    assert.ok(!result.stdout.includes(alternateUrl));
    t.diagnostic(`Redirect response status=fail; alternate_requests=${alternateRequests}; marker exposed=false`);
  } finally {
    await close(redirect);
    await close(alternate);
  }
});
