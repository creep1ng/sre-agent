import { expect, test, type Page } from "@playwright/test";

/*
 * The console shell (#715): the previous console's operations addresses open the new console,
 * the sidebar and the search work from the keyboard, and the backend ids stay inside
 * «Detalles técnicos». Paths that start with "/" are the proxy's, outside /app.
 */

const SHOTS = "e2e/artifacts/shell";

/** Opaque ids of the backend: incidents, agent runs and alert episodes. */
const BACKEND_ID = /\binc-[0-9a-f]{8}|\brun_[0-9a-f]{8}|\balt-[a-z-]+-[0-9a-f]{12}/;

const settle = (page: Page) => page.waitForTimeout(600);

async function freshMockStart(page: Page) {
  await page.goto("./?mock");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await expect(page.getByRole("navigation", { name: "Principal" })).toBeVisible();
}

test("las direcciones de la consola anterior abren la consola nueva", async ({ page }) => {
  // / is the Midnight landing's address (#870), so it never redirects to /app; until the landing
  // lands it serves what it served before.
  for (const root of ["/", "/index.html"]) {
    const response = await page.goto(root);
    expect(response?.status(), root).toBe(200);
    expect(response?.request().redirectedFrom(), root).toBeNull();
    await expect(page, root).not.toHaveURL(/\/app\//);
  }
  await settle(page);
  await page.screenshot({ path: `${SHOTS}/01-raiz-no-redirige-a-la-consola.png` });

  // The simulator has incidents to land on; the flag lives in this tab's session.
  await freshMockStart(page);

  const toInbox = [
    "/?view=alerts",
    "/?view=triage&alert_id=alert_0123456789abcdef",
    "/public/incident-ui/alerts.html",
    "/public/admin/triage.html?alert_id=alert_0123456789abcdef",
  ];
  for (const old of toInbox) {
    await page.goto(old);
    await expect(page, old).toHaveURL(/\/app\/$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(/necesitan? tu atención/);
  }

  for (const old of ["/?view=war-room&incident_id=INC-11", "/public/incident-ui/war-room.html?incident_id=INC-11"]) {
    await page.goto(old);
    await expect(page, old).toHaveURL(/\/app\/incidentes\/INC-11$/);
    await expect(page.getByRole("heading", { name: "El carrito no guarda productos", level: 1 })).toBeVisible();
  }
  await settle(page);
  await page.screenshot({ path: `${SHOTS}/02-war-room-anterior-abre-el-incidente.png` });

  await page.goto("/?view=war-room");
  await expect(page).toHaveURL(/\/app\/incidentes$/);
  await expect(page.getByRole("heading", { name: "Incidentes", level: 1 })).toBeVisible();

  // Without an /app equivalent yet, decisions, postmortem and governance keep their page.
  for (const [old, kept] of [
    ["/?view=decisions&incident_id=INC-11", /\/\?view=decisions&incident_id=INC-11$/],
    ["/public/incident-ui/postmortem.html?incident_id=INC-11", /\/\?view=postmortem&incident_id=INC-11$/],
  ] as const) {
    await page.goto(old);
    await expect(page, old).toHaveURL(kept);
    await expect(page.getByRole("navigation", { name: "Superficies" })).toBeVisible();
  }
  await page.goto("/public/admin/principals.html");
  await expect(page).toHaveURL(/\/public\/admin\/principals\.html$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Principals");
});

test("la barra lateral y la búsqueda se usan con el teclado y los ids quedan en detalles técnicos", async ({
  page,
}) => {
  await freshMockStart(page);

  // Tab reaches the sidebar's sections in order; Enter opens them.
  const reached: string[] = [];
  for (let step = 0; step < 12 && !reached.includes("Postmortems"); step += 1) {
    await page.keyboard.press("Tab");
    reached.push(await page.evaluate(() => document.activeElement?.textContent?.trim() ?? ""));
  }
  expect(reached.map((name) => name.replace(/\d+$/, ""))).toEqual(
    expect.arrayContaining(["Bandeja", "Incidentes", "Postmortems"]),
  );
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/app\/postmortems$/);
  await expect(page.getByRole("tab", { name: /Cerrados/ })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("link", { name: "Postmortems" })).toHaveAttribute("aria-current", "page");
  await settle(page);
  await page.screenshot({ path: `${SHOTS}/03-postmortems.png` });

  await page.getByText("El carrito no guarda productos").click();
  await expect(page).toHaveURL(/\/app\/incidentes\/INC-11$/);
  expect(await page.locator("body").innerText()).not.toMatch(BACKEND_ID);

  // Ctrl K from an incident opens another one by its title.
  await page.keyboard.press("Control+k");
  const search = page.getByRole("dialog", { name: "Buscar" });
  await expect(search).toBeVisible();
  await page.keyboard.type("imágenes de productos");
  await expect(search.getByRole("option", { name: /Imágenes de productos lentas/ })).toBeVisible();
  await settle(page);
  await page.screenshot({ path: `${SHOTS}/04-ctrl-k-desde-un-incidente.png` });
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/app\/incidentes\/INC-10$/);
  await expect(search).toBeHidden();
  await expect(page.getByRole("heading", { name: "Imágenes de productos lentas", level: 1 })).toBeVisible();
  expect(await page.locator("body").innerText()).not.toMatch(BACKEND_ID);

  // The ids live under ⋯ → «Detalles técnicos», reached from the keyboard too.
  await page.getByRole("button", { name: "Más acciones" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("menuitem", { name: "Detalles técnicos" }).focus();
  await page.keyboard.press("Enter");
  const details = page.getByRole("dialog", { name: "Detalles técnicos" });
  await expect(details).toBeVisible();
  expect(await details.innerText()).toMatch(BACKEND_ID);
  await settle(page);
  await page.screenshot({ path: `${SHOTS}/05-detalles-tecnicos.png` });
  await page.keyboard.press("Escape");
  await expect(details).toBeHidden();
  expect(await page.locator("body").innerText()).not.toMatch(BACKEND_ID);

  // «Gobierno de IA» leaves the operations console for a new tab.
  const governance = page.getByRole("link", { name: "Gobierno de IA" });
  await expect(governance).toHaveAttribute("target", "_blank");
  await expect(governance).toHaveAttribute("href", "/public/admin/principals.html");
});
