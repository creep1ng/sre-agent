import { expect, test, type Page } from "@playwright/test";

/*
 * RC-2 navigation (#870): sections read in the text face with one icon each, live mode lists only
 * screens backed by the API, and the sidebar folds to an icon rail that a reload remembers.
 * Muted text keeps 4.5:1 on the sidebar in both themes. Screenshots land in
 * e2e/artifacts/issue-870/shell.
 */

const SHOTS = "e2e/artifacts/issue-870/shell";

async function freshStart(page: Page, path = "./?mock") {
  await page.goto(path);
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
}

const sidebar = (page: Page) => page.getByRole("complementary");
const mainNav = (page: Page) => sidebar(page).getByRole("navigation", { name: "Principal" });

test("each section is a word in the text face with its own icon", async ({ page }) => {
  await freshStart(page);
  const links = mainNav(page).getByRole("link");
  await expect(links).toHaveText([/Bandeja/, /Incidentes/, /Acciones/]);
  for (const link of await links.all()) {
    await expect(link.locator("svg.lucide")).toHaveCount(1);
    await expect(link.locator("span").first()).toHaveCSS("font-family", /Newsreader/);
  }
  await expect(sidebar(page).getByRole("link", { name: "Gobierno de IA" }).locator("svg.lucide").first()).toBeVisible();
});

test("live mode lists only sections backed by the API", async ({ page }) => {
  await freshStart(page, "./");
  await expect(mainNav(page).getByRole("link")).toHaveText([/Bandeja/, /Acciones/]);
  await page.keyboard.press("Control+k");
  const search = page.getByRole("dialog", { name: "Buscar" });
  await expect(search.getByRole("option")).toHaveText([/Bandeja/, /Acciones/]);
});

test("the sidebar folds from the keyboard and a reload remembers it", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await freshStart(page);
  const fold = sidebar(page).getByRole("button", { name: "Plegar navegación" });
  await expect(fold).toHaveAttribute("aria-expanded", "true");

  await fold.focus();
  await page.keyboard.press("Enter");
  const unfold = sidebar(page).getByRole("button", { name: "Desplegar navegación" });
  await expect(unfold).toHaveAttribute("aria-expanded", "false");
  await expect(sidebar(page)).toHaveCSS("width", "64px");
  // Folded labels leave the screen but keep naming the links.
  await expect(mainNav(page).getByRole("link", { name: "Bandeja" })).toBeVisible();
  await expect(mainNav(page).getByText("Bandeja")).not.toBeInViewport();

  await page.reload();
  await expect(unfold).toHaveAttribute("aria-expanded", "false");
  await expect(sidebar(page)).toHaveCSS("width", "64px");
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${SHOTS}/sidebar-folded-dark-es.png` });

  await unfold.focus();
  await page.keyboard.press("Space");
  await page.reload();
  await expect(fold).toHaveAttribute("aria-expanded", "true");
  await expect(sidebar(page)).toHaveCSS("width", "256px");
});

/** WCAG relative-luminance contrast of two computed rgb() colours. */
function ratio(a: string, b: string) {
  const luminance = (rgb: string) => {
    const [r, g, bl] = rgb.match(/\d+(\.\d+)?/g)!.slice(0, 3).map((v) => {
      const c = Number(v) / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  };
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

test("muted text keeps 4.5:1 on the sidebar and the page in both themes", async ({ page }) => {
  for (const theme of ["dark", "light"] as const) {
    await page.emulateMedia({ colorScheme: theme });
    await freshStart(page);
    const muted = await sidebar(page).getByText("Disponible").evaluate((el) => getComputedStyle(el).color);
    const surfaces = [
      await sidebar(page).evaluate((el) => getComputedStyle(el).backgroundColor),
      await page.locator("body").evaluate((el) => getComputedStyle(el).backgroundColor),
    ];
    for (const surface of surfaces) expect(ratio(muted, surface), `${theme} ${muted} on ${surface}`).toBeGreaterThanOrEqual(4.5);
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${SHOTS}/navigation-${theme}-es.png` });
  }
});
