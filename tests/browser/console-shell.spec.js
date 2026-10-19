import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// The integrated console (#487): one document at "/", one navigation for incident response and
// AI governance, one session per tab, and old page addresses that open the same view inside it.
const connected = process.env.PLAYWRIGHT_PRODUCTION_TOPOLOGY === "1";
const KEY = "sre_console_shell_test_key";

test.beforeEach(async ({ page }) => {
  const errors = [];
  page.on("console", (message) => {
    // Nginx's CSP blocks third-party fonts, and aborted routes log a resource error on purpose.
    const text = message.text();
    if (
      message.type() === "error" &&
      !text.includes("Content Security Policy") &&
      !text.startsWith("Failed to load resource")
    )
      errors.push(text);
  });
  page.on("pageerror", (error) => errors.push(String(error?.message ?? error)));
  page.context()["__errors"] = errors;
  // With a session the inbox polls live alerts; the shell specs answer it like whoami.
  await page.route("**/api/v1/alerts", (route) =>
    route.fulfill({ json: { evaluated_at: "2026-10-19T04:00:00Z", rules: [], alerts: [] } }),
  );
});

test.afterEach(async ({ page }) => {
  expect(page.context()["__errors"]).toEqual([]);
});

async function mockWhoAmI(page, reply) {
  const calls = [];
  await page.route("**/api/v1/whoami", async (route) => {
    calls.push(route.request().headers().authorization ?? null);
    await reply(route);
  });
  return calls;
}

const asPrincipal = (principalId) => (route) =>
  route.fulfill({ json: { principal_id: principalId }, headers: { "Cache-Control": "no-store" } });

async function connect(page, value = KEY) {
  const chip = page.locator("#session-chip");
  if (await page.locator("#console-session").isHidden()) await chip.click();
  await page.fill("#api-key", value);
  await page.click("#connect-button");
}

async function browserStorage(page) {
  return page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage } }));
}

test("la raíz abre la consola con las dos secciones y Alertas como vista inicial", async ({ page }) => {
  const response = await page.goto("/");
  expect(response?.status()).toBe(200);

  const incidents = page.getByRole("list", { name: "Atención a incidentes" });
  const governance = page.getByRole("list", { name: "Gobierno de IA" });
  await expect(incidents.getByRole("link")).toHaveText([
    "Alertas",
    "Triage",
    "War room",
    "Decisiones",
    "Postmortem",
  ]);
  await expect(governance.getByRole("link")).toHaveText([
    "Principals",
    "Recursos y aliases",
    "Grants",
    "Auditoría y consumo",
  ]);
  await expect(page.locator("[data-console-nav][aria-current='page']")).toHaveText("Alertas");
  await expect(page.locator(".console-breadcrumb")).toContainText("Atención a incidentes");
  await expect(page.locator("#console-surface")).toHaveText("Alertas");
  await expect(page.locator("#alert-inbox")).toHaveAttribute("data-state", "locked");
  await expect(page).toHaveTitle("Alertas · midnight.agent");
  await expect(page.getByRole("link", { name: "Sistema de diseño" })).toHaveAttribute(
    "href",
    "/design-system.html",
  );
  await expect(page.getByRole("main")).toHaveCount(1);
});

test("una dirección antigua abre la misma vista dentro de la consola con sus parámetros", async ({ page }) => {
  await page.goto("/public/incident-ui/alerts.html?fixture=empty");
  await expect(page).toHaveURL(/\/\?view=alerts&fixture=empty$/);
  await expect(page.locator("#alert-inbox")).toHaveAttribute("data-state", "empty");
  await expect(page.locator("[data-console-nav][aria-current='page']")).toHaveText("Alertas");
});

test("navegar dentro de la consola conserva el documento y Atrás/Adelante restauran la vista", async ({ page }) => {
  await page.goto("/?view=vista-inexistente");
  await expect(page.locator("#console-view h1")).toHaveText("Vista no encontrada");
  await expect(page.locator("[data-console-nav][aria-current='page']")).toHaveCount(0);
  await page.evaluate(() => {
    window.__sameDocument = true;
  });

  await page.getByRole("link", { name: "Ir a Alertas" }).click();
  await expect(page).toHaveURL(/\/\?view=alerts$/);
  await expect(page.locator("#alert-inbox")).toHaveAttribute("data-state", "locked");
  await expect(page.locator("#alert-inbox h1")).toBeFocused();

  await page.goBack();
  await expect(page.locator("#console-view h1")).toHaveText("Vista no encontrada");
  await page.goForward();
  await expect(page.locator("#alert-inbox")).toHaveAttribute("data-state", "locked");
  expect(await page.evaluate(() => window.__sameDocument)).toBe(true);
});

test("la credencial se escribe una vez, vale para toda la consola y se cierra para todas las vistas", async ({ page }) => {
  const calls = await mockWhoAmI(page, asPrincipal("admin-human"));
  await page.goto("/");
  await expect(page.locator("#session-chip")).toContainText("Sin sesión");

  await connect(page);
  await expect(page.locator("#session-principal")).toHaveText("admin-human");
  await expect(page.locator("#session-state")).toHaveText("Sesión activa");
  await expect(page.locator("#console-session")).toBeHidden();
  expect(calls).toEqual([`Bearer ${KEY}`]);

  await page.goto("/?view=vista-inexistente");
  await expect(page.locator("#session-chip")).toContainText("Sin sesión");
  await connect(page);
  await expect(page.locator("#session-principal")).toHaveText("admin-human");
  await page.getByRole("link", { name: "Ir a Alertas" }).click();
  await expect(page.locator("#alert-inbox")).toHaveAttribute("data-state", "empty");
  await expect(page.locator("#session-principal")).toHaveText("admin-human");
  expect(calls).toHaveLength(2);

  await page.locator("#session-chip").click();
  await page.locator("#disconnect-button").click();
  await expect(page.locator("#session-chip")).toContainText("Sin sesión");
  await expect(page.locator("#console-live")).toHaveText(/Sesión cerrada/);

  expect(page.url()).not.toContain(KEY);
  expect(JSON.stringify(await browserStorage(page))).not.toContain(KEY);
  await expect(page.locator("#api-key")).toHaveValue("");
});

test("una credencial rechazada no abre sesión ni se queda en la página", async ({ page }) => {
  await mockWhoAmI(page, (route) =>
    route.fulfill({
      status: 401,
      json: { error: { code: "unauthorized", message: "Invalid credential." }, request_id: "r-1", retryable: false },
    }),
  );
  await page.goto("/");
  await connect(page, "sre_rejected_key");
  await expect(page.locator("#session-message")).toHaveText(/La API rechazó esa credencial/);
  await expect(page.locator("#session-chip")).toHaveAttribute("data-phase", "anonymous");
  await expect(page.locator("#api-key")).toHaveValue("");
});

test("si la API no responde, la validación se puede reintentar sin escribir la key otra vez", async ({ page }, testInfo) => {
  let releaseRetry;
  const pendingRetry = new Promise((resolve) => { releaseRetry = resolve; });
  let attempts = 0;
  const calls = await mockWhoAmI(page, async (route) => {
    attempts += 1;
    if (attempts === 1) return route.abort("failed");
    if (attempts === 2) {
      await pendingRetry;
      return route.abort("failed");
    }
    return asPrincipal("demo-human")(route);
  });
  await page.goto("/");
  await connect(page);
  await expect(page.locator("#session-message")).toHaveText(/No se pudo contactar la API/);
  await expect(page.locator("#session-chip")).toHaveAttribute("data-phase", "validating");

  try {
    await page.locator("#session-retry").evaluate((button) => { button.click(); button.click(); });
    await expect(page.locator("#session-message")).toHaveText("Validando la credencial con la API…");
    await expect(page.locator("#session-retry")).toBeHidden();
    await expect(page.locator("#connect-button")).toBeDisabled();
    await expect.poll(() => calls.length).toBe(2);
    await page.screenshot({ path: testInfo.outputPath("session-retry-pending.png") });
  } finally {
    releaseRetry();
  }
  await expect(page.locator("#session-message")).toHaveText(/No se pudo contactar la API/);
  await page.getByRole("button", { name: "Reintentar" }).click();
  await expect(page.locator("#session-principal")).toHaveText("demo-human");
  expect(calls).toEqual(Array(3).fill(`Bearer ${KEY}`));
  await page.screenshot({ path: testInfo.outputPath("session-retry-recovered.png") });
});

for (const width of [320, 375]) {
  test(`session controls remain reachable at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    if (!connected) await mockWhoAmI(page, asPrincipal("admin-human"));
    await page.goto("/");
    await connect(page, connected ? process.env.ADMIN_HUMAN_API_KEY : KEY);
    await expect(page.locator("#session-principal")).toHaveText("admin-human");
    await page.locator("#session-chip").click();
    await page.screenshot({ path: testInfo.outputPath(`session-popover-${width}.png`) });
    for (const id of ["session-menu", "change-credential", "disconnect-button"]) {
      const bounds = await page.locator(`#${id}`).boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds.x).toBeGreaterThanOrEqual(0);
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
      expect(bounds.y).toBeGreaterThanOrEqual(0);
      expect(bounds.y + bounds.height).toBeLessThanOrEqual(900);
    }
    await page.locator("#change-credential").click();
    await expect(page.locator("#api-key")).toBeFocused();
    await page.locator("#session-cancel").click();
    await expect(page.locator("#session-chip")).toBeFocused();
    await page.locator("#session-chip").click();
    await page.locator("#disconnect-button").click();
    await expect(page.locator("#session-chip")).toHaveAttribute("data-phase", "anonymous");
  });
}

test("el tema elegido aplica a toda la consola y persiste al recargar", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Oscuro" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("button", { name: "Oscuro" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Claro" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  expect((await browserStorage(page)).local).toEqual({ "ma-theme": "light" });
});

test("Alertas entrega la alerta seleccionada a Triage sin copiar su ID", async ({ page }) => {
  await page.goto("/?fixture=default");
  await expect(page.locator("#alert-inbox")).toHaveAttribute("data-state", "ready");
  await page.evaluate(() => {
    window.__sameDocument = true;
  });
  await page.getByRole("button", { name: "Iniciar triage" }).click();
  await expect(page).toHaveURL("/?view=triage&alert_id=alert-checkout-001");
  await expect(page.locator("#alert-id")).toHaveValue("alert-checkout-001");
  await expect(page.locator("[data-console-nav][aria-current='page']")).toHaveText("Triage");
  expect(await page.evaluate(() => window.__sameDocument)).toBe(true);
});

test("la consola no tiene violaciones WCAG A/AA detectables", async ({ page }) => {
  await page.goto("/?fixture=default");
  await expect(page.locator("#alert-inbox")).toHaveAttribute("data-state", "ready");
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    // The palette's measured contrast baseline is tracked by the design-system smoke.
    .disableRules(["color-contrast"])
    .analyze();
  expect(results.violations).toEqual([]);
});

test("con el stack real, la sesión de la consola se valida con whoami", async ({ page }) => {
  test.skip(!connected || !process.env.ADMIN_HUMAN_API_KEY, "requires the production topology");
  await page.goto("/");
  await connect(page, process.env.ADMIN_HUMAN_API_KEY);
  await expect(page.locator("#session-principal")).toHaveText("admin-human", { timeout: 20_000 });
  expect(JSON.stringify(await browserStorage(page))).not.toContain(process.env.ADMIN_HUMAN_API_KEY);
});
