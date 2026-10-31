// Screenshot an incident's war room (#718) and, with ADMIN_HUMAN_API_KEY, the audit view of the
// investigator's denied calls. Env: BASE_URL, DEMO_HUMAN_API_KEY, OUT, and INCIDENT_ID or REPORT
// (the E2E's bok-topology-e2e.json, whose revoked incident is taken).
import { readFileSync } from "node:fs";
import { chromium } from "@playwright/test";
const { BASE_URL, DEMO_HUMAN_API_KEY: key, ADMIN_HUMAN_API_KEY: admin, OUT, REPORT } = process.env;
const incident = process.env.INCIDENT_ID ?? JSON.parse(readFileSync(REPORT)).revoked.incident_id;
const prefix = process.env.INCIDENT_ID ? "war-room" : "revoked-war-room";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
await page.goto(`${BASE_URL}/public/incident-ui/war-room.html?incident_id=${incident}`);
if (await page.locator("#console-session").isHidden()) await page.locator("#session-chip").click();
await page.locator("#api-key").fill(key);
await page.locator("#connect-button").click();
await page.locator("#hypothesis-block").waitFor({ state: "visible", timeout: 30000 });
await page.locator("#reasoning-section").scrollIntoViewIfNeeded();
await page.waitForTimeout(1500);
await page.locator("#reasoning-section").screenshot({ path: `${OUT}/${prefix}-reasoning.png` });
await page.screenshot({ path: `${OUT}/${prefix}-full.png`, fullPage: true });
if (admin) {
  await page.goto(`${BASE_URL}/public/admin/audit-events.html`);
  await page.locator("#api-key").fill(admin);
  await page.locator("#connect-button").click();
  await page.locator("#filter-principal-id").fill("incident-harness");
  await page.locator("#filter-decision").fill("deny");
  await page.locator("#apply-button").click();
  await page.locator("#event-rows tr").first().waitFor({ timeout: 30000 });
  await page.screenshot({ path: `${OUT}/revoked-audit-denied.png`, fullPage: true });
}
await browser.close();
