import { expect, test } from "@playwright/test";
import { connectConsole } from "./support/console-session.mjs";

// Issue #37 T1 acceptance against the REAL stack (compose web proxy + FastAPI +
// Postgres): start creates one run with the pinned body, a reload keeps it, a
// double click cannot create a second one, restricted-harness stays at 403, and
// 404/401 present their own states. Every seeded journey owns its stamped
// `active` incident (scripts/seed_war_room_runs.py), so no test depends on order
// or residual data. The static-web lane and any run without the compose
// environment skip: SRE_REAL_BACKEND=1, the demo/restricted keys and SEED_STAMP
// come from the PR's reproduction commands.
const STAMP = process.env.SEED_STAMP ?? "";
const ACTIVE = {
  start: STAMP ? `inc-37-start-${STAMP}` : "",
  double: STAMP ? `inc-37-double-${STAMP}` : "",
  restricted: STAMP ? `inc-37-restricted-${STAMP}` : "",
};
const DEMO_KEY = process.env.DEMO_HUMAN_API_KEY ?? "";
const RESTRICTED_KEY = process.env.RESTRICTED_HARNESS_API_KEY ?? "";
const REAL =
  process.env.SRE_REAL_BACKEND === "1" && Boolean(DEMO_KEY) && Boolean(RESTRICTED_KEY) && Boolean(STAMP);

test.skip(!REAL, "requires SRE_REAL_BACKEND=1, demo/restricted keys and a SEED_STAMP seed");

test("starting one investigation shows the created run and keeps it across reload", async ({
  page,
}) => {
  test.setTimeout(90_000);
  await page.goto(`/public/incident-ui/war-room.html?incident_id=${ACTIVE.start}`);
  await connectConsole(page, DEMO_KEY);

  await expect(page.locator("#run-start")).toBeVisible();
  await page.locator("#run-start").click();
  await expect(page.locator("#run-select option")).toHaveCount(1);
  const runId = await page.locator("#run-select").inputValue();
  expect(runId).toMatch(/^run_[0-9a-z]{8,32}$/);
  await expect(page.locator("#run-state")).toContainText(`${runId} ·`);
  // This stack has no Grafana MCP: the run ends with its cause instead of staying "en curso"
  // (#761, #705), and the incident offers a retry.
  await expect(page.locator("#run-terminated")).toHaveText(
    "Run terminado: Las herramientas de observabilidad no están configuradas o rechazaron la conexión (mcp_discovery_rejected).",
  );
  await expect(page.locator(".ma-timeline__detail", { hasText: "Causa:" }).first()).toBeVisible();
  await expect(page.locator("#run-start")).toHaveText("Reintentar investigación");

  // A reload re-derives the same run from the stored detail; nothing starts another one.
  await page.reload();
  await connectConsole(page, DEMO_KEY);
  await expect(page.locator("#run-select option")).toHaveCount(1);
  await expect(page.locator("#run-select")).toHaveValue(runId);

  // The retry opens a second run of the same incident.
  await page.locator("#run-start").click();
  await expect(page.locator("#run-select option")).toHaveCount(2);
  await expect(page.locator("#run-select")).not.toHaveValue(runId);
  await expect(page.locator("#run-terminated")).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("war-room-retry.png"), fullPage: true });
});

test("a double click keeps one run in detail.runs", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto(`/public/incident-ui/war-room.html?incident_id=${ACTIVE.double}`);
  await connectConsole(page, DEMO_KEY);

  await expect(page.locator("#run-start")).toBeVisible();
  await page.locator("#run-start").dblclick({ force: true });
  await expect(page.locator("#run-select option")).toHaveCount(1);
  const runId = await page.locator("#run-select").inputValue();
  expect(runId).toMatch(/^run_[0-9a-z]{8,32}$/);
  await expect(page.locator("#run-state")).toContainText(`${runId} ·`);
  await expect(page.locator("#run-start")).toHaveText("Reintentar investigación");
  await expect(page.locator("#run-select option")).toHaveCount(1);
});

test("restricted-harness stays at 403 without any success state", async ({ page }) => {
  await page.goto(`/public/incident-ui/war-room.html?incident_id=${ACTIVE.restricted}`);
  await connectConsole(page, RESTRICTED_KEY);

  await expect(page.locator("#error-403")).toBeVisible();
  await expect(page.locator("#summary-section")).toBeHidden();
  await expect(page.locator("#timeline-section")).toBeHidden();
  await expect(page.locator("#run-start")).toBeHidden();
  await expect(page.locator("#run-select option")).toHaveCount(0);
});

test("a proposed mitigation sends the operator to Decisiones", async ({ page }) => {
  await page.goto(`/public/incident-ui/war-room.html?incident_id=inc-37-decide-${STAMP}`);
  await connectConsole(page, DEMO_KEY);

  await expect(page.locator("#run-state")).toContainText("Mitigando");
  await expect(page.locator("#run-resume")).toBeHidden();
  await page.locator("#run-decide").click();
  await expect(page).toHaveURL(/[?&]view=decisions&incident_id=inc-37-decide-/);
  await expect(page.locator("#session-chip")).toHaveAttribute("data-phase", "active");
  await expect(page.getByRole("button", { name: "Aprobar mitigación" })).toBeVisible();
});

test("unknown incident and rejected credential surface 404 and 401", async ({ page }) => {
  await page.goto("/public/incident-ui/war-room.html?incident_id=inc-37-not-there");
  await connectConsole(page, DEMO_KEY);
  await expect(page.locator("#error-404")).toBeVisible();
  await expect(page.locator("#summary-section")).toBeHidden();

  await page.goto(`/public/incident-ui/war-room.html?incident_id=${ACTIVE.start}`);
  if (await page.locator("#console-session").isHidden()) await page.locator("#session-chip").click();
  await page.locator("#api-key").fill("sre_demo_wrong_key_00");
  await page.locator("#connect-button").click();
  await expect(page.locator("#error-401")).toBeVisible();
  await expect(page.locator("#summary-section")).toBeHidden();
});
