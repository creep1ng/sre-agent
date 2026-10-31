import { expect, test, type Page } from "@playwright/test";

/*
 * RC-2 languages (#870): the console starts in the browser's language (Spanish unless it is
 * English), the account menu switches between Spanish and English, and the choice survives a
 * reload. Only the shell chrome is translated so far; each screen adds its own namespace.
 * Screenshots land in e2e/artifacts/issue-870.
 */

const SHOTS = "e2e/artifacts/issue-870";

async function freshStart(page: Page) {
  await page.goto("./?mock");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
}

const sidebar = (page: Page) => page.getByRole("complementary");

async function chooseLanguage(page: Page, label: "Español" | "English") {
  await sidebar(page).getByRole("button", { name: /demo-human/ }).click();
  await page.getByRole("menuitemradio", { name: label }).click();
}

async function expectSpanish(page: Page) {
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  await expect(sidebar(page).getByRole("navigation", { name: "Principal" }).getByRole("link")).toHaveText([/Bandeja/, /Incidentes/]);
  await expect(sidebar(page).getByRole("link", { name: /Gobierno de IA/ })).toBeVisible();
  await expect(sidebar(page).getByText("Agente de incidentes")).toBeVisible();
}

async function expectEnglish(page: Page) {
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(sidebar(page).getByRole("navigation", { name: "Main" }).getByRole("link")).toHaveText([/Inbox/, /Incidents/]);
  await expect(sidebar(page).getByRole("link", { name: /AI governance/ })).toBeVisible();
  await expect(sidebar(page).getByText("Incident agent")).toBeVisible();
}

test("a Spanish browser starts in Spanish and switches to English and back", async ({ page }) => {
  await freshStart(page);
  await expectSpanish(page);

  await chooseLanguage(page, "English");
  await expectEnglish(page);
  await page.reload();
  await expectEnglish(page);

  await sidebar(page).getByRole("button", { name: /demo-human/ }).click();
  await expect(page.getByRole("menuitemradio", { name: "English" })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("menuitemradio", { name: "Dark" })).toBeVisible();
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${SHOTS}/account-menu-en.png` });
  await page.keyboard.press("Escape");

  await chooseLanguage(page, "Español");
  await expectSpanish(page);
  await page.reload();
  await expectSpanish(page);
});

test.describe("an English browser", () => {
  test.use({ locale: "en-US" });

  test("starts in English, and a stored Spanish choice wins over it", async ({ page }) => {
    await freshStart(page);
    await expectEnglish(page);

    await chooseLanguage(page, "Español");
    await page.reload();
    await expectSpanish(page);
  });

  test("shows the shell in English in both themes", async ({ page }) => {
    for (const theme of ["dark", "light"] as const) {
      await page.emulateMedia({ colorScheme: theme });
      await freshStart(page);
      await expectEnglish(page);
      await page.waitForTimeout(600);
      await page.screenshot({ path: `${SHOTS}/console-${theme}-en.png` });
    }
  });
});
