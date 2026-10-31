import { expect, test, type Page } from "@playwright/test";

/*
 * RC-2 tokens (#870): the console follows the OS in Nocturno night and day. Amber appears only
 * where a human decision is pending, so the shell itself paints no amber. Screenshots land in
 * e2e/artifacts/issue-870.
 */

const SHOTS = "e2e/artifacts/issue-870";
const NIGHT = "rgb(10, 14, 29)";
const PAPER = "rgb(247, 245, 251)";
const AMBER = ["rgb(242, 180, 90)", "rgb(166, 90, 0)"];

async function freshStart(page: Page) {
  await page.goto("./?mock");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
}

async function expectTheme(page: Page, theme: "light" | "dark") {
  const dark = /\bdark\b/;
  if (theme === "dark") await expect(page.locator("html")).toHaveClass(dark);
  else await expect(page.locator("html")).not.toHaveClass(dark);
  await expect(page.locator("body")).toHaveCSS("background-color", theme === "dark" ? NIGHT : PAPER);
}

/** Every painted colour of the visible page, so a stray amber cannot hide in a border or an icon. */
function paintedColours(page: Page) {
  return page.evaluate(() => {
    const seen = new Set<string>();
    for (const element of document.querySelectorAll("body *")) {
      const style = getComputedStyle(element);
      for (const value of [style.color, style.backgroundColor, style.borderTopColor, style.borderLeftColor, style.fill, style.stroke]) {
        seen.add(value);
      }
    }
    return [...seen];
  });
}

test("the console follows the system theme and repaints when it changes", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await freshStart(page);
  await expectTheme(page, "dark");
  await expect(page.getByRole("heading", { level: 1 })).toHaveCSS("font-family", /Fraunces/);

  await page.emulateMedia({ colorScheme: "light" });
  await expectTheme(page, "light");
});

test("the shell paints no amber in either theme", async ({ page }) => {
  for (const theme of ["dark", "light"] as const) {
    await page.emulateMedia({ colorScheme: theme });
    await freshStart(page);
    await expectTheme(page, theme);
    await page.waitForTimeout(600);
    const amber = (await paintedColours(page)).filter((colour) => AMBER.includes(colour));
    expect(amber).toEqual([]);
    await page.screenshot({ path: `${SHOTS}/console-${theme}-es.png` });
  }
});
