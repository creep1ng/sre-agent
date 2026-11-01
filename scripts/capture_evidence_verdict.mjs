// Browser evidence for #707 against the REAL stack of compose.evidence-verdict-e2e.yaml: opens
// the war room of each incident scripts/evidence_verdict_e2e.py investigated, as the demo
// operator, and writes one PNG of the recorded reasoning per scenario. No route is mocked.
// Env: PLAYWRIGHT_BASE_URL, DEMO_HUMAN_API_KEY, EVIDENCE_DIR (holds evidence-verdict-e2e.json).
import { readFileSync } from "node:fs";
import { chromium, expect } from "@playwright/test";
import { connectConsole } from "../tests/browser/support/console-session.mjs";

const out = process.env.EVIDENCE_DIR ?? "/artifacts";
const runs = JSON.parse(readFileSync(`${out}/evidence-verdict-e2e.json`, "utf8"));
const browser = await chromium.launch();
const page = await browser.newPage({ baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://web" });
page.setViewportSize({ width: 1280, height: 1100 });
for (const [scenario, { incident, evidence: found = [] }] of Object.entries(runs)) {
  if (!incident) continue;
  await page.goto(`/public/incident-ui/war-room.html?incident_id=${incident}`);
  await connectConsole(page, process.env.DEMO_HUMAN_API_KEY);
  await expect(page.locator("#reasoning-section")).toBeVisible({ timeout: 30_000 });
  // A run whose only hypothesis was rejected (#760) records no evidence: its timeline says why.
  if (found.some((item) => item.empty)) {
    await expect(page.locator("#evidence-block")).toContainText("No encontró nada");
  }
  await page.screenshot({ path: `${out}/war-room-${scenario}.png`, fullPage: true });
}
await browser.close();
