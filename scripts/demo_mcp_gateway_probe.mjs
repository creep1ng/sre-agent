#!/usr/bin/env node

// Discovery-only public gateway probe. No tool invocation or upstream connection.
import { pathToFileURL } from "node:url";

const EXPECTED_SERVER = "grafana-mcp";
const EXPECTED_TOOLS = ["query_elasticsearch", "query_prometheus"];
const GATEWAY_RESPONSE_TIMEOUT_MS = 35_000;

function validGatewayUrl(value) {
  try {
    const url = new URL(value);
    return (url.protocol === "http:" || url.protocol === "https:") &&
      !url.username && !url.password && !url.search && !url.hash
      ? url.origin
      : null;
  } catch {
    return null;
  }
}

export async function fetchJson({ url, token }) {
  const response = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json", Authorization: `Bearer ${token}` },
    redirect: "error",
    signal: AbortSignal.timeout(GATEWAY_RESPONSE_TIMEOUT_MS),
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    // A non-JSON response is represented only by its HTTP status.
  }
  return { status: response.status, body: payload };
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
    schema: "sre-agent.mcp45-discovery/v1",
    phase: "gateway-discovery",
    status: "fail",
    failures: [code],
    discovery: { server: null, tools: [] },
    restricted_discovery: null,
  };
}

export async function runDiscovery({ gatewayUrl, humanToken, restrictedToken }) {
  const origin = validGatewayUrl(gatewayUrl);
  if (!origin || !humanToken || !restrictedToken) return failureResult("probe_configuration_missing");

  const discover = async (token) => {
    try {
      return await fetchJson({ url: `${origin}/v1/mcp/discovery`, token });
    } catch {
      return { status: 0, body: {} };
    }
  };
  const allowed = await discover(humanToken);
  const discovery = summarizeDiscovery(allowed.status, allowed.body);
  const restricted = await discover(restrictedToken);
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
  if (restrictedDiscovery.http_status !== 403 || restrictedDiscovery.error_code !== "resource_unavailable" ||
      !restrictedDiscovery.request_id || restrictedDiscovery.retryable !== false || !restrictedDiscovery.enumeration_absent) {
    failures.push("restricted_discovery_not_denied");
  }
  return {
    ...failureResult(null),
    status: failures.length ? "fail" : "pass",
    failures,
    discovery: { server: discovery.server, tools: discovery.tools },
    restricted_discovery: restrictedDiscovery,
  };
}

async function main() {
  const result = process.argv.length > 2
    ? failureResult("probe_arguments_invalid")
    : await runDiscovery({
        gatewayUrl: process.env.MCP_GATEWAY_URL ?? "http://api:8000",
        humanToken: process.env.DEMO_HUMAN_API_KEY,
        restrictedToken: process.env.RESTRICTED_HARNESS_API_KEY,
      });
  process.stdout.write(`${JSON.stringify(result)}\n`);
  process.exitCode = result.status === "pass" ? 0 : 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
