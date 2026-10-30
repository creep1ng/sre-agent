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
for (const [scenario, { incident }] of Object.entries(runs)) {
  await page.goto(`/public/incident-ui/war-room.html?incident_id=${incident}`);
  await connectConsole(page, process.env.DEMO_HUMAN_API_KEY);
  const evidence = page.locator("#evidence-block");
  await expect(evidence).toBeVisible({ timeout: 30_000 });
  await expect(evidence).toContainText("No encontró nada");
  await page.locator("#reasoning-section").screenshot({ path: `${out}/war-room-${scenario}.png` });
}
await browser.close();
