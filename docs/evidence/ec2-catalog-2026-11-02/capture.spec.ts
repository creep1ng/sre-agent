import { mkdirSync } from "node:fs";
import { expect, test } from "@playwright/test";

/*
 * The incident page after flag.set ran (#724), for the PR evidence: connects the console with
 * DEMO_HUMAN_API_KEY (kept in this tab's memory only), opens INCIDENT_ID inside the app and saves
 * a full-page screenshot under SHOTS. Mount it into incident-console-e2e (see README.md).
 */
const KEY = process.env.DEMO_HUMAN_API_KEY ?? "";
const INCIDENT = process.env.INCIDENT_ID ?? "";
const DIR = process.env.SHOTS ?? "e2e/artifacts/flag-set";

test.use({ video: "off", trace: "off", viewport: { width: 1440, height: 1100 } });

test("incident page after the approved flag.set", async ({ page }) => {
  test.skip(!KEY || !INCIDENT, "needs DEMO_HUMAN_API_KEY and INCIDENT_ID");
  mkdirSync(DIR, { recursive: true });
  await page.goto(`${process.env.BASE_URL ?? "http://web"}/app/`);
  await page.getByRole("button", { name: "Conectar API" }).click();
  await page.getByRole("dialog").getByLabel("Clave de API").fill(KEY);
  await page.getByRole("dialog").getByRole("button", { name: "Conectar", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).not.toHaveText(/API/, { timeout: 30_000 });
  await page.screenshot({ path: `${DIR}/inbox.png`, fullPage: true });
  // A reload would drop the key: route inside the app instead.
  await page.evaluate((id) => {
    history.pushState({}, "", `/app/incidentes/${id}`);
    dispatchEvent(new PopStateEvent("popstate"));
  }, INCIDENT);
  await expect(page.getByText(/flag\.set/).first()).toBeVisible({ timeout: 30_000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${DIR}/incident.png`, fullPage: true });
});
