#!/usr/bin/env node

// Probe only supplied service-name, direct-IP, and published-origin health targets; full boundary proof remains pending.
import { realpathSync } from "node:fs";
import { isIP } from "node:net";
import { fileURLToPath } from "node:url";

const HEALTH_PATH = "/healthz";
const REQUEST_TIMEOUT_MS = 1_500;
const MAX_TARGETS = 16;
const MAX_LIST_LENGTH = 4_096;

function splitTargets(value) {
  if (typeof value !== "string" || value.length === 0 || value.length > MAX_LIST_LENGTH) return null;
  const targets = value.split(/[\s,]+/).filter(Boolean);
  return targets.length > 0 && targets.length <= MAX_TARGETS && targets.every((target) => target.length <= 512)
    ? targets : null;
}

function validServiceName(value) {
  if (typeof value !== "string" || value.length > 253 || !/^[A-Za-z0-9.-]+$/.test(value)) return false;
  return value.split(".").every((label) => label.length > 0 && label.length <= 63 &&
    /^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$/.test(label));
}

function parsePort(value) {
  if (typeof value !== "string" || !/^\d{1,5}$/.test(value)) return null;
  const port = Number(value);
  return port >= 1 && port <= 65_535 ? port : null;
}

function parsePublishedEndpoint(value) {
  if (typeof value !== "string" || value.length > 512 || /\s|[?#]/.test(value) ||
      !/^https?:\/\//i.test(value)) return null;
  try {
    const separator = value.indexOf("://");
    const authority = value.slice(separator + 3).split(/[/?#]/, 1)[0];
    if (!authority || authority.includes("@")) return null;
    const url = new URL(value);
    if (!(["http:", "https:"].includes(url.protocol)) || !url.hostname ||
        url.username || url.password || url.pathname !== "/" || url.search || url.hash) return null;
    const host = url.hostname.replace(/^\[|\]$/g, "");
    if (isIP(host) === 0 && !validServiceName(host)) return null;
    if (url.port && parsePort(url.port) === null) return null;
    url.pathname = HEALTH_PATH;
    return url.toString();
  } catch {
    return null;
  }
}

function buildInventory(env) {
  const host = env.MCP_PROBE_HOST;
  const portValue = env.MCP_PROBE_PORT;
  const ipValues = splitTargets(env.MCP_IPS);
  const publishedValues = splitTargets(env.MCP_PUBLISHED_ENDPOINTS);
  if (!host || !portValue || !env.MCP_IPS || !env.MCP_PUBLISHED_ENDPOINTS) {
    return { failure: "target_inventory_missing" };
  }
  const port = parsePort(portValue);
  if (!validServiceName(host) || port === null || !ipValues || !publishedValues ||
      ipValues.some((ip) => isIP(ip) === 0)) {
    return { failure: "target_inventory_invalid" };
  }
  const publishedUrls = publishedValues.map(parsePublishedEndpoint);
  if (publishedUrls.some((url) => !url) || 1 + ipValues.length + publishedUrls.length > MAX_TARGETS) {
    return { failure: "target_inventory_invalid" };
  }
  const serviceUrl = `http://${host}:${port}${HEALTH_PATH}`;
  const ipUrls = ipValues.map((ip) => `http://${isIP(ip) === 6 ? `[${ip}]` : ip}:${port}${HEALTH_PATH}`);
  return { targets: [
    { kind: "service-name", url: serviceUrl },
    ...ipUrls.map((url) => ({ kind: "direct-ip", url })),
    ...publishedUrls.map((url) => ({ kind: "published-port", url })),
  ] };
}

async function probe(target) {
  try {
    const response = await fetch(target.url, {
      method: "GET",
      redirect: "manual",
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    await response.body?.cancel().catch(() => {});
    return { kind: target.kind, status: "reachable", http_status: response.status };
  } catch {
    return { kind: target.kind, status: "blocked", http_status: null };
  }
}

async function main() {
  const inventory = buildInventory(process.env);
  let status = "unverified";
  let failures = [inventory.failure ?? "direct_targets_unavailable"];
  let targets = [];
  if (inventory.targets) {
    targets = await Promise.all(inventory.targets.map(probe));
    const reachable = targets.some((target) => target.status === "reachable");
    failures = [reachable ? "direct_mcp_path_reachable" : "direct_targets_unavailable"];
    if (reachable) status = "fail";
  }
  process.stdout.write(`${JSON.stringify({
    status,
    failures,
    coverage: "supplied-targets-only",
    full_boundary: "pending",
    targets,
  })}\n`);
  process.exitCode = status === "fail" ? 1 : 2;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === realpathSync(process.argv[1])) await main();
