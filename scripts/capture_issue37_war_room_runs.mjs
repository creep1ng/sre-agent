// Real evidence for issue #37 T1 (HU-OPS demo, Monday Oct 19): opens the console
// war room against the REAL compose stack, starts the investigation of the
// stamped incident with the demo-human operator, waits for the projected run
// strip and captures docs/evidence/37-war-room-run-start.png.
//
// Runs in the e2e container on the stack network, after scripts/seed_war_room_runs.py
// seeded SEED_STAMP; DEMO_HUMAN_API_KEY comes from the e2e service environment:
//   docker compose --profile e2e run --rm --no-deps -v ./scripts:/e2e/scripts:ro \
//     -v ./docs/evidence:/e2e/docs/evidence -e PLAYWRIGHT_BASE_URL=http://web \
//     -e SEED_STAMP=<stamp> e2e node scripts/capture_issue37_war_room_runs.mjs
import { chromium } from "@playwright/test";
import { connectConsole } from "../tests/browser/support/console-session.mjs";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:8091";
const key = process.env.DEMO_HUMAN_API_KEY;
const stamp = process.env.SEED_STAMP;
if (!key) throw new Error("DEMO_HUMAN_API_KEY is required.");
if (!stamp) throw new Error("SEED_STAMP is required.");
const incident = `inc-37-start-${stamp}`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
try {
  await page.goto(`${baseURL}/public/incident-ui/war-room.html?incident_id=${incident}`);
  await connectConsole(page, key);

  await page.locator("#run-start").waitFor({ state: "visible" });
  await page.locator("#run-start").click();
  await page.locator("#run-state").waitFor({ state: "visible" });
  await page
    .locator("#run-select option")
    .first()
    .waitFor({ state: "attached" });
  await page.waitForTimeout(400);
  // One single-shot capture: the viewport grows to the real content height,
  // so no sticky-header stitching ever enters the evidence.
  const contentHeight = await page.evaluate(() => document.body.scrollHeight);
  await page.setViewportSize({ width: 1440, height: Math.min(contentHeight, 4000) });
  await page.waitForTimeout(200);
  await page.screenshot({ path: "docs/evidence/37-war-room-run-start.png" });
  const runId = await page.locator("#run-select").inputValue();
  const strip = (await page.locator("#run-state").textContent()) ?? "";
  console.log(
    JSON.stringify({ incident, run_id: runId, strip: strip.trim().slice(0, 120), url: page.url() }),
  );
} finally {
  await browser.close();
}
