import { expect, test, type Page } from "@playwright/test";

/*
 * The administration plane inside the RC-2 console: identities, permissions, models and resources,
 * consumption and audit. The first test needs no API; the journey drives the real control plane
 * with the administrative key (ADMIN_REAL=1) and leaves its screenshots in e2e/artifacts/admin.
 */

const SHOTS = "e2e/artifacts/admin";
const KEY = process.env.ADMIN_HUMAN_API_KEY ?? "";
const STAMP = Date.now().toString(36);

const sidebar = (page: Page) => page.locator("#console-sidebar");
const adminNav = (page: Page, name: string) => sidebar(page).getByRole("navigation", { name });
const settle = (page: Page) => page.waitForTimeout(600);

async function open(page: Page, { theme, language }: { theme: "dark" | "light"; language: "es" | "en" }) {
  await page.emulateMedia({ colorScheme: theme });
  await page.addInitScript(
    ([theme, language]) => {
      localStorage.setItem("midnight-theme", JSON.stringify({ state: { theme }, version: 0 }));
      localStorage.setItem("midnight-language", JSON.stringify({ state: { language }, version: 0 }));
    },
    [theme, language],
  );
  await page.goto("./admin");
}

async function connect(page: Page, language: "es" | "en") {
  await page.getByRole("button", { name: language === "es" ? "Conectar con la API" : "Connect to the API" }).click();
  await page.locator("#api-key").fill(KEY);
  await page.locator("#api-key").press("Enter");
  await expect(page.locator("[data-principal-row]").first()).toBeVisible();
}

async function go(page: Page, label: string, heading: string) {
  await sidebar(page).getByRole("link", { name: label, exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(heading);
}

test("the administration plane lives in the console's own navigation", async ({ page }) => {
  await open(page, { theme: "dark", language: "es" });
  await expect(page).toHaveURL(/\/app\/admin\/identidades$/);
  await expect(adminNav(page, "Administración").getByRole("link")).toHaveText([
    /Identidades/,
    /Permisos/,
    /Modelos y recursos/,
    /Consumo/,
    /Auditoría/,
  ]);
  for (const link of await adminNav(page, "Administración").getByRole("link").all()) {
    await expect(link).not.toHaveAttribute("target", "_blank");
    await expect(link.locator("svg.lucide")).toHaveCount(1);
  }
  // Without a session, every page asks for a key instead of showing an empty list.
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Identidades");
  await expect(page.getByText("Conecta una clave de administración para ver esta sección.")).toBeVisible();
  await go(page, "Auditoría", "Auditoría");
  await expect(page).toHaveURL(/\/app\/admin\/auditoria$/);
});

test.describe("against the real control plane", () => {
  test.skip(process.env.ADMIN_REAL !== "1" || !KEY, "set ADMIN_REAL=1 and ADMIN_HUMAN_API_KEY");

  test("an operator creates an identity, issues its key, grants it a model and reads the audit", async ({ page }) => {
    await open(page, { theme: "dark", language: "es" });
    await connect(page, "es");
    await settle(page);
    await page.screenshot({ path: `${SHOTS}/01-identidades.png` });

    const id = `freelancer-bot-${STAMP}`;
    await page.getByRole("button", { name: "Nueva identidad" }).click();
    await page.locator("#principal-id").fill(id);
    await page.locator("#principal-name").fill("Bot del freelancer");
    await page.getByRole("button", { name: "Crear identidad" }).click();
    const sheet = page.getByRole("dialog");
    await expect(sheet.getByRole("heading", { name: "Bot del freelancer" })).toBeVisible();
    await expect(sheet.getByText("Sin claves emitidas.")).toBeVisible();

    await sheet.getByRole("button", { name: "Emitir clave" }).click();
    await page.getByRole("button", { name: "Emitir", exact: true }).click();
    const secret = page.locator("[data-secret]");
    await expect(secret).toHaveText(/^sre_/);
    await settle(page);
    // Neither the key nor the issued credential's prefix appears in the evidence.
    await page.screenshot({ path: `${SHOTS}/02-clave-una-vez.png`, mask: [secret, page.locator("[data-credential-list] li")] });
    await page.getByRole("button", { name: "Cerrar" }).last().click();
    await expect(secret).toHaveCount(0);
    await expect(page.locator(`[data-credential-list="${id}"] li`)).toHaveCount(1);
    await settle(page);
    await page.screenshot({ path: `${SHOTS}/03-identidad.png`, mask: [page.locator("[data-credential-list] li")] });
    await page.keyboard.press("Escape");

    await go(page, "Permisos", "Permisos");
    await page.getByRole("button", { name: "Conceder permiso" }).click();
    await page.locator("#grant-id").fill(`grant-${STAMP}`);
    await page.locator("#grant-principal").selectOption(id);
    await page.locator("#grant-resource").selectOption("llm_model/triage-agent");
    // Only the actions the API admits for a model are offered.
    await expect(page.locator("#grant-action option:not([value=''])")).toHaveText(["admin.read", "admin.write", "invoke"]);
    await page.locator("#grant-action").selectOption("invoke");
    await page.getByRole("button", { name: "Conceder", exact: true }).click();
    const row = page.locator(`[data-grant-row="grant-${STAMP}"]`);
    await expect(row).toContainText("invoke");
    await expect(row).toContainText("Activo");
    await settle(page);
    await page.screenshot({ path: `${SHOTS}/04-permisos.png` });

    await row.getByRole("button", { name: `Revocar grant-${STAMP}` }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Revocar" }).click();
    await expect(page.getByText(`Permiso grant-${STAMP} revocado.`)).toBeVisible();

    await go(page, "Modelos y recursos", "Modelos y recursos");
    await expect(page.locator('[data-alias-row="triage-agent"]')).toContainText("openrouter");
    await expect(page.locator('[data-resource-row="llm_model/triage-agent"]')).toContainText("Modelo LLM");
    await page.locator('[data-alias-row="triage-agent"]').click();
    await page.getByRole("button", { name: "Cambiar modelo" }).click();
    await page.locator("#alias-router").fill("direct");
    await page.getByRole("button", { name: "Guardar asignación" }).click();
    // The console refuses a router the API does not admit before anything is sent.
    await expect(page.getByText("Revisa los campos marcados. No se envió nada.")).toBeVisible();
    await settle(page);
    await page.screenshot({ path: `${SHOTS}/05-alias.png` });
    await page.keyboard.press("Escape");

    await go(page, "Consumo", "Consumo");
    await expect(page.getByText("Tokens por incidente").first()).toBeVisible();
    await settle(page);
    await page.screenshot({ path: `${SHOTS}/06-consumo.png`, fullPage: true });

    await go(page, "Auditoría", "Auditoría");
    await page.locator("#audit-principal_id").fill("admin-human");
    await page.getByRole("button", { name: "Aplicar filtros" }).click();
    // The grant this journey created is on the record, with its decision.
    const created = page.locator("[data-event-row]").filter({ hasText: "grants.create" }).first();
    await expect(created).toContainText("allow");
    await created.click();
    await expect(page.getByRole("dialog").getByText("Correlación")).toBeVisible();
    await settle(page);
    await page.screenshot({ path: `${SHOTS}/07-auditoria.png` });
  });

  test("the same plane reads in English on the light theme", async ({ page }) => {
    await open(page, { theme: "light", language: "en" });
    await connect(page, "en");
    await settle(page);
    await page.screenshot({ path: `${SHOTS}/11-identities-light.png` });
    await go(page, "Permissions", "Permissions");
    await page.locator("#grants-principal").selectOption("admin-human");
    await expect(page.locator("[data-grant-row]").first()).toBeVisible();
    await settle(page);
    await page.screenshot({ path: `${SHOTS}/12-permissions-light.png` });
    await go(page, "Models and resources", "Models and resources");
    await go(page, "Consumption", "Consumption");
    await page.getByRole("button", { name: "Change limits" }).click();
    await settle(page);
    await page.screenshot({ path: `${SHOTS}/13-consumption-light.png`, fullPage: true });
    await go(page, "Audit", "Audit");
  });
});
