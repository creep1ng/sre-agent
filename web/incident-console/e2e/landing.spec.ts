import { expect, test, type Page } from "@playwright/test";

/*
 * The web proxy's / serves the Midnight landing (#870): Spanish or English, remembered, with
 * every asset served by the proxy itself. «Abrir la consola» opens /app/. The previous console
 * keeps the addresses /app does not replace yet, and the ones it does replace redirect there.
 * Screenshots land in e2e/artifacts/landing; docs/evidence/issue-870/landing keeps a copy.
 */

const SHOTS = "e2e/artifacts/landing";
const MOONLIGHT = "rgb(228, 217, 255)";

// Every request the page makes, so the test can prove none leaves the proxy.
function recordRequests(page: Page) {
  const urls: string[] = [];
  const problems: string[] = [];
  page.on("request", (request) => urls.push(request.url()));
  page.on("requestfailed", (request) => problems.push(`failed ${request.url()}`));
  page.on("console", (message) => { if (message.type() === "error") problems.push(message.text()); });
  page.on("pageerror", (error) => problems.push(error.message));
  return { urls, problems };
}

async function expectOnlyOwnOrigin(page: Page, urls: string[]) {
  const origin = new URL(page.url()).origin;
  expect(urls.length).toBeGreaterThan(0);
  expect(urls.filter((url) => !url.startsWith(`${origin}/`) && !url.startsWith("data:"))).toEqual([]);
}

test("/ sirve la landing en español, con fuentes propias y sin peticiones a terceros", async ({ page }) => {
  const { urls, problems } = recordRequests(page);
  const response = await page.goto("/");
  expect(response?.status()).toBe(200);
  expect(response?.headers()["content-type"]).toContain("text/html");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Mil señales en una semana. Una era para ti.");
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  await expect(page.getByRole("button", { name: "ES" })).toHaveAttribute("aria-pressed", "true");

  // The fonts are the proxy's own files, and they are in use.
  await page.evaluate(() => document.fonts.ready);
  expect(await page.evaluate(() => ["300 40px Fraunces", "400 19px Newsreader", "500 14px 'JetBrains Mono'"].every((font) => document.fonts.check(font)))).toBe(true);
  expect(urls.filter((url) => url.endsWith(".woff2")).length).toBeGreaterThanOrEqual(3);
  await page.screenshot({ path: `${SHOTS}/desktop-es.png`, fullPage: true, animations: "disabled" });

  await expectOnlyOwnOrigin(page, urls);
  // A CSP violation (inline style or script) would show up here as a console error.
  expect(problems).toEqual([]);

  // The way into the product is moonlight, never amber.
  const open = page.getByRole("link", { name: "Abrir la consola →" });
  await expect(open).toHaveCount(2);
  for (const link of await open.all()) {
    await expect(link).toHaveAttribute("href", "/app/");
    expect(await link.evaluate((node) => getComputedStyle(node).backgroundColor)).toBe(MOONLIGHT);
  }
  await open.first().click();
  await expect(page).toHaveURL(/\/app\/$/);
  await expect(page.locator("#root")).not.toBeEmpty();
});

test("el selector ES · EN cambia el idioma y lo recuerda al recargar", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "EN" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("A thousand signals in a week. One was for you.");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page).toHaveTitle("Midnight · Close the laptop");
  await expect(page.getByRole("link", { name: "Open the console →" })).toHaveCount(2);
  // Labelled numbers keep their label in English: the target and the simulated week.
  await expect(page.getByText("Under 1 USD per user per month as a target.", { exact: false })).toBeVisible();
  await expect(page.getByText("The week on the cover is simulated.", { exact: false })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("A thousand signals in a week. One was for you.");
  await expect(page.getByRole("button", { name: "EN" })).toHaveAttribute("aria-pressed", "true");
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: `${SHOTS}/desktop-en.png`, fullPage: true, animations: "disabled" });

  await page.getByRole("button", { name: "ES" }).click();
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Mil señales en una semana. Una era para ti.");
});

test("sin elección guardada, un navegador en inglés ve la landing en inglés", async ({ browser, baseURL }) => {
  const context = await browser.newContext({ locale: "en-US", baseURL });
  const page = await context.newPage();
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.getByRole("link", { name: "Promises" })).toBeVisible();
  await context.close();
});

for (const lang of ["es", "en"] as const) {
  test(`en un móvil el cielo enmarca solo la noche del viernes (${lang})`, async ({ browser, baseURL }) => {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: lang === "en" ? "en-GB" : "es-CO", baseURL });
    const page = await context.newPage();
    const { urls } = recordRequests(page);
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("lang", lang);
    // Friday is the fifth of seven 1440/7 columns: the narrow view box starts at 3.5 columns.
    await expect(page.locator("#sky")).toHaveAttribute("viewBox", /^720 280 411\.428\d* 460$/);
    await expect(page.locator("#sky text", { hasText: "02:47" })).toBeInViewport();
    // The nav keeps the switch and a short "Console →" button; the other links fold away.
    await expect(page.getByRole("button", { name: lang.toUpperCase() })).toBeVisible();
    await expect(page.locator("nav .console")).toBeInViewport();
    await expect(page.locator("nav .console .lg")).toBeHidden();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: `${SHOTS}/phone-${lang}.png`, fullPage: true, animations: "disabled" });
    await expectOnlyOwnOrigin(page, urls);
    await context.close();
  });
}

test("la consola anterior sigue donde /app aún no llega, y lo que /app reemplaza redirige", async ({ page }) => {
  const decisions = await page.goto("/?view=decisions");
  expect(decisions?.status()).toBe(200);
  await expect(page.getByRole("navigation", { name: "Superficies" })).toBeVisible();

  const governance = await page.goto("/public/admin/principals.html");
  expect(governance?.status()).toBe(200);

  await page.goto("/?view=alerts");
  await expect(page).toHaveURL(/\/app\/$/);
  await page.goto("/?view=triage&alert_id=alert-1");
  await expect(page).toHaveURL(/\/app\/$/);
  await page.goto("/?view=war-room&incident_id=INC-11");
  await expect(page).toHaveURL(/\/app\/incidentes\/INC-11$/);
});

test("/llms.txt existe y describe Midnight para agentes", async ({ page, request }) => {
  await page.goto("/");
  const href = await page.locator('link[rel="alternate"][type="text/markdown"]').getAttribute("href");
  expect(href).toBe("/llms.txt");
  const llms = await request.get(href!);
  expect(llms.status()).toBe(200);
  expect(llms.headers()["content-type"]).toContain("text/markdown");
  const text = await llms.text();
  expect(text.startsWith("# Midnight\n")).toBe(true);
  // Its API link is not dead either.
  expect(text).toContain("(/api/openapi.json)");
  expect((await request.get("/api/openapi.json")).status()).toBe(200);
});
