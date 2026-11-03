import { mkdirSync } from "node:fs";
import { expect, test } from "@playwright/test";

/*
 * The incident page after run.sh: the failed verification, the runs the agent started on its own
 * and how it ended. Connects with DEMO_HUMAN_API_KEY, kept in this tab's memory only.
 */
const KEY = process.env.DEMO_HUMAN_API_KEY ?? "";
const INCIDENT = process.env.INCIDENT_ID ?? "";
const WEB = process.env.BASE_URL ?? "http://web";
const DIR = process.env.SHOTS ?? "e2e/artifacts/reinvestigate";

test.use({ video: "off", trace: "off", viewport: { width: 1440, height: 1100 } });

test("the incident page after a automatic re-investigation", async ({ page }) => {
  test.skip(!KEY || !INCIDENT, "needs DEMO_HUMAN_API_KEY and INCIDENT_ID");
  mkdirSync(DIR, { recursive: true });
  await page.goto(`${WEB}/app/`);
  await page.getByRole("button", { name: "Conectar API" }).click();
  await page.getByRole("dialog").getByLabel("Clave de API").fill(KEY);
  await page.getByRole("dialog").getByRole("button", { name: "Conectar", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).not.toHaveText(/API/, { timeout: 30_000 });
  // A reload would drop the key: route inside the app instead.
  await page.evaluate((to) => {
    history.pushState({}, "", to);
    dispatchEvent(new PopStateEvent("popstate"));
  }, `/app/incidentes/${INCIDENT}`);
  await expect(page.getByText(/intento|attempt/).first()).toBeVisible({ timeout: 30_000 });
  await page.mouse.move(0, 0);
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${DIR}/incident.png`, fullPage: true });
});
