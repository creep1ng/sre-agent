#!/usr/bin/env node

// Public gateway smoke-query probe. All tool calls go through the API gateway.
import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const EXPECTED_SERVER = "grafana-mcp";
const EXPECTED_TOOLS = ["query_elasticsearch", "query_prometheus"];
const REPORT_SCHEMA = "sre-agent.mcp45-query-smoke/v1";
const REPORT_PHASE = "gateway-query-smoke";
const GATEWAY_RESPONSE_TIMEOUT_MS = 35_000;
const METRIC_QUERY = {
  datasource_uid: "webstore-metrics", expr: "up", query_type: "instant", end_time: "now",
};
const LOG_QUERY = {
  datasource_uid: "webstore-logs", index: "otel-logs-*", query: "resource.service.name:checkout",
  start_time: "now-5m", end_time: "now", limit: 1,
};

function validGatewayUrl(value) {
  try {
    const url = new URL(value);
    return (url.protocol === "http:" || url.protocol === "https:") && url.pathname === "/" &&
      !url.username && !url.password && !url.search && !url.hash
      ? url.origin
      : null;
  } catch {
    return null;
  }
}

export async function fetchJson({ method = "GET", url, token, body }) {
  const headers = { Accept: "application/json", Authorization: `Bearer ${token}` };
  const options = { method, headers, redirect: "error", signal: AbortSignal.timeout(GATEWAY_RESPONSE_TIMEOUT_MS) };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(url, options);
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    // A non-JSON response is represented only by its HTTP status.
  }
  return { status: response.status, body: payload };
}

function normalizedErrorKind(status, body) {
  if (status === 504 && body?.error?.code === "upstream_timeout") return "upstream_timeout";
  if (status === 503 && body?.error?.code === "upstream_unavailable") return "upstream_unavailable";
  return null;
}

function summarizeMetric(status, body) {
  const results = Array.isArray(body?.result) ? body.result : [];
  const warnings = Array.isArray(body?.warnings) ? body.warnings : [];
  const resultType = body?.result_type === "vector" ? "vector" : null;
  return { ok: status === 200 && resultType === "vector" && results.length > 0,
    failure: status === 200 ? "metric_signal_missing" : "metric_query_failed",
    source: METRIC_QUERY.datasource_uid, window: "instant@now", http_status: status,
    error_kind: normalizedErrorKind(status, body), result_type: resultType,
    result_count: results.length, warning_count: warnings.length };
}

function summarizeLogs(status, body) {
  const documents = Array.isArray(body?.documents) ? body.documents : [];
  const warnings = Array.isArray(body?.warnings) ? body.warnings : [];
  const total = Number.isSafeInteger(body?.total) && body.total >= 0 ? body.total : null;
  return { ok: status === 200 && total !== null && total > 0 && documents.length > 0,
    failure: status === 200 ? "log_signal_missing" : "log_query_failed",
    source: LOG_QUERY.datasource_uid, window: `${LOG_QUERY.start_time}..${LOG_QUERY.end_time}`,
    http_status: status, error_kind: normalizedErrorKind(status, body), result_count: total,
    returned_count: documents.length, warning_count: warnings.length };
}

function safeRequestId(value) {
  return typeof value === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
    ? value
    : null;
}

function summarizeDiscovery(status, body) {
  const rawTools = Array.isArray(body?.tools) ? body.tools : [];
  const validEntries = Array.isArray(body?.tools) && rawTools.length === EXPECTED_TOOLS.length &&
    rawTools.every((tool) => typeof tool?.tool_id === "string" && EXPECTED_TOOLS.includes(tool.tool_id));
  const listed = rawTools.map((tool) => tool?.tool_id).filter((id) => typeof id === "string");
  const tools = [...new Set(listed.filter((id) => EXPECTED_TOOLS.includes(id)))].sort();
  const exact =
    status === 200 && body?.server?.server_id === EXPECTED_SERVER &&
    validEntries &&
    listed.length === EXPECTED_TOOLS.length &&
    tools.length === EXPECTED_TOOLS.length &&
    listed.every((id) => EXPECTED_TOOLS.includes(id));
  return { ok: exact, server: body?.server?.server_id === EXPECTED_SERVER ? EXPECTED_SERVER : null, tools };
}

function failureResult(code) {
  return {
    schema: "sre-agent.mcp45-query-smoke/v1",
    phase: "gateway-query-smoke",
    status: "fail",
    failures: [code],
    discovery: { server: null, tools: [] },
    metric: null,
    logs: null,
    denied: null,
    restricted_discovery: null,
  };
}

export async function runDiscovery({ gatewayUrl, humanToken, restrictedToken }) {
  const origin = validGatewayUrl(gatewayUrl);
  if (!origin || !humanToken || !restrictedToken) return failureResult("probe_configuration_missing");

  const call = async (method, path, token, body) => {
    try {
      return await fetchJson({ method, url: `${origin}${path}`, token, body });
    } catch {
      return { status: 0, body: {} };
    }
  };
  const invocation = await call("POST", "/v1/mcp/tools/query_prometheus", restrictedToken, METRIC_QUERY);
  const invocationBody = invocation.body && typeof invocation.body === "object" ? invocation.body : {};
  const restrictedInvocation = {
    http_status: invocation.status,
    error_code: invocationBody.error?.code === "resource_unavailable" ? "resource_unavailable" : null,
    request_id: safeRequestId(invocationBody.request_id),
    retryable: typeof invocationBody.retryable === "boolean" ? invocationBody.retryable : null,
    upstream_delta: null,
  };
  const allowed = await call("GET", "/v1/mcp/discovery", humanToken);
  const discovery = summarizeDiscovery(allowed.status, allowed.body);
  const metricResponse = await call("POST", "/v1/mcp/tools/query_prometheus", humanToken, METRIC_QUERY);
  const metric = summarizeMetric(metricResponse.status, metricResponse.body);
  const logResponse = await call("POST", "/v1/mcp/tools/query_elasticsearch", humanToken, LOG_QUERY);
  const logs = summarizeLogs(logResponse.status, logResponse.body);
  const restricted = await call("GET", "/v1/mcp/discovery", restrictedToken);
  const body = restricted.body && typeof restricted.body === "object" ? restricted.body : {};
  const restrictedDiscovery = {
    http_status: restricted.status,
    error_code: body.error?.code === "resource_unavailable" ? "resource_unavailable" : null,
    request_id: safeRequestId(body.request_id),
    retryable: typeof body.retryable === "boolean" ? body.retryable : null,
    enumeration_absent: !Object.hasOwn(body, "server") && !Object.hasOwn(body, "tools"),
  };
  const failures = [];
  if (!discovery.ok) failures.push("discovery_mismatch");
  if (!metric.ok) failures.push(metric.failure);
  if (!logs.ok) failures.push(logs.failure);
  if (restrictedInvocation.http_status !== 403 || restrictedInvocation.error_code !== "resource_unavailable" ||
      !restrictedInvocation.request_id || restrictedInvocation.retryable !== false) {
    failures.push("restricted_invocation_not_denied");
  }
  if (restrictedDiscovery.http_status !== 403 || restrictedDiscovery.error_code !== "resource_unavailable" ||
      !restrictedDiscovery.request_id || restrictedDiscovery.retryable !== false || !restrictedDiscovery.enumeration_absent) {
    failures.push("restricted_discovery_not_denied");
  }
  if (restrictedInvocation.request_id && restrictedDiscovery.request_id &&
      restrictedInvocation.request_id.toLowerCase() === restrictedDiscovery.request_id.toLowerCase()) {
    failures.push("restricted_request_ids_not_distinct");
  }
  return {
    ...failureResult(null),
    status: failures.length ? "fail" : "pending",
    failures: failures.length ? failures : ["upstream_witness_pending"],
    discovery: { server: discovery.server, tools: discovery.tools },
    metric: { source: metric.source, window: metric.window, http_status: metric.http_status,
      error_kind: metric.error_kind, result_type: metric.result_type, result_count: metric.result_count,
      warning_count: metric.warning_count },
    logs: { source: logs.source, window: logs.window, http_status: logs.http_status,
      error_kind: logs.error_kind, result_count: logs.result_count, returned_count: logs.returned_count,
      warning_count: logs.warning_count },
    denied: restrictedInvocation,
    restricted_discovery: restrictedDiscovery,
  };
}

function safePendingReport(report) {
  const validCount = (value) => Number.isSafeInteger(value) && value > 0;
  const validWarnings = (value) => Number.isSafeInteger(value) && value >= 0;
  if (!report || typeof report !== "object" || Array.isArray(report) ||
      report.schema !== REPORT_SCHEMA || report.phase !== REPORT_PHASE || report.status !== "pending" ||
      !Array.isArray(report.failures) || report.failures.length !== 1 ||
      report.failures[0] !== "upstream_witness_pending" ||
      report.discovery?.server !== EXPECTED_SERVER ||
      !Array.isArray(report.discovery?.tools) || report.discovery.tools.length !== EXPECTED_TOOLS.length ||
      !EXPECTED_TOOLS.every((tool, index) => report.discovery.tools[index] === tool) ||
      report.metric?.http_status !== 200 || report.metric.source !== METRIC_QUERY.datasource_uid ||
      report.metric.window !== "instant@now" || report.metric.error_kind !== null ||
      report.metric.result_type !== "vector" || !validCount(report.metric.result_count) ||
      !validWarnings(report.metric.warning_count) ||
      report.logs?.http_status !== 200 || report.logs.source !== LOG_QUERY.datasource_uid ||
      report.logs.window !== `${LOG_QUERY.start_time}..${LOG_QUERY.end_time}` ||
      report.logs.error_kind !== null || !validCount(report.logs.result_count) ||
      !validCount(report.logs.returned_count) || !validWarnings(report.logs.warning_count) ||
      report.denied?.http_status !== 403 || report.denied.error_code !== "resource_unavailable" ||
      !safeRequestId(report.denied.request_id) || report.denied.upstream_delta !== null ||
      report.restricted_discovery?.http_status !== 403 ||
      report.restricted_discovery.error_code !== "resource_unavailable" ||
      !safeRequestId(report.restricted_discovery.request_id) ||
      report.restricted_discovery.request_id === report.denied.request_id ||
      report.restricted_discovery.retryable !== false || report.restricted_discovery.enumeration_absent !== true) {
    return null;
  }
  return {
    schema: REPORT_SCHEMA,
    phase: REPORT_PHASE,
    status: "pending",
    failures: ["upstream_witness_pending"],
    discovery: { server: EXPECTED_SERVER, tools: EXPECTED_TOOLS },
    metric: { source: METRIC_QUERY.datasource_uid, window: "instant@now", http_status: 200,
      error_kind: null, result_type: "vector", result_count: report.metric.result_count,
      warning_count: report.metric.warning_count },
    logs: { source: LOG_QUERY.datasource_uid, window: `${LOG_QUERY.start_time}..${LOG_QUERY.end_time}`,
      http_status: 200, error_kind: null, result_count: report.logs.result_count,
      returned_count: report.logs.returned_count, warning_count: report.logs.warning_count },
    denied: { http_status: 403, error_code: "resource_unavailable",
      request_id: report.denied.request_id, upstream_delta: null },
    restricted_discovery: { http_status: 403, error_code: "resource_unavailable",
      request_id: report.restricted_discovery.request_id, retryable: false, enumeration_absent: true },
    witness: null,
  };
}

function reconcileWitness(witness, deniedRequestId) {
  if (!witness || typeof witness !== "object" || Array.isArray(witness)) {
    return { failure: "upstream_witness_unavailable" };
  }
  const { kind, source, request_id: requestId, before, after } = witness;
  if (kind !== "upstream-counter" || typeof source !== "string" ||
      !/^[A-Za-z0-9_.:-]{1,128}$/.test(source) || source.toLowerCase() === "audit_events_total" ||
      !safeRequestId(requestId) || !Number.isSafeInteger(before) || before < 0 ||
      !Number.isSafeInteger(after) || after < 0 || after < before) {
    return { failure: "upstream_witness_unavailable" };
  }
  if (requestId !== deniedRequestId) return { failure: "upstream_witness_mismatch" };
  return { kind, source, request_id: requestId, delta: after - before };
}

export function reconcileReport(report, witness) {
  const normalized = safePendingReport(report);
  if (!normalized) return failureResult("probe_report_invalid");
  const safeWitness = reconcileWitness(witness, normalized.denied.request_id);
  if (safeWitness.failure) {
    return { ...normalized, status: "fail", failures: [safeWitness.failure] };
  }
  normalized.denied.upstream_delta = safeWitness.delta;
  normalized.witness = { kind: safeWitness.kind, source: safeWitness.source, request_id: safeWitness.request_id };
  if (safeWitness.delta !== 0) {
    return { ...normalized, status: "fail", failures: ["denied_upstream_delta_nonzero"] };
  }
  return { ...normalized, status: "pass", failures: [] };
}

async function loadJsonFile(path) {
  if (!path) return null;
  try {
    const file = await readFile(path);
    if (file.byteLength > 16_384) return null;
    return JSON.parse(file.toString("utf8"));
  } catch {
    return null;
  }
}

async function main() {
  const args = process.argv.slice(2);
  const result = args.length === 0
    ? await runDiscovery({
        gatewayUrl: process.env.MCP_GATEWAY_URL ?? "http://api:8000",
        humanToken: process.env.DEMO_HUMAN_API_KEY,
        restrictedToken: process.env.RESTRICTED_HARNESS_API_KEY,
      })
    : args.length === 4 && args[0] === "--reconcile" && args[2] === "--witness"
      ? reconcileReport(await loadJsonFile(args[1]), await loadJsonFile(args[3]))
      : failureResult("probe_arguments_invalid");
  process.stdout.write(`${JSON.stringify(result)}\n`);
  process.exitCode = result.status === "pending" || result.status === "pass" ? 0 : 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
