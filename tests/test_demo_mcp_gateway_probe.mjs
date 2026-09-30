import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SCRIPT = fileURLToPath(new URL("../scripts/demo_mcp_gateway_probe.mjs", import.meta.url));
const HUMAN_TOKEN = "fixture-allowed-token";
const RESTRICTED_TOKEN = "fixture-restricted-token";
const PRIVATE_MARKER = "fixture-private-body";
const REQUEST_ID = "10000000-0000-4000-8000-000000000006";

async function listen(server) {
  await new Promise((done) => server.listen(0, "127.0.0.1", done));
  return `http://127.0.0.1:${server.address().port}`;
}

async function close(server) {
  server.closeAllConnections();
  await new Promise((done) => server.close(done));
}

function runCli(url, overrides = {}, args = []) {
  return new Promise((done, reject) => {
    const child = spawn(process.execPath, [SCRIPT, ...args], {
      env: { PATH: process.env.PATH, MCP_GATEWAY_URL: url,
        DEMO_HUMAN_API_KEY: HUMAN_TOKEN, RESTRICTED_HARNESS_API_KEY: RESTRICTED_TOKEN, ...overrides },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    const timeout = setTimeout(() => child.kill("SIGKILL"), 10_000);
    child.on("error", reject);
    child.on("close", (status) => {
      clearTimeout(timeout);
      done({ status, stdout, stderr });
    });
  });
}

function report(result) {
  assert.equal(result.stderr, "");
  for (const secret of [HUMAN_TOKEN, RESTRICTED_TOKEN, PRIVATE_MARKER]) {
    assert.ok(!result.stdout.includes(secret), "output must exclude synthetic sensitive fields");
  }
  return JSON.parse(result.stdout);
}

test("discovery CLI validates allowed and server-restricted HTTP responses without invocation", async (t) => {
  const calls = [];
  let allowed = { server: { server_id: "grafana-mcp", endpoint: PRIVATE_MARKER },
    tools: [{ tool_id: "query_prometheus" }, { tool_id: "query_elasticsearch" }] };
  let denied = { error: { code: "resource_unavailable", message: PRIVATE_MARKER },
    request_id: REQUEST_ID, retryable: false };
  const server = createServer((request, response) => {
    calls.push(`${request.method} ${request.url}`);
    assert.equal(request.method, "GET");
    assert.equal(request.url, "/v1/mcp/discovery");
    const restricted = request.headers.authorization === `Bearer ${RESTRICTED_TOKEN}`;
    assert.equal(request.headers.authorization, `Bearer ${restricted ? RESTRICTED_TOKEN : HUMAN_TOKEN}`);
    response.writeHead(restricted ? 403 : 200, { "Content-Type": "application/json" });
    response.end(JSON.stringify(restricted ? denied : allowed));
  });
  const url = await listen(server);
  try {
    const success = await runCli(url);
    assert.equal(success.status, 0, success.stderr);
    const observed = report(success);
    assert.equal(observed.phase, "gateway-discovery");
    assert.equal(observed.status, "pass");
    assert.deepEqual(observed.failures, []);
    assert.deepEqual(observed.discovery, { server: "grafana-mcp", tools: ["query_elasticsearch", "query_prometheus"] });
    assert.deepEqual(observed.restricted_discovery, {
      http_status: 403, error_code: "resource_unavailable", request_id: REQUEST_ID,
      retryable: false, enumeration_absent: true,
    });
    assert.deepEqual(calls, ["GET /v1/mcp/discovery", "GET /v1/mcp/discovery"]);
    t.diagnostic(`Controlled discovery report: ${JSON.stringify(observed)}`);

    for (const invalid of [null, { server: { server_id: PRIVATE_MARKER }, tools: [] },
      { ...allowed, tools: [...allowed.tools, { tool_id: PRIVATE_MARKER }] },
      { ...allowed, tools: [{ tool_id: "query_prometheus" }, { tool_id: "query_prometheus" }] },
      { ...allowed, tools: [...allowed.tools, {}] },
      { ...allowed, tools: [...allowed.tools, null] },
      { ...allowed, tools: [...allowed.tools, { tool_id: 42 }] }]) {
      const previous = allowed;
      allowed = invalid;
      const result = await runCli(url);
      assert.equal(result.status, 1);
      assert.ok(report(result).failures.includes("discovery_mismatch"));
      allowed = previous;
    }
    for (const invalid of [null, { ...denied, tools: [] }, { ...denied, retryable: true },
      { ...denied, request_id: PRIVATE_MARKER }, { ...denied, error: { code: PRIVATE_MARKER } }]) {
      const previous = denied;
      denied = invalid;
      const result = await runCli(url);
      assert.equal(result.status, 1);
      assert.ok(report(result).failures.includes("restricted_discovery_not_denied"));
      denied = previous;
    }
    const count = calls.length;
    for (const invalidUrl of [`${url}?token=${PRIVATE_MARKER}`, `http://user:pass@127.0.0.1`, "file:///tmp/invalid"]) {
      const result = await runCli(invalidUrl);
      assert.equal(result.status, 1);
      assert.deepEqual(report(result).failures, ["probe_configuration_missing"]);
    }
    const missing = await runCli(url, { RESTRICTED_HARNESS_API_KEY: "" });
    assert.equal(missing.status, 1);
    assert.deepEqual(report(missing).failures, ["probe_configuration_missing"]);
    const unsupported = await runCli(url, {}, ["--reconcile"]);
    assert.equal(unsupported.status, 1);
    assert.deepEqual(report(unsupported).failures, ["probe_arguments_invalid"]);
    assert.equal(calls.length, count, "invalid configuration and unsupported stages must not contact the gateway");
  } finally {
    await close(server);
  }
});

test("discovery CLI rejects redirects and bounds malformed or unavailable responses", async (t) => {
  let alternateCalls = 0;
  const alternate = createServer((_request, response) => {
    alternateCalls += 1;
    response.end(PRIVATE_MARKER);
  });
  const alternateUrl = await listen(alternate);
  let mode = "redirect";
  let gatewayCalls = 0;
  const gateway = createServer((request, response) => {
    gatewayCalls += 1;
    if (mode === "unavailable") return request.socket.destroy();
    response.writeHead(mode === "redirect" ? 307 : 503, { Location: `${alternateUrl}/${PRIVATE_MARKER}` });
    response.end(PRIVATE_MARKER);
  });
  const url = await listen(gateway);
  try {
    for (mode of ["redirect", "malformed", "unavailable"]) {
      const result = await runCli(url);
      assert.equal(result.status, 1);
      assert.equal(report(result).status, "fail");
      assert.equal(alternateCalls, 0, "redirects must not create alternate routes");
    }
    assert.equal(gatewayCalls, 6, "each scenario attempts only its two discovery requests");
    t.diagnostic(`Controlled alternate-server calls: ${alternateCalls}; discovery requests: ${gatewayCalls}`);
  } finally {
    await close(gateway);
    await close(alternate);
  }
});
