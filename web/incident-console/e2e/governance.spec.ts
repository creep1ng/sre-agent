import { expect, test, type Page } from "@playwright/test";

/*
 * The administration console (principals, resources, grants, audit) still lives outside the
 * new console. The sidebar offers one link that opens it in another tab, so an operator keeps
 * the incident view where it was. Screenshots land in e2e/artifacts/governance.
 */

const SHOTS = "e2e/artifacts/governance";

const settle = (page: Page) => page.waitForTimeout(600);

async function freshStart(page: Page) {
  await page.goto("./?mock");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("3 cosas necesitan tu atención");
}

test("el gobierno de IA se abre desde la barra lateral en otra pestaña", async ({ page }) => {
  await freshStart(page);

  const link = page.getByRole("link", { name: /Gobierno de IA/ });
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute("target", "_blank");
  await expect(link).toHaveAttribute("rel", /noopener/);
  await expect(link).toHaveAttribute("href", "/public/admin/principals.html");
  await expect(page.getByRole("navigation", { name: "Administración" }).getByRole("link")).toHaveCount(1);

  await settle(page);
  await page.screenshot({ path: `${SHOTS}/barra-lateral-gobierno.png`, clip: { x: 0, y: 0, width: 256, height: 440 } });

  const popupPromise = page.waitForEvent("popup");
  await link.click();
  const admin = await popupPromise;
  await admin.waitForLoadState();

  await expect(admin).toHaveURL(/\/public\/admin\/principals\.html$/);
  await expect(admin.getByRole("heading", { level: 1 })).toHaveText("Principals", { timeout: 15_000 });
  await expect(admin.getByRole("heading", { level: 1 })).toBeVisible();
  await settle(admin);
  await admin.screenshot({ path: `${SHOTS}/administracion-principals.png` });

  // The new console stays where it was: the link opened elsewhere.
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("3 cosas necesitan tu atención");
});
