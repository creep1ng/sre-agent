import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SCRIPT = fileURLToPath(new URL("../scripts/demo_signal_capture.mjs", import.meta.url));
const TOKEN = "controlled-human-token";
const MARKER = "private-operational-body";
const series = (label, name, value) => ({ metric: { [label]: name }, value: [1, String(value)] });

function fixture(phase, body) {
  const failed = phase === "failure";
  if (body.datasource_uid === "webstore-metrics") {
    const service = body.expr.includes("service_name=~");
    return { result_type: "vector", result: service
      ? [series("service_name", "checkout", failed ? 12 : 0)]
      : [series("span_name", "oteldemo.CheckoutService/PlaceOrder", failed ? 4 : 0)],
    warnings: [MARKER] };
  }
  const proxy = body.query.includes("frontend-proxy");
  const documents = proxy
    ? Array.from({ length: 3 }, () => ({ _source: { body: `"POST /api/checkout HTTP/1.1" ${failed ? 500 : 200} ${MARKER}` } }))
    : Array.from({ length: 3 }, (_, index) => {
      const traceId = `private-trace-${index}`;
      return [
        { _source: { resource: { "service.name": "checkout" }, body: "[PlaceOrder]", traceId } },
        ...(!failed ? [
          { _source: { resource: { "service.name": "checkout" }, body: "payment went through", traceId } },
          { _source: { resource: { "service.name": "checkout" }, body: "order placed", traceId } },
        ] : []),
      ];
    }).flat();
  return { total: documents.length, documents, warnings: [MARKER] };
}

function runCli(url, phase, settledSince) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [SCRIPT, "capture", "--cycle", "1", "--phase", phase,
      "--settled-since", settledSince], {
      env: { PATH: process.env.PATH, MCP_GATEWAY_URL: url, DEMO_HUMAN_API_KEY: TOKEN },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    const timeout = setTimeout(() => child.kill("SIGKILL"), 10_000);
    child.on("error", reject);
    child.on("close", (status) => { clearTimeout(timeout); resolve({ status, stdout, stderr }); });
  });
}

test("gateway CLI captures real-shape baseline/failure summaries without raw contents", async () => {
  let phase = "baseline";
  const calls = [];
  const server = createServer(async (request, response) => {
    let raw = "";
    for await (const chunk of request) raw += chunk;
    const body = JSON.parse(raw);
    calls.push({ method: request.method, path: request.url, auth: request.headers.authorization, body });
    response.writeHead(200, { "Content-Type": "application/json" });
    response.end(JSON.stringify(fixture(phase, body)));
  });
  await new Promise((done) => server.listen(0, "127.0.0.1", done));
  const url = `http://127.0.0.1:${server.address().port}`;
  try {
    for (phase of ["baseline", "failure"]) {
      const observed = await runCli(url, phase, new Date(Date.now() - 151_000).toISOString());
      assert.equal(observed.status, 0, observed.stderr || observed.stdout);
      assert.equal(observed.stderr, "");
      assert.ok(!observed.stdout.includes(TOKEN) && !observed.stdout.includes(MARKER));
      assert.ok(!observed.stdout.includes("private-trace"));
      const report = JSON.parse(observed.stdout);
      assert.equal(report.schema, "sre-agent.mcp45-3-signal-capture/v1");
      assert.equal(report.status, "observed");
      assert.equal(report.phase, phase);
      assert.ok(report.settled_for_seconds >= 150);
      assert.equal(report.metric.source, "webstore-metrics");
      assert.equal(report.logs.source, "webstore-logs/otel-logs-*");
      assert.equal(report.metric.checkout_errors, phase === "failure" ? 12 : 0);
      assert.equal(report.logs.stalled_orders, phase === "failure" ? 3 : 0);
      assert.equal(report.logs.proxy_checkout_statuses[phase === "failure" ? "500" : "200"], 3);
    }
    assert.equal(calls.length, 8);
    assert.ok(calls.every(({ method, path, auth }) => method === "POST" &&
      ["/v1/mcp/tools/query_prometheus", "/v1/mcp/tools/query_elasticsearch"].includes(path) &&
      auth === `Bearer ${TOKEN}`));
    assert.ok(calls.filter(({ body }) => body.datasource_uid === "webstore-metrics").every(({ body }) =>
      body.expr.includes("traces_span_metrics_calls_total") && body.end_time === "now"));
    assert.ok(calls.filter(({ body }) => body.datasource_uid === "webstore-logs").every(({ body }) =>
      body.index === "otel-logs-*" && body.start_time === "now-2m" && body.end_time === "now"));
    const before = calls.length;
    const unsettled = await runCli(url, "failure", new Date(Date.now() - 20_000).toISOString());
    assert.equal(unsettled.status, 1);
    assert.deepEqual(JSON.parse(unsettled.stdout).failures, ["signal_window_not_settled"]);
    assert.equal(calls.length, before, "invalid window must not contact the gateway");
  } finally {
    server.closeAllConnections();
    await new Promise((done) => server.close(done));
  }
});
