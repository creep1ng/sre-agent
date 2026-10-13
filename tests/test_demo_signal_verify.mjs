import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SCRIPT = fileURLToPath(new URL("../scripts/demo_signal_verify.mjs", import.meta.url));
const MARKER = "private-upstream-marker";
const BASE = Date.parse("2026-10-13T00:00:00Z");
const phases = ["baseline", "failure", "reset", "baseline", "failure", "reset"];

function fixture(index) {
  const cycle = Math.floor(index / 3) + 1;
  const phase = phases[index];
  const failed = phase === "failure";
  const captured = BASE + index * 240_000;
  return {
    schema: "sre-agent.mcp45-3-signal-capture/v1", status: "observed",
    cycle, phase, captured_at: new Date(captured).toISOString(),
    settled_since: new Date(captured - 151_000).toISOString(), settled_for_seconds: 151,
    failures: [],
    metric: { source: "webstore-metrics", window: "increase(...[2m]) @ now",
      checkout_errors: failed ? 12 : 0, checkout_place_order_errors: failed ? 4 : 0 },
    logs: { source: "webstore-logs/otel-logs-*", window: "now-2m..now",
      stage_counts: { "[PlaceOrder]": 3, "payment went through": failed ? 0 : 3,
        "order placed": failed ? 0 : 3 },
      stalled_orders: failed ? 3 : 0,
      proxy_checkout_statuses: { "200": failed ? 0 : 3, "500": failed ? 3 : 0 } },
    ignored_private_detail: MARKER,
  };
}

function runCli(paths) {
  return new Promise((done, reject) => {
    const child = spawn(process.execPath, [SCRIPT, "verify", ...paths], {
      env: { PATH: process.env.PATH }, stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    const timer = setTimeout(() => child.kill("SIGKILL"), 10_000);
    child.on("error", reject);
    child.on("close", (status) => { clearTimeout(timer); done({ status, stdout, stderr }); });
  });
}

test("offline CLI verifies two ordered fail-signal-reset cycles and rejects unsafe evidence", async () => {
  const dir = await mkdtemp(join(tmpdir(), "issue45-signal-verify-"));
  const paths = phases.map((_, i) => join(dir, `phase-${i}.json`));
  const reports = phases.map((_, i) => fixture(i));
  const writeReports = () => Promise.all(paths.map((path, i) => writeFile(path, JSON.stringify(reports[i]))));
  try {
    await writeReports();
    const success = await runCli(paths);
    assert.equal(success.status, 0, success.stderr || success.stdout);
    assert.equal(success.stderr, "");
    assert.ok(!success.stdout.includes(MARKER));
    const verified = JSON.parse(success.stdout);
    assert.equal(verified.schema, "sre-agent.mcp45-3-cycle-verification/v1");
    assert.equal(verified.status, "pass");
    assert.equal(verified.cycles_verified, 2);
    assert.deepEqual(verified.failures, []);

    reports[1].metric.checkout_errors = 0;
    await writeReports();
    const missingSignal = await runCli(paths);
    assert.equal(missingSignal.status, 1);
    assert.ok(JSON.parse(missingSignal.stdout).failures.includes("cycle_1_failure_signal_missing"));
    reports[1] = fixture(1);

    reports[3].settled_since = reports[2].settled_since;
    reports[3].settled_for_seconds = Math.floor((Date.parse(reports[3].captured_at) -
      Date.parse(reports[3].settled_since)) / 1000);
    await writeReports();
    const reusedResetWindow = await runCli(paths);
    assert.equal(reusedResetWindow.status, 0,
      "cycle 2 baseline may reuse the settled reset state from cycle 1");
    reports[3] = fixture(3);

    reports[3].settled_since = new Date(Date.parse(reports[2].captured_at) - 10_000).toISOString();
    reports[3].captured_at = new Date(Date.parse(reports[3].settled_since) + 151_000).toISOString();
    await writeReports();
    const overlap = await runCli(paths);
    assert.equal(overlap.status, 1);
    assert.ok(JSON.parse(overlap.stdout).failures.includes("cycle_chronology_invalid"));
    reports[3] = fixture(3);

    const incomplete = await runCli(paths.slice(0, 5));
    assert.equal(incomplete.status, 1);
    assert.deepEqual(JSON.parse(incomplete.stdout).failures, ["six_cycle_reports_required"]);
    reports[0].settled_for_seconds = 20;
    await writeReports();
    const unsettled = await runCli(paths);
    assert.equal(unsettled.status, 1);
    assert.ok(JSON.parse(unsettled.stdout).failures.includes("cycle_1_baseline_evidence_invalid"));
    assert.ok(!unsettled.stdout.includes(MARKER));
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
