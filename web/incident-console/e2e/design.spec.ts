import { expect, test, type Locator, type Page } from "@playwright/test";

/*
 * The design the maintainer chose: the service filter is a menu, the story is a column beside
 * the incident with findings and decisions unfolding inside it, the closure is summed up as a
 * timeline, and the agent has its own violet. Screenshots land in e2e/artifacts/design.
 */

const SHOTS = "e2e/artifacts/design";
const AGENT_VIOLET = "rgb(102, 85, 199)";
const INK = "rgb(30, 39, 73)";

const settle = (page: Page) => page.waitForTimeout(600);

/** Screenshots without leftover toasts. */
async function quiet(page: Page) {
  await expect(page.locator("[data-sonner-toast]")).toHaveCount(0, { timeout: 10_000 });
  await settle(page);
}

async function freshStart(page: Page) {
  await page.goto("./");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("3 cosas necesitan tu atención");
}

const headline = (page: Page) => page.getByRole("heading", { level: 1 });

test("el filtro de servicios es un menú junto al titular y filtra la bandeja", async ({ page }) => {
  await freshStart(page);
  await expect(page.getByRole("group", { name: "Filtrar por servicio" })).toHaveCount(0);

  const filter = page.getByRole("button", { name: /Filtrar por servicio/ });
  await expect(filter).toContainText("Todos los servicios");
  await filter.click();
  await expect(page.getByRole("menuitemradio")).toHaveText([/Todos los servicios\s*3/, /^checkout/, /^recommendation/, /^ad/]);
  await settle(page);
  await page.screenshot({ path: `${SHOTS}/filtro-menu.png`, clip: { x: 256, y: 0, width: 1184, height: 440 } });

  await page.getByRole("menuitemradio", { name: /^recommendation/ }).click();
  await expect(headline(page)).toHaveText("1 cosa necesita tu atención");
  await expect(filter).toContainText("recommendation");

  await filter.click();
  await page.getByRole("menuitemradio", { name: /^Todos los servicios/ }).click();
  await expect(headline(page)).toHaveText("3 cosas necesitan tu atención");
});

test("la historia va en una columna al lado, con hallazgos y decisiones dentro, y el agente en violeta", async ({ page }) => {
  await freshStart(page);
  await page
    .locator("article", { has: page.getByRole("heading", { name: "Pagos fallando en checkout" }) })
    .getByRole("button", { name: "Declarar incidente" })
    .click();
  await page.getByRole("dialog").getByRole("button", { name: /Declarar e investigar/ }).click();
  await expect(page.getByRole("heading", { name: "El agente propone una mitigación" })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Aprobar mitigación" }).click();
  await page.getByRole("button", { name: "Ya la apliqué" }).click();
  await expect(page.getByText("Está vigilando la señal para confirmar la recuperación").first()).toBeVisible();

  // Sin tarjeta: una columna al lado del incidente, siempre visible.
  const rail = page.getByRole("complementary", { name: "Historia del incidente" });
  await expect(rail).toBeVisible();
  await expect(rail.getByText("Agente", { exact: true }).first()).toHaveCSS("color", AGENT_VIOLET);
  await expect(rail.getByText("Tú", { exact: true }).first()).toHaveCSS("color", INK);

  // Hallazgos y decisiones no viven en bloques aparte: cada entrada de la historia se despliega.
  await expect(page.getByRole("region", { name: "Hallazgos y decisiones" })).toHaveCount(0);
  await rail.getByRole("button", { name: /Propuso una hipótesis con confianza alta/ }).click();
  await expect(rail.getByText("Qué la descartaría:")).toBeVisible();
  await rail.getByRole("button", { name: /1.284 errores «Unavailable» en checkout/ }).click();
  await expect(rail.getByRole("button", { name: "Ver la consulta" })).toBeVisible();

  await page.mouse.move(700, 120);
  await page.evaluate(() => window.scrollTo(0, 0));
  await quiet(page);
  await page.screenshot({ path: `${SHOTS}/historia-columna.png` });
  await page.emulateMedia({ colorScheme: "dark" });
  await settle(page);
  await page.screenshot({ path: `${SHOTS}/historia-columna-oscuro.png` });
});

test("el cierre se resume como línea de tiempo, sin tarjetas ni listas", async ({ page }) => {
  await freshStart(page);
  await page.goto("incidentes/INC-11");
  await expect(page.getByRole("heading", { name: "Incidente cerrado" })).toBeVisible();
  const panel: Locator = page.locator("section", { has: page.getByRole("heading", { name: "Incidente cerrado" }) });
  await expect(panel.getByText("Hasta detectarlo")).toHaveCount(0);

  const phases = panel.getByRole("group", { name: "En qué se fue el tiempo" }).getByRole("button");
  await expect(phases).toHaveCount(3);
  await expect(phases.nth(0)).toHaveAccessibleName(/^Detectar: /);
  await panel.getByRole("button", { name: "Ver los datos" }).click();
  await expect(panel.getByRole("table").getByRole("row")).toHaveCount(4);
  await panel.getByRole("button", { name: "Ocultar los datos" }).click();
  await settle(page);
  await panel.screenshot({ path: `${SHOTS}/cierre-linea-de-tiempo.png` });
});
