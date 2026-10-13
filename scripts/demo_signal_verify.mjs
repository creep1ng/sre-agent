#!/usr/bin/env node

// Offline, bounded verification of six sanitized gateway signal captures.
// No gateway, MCP, Docker or demo access is required or attempted.
import { open } from "node:fs/promises";

const CAPTURE_SCHEMA = "sre-agent.mcp45-3-signal-capture/v1";
const SUMMARY_SCHEMA = "sre-agent.mcp45-3-cycle-verification/v1";
const PHASES = ["baseline", "failure", "reset", "baseline", "failure", "reset"];
const STAGES = ["[PlaceOrder]", "payment went through", "order placed"];
const safeCount = (value) => Number.isFinite(value) && value >= 0;

async function readReport(path) {
  let handle;
  try {
    handle = await open(path, "r");
    const bytes = Buffer.alloc(16_385);
    let length = 0;
    while (length < bytes.length) {
      const { bytesRead } = await handle.read(bytes, length, bytes.length - length, length);
      if (bytesRead === 0) break;
      length += bytesRead;
    }
    if (length > 16_384) return null;
    return JSON.parse(bytes.toString("utf8", 0, length));
  } catch {
    return null;
  } finally {
    if (handle) await handle.close().catch(() => {});
  }
}

function observationFailures(report, cycle, phase) {
  const invalid = `cycle_${cycle}_${phase}_evidence_invalid`;
  const capturedAt = Date.parse(report?.captured_at);
  const settledSince = Date.parse(report?.settled_since);
  const settledFor = Math.floor((capturedAt - settledSince) / 1000);
  if (!report || report.schema !== CAPTURE_SCHEMA || report.status !== "observed" ||
      report.cycle !== cycle || report.phase !== phase || !Number.isFinite(capturedAt) ||
      !Number.isFinite(settledSince) || settledFor < 150 ||
      !Number.isSafeInteger(report.settled_for_seconds) ||
      Math.abs(report.settled_for_seconds - settledFor) > 1 ||
      report.metric?.source !== "webstore-metrics" ||
      report.metric?.window !== "increase(...[2m]) @ now" ||
      report.logs?.source !== "webstore-logs/otel-logs-*" ||
      report.logs?.window !== "now-2m..now") return [invalid];

  const metric = report.metric;
  const logs = report.logs;
  const counts = logs.stage_counts;
  const proxy = logs.proxy_checkout_statuses;
  if (![metric.checkout_errors, metric.checkout_place_order_errors, logs.stalled_orders,
    counts?.[STAGES[0]], counts?.[STAGES[1]], counts?.[STAGES[2]],
    proxy?.["200"], proxy?.["500"]].every(safeCount)) return [invalid];
  if (![logs.stalled_orders, counts[STAGES[0]], counts[STAGES[1]], counts[STAGES[2]],
    proxy["200"], proxy["500"]].every(Number.isSafeInteger)) return [invalid];

  const started = counts[STAGES[0]];
  const charged = counts[STAGES[1]];
  const completed = counts[STAGES[2]];
  if (phase === "failure") {
    return metric.checkout_errors > 0 && metric.checkout_place_order_errors > 0 &&
      started >= 2 && logs.stalled_orders >= 2 && charged === 0 && completed === 0 &&
      proxy["500"] > 0 ? [] : [`cycle_${cycle}_failure_signal_missing`];
  }
  return metric.checkout_errors === 0 && metric.checkout_place_order_errors === 0 &&
    started > 0 && charged > 0 && completed > 0 && logs.stalled_orders <= 1 &&
    proxy["200"] > 0 && proxy["500"] === 0 ? [] : [`cycle_${cycle}_${phase}_baseline_missing`];
}

function chronologyValid(reports) {
  for (let index = 1; index < reports.length; index += 1) {
    const previousCapture = Date.parse(reports[index - 1]?.captured_at);
    const nextSettled = Date.parse(reports[index]?.settled_since);
    const nextCapture = Date.parse(reports[index]?.captured_at);
    const sameResetWindow = index === 3 &&
      nextSettled === Date.parse(reports[index - 1]?.settled_since);
    if (!Number.isFinite(previousCapture) || !Number.isFinite(nextSettled) ||
        !Number.isFinite(nextCapture) || (nextSettled < previousCapture && !sameResetWindow) ||
        nextCapture <= previousCapture) return false;
  }
  return true;
}

function failure(code) {
  return { schema: SUMMARY_SCHEMA, status: "fail", cycles_verified: 0,
    failures: [code], cycles: [] };
}

async function verify(paths) {
  if (paths.length !== 6) return failure("six_cycle_reports_required");
  const reports = await Promise.all(paths.map(readReport));
  const failures = [];
  for (let index = 0; index < PHASES.length; index += 1) {
    failures.push(...observationFailures(reports[index], Math.floor(index / 3) + 1, PHASES[index]));
  }
  if (!chronologyValid(reports)) failures.push("cycle_chronology_invalid");
  const safeFailures = [...new Set(failures)].sort();
  return {
    schema: SUMMARY_SCHEMA,
    status: safeFailures.length ? "fail" : "pass",
    cycles_verified: safeFailures.length ? 0 : 2,
    failures: safeFailures,
    cycles: [1, 2].map((cycle) => ({ cycle, phases: PHASES.slice((cycle - 1) * 3, cycle * 3) })),
  };
}

const args = process.argv.slice(2);
const result = args[0] === "verify" ? await verify(args.slice(1)) : failure("arguments_invalid");
process.stdout.write(`${JSON.stringify(result)}\n`);
process.exitCode = result.status === "pass" ? 0 : 1;
