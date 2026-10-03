// Containerized E2E-style probe for PR #461 (issue #143, S1B consumption page).
// Drives the REAL page (/public/admin/consumption.html served by the web
// container) against the REAL endpoint (/api/v1/usage/consumption via the web
// proxy to the api container) with CONTROLLED data (month 2026-09, incident-a,
// both empty complete scopes) and one explicitly labeled ARTIFICIAL delay:
// the Playwright route calls route.fetch() to the real endpoint first, waits
// 1500 ms, then fulfills. Delayed runs are therefore real-endpoint responses
// delivered late; nothing is mocked. Credential values are never printed or
// recorded; only roles (admin-a, restricted-b) appear in the transcript.
import { chromium } from "@playwright/test";
import { createHash } from "node:crypto";
import { writeFileSync } from "node:fs";

const BASE = process.env.PLAYWRIGHT_BASE_URL || "http://web";
const PAGE_URL = `${BASE}/public/admin/consumption.html`;
const DELAY_MS = 1500;
const LATE_WINDOW_MS = 3500;
const OUT = process.argv[2] || "pr461-traversals.json";
const IDLE_TEXT = "Choose a filter and load consumption.";

const ADMIN_A = process.env.ADMIN_HUMAN_API_KEY || "";
const RESTRICTED_B = process.env.RESTRICTED_HARNESS_API_KEY || "";
if (!ADMIN_A || !RESTRICTED_B) {
  console.error("missing ADMIN_HUMAN_API_KEY or RESTRICTED_HARNESS_API_KEY");
  process.exit(2);
}

const findings = [];
const check = (id, ok, detail) => {
  findings.push({ id, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${id} :: ${detail}`);
};

async function pageState(page) {
  return page.evaluate((idle) => {
    const byId = (x) => document.getElementById(x);
    return {
      dataState: byId("consumption-page")?.dataset.state ?? "?",
      status: byId("result-status")?.textContent ?? "?",
      resultHidden: !!byId("result-list")?.hidden,
      loadingHidden: !!byId("result-loading")?.hidden,
      scopeHidden: !!byId("result-scope-note")?.hidden,
      monthHidden: !!byId("result-month-note")?.hidden,
      apiKeyEmpty: (byId("api-key")?.value ?? "?") === "",
      requestCount: byId("summary-request-count")?.textContent ?? "?",
      monthText: byId("summary-month")?.textContent ?? "?",
      monthInput: byId("consumption-month")?.value ?? "?",
      incidentInput: byId("incident-id")?.value ?? "?",
      idleText: idle,
    };
  }, IDLE_TEXT);
}

async function connectAs(page, key, role) {
  await page.fill("#api-key", key);
  await page.click("#connect-button");
  return role;
}

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const consoleErrors = [];
  page.on("console", (m) => {
    if (
      m.type() === "error" &&
      !m.text().includes("Content Security Policy") &&
      !m.text().startsWith("Failed to load resource")
    )
      consoleErrors.push(m.text());
  });
  page.on("pageerror", (e) => consoleErrors.push(String(e?.message ?? e)));

  const apiLog = [];
  const installDelayedRoute = async (phase) =>
    page.route("**/api/v1/usage/consumption**", async (route) => {
      const response = await route.fetch();
      apiLog.push({
        phase,
        method: route.request().method(),
        query: new URL(route.request().url()).searchParams.toString(),
        status: response.status(),
        delayed_ms: DELAY_MS,
      });
      await new Promise((r) => setTimeout(r, DELAY_MS));
      await route.fulfill({ response });
    });

  await page.goto(PAGE_URL, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(
    () => document.getElementById("consumption-page")?.dataset.state === "idle",
    null,
    { timeout: 20000 },
  );

  const asset = await page.evaluate(async () => {
    const res = await fetch("/public/admin/consumption.js", { cache: "no-store" });
    const text = await res.text();
    return { status: res.status, bytes: text.length, text };
  });
  const servedAsset = {
    path: "/public/admin/consumption.js",
    http: asset.status,
    bytes: asset.bytes,
    sha256_16: createHash("sha256").update(asset.text).digest("hex").slice(0, 16),
  };

  // T1: pending query + filter change. Real month query delayed; switch filter
  // while pending; the late month response must not render under incident.
  await connectAs(page, ADMIN_A, "admin-a");
  await page.click("#filter-month");
  await page.fill("#consumption-month", "2026-09");
  await installDelayedRoute("T1-pending-month");
  await page.click("#query-submit");
  await page.waitForFunction(
    () => document.getElementById("consumption-page")?.dataset.state === "loading",
    null,
    { timeout: 20000 },
  );
  await page.click("#filter-incident");
  await page.waitForFunction(
    () => document.getElementById("consumption-page")?.dataset.state === "idle",
    null,
    { timeout: 5000 },
  );
  const t1switch = await pageState(page);
  await page.waitForTimeout(LATE_WINDOW_MS);
  const t1late = await pageState(page);
  const t1log = apiLog.filter((e) => e.phase === "T1-pending-month");
  const t1ok =
    t1switch.dataState === "idle" &&
    t1switch.resultHidden &&
    t1switch.status === IDLE_TEXT &&
    t1late.dataState === "idle" &&
    t1late.resultHidden &&
    t1late.status === IDLE_TEXT &&
    t1late.monthInput === "" &&
    t1log.length === 1 &&
    t1log[0].status === 200;
  check(
    "T1",
    t1ok,
    `pending month query then filter switch: late status=${t1log[0]?.status ?? "none"} ` +
      `discarded=${t1late.resultHidden && t1late.dataState === "idle"} ` +
      `status=${JSON.stringify(t1late.status)}`,
  );
  const t1 = { id: "T1", pass: t1ok, atSwitch: t1switch, afterLateWindow: t1late, delayedCall: t1log[0] ?? null };

  // T2: data loaded with A + Connect B clears immediately (fast real query).
  await page.unrouteAll({ behavior: "wait" });
  await page.click("#filter-month");
  await connectAs(page, ADMIN_A, "admin-a");
  await page.fill("#consumption-month", "2026-09");
  await page.click("#query-submit");
  await page.waitForFunction(
    () => document.getElementById("consumption-page")?.dataset.state === "ready",
    null,
    { timeout: 20000 },
  );
  const t2loaded = await pageState(page);
  const t0 = Date.now();
  await connectAs(page, RESTRICTED_B, "restricted-b");
  const t2cleared = await pageState(page);
  const clearLatencyMs = Date.now() - t0;
  await page.waitForTimeout(1500);
  const t2settled = await pageState(page);
  const t2ok =
    t2loaded.dataState === "ready" &&
    !t2loaded.resultHidden &&
    t2loaded.requestCount === "0" &&
    t2cleared.dataState === "idle" &&
    t2cleared.resultHidden &&
    t2cleared.status === IDLE_TEXT &&
    t2cleared.apiKeyEmpty &&
    t2settled.dataState === "idle" &&
    t2settled.resultHidden;
  check(
    "T2",
    t2ok,
    `loaded request_count=${t2loaded.requestCount} then Connect B cleared in ~${clearLatencyMs}ms ` +
      `immediate=${t2cleared.resultHidden && t2cleared.dataState === "idle"} settled=${t2settled.dataState}`,
  );
  const t2 = { id: "T2", pass: t2ok, loaded: t2loaded, cleared: t2cleared, settled: t2settled, clearLatencyMs };

  // T3: pending A query + Connect B discards the late A response.
  await connectAs(page, ADMIN_A, "admin-a");
  await page.click("#filter-month");
  await page.fill("#consumption-month", "2026-09");
  await installDelayedRoute("T3-pending-A");
  await page.click("#query-submit");
  await page.waitForFunction(
    () => document.getElementById("consumption-page")?.dataset.state === "loading",
    null,
    { timeout: 20000 },
  );
  await connectAs(page, RESTRICTED_B, "restricted-b");
  const t3cleared = await pageState(page);
  await page.waitForTimeout(LATE_WINDOW_MS);
  const t3late = await pageState(page);
  const t3log = apiLog.filter((e) => e.phase === "T3-pending-A");
  const t3ok =
    t3cleared.dataState === "idle" &&
    t3cleared.resultHidden &&
    t3cleared.apiKeyEmpty &&
    t3late.dataState === "idle" &&
    t3late.resultHidden &&
    t3late.status === IDLE_TEXT &&
    t3log.length === 1 &&
    t3log[0].status === 200;
  check(
    "T3",
    t3ok,
    `pending A then Connect B: late A status=${t3log[0]?.status ?? "none"} ` +
      `discarded=${t3late.resultHidden && t3late.dataState === "idle"}`,
  );
  const t3 = { id: "T3", pass: t3ok, cleared: t3cleared, afterLateWindow: t3late, delayedCall: t3log[0] ?? null };

  // Baseline: real endpoint statuses with no artificial delay.
  await page.unrouteAll({ behavior: "wait" });
  const baseline = await page.evaluate(async ({ adminA, restrictedB }) => {
    const get = async (query, key) => {
      const headers = key ? { Authorization: `Bearer ${key}` } : {};
      const res = await fetch(`/api/v1/usage/consumption?${query}`, { headers, cache: "no-store" });
      let body = null;
      try {
        body = await res.json();
      } catch { /* non-JSON stays null */ }
      return { query, status: res.status, body };
    };
    return [
      await get("month=2026-09", adminA),
      await get("incident_id=incident-a", adminA),
      await get("request_id=not-a-uuid", adminA),
      await get("month=2026-09", null),
      await get("month=2026-09", restrictedB),
    ];
  }, { adminA: ADMIN_A, restrictedB: RESTRICTED_B });
  const slim = baseline.map(({ query, status, body }) => ({
    query,
    status,
    filter: body?.filter ?? null,
    request_count: body?.request_count ?? null,
    coverage: body?.coverage ?? null,
    error_code: body?.error?.code ?? null,
  }));
  const got = slim.map((e) => e.status);
  const baselineOk = JSON.stringify(got) === JSON.stringify([200, 200, 422, 401, 403]);
  check("BASELINE", baselineOk, `real endpoint statuses month/incident/malformed/no-auth/restricted = ${got.join("/")}`);
  const month200 = slim[0];
  const baselineFieldsOk =
    month200.filter?.month === "2026-09" &&
    month200.request_count === 0 &&
    month200.coverage?.status === "complete";
  check("BASELINE-FIELDS", baselineFieldsOk, `month 2026-09 filter/request_count/coverage = ${month200.filter?.month}/${month200.request_count}/${month200.coverage?.status}`);

  const consoleOk = consoleErrors.length === 0;
  check("CONSOLE", consoleOk, `page errors: ${consoleErrors.length ? JSON.stringify(consoleErrors).slice(0, 300) : "none"}`);

  const overall = [t1ok, t2ok, t3ok, baselineOk, baselineFieldsOk, consoleOk].every(Boolean);
  const transcript = {
    probe: "docs/evidence/pr461-traversals.probe.mjs",
    page_url: PAGE_URL,
    transport: "real page plus real endpoint through the web proxy; artificial delay injected only after route.fetch() to the real endpoint",
    artificial_delay_ms: DELAY_MS,
    late_window_ms: LATE_WINDOW_MS,
    controlled_data: { month: "2026-09", incident: "incident-a" },
    credentials: { admin_a: "ADMIN_HUMAN_API_KEY, value redacted", restricted_b: "RESTRICTED_HARNESS_API_KEY, value redacted" },
    served_asset: servedAsset,
    http_baseline: slim,
    traversals: [t1, t2, t3],
    console_errors: consoleErrors,
    overall: overall ? "pass" : "fail",
    sanitized: true,
  };
  writeFileSync(OUT, `${JSON.stringify(transcript, null, 2)}\n`);
  console.log(`OUT ${OUT} overall=${transcript.overall}`);
  await browser.close();
  process.exit(overall ? 0 : 1);
}

main().catch((error) => {
  console.error(`FATAL ${String(error?.message ?? error).slice(0, 300)}`);
  process.exit(1);
});
