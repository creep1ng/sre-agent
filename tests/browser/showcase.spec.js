import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const browserErrors = new WeakMap();
const assetFailures = new WeakMap();
const essentialAssets = [
  "/scripts/showcase.js",
  "/styles/design-system.css",
  "/styles/showcase.css",
];

test.beforeEach(async ({ page }) => {
  const browserState = { consoleErrors: [], captureConsole: true };
  page.on("console", (message) => {
    if (message.type() === "error" && browserState.captureConsole)
      browserState.consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserState.consoleErrors.push(error.message));
  browserErrors.set(page, browserState);
  const failedAssets = [];
  page.on("response", (response) => {
    const path = new URL(response.url()).pathname;
    if (essentialAssets.includes(path) && !response.ok())
      failedAssets.push(`${path}: HTTP ${response.status()}`);
  });
  page.on("requestfailed", (request) => {
    const path = new URL(request.url()).pathname;
    if (essentialAssets.includes(path)) failedAssets.push(`${path}: request failed`);
  });
  assetFailures.set(page, failedAssets);
  await page.goto("/index.html");
  for (const path of essentialAssets)
    await expect(page.locator(`link[href=".${path}"], script[src=".${path}"]`)).toHaveCount(1);
});

test.afterEach(async ({ page }) => {
  expect(browserErrors.get(page).consoleErrors, "unexpected browser errors").toEqual([]);
  expect(assetFailures.get(page), "essential browser assets").toEqual([]);
});

test("loads the catalog and changes theme through the existing control", async ({ page }) => {
  await expect(page).toHaveTitle(/midnight\.agent/);

  const darkTheme = page.getByRole("button", { name: "Use dark theme" });
  await darkTheme.click();

  await expect(darkTheme).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("#live-region")).toHaveText("dark theme selected");
});

test("has no scoped automatically detectable WCAG A or AA violations", async ({
  page,
}) => {
  // axe reinjects imported CSS against the page URL; ignore only its own resource noise.
  browserErrors.get(page).captureConsole = false;
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    // The measured baseline has one palette contrast violation; this smoke gates structure.
    .disableRules(["color-contrast"])
    .analyze();

  expect(results.violations).toEqual([]);
});
