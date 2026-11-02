import { expect, test } from "@playwright/test";

/*
 * The web proxy serves the new console at /app next to the previous console, which keeps the
 * views /app does not replace yet (#870). Deep links into the new console survive a reload.
 */

test("el proxy sirve la consola nueva en /app y la anterior sigue en sus vistas pendientes", async ({ page }) => {
  // The demo journey below is the simulated one; live is the production default.
  const app = await page.goto("/app/?mock");
  expect(app?.status()).toBe(200);
  await expect(page).toHaveURL(/\/app\/$/);
  await expect(page.getByRole("navigation", { name: "Principal" })).toBeVisible();

  await page.goto("/app/incidentes/INC-11");
  await expect(page.getByRole("heading", { name: "Incidente cerrado" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Incidente cerrado" })).toBeVisible();
  await page.screenshot({ path: "e2e/artifacts/proxy/app-incidente-cerrado.png" });

  const current = await page.goto("/?view=decisions");
  expect(current?.status()).toBe(200);
  await expect(page.getByRole("navigation", { name: "Superficies" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Principal" })).toHaveCount(0);
  await page.screenshot({ path: "e2e/artifacts/proxy/consola-actual.png" });

  const health = await page.request.get("/health");
  expect(await health.text()).toBe("ok\n");
});
