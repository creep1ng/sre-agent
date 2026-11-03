import { expect, test, type Page } from "@playwright/test";
import { strToU8, zipSync } from "fflate";

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
    /Skills/,
    /Conocimiento/,
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
    await page.keyboard.press("Escape");

    // The journey leaves its identity inactive, so runs do not pile up active test identities.
    await go(page, "Identidades", "Identidades");
    await page.locator(`[data-principal-row="${id}"]`).click();
    await page.getByRole("dialog").getByRole("button", { name: "Desactivar" }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Desactivar" }).click();
    await expect(page.getByText(`${id} quedó inactiva.`)).toBeVisible();
  });

  test("an operator publishes a Skill version, reads it and activates it", async ({ page }) => {
    await open(page, { theme: "dark", language: "es" });
    await connect(page, "es");
    await go(page, "Skills", "Skills");
    const skill = `runbook-check-${STAMP}`;
    await page.getByRole("button", { name: "Publicar versión" }).click();
    await page.locator("#skill-id").fill(skill);
    await page.locator("#skill-version").fill("1.0.0");
    await page.locator("#skill-name").fill("Revisión de runbook");
    await page.locator("#skill-description").fill("Revisa que el runbook del servicio cubra el síntoma antes de proponer.");
    await page.locator("#skill-instructions").fill("Lee el runbook del servicio afectado.\n\n## Pasos\n1. Busca el síntoma.\n2. Cita la sección que aplica.");
    // A dependency that is not id@version is refused before anything is sent.
    // The version is published in the name of the connected identity; there is no list to pick from.
    await expect(page.locator("[data-skill-owner]")).toContainText("admin-human");
    await page.locator("#skill-dependencies").fill("incident-triage");
    await page.getByRole("button", { name: "Publicar", exact: true }).click();
    await expect(page.getByText("Revisa los campos marcados. No se envió nada.")).toBeVisible();
    await page.locator("#skill-dependencies").fill("");
    await page.getByRole("button", { name: "Publicar", exact: true }).click();

    // The new version opens with its manifest, published and not yet active.
    const sheet = page.getByRole("dialog");
    await expect(sheet.getByRole("heading", { name: "Revisión de runbook" })).toBeVisible();
    await expect(sheet.getByText("Publicado")).toBeVisible();
    await expect(sheet.locator("[data-skill-instructions]")).toContainText("Cita la sección que aplica.");
    await sheet.getByRole("button", { name: "Activar" }).click();
    await expect(page.getByText(`${skill}@1.0.0 activada.`)).toBeVisible();
    await expect(sheet.getByRole("button", { name: "Desactivar" })).toBeVisible();
    await settle(page);
    await page.screenshot({ path: `${SHOTS}/08-skill.png` });
    await page.keyboard.press("Escape");
    await expect(page.locator(`[data-skill-row="${skill}@1.0.0"]`)).toContainText("Activo");

    // The same version with other content is refused, and the published one stays as it was.
    await page.getByRole("button", { name: "Publicar versión" }).click();
    await page.locator("#skill-id").fill(skill);
    await page.locator("#skill-name").fill("Otra cosa");
    await page.locator("#skill-description").fill("Otro contenido.");
    await page.locator("#skill-instructions").fill("Otro texto.");
    await page.getByRole("button", { name: "Publicar", exact: true }).click();
    await expect(page.getByText("Esa versión ya existe con otro contenido. Publica una versión nueva.")).toBeVisible();
  });

  test("an operator publishes a knowledge collection and the search finds it once it is granted", async ({ page }) => {
    await open(page, { theme: "dark", language: "es" });
    await connect(page, "es");
    await go(page, "Conocimiento", "Conocimiento");
    const collection = `runbooks-checkout-${STAMP}`;
    const resource = `${collection}@1.0.0`;
    await page.getByRole("button", { name: "Publicar colección" }).click();
    await page.locator("#bok-id").fill(collection);
    await page.locator("#bok-name").fill("Runbooks de checkout");
    await page.locator("#bok-description").fill("Qué hacer cuando checkout falla.");
    // A document without text is refused before anything is sent.
    await page.locator("#bok-doc-0-title").fill("Rollback de checkout");
    await page.getByRole("button", { name: "Publicar", exact: true }).click();
    await expect(page.getByText("Revisa los campos marcados. No se envió nada.")).toBeVisible();
    await page
      .locator("#bok-doc-0-body")
      .fill("Cuándo volver atrás.\n\n## Señales\nLa tasa de errores de pagos sube después de un despliegue.\n\n## Pasos\nHaz rollback a la versión anterior y verifica la latencia.");
    // Each heading opens a section: the text before the first one, then two sections.
    await expect(page.locator('[data-bok-chunk-count="0"]')).toHaveText("Fragmentos: 3");
    await page.getByRole("button", { name: "Publicar", exact: true }).click();

    const sheet = page.getByRole("dialog");
    await expect(sheet.getByRole("heading", { name: "Runbooks de checkout" })).toBeVisible();
    await expect(sheet.getByText("Activo")).toBeVisible();
    await expect(sheet.locator('[data-bok-document="rollback-de-checkout"]')).toContainText("Haz rollback a la versión anterior");
    // Publishing grants nothing: the search answers as it would to an agent without the grant.
    await sheet.locator("#bok-query").fill("rollback");
    await sheet.getByRole("button", { name: "Buscar" }).click();
    await expect(sheet.getByText(`Tu identidad no puede buscar en ${resource}.`, { exact: false })).toBeVisible();
    await page.keyboard.press("Escape");

    await go(page, "Permisos", "Permisos");
    await page.getByRole("button", { name: "Conceder permiso" }).click();
    await page.locator("#grant-id").fill(`grant-bok-${STAMP}`);
    await page.locator("#grant-principal").selectOption("admin-human");
    await page.locator("#grant-resource").selectOption(`bok_collection/${resource}`);
    await page.locator("#grant-action").selectOption("bok.search");
    await page.getByRole("button", { name: "Conceder", exact: true }).click();
    await expect(page.locator(`[data-grant-row="grant-bok-${STAMP}"]`)).toContainText("bok.search");

    await go(page, "Conocimiento", "Conocimiento");
    await page.locator(`[data-collection-row="${resource}"]`).click();
    await sheet.locator("#bok-query").fill("rollback");
    await sheet.getByRole("button", { name: "Buscar" }).click();
    await expect(sheet.locator("[data-bok-results] li").first()).toContainText("Rollback de checkout");
    await settle(page);
    await page.screenshot({ path: `${SHOTS}/09-conocimiento.png` });
  });

  test("a .zip of runbooks becomes a collection, and a Skill archive fills the Skill form", async ({ page }) => {
    await open(page, { theme: "dark", language: "es" });
    await connect(page, "es");

    await go(page, "Conocimiento", "Conocimiento");
    await page.getByRole("button", { name: "Publicar colección" }).click();
    const runbooks = zipSync({
      "runbooks/pagos.md": strToU8("# Pagos caídos\n\n## Señales\nSube la tasa de errores de pagos.\n\n## Pasos\nApaga el flag y mide otra vez."),
      "runbooks/latencia.md": strToU8("# Latencia alta\n\nRevisa la latencia del checkout antes de escalar."),
      "scripts/run.sh": strToU8("echo nada"),
    });
    await page.locator("#bok-upload").setInputFiles({ name: `runbooks-${STAMP}.zip`, mimeType: "application/zip", buffer: Buffer.from(runbooks) });
    // Each .md is a document titled by its heading; anything else is left out and said so.
    await expect(page.locator("[data-bok-upload-note]")).toContainText("Documentos cargados: 2.");
    await expect(page.locator("[data-bok-upload-note]")).toContainText("Quedaron fuera: scripts/run.sh.");
    await expect(page.locator("#bok-id")).toHaveValue(`runbooks-${STAMP}`);
    await expect(page.locator("#bok-doc-0-title")).toHaveValue("Latencia alta");
    await expect(page.locator("#bok-doc-1-title")).toHaveValue("Pagos caídos");
    await page.getByRole("dialog").screenshot({ path: `${SHOTS}/10a-conocimiento-formulario.png` });
    await page.getByRole("button", { name: "Publicar", exact: true }).click();
    const sheet = page.getByRole("dialog");
    await expect(sheet.locator('[data-bok-document="pagos-caidos"]')).toContainText("Apaga el flag y mide otra vez.");
    await expect(sheet.locator('[data-bok-document="latencia-alta"]')).toBeVisible();
    await settle(page);
    await page.screenshot({ path: `${SHOTS}/10-conocimiento-zip.png` });
    await page.keyboard.press("Escape");

    await go(page, "Skills", "Skills");
    await page.getByRole("button", { name: "Publicar versión" }).click();
    const skill = zipSync({
      "log-reader/SKILL.md": strToU8(
        `---\nname: log-reader-${STAMP}\ndescription: Lee los logs del servicio y resume los errores.\n---\n# Lector de logs\n\nAgrupa los errores por mensaje y cita la hora del primero.`,
      ),
      "log-reader/scripts/parse.py": strToU8("print('x')"),
    });
    await page.locator("#skill-upload").setInputFiles({ name: "log-reader.zip", mimeType: "application/zip", buffer: Buffer.from(skill) });
    await expect(page.locator("#skill-id")).toHaveValue(`log-reader-${STAMP}`);
    await expect(page.locator("#skill-name")).toHaveValue("Lector de logs");
    await expect(page.locator("#skill-description")).toHaveValue("Lee los logs del servicio y resume los errores.");
    await expect(page.locator("[data-skill-upload-note]")).toContainText("quedaron fuera: log-reader/scripts/parse.py");
    await page.getByRole("dialog").screenshot({ path: `${SHOTS}/08a-skill-formulario.png` });
    await page.getByRole("button", { name: "Publicar", exact: true }).click();
    await expect(page.getByRole("dialog").locator("[data-skill-instructions]")).toContainText("cita la hora del primero");
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
    await go(page, "Skills", "Skills");
    await expect(page.locator("[data-skill-row]").first()).toBeVisible();
    await settle(page);
    await page.screenshot({ path: `${SHOTS}/14-skills-light.png` });
    await go(page, "Knowledge", "Knowledge");
    await expect(page.locator("[data-collection-row]").first()).toBeVisible();
    await settle(page);
    await page.screenshot({ path: `${SHOTS}/15-knowledge-light.png` });
    await go(page, "Consumption", "Consumption");
    await page.getByRole("button", { name: "Change limits" }).click();
    await settle(page);
    await page.screenshot({ path: `${SHOTS}/13-consumption-light.png`, fullPage: true });
    await go(page, "Audit", "Audit");
  });
});
