import { expect, test, type Page } from "@playwright/test";

/*
 * RC-2 account menu (#870): the avatar opens one popover with language, theme and the session.
 * Sign out drops the in-memory credential of the real API and returns to the credential screen.
 * Theme persistence and the system theme are covered by theme.spec.ts, the language switch by
 * language.spec.ts, both through this popover. Screenshots land in e2e/artifacts/issue-870/shell.
 */

const SHOTS = "e2e/artifacts/issue-870/shell";

// A trace would record the typed key; the screenshots are the artifact.
test.use({ video: "off", trace: "off" });

const sidebar = (page: Page) => page.getByRole("complementary");
const menu = (page: Page) => page.getByRole("dialog");

test("the popover shows language, theme and the session, in both themes and languages", async ({ page }) => {
  await page.goto("./?mock");
  await page.evaluate(() => localStorage.clear());
  for (const [language, account, theme, shown] of [
    ["Español", "Tu cuenta", "Oscuro", "dark-es"],
    ["Español", "Tu cuenta", "Claro", "light-es"],
    ["English", "Your account", "Dark", "dark-en"],
    ["English", "Your account", "Light", "light-en"],
  ] as const) {
    await page.reload();
    await sidebar(page).getByRole("button", { name: /Tu cuenta|Your account/ }).click();
    await menu(page).getByRole("button", { name: language }).click();
    await menu(page).getByRole("button", { name: theme }).click();
    await expect(sidebar(page).getByRole("button", { name: account })).toBeVisible();
    await expect(menu(page).getByRole("group")).toHaveCount(2);
    await expect(menu(page).getByRole("button", { name: theme })).toHaveAttribute("aria-pressed", "true");
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${SHOTS}/account-menu-${shown}.png` });
  }
});

test.describe("against the real API", () => {
  const key = process.env.DEMO_HUMAN_API_KEY;
  test.skip(!key, "Requires DEMO_HUMAN_API_KEY, which the e2e runner receives from the stack's .env");
  test("sign out drops the credential and returns to the credential screen", async ({ page }) => {
    await page.goto("./");
    await page.getByRole("main").getByRole("button", { name: "Conectar API" }).click();
    await page.getByRole("dialog").getByLabel("Clave de API").fill(key!);
    const polled = page.waitForResponse((response) => response.url().includes("/api/v1/alerts"));
    await page.getByRole("dialog").getByRole("button", { name: "Conectar", exact: true }).click();
    // The API knows the key: 200 with the demo grants, 403 on a bare stack without alert.read.
    expect([200, 403]).toContain((await polled).status());
    await expect(page.getByRole("main").getByRole("button", { name: "Conectar API" })).toHaveCount(0);

    // Keyboard only: open the popover from the avatar and sign out.
    await sidebar(page).getByRole("button", { name: "Tu cuenta" }).focus();
    await page.keyboard.press("Enter");
    await menu(page).getByRole("button", { name: "Cerrar sesión" }).focus();
    await page.keyboard.press("Enter");

    await expect(menu(page)).toHaveCount(0);
    await expect(page.getByRole("main").getByRole("button", { name: "Conectar API" })).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/signed-out-light-es.png` });

    // Nothing is left to reuse: the popover offers to connect, and the dialog starts empty.
    await sidebar(page).getByRole("button", { name: "Tu cuenta" }).click();
    await expect(menu(page).getByRole("button", { name: "Cerrar sesión" })).toHaveCount(0);
    await menu(page).getByRole("button", { name: "Conectar API" }).click();
    await expect(page.getByRole("dialog").getByLabel("Clave de API")).toHaveValue("");
  });
});
