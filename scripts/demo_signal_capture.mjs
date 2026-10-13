#!/usr/bin/env node

// Capture the pinned payment-failure signals through governed public gateway routes.
// Capture after a settled two-minute window; no raw log bodies or trace IDs leave this CLI.


const SCHEMA = "sre-agent.mcp45-3-signal-capture/v1";
const SERVICES = "frontend-proxy|frontend|checkout|payment";
const ERROR_CALLS = `sum by (service_name) (increase(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR", service_name=~"${SERVICES}"}[2m]))`;
const CHECKOUT_SPANS = 'sum by (span_name) (increase(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR", service_name="checkout"}[2m]))';
const SOURCES = {
  metric: "webstore-metrics",
  logs: "webstore-logs/otel-logs-*",
};
const WINDOWS = {
  metric: "increase(...[2m]) @ now",
  logs: "now-2m..now",
};
const GATEWAY_RESPONSE_TIMEOUT_MS = 35_000;
const STAGES = ["[PlaceOrder]", "payment went through", "order placed"];
const REQUEST_STATUS = /"POST [^"]*checkout[^"]*" (\d{3}) /;

function failureCapture(cycle, phase, code) {
  return {
    schema: SCHEMA,
    status: "fail",
    cycle,
    phase,
    captured_at: new Date().toISOString(),
    failures: [code],
    metric: { source: SOURCES.metric, window: WINDOWS.metric },
    logs: { source: SOURCES.logs, window: WINDOWS.logs },
  };
}

function safeCount(value) {
  return Number.isFinite(value) && value >= 0 ? value : null;
}

function metricValues(body, label) {
  if (body?.result_type !== "vector" || !Array.isArray(body.result)) {
    return null;
  }
  const values = new Map();
  for (const row of body.result) {
    const key = row?.metric?.[label];
    const value = Array.isArray(row?.value) ? Number(row.value[1]) : NaN;
    if (typeof key !== "string" || !key || safeCount(value) === null) return null;
    values.set(key, (values.get(key) ?? 0) + value);
  }
  return Object.fromEntries(values);
}

function logSource(document) {
  const source = document?._source ?? document;
  return source && typeof source === "object" ? source : {};
}

function serviceName(log) {
  return log?.resource?.["service.name"] ?? log?.resource?.service?.name ??
    log?.["resource.service.name"] ?? null;
}

function summarizeLogs(body) {
  if (!Array.isArray(body?.documents) || body.documents.length === 0 ||
      !Number.isSafeInteger(body?.total) || body.total <= 0) return null;
  const checkout = body.documents.map(logSource).filter((log) => serviceName(log) === "checkout");
  if (checkout.length === 0) return null;
  const counts = Object.fromEntries(STAGES.map((stage) => [stage, 0]));
  const started = new Set();
  const completed = new Set();
  for (const log of checkout) {
    if (typeof log.body !== "string") continue;
    if (Object.hasOwn(counts, log.body)) counts[log.body] += 1;
    if (typeof log.traceId === "string" && log.traceId) {
      if (log.body === STAGES[0]) started.add(log.traceId);
      if (log.body === STAGES[2]) completed.add(log.traceId);
    }
  }
  const proxy = body._proxy_documents;
  if (!Array.isArray(proxy) || proxy.length === 0) return null;
  const proxyStatuses = { "200": 0, "500": 0 };
  for (const document of proxy) {
    const match = REQUEST_STATUS.exec(String(logSource(document).body ?? ""));
    if (match && Object.hasOwn(proxyStatuses, match[1])) proxyStatuses[match[1]] += 1;
  }
  return {
    stage_counts: counts,
    stalled_orders: [...started].filter((traceId) => !completed.has(traceId)).length,
    proxy_checkout_statuses: proxyStatuses,
  };
}

function summarize(status, cycle, phase, settledSince, serviceErrors, spanErrors, checkoutBody, proxyBody) {
  const checkoutLogs = checkoutBody?.documents;
  const combinedLogs = Array.isArray(checkoutLogs) ? { ...checkoutBody, _proxy_documents: proxyBody?.documents } : null;
  const logs = summarizeLogs(combinedLogs);
  // Error-only Prometheus vectors omit a series entirely during a clean
  // baseline; a successful empty query is zero, not a missing datasource.
  const checkoutErrors = serviceErrors?.checkout ?? 0;
  const placeOrderErrors = spanErrors?.["oteldemo.CheckoutService/PlaceOrder"] ?? 0;
  if (status !== 200 || !serviceErrors || !spanErrors || !logs) {
    return failureCapture(cycle, phase, "signal_query_unavailable");
  }
  const report = {
    schema: SCHEMA,
    status: "observed",
    cycle,
    phase,
    captured_at: new Date().toISOString(),
    settled_since: settledSince.toISOString(),
    settled_for_seconds: Math.floor((Date.now() - settledSince.getTime()) / 1000),
    failures: [],
    metric: {
      source: SOURCES.metric,
      window: WINDOWS.metric,
      checkout_errors: safeCount(checkoutErrors),
      checkout_place_order_errors: safeCount(placeOrderErrors),
    },
    logs: {
      source: SOURCES.logs,
      window: WINDOWS.logs,
      ...logs,
    },
  };
  if (report.metric.checkout_errors === null || report.metric.checkout_place_order_errors === null) {
    return failureCapture(cycle, phase, "signal_query_unavailable");
  }
  return report;
}

function validOrigin(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password &&
      !url.search && !url.hash && url.pathname === "/" ? url.origin : null;
  } catch {
    return null;
  }
}

export async function query(origin, token, route, body) {
  const response = await fetch(`${origin}${route}`, {
    method: "POST",
    redirect: "error",
    headers: { Authorization: `Bearer ${token}`, Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(GATEWAY_RESPONSE_TIMEOUT_MS),
  });
  let payload = {};
  try { payload = await response.json(); } catch { /* Keep response bodies out of reports. */ }
  return { status: response.status, body: payload };
}

async function capture(cycle, phase, settledSinceValue) {
  const gateway = validOrigin(process.env.MCP_GATEWAY_URL ?? "http://api:8000");
  const token = process.env.DEMO_HUMAN_API_KEY;
  const settledSince = new Date(settledSinceValue);
  if (!gateway || !token || ![1, 2].includes(cycle) || !["baseline", "failure", "reset"].includes(phase) ||
      !settledSinceValue || !Number.isFinite(settledSince.getTime())) {
    return failureCapture(cycle, phase, "signal_probe_configuration_invalid");
  }
  if (Date.now() - settledSince.getTime() < 150_000) {
    return failureCapture(cycle, phase, "signal_window_not_settled");
  }
  try {
    const metricQuery = {
      datasource_uid: SOURCES.metric,
      expr: ERROR_CALLS,
      query_type: "instant",
      end_time: "now",
    };
    const checkoutSpanQuery = { ...metricQuery, expr: CHECKOUT_SPANS };
    const logQuery = {
      datasource_uid: "webstore-logs",
      index: "otel-logs-*",
      query: "resource.service.name:checkout",
      start_time: "now-2m",
      end_time: "now",
      limit: 100,
    };
    const proxyQuery = {
      ...logQuery,
      query: 'resource.service.name:"frontend-proxy" AND body:*checkout*',
    };
    const [serviceResponse, spanResponse, checkoutResponse, proxyResponse] = await Promise.all([
      query(gateway, token, "/v1/mcp/tools/query_prometheus", metricQuery),
      query(gateway, token, "/v1/mcp/tools/query_prometheus", checkoutSpanQuery),
      query(gateway, token, "/v1/mcp/tools/query_elasticsearch", logQuery),
      query(gateway, token, "/v1/mcp/tools/query_elasticsearch", proxyQuery),
    ]);
    if ([serviceResponse, spanResponse].some((result) => result.status !== 200)) {
      return failureCapture(cycle, phase, "metric_query_failed");
    }
    if ([checkoutResponse, proxyResponse].some((result) => result.status !== 200)) {
      return failureCapture(cycle, phase, "log_query_failed");
    }
    const serviceErrors = metricValues(serviceResponse.body, "service_name");
    const spanErrors = metricValues(spanResponse.body, "span_name");
    if (!serviceErrors || !spanErrors) return failureCapture(cycle, phase, "metric_signal_missing");
    const report = summarize(200, cycle, phase, settledSince, serviceErrors, spanErrors,
      checkoutResponse.body, proxyResponse.body);
    if (report.status === "observed" && report.settled_for_seconds < 150) {
      return failureCapture(cycle, phase, "signal_window_not_settled");
    }
    return report;
  } catch {
    return failureCapture(cycle, phase, "signal_query_failed");
  }
}

function parseArgs(args) {
  if (args.length !== 7 || args[0] !== "capture" || args[1] !== "--cycle" ||
      args[3] !== "--phase" || args[5] !== "--settled-since") return null;
  return { cycle: Number(args[2]), phase: args[4], settledSince: args[6] };
}

const args = parseArgs(process.argv.slice(2));
const report = args
  ? await capture(args.cycle, args.phase, args.settledSince)
  : failureCapture(null, null, "signal_probe_configuration_invalid");
process.stdout.write(`${JSON.stringify(report)}\n`);
process.exitCode = report.status === "observed" ? 0 : 1;
