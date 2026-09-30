import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SCRIPT = fileURLToPath(new URL("../scripts/demo_mcp_gateway_probe.mjs", import.meta.url));
const HUMAN_TOKEN = "fixture-allowed-token";
const RESTRICTED_TOKEN = "fixture-restricted-token";
const PRIVATE_MARKER = "fixture-private-body";
const DENIAL_REQUEST_ID = "10000000-0000-4000-8000-000000000006";
const DISCOVERY_REQUEST_ID = "10000000-0000-4000-8000-000000000007";

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

test("gateway smoke CLI validates queries and server-restricted discovery", async (t) => {
  const calls = [];
  const requests = [];
  let metricReply = { status: 200, body: { result_type: "vector", result: [{ value: [1, "1"] }], warnings: [] } };
  let logReply = { status: 200, body: { total: 1, documents: [{ marker: PRIVATE_MARKER }], warnings: [] } };
  let allowed = { server: { server_id: "grafana-mcp", endpoint: PRIVATE_MARKER },
    tools: [{ tool_id: "query_prometheus" }, { tool_id: "query_elasticsearch" }] };
  let denied = { error: { code: "resource_unavailable", message: PRIVATE_MARKER },
    request_id: DISCOVERY_REQUEST_ID, retryable: false };
  let invocationDenied = { error: { code: "resource_unavailable", message: PRIVATE_MARKER },
    request_id: DENIAL_REQUEST_ID };
  const server = createServer((request, response) => {
    calls.push(`${request.method} ${request.url}`);
    let rawBody = "";
    request.on("data", (chunk) => { rawBody += chunk; });
    request.on("end", () => {
      const restricted = request.headers.authorization === `Bearer ${RESTRICTED_TOKEN}`;
      assert.equal(request.headers.authorization, `Bearer ${restricted ? RESTRICTED_TOKEN : HUMAN_TOKEN}`);
      const body = rawBody ? JSON.parse(rawBody) : null;
      requests.push({ method: request.method, path: request.url, body, restricted });
      if (request.method === "POST" && restricted) {
        assert.equal(request.url, "/v1/mcp/tools/query_prometheus");
        assert.deepEqual(body, { datasource_uid: "webstore-metrics", expr: "up",
          query_type: "instant", end_time: "now" });
        response.writeHead(invocationDenied.status ?? 403, { "Content-Type": "application/json" });
        response.end(JSON.stringify(invocationDenied.body ?? invocationDenied));
        return;
      }
      if (request.method === "POST") {
        assert.equal(request.headers["content-type"], "application/json");
        const metric = request.url.endsWith("query_prometheus");
        assert.ok(metric || request.url.endsWith("query_elasticsearch"));
        const reply = metric ? metricReply : logReply;
        response.writeHead(reply.status, { "Content-Type": "application/json" });
        response.end(JSON.stringify(reply.body));
        return;
      }
      assert.equal(request.method, "GET");
      assert.equal(request.url, "/v1/mcp/discovery");
      response.writeHead(restricted ? 403 : 200, { "Content-Type": "application/json" });
      response.end(JSON.stringify(restricted ? denied : allowed));
    });
  });
  const url = await listen(server);
  try {
    const success = await runCli(url);
    assert.equal(success.status, 0, success.stderr);
    const observed = report(success);
    assert.equal(observed.phase, "gateway-query-smoke");
    assert.equal(observed.status, "pending", "query success is not live upstream-witness acceptance");
    assert.deepEqual(observed.failures, ["upstream_witness_pending"]);
    assert.deepEqual(observed.discovery, { server: "grafana-mcp", tools: ["query_elasticsearch", "query_prometheus"] });
    assert.deepEqual(observed.metric, { source: "webstore-metrics", window: "instant@now", http_status: 200,
      error_kind: null, result_type: "vector", result_count: 1, warning_count: 0 });
    assert.deepEqual(observed.logs, { source: "webstore-logs", window: "now-5m..now", http_status: 200,
      error_kind: null, result_count: 1, returned_count: 1, warning_count: 0 });
    assert.deepEqual(observed.denied, {
      http_status: 403, error_code: "resource_unavailable", request_id: DENIAL_REQUEST_ID,
      upstream_delta: null,
    });
    assert.deepEqual(observed.restricted_discovery, {
      http_status: 403, error_code: "resource_unavailable", request_id: DISCOVERY_REQUEST_ID,
      retryable: false, enumeration_absent: true,
    });
    assert.deepEqual(requests.map(({ method, path }) => `${method} ${path}`), [
      "POST /v1/mcp/tools/query_prometheus", "GET /v1/mcp/discovery",
      "POST /v1/mcp/tools/query_prometheus", "POST /v1/mcp/tools/query_elasticsearch",
      "GET /v1/mcp/discovery",
    ]);
    assert.equal(requests[0].body.expr, "up", "restricted request reuses the fixed metric payload");
    assert.deepEqual(calls, ["POST /v1/mcp/tools/query_prometheus", "GET /v1/mcp/discovery",
      "POST /v1/mcp/tools/query_prometheus", "POST /v1/mcp/tools/query_elasticsearch",
      "GET /v1/mcp/discovery"]);
    assert.deepEqual(requests.filter(({ method, restricted }) => method === "POST" && !restricted).map(({ body }) => body), [
      { datasource_uid: "webstore-metrics", expr: "up", query_type: "instant", end_time: "now" },
      { datasource_uid: "webstore-logs", index: "otel-logs-*", query: "resource.service.name:checkout",
        start_time: "now-5m", end_time: "now", limit: 1 },
    ]);

    metricReply = { status: 200, body: { result_type: "vector", result: [], warnings: [] } };
    const emptyMetric = await runCli(url);
    assert.equal(emptyMetric.status, 1);
    const emptyMetricReport = report(emptyMetric);
    assert.ok(emptyMetricReport.failures.includes("metric_signal_missing"));
    assert.equal(emptyMetricReport.metric.result_count, 0);
    metricReply = { status: 504, body: { error: { code: "upstream_timeout", message: PRIVATE_MARKER } } };
    const timeoutMetric = await runCli(url);
    assert.equal(timeoutMetric.status, 1);
    const timeoutMetricReport = report(timeoutMetric);
    assert.ok(timeoutMetricReport.failures.includes("metric_query_failed"));
    assert.equal(timeoutMetricReport.metric.error_kind, "upstream_timeout");
    assert.equal(timeoutMetricReport.metric.http_status, 504);
    metricReply = { status: 200, body: { result_type: "vector", result: [{ value: [1, "1"] }], warnings: [] } };
    logReply = { status: 200, body: { total: 0, documents: [], warnings: [] } };
    const emptyLogs = await runCli(url);
    assert.equal(emptyLogs.status, 1);
    const emptyLogsReport = report(emptyLogs);
    assert.ok(emptyLogsReport.failures.includes("log_signal_missing"));
    assert.equal(emptyLogsReport.logs.result_count, 0);
    t.diagnostic(`Controlled gateway query report: ${JSON.stringify(observed)}`);

    logReply = { status: 200, body: { total: 1, documents: [{ marker: PRIVATE_MARKER }], warnings: [] } };
    const beforeRootSlash = calls.length;
    const rootSlash = await runCli(`${url}/`);
    assert.equal(rootSlash.status, 0, rootSlash.stderr);
    assert.equal(report(rootSlash).status, "pending", "a controlled query has no independent upstream witness");
    assert.deepEqual(calls.slice(beforeRootSlash), ["POST /v1/mcp/tools/query_prometheus",
      "GET /v1/mcp/discovery", "POST /v1/mcp/tools/query_prometheus",
      "POST /v1/mcp/tools/query_elasticsearch", "GET /v1/mcp/discovery"]);

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
    for (const invalid of [
      { status: 200, body: invocationDenied },
      { status: 403, body: { ...invocationDenied, error: { code: "not_authorized" } } },
      { status: 403, body: { ...invocationDenied, request_id: undefined } },
      { status: 403, body: { ...invocationDenied, request_id: PRIVATE_MARKER } },
    ]) {
      const previous = invocationDenied;
      invocationDenied = invalid;
      const result = await runCli(url);
      assert.equal(result.status, 1);
      assert.ok(report(result).failures.includes("restricted_invocation_not_denied"));
      invocationDenied = previous;
    }
    const count = calls.length;
    for (const invalidUrl of [`${url}/mcp-gateway`, `${url}/mcp-gateway/`, `${url}?token=${PRIVATE_MARKER}`,
      `http://user:pass@127.0.0.1`, "file:///tmp/invalid"]) {
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

test("gateway smoke CLI rejects redirects and bounds malformed or unavailable responses", async (t) => {
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
    assert.equal(gatewayCalls, 15, "each scenario attempts only its five fixed gateway requests");
    t.diagnostic(`Controlled alternate-server calls: ${alternateCalls}; gateway requests: ${gatewayCalls}`);
  } finally {
    await close(gateway);
    await close(alternate);
  }
});
