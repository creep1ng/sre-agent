import { expect, test, type Locator, type Page } from "@playwright/test";

/*
 * End-to-end journeys of the incident console, served by the web proxy at /app.
 * Screenshots land in e2e/artifacts/screens; videos and the HTML report next to them.
 */

const SCREENS = "e2e/artifacts/screens";

/** Protocol details the UX review asked to keep out of the operator's view. */
const LEAKS = [
  "open_triage",
  "triage_declare",
  "triage_dismiss",
  "triage_link",
  "Versión esperada",
  "Snapshot",
  "seq 0",
  "run_",
  "evt_",
  "inc-",
  "Solicitud MCP",
  "backend",
  "awaiting_human",
  "idempotencia",
  "fixture",
  "Contexto autoritativo",
  "RFC 3339",
];

async function expectNoLeaks(page: Page) {
  const text = await page.locator("body").innerText();
  for (const leak of LEAKS) expect(text, `the UI shows "${leak}"`).not.toContain(leak);
}

/** Lets entrance animations finish so screenshots show the settled UI. */
const settle = (page: Page) => page.waitForTimeout(600);

async function freshStart(page: Page) {
  await page.goto("./");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("3 cosas necesitan tu atención");
}

function alertCard(page: Page, title: string): Locator {
  return page.locator("article", { has: page.getByRole("heading", { name: title }) });
}

async function declare(page: Page, title: string) {
  await alertCard(page, title).getByRole("button", { name: "Declarar incidente" }).click();
  await page.getByRole("dialog").getByRole("button", { name: /Declarar e investigar/ }).click();
}

test("una alerta crítica llega a incidente cerrado en 7 clics, sin salir de una sola vista", async ({ page }) => {
  let clicks = 0;
  const click = async (locator: Locator) => {
    await locator.click();
    clicks += 1;
  };

  await freshStart(page);
  await expectNoLeaks(page);
  await page.screenshot({ path: `${SCREENS}/01-bandeja.png`, fullPage: true });

  // 1-2: declarar desde la tarjeta; el formulario ya viene lleno con lo que dice la alerta.
  await click(alertCard(page, "Pagos fallando en checkout").getByRole("button", { name: "Declarar incidente" }));
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("radio", { name: /SEV1/ })).toHaveAttribute("aria-checked", "true");
  await expect(dialog.getByLabel("¿Qué notan tus clientes?")).toHaveValue(/no pueden pagar/);
  await settle(page);
  await page.screenshot({ path: `${SCREENS}/02-declarar.png` });
  await click(dialog.getByRole("button", { name: /Declarar e investigar/ }));

  // La investigación arranca sola: no hay botón "Iniciar investigación".
  await expect(page).toHaveURL(/\/incidentes\/INC-12$/);
  await expect(page.getByRole("heading", { name: "El agente está investigando" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Iniciar investigación/ })).toHaveCount(0);
  await expect(page.getByText("El 100 % de los cobros falla").first()).toBeVisible({ timeout: 20_000 });
  await page.waitForTimeout(4_000);
  await expectNoLeaks(page);
  await page.screenshot({ path: `${SCREENS}/03-investigando.png`, fullPage: true });

  // 3: decidir dentro de la misma tarjeta de la propuesta.
  await expect(page.getByRole("heading", { name: "El agente propone una mitigación" })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("Qué la descartaría:")).toBeVisible();
  await settle(page);
  await expectNoLeaks(page);
  await page.screenshot({ path: `${SCREENS}/04-propuesta.png`, fullPage: true });
  await click(page.getByRole("button", { name: "Aprobar mitigación" }));

  // 4: aplicar y avisar; los pasos son una lista opcional.
  await expect(page.getByRole("heading", { name: "Aplica la mitigación" })).toBeVisible();
  await page.getByText("Cambia «paymentUnreachable» a off y guarda.").click();
  await settle(page);
  await page.screenshot({ path: `${SCREENS}/05-aplicar.png`, fullPage: true });
  await click(page.getByRole("button", { name: "Ya la apliqué" }));

  // 5: el agente vigila la señal y avisa cuando está estable.
  await expect(page.getByText("La señal se mantiene bajo el umbral").first()).toBeVisible({ timeout: 60_000 });
  await page.screenshot({ path: `${SCREENS}/06-recuperado.png`, fullPage: true });
  await click(page.getByRole("button", { name: "El servicio está estable" }));

  // El postmortem se redacta solo; se edita en el mismo documento.
  await expect(page.getByRole("heading", { name: "El agente está redactando el postmortem" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Revisa el postmortem y cierra el incidente" })).toBeVisible({
    timeout: 60_000,
  });
  await page.getByRole("button", { name: "Editar los pendientes" }).click();
  const pending = page.getByRole("textbox", { name: "los pendientes" });
  await pending.press("Control+End");
  await pending.pressSequentially("\nDocumentar el panel de flags en el runbook.");
  await pending.blur();
  await expect(page.getByText("Documentar el panel de flags en el runbook.")).toBeVisible();
  await expect(page.getByText(/editado por ti/)).toBeVisible();
  await expectNoLeaks(page);
  await page.screenshot({ path: `${SCREENS}/07-postmortem.png`, fullPage: true });

  // 6-7: aprobar y cerrar en un paso, con una confirmación explícita.
  await click(page.getByRole("button", { name: "Aprobar y cerrar incidente" }));
  await click(page.getByRole("alertdialog").getByRole("button", { name: "Aprobar y cerrar" }));
  await expect(page.getByRole("heading", { name: "Incidente cerrado" })).toBeVisible();
  await settle(page);
  await expectNoLeaks(page);
  await page.screenshot({ path: `${SCREENS}/08-cerrado.png`, fullPage: true });

  expect(clicks).toBe(7);

  await page.getByRole("link", { name: "Volver a la bandeja" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("2 cosas necesitan tu atención");
});

test("descartar pide un motivo y se puede deshacer", async ({ page }) => {
  await freshStart(page);
  await alertCard(page, "Errores intermitentes en anuncios").getByRole("button", { name: "Descartar" }).click();
  await page.getByRole("radio", { name: "Falsa alarma" }).click();
  await page.getByRole("button", { name: "Descartar alerta" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("2 cosas necesitan tu atención");
  await page.getByRole("button", { name: /Resuelto recientemente/ }).click();
  await expect(page.getByText("Descartada: Falsa alarma")).toBeVisible();
  await page.screenshot({ path: `${SCREENS}/10-descartada.png`, fullPage: true });
  await page.getByRole("button", { name: "Deshacer" }).last().click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("3 cosas necesitan tu atención");
});

test("si el agente no puede investigar, dice por qué y se reintenta en el mismo incidente", async ({ page }) => {
  await freshStart(page);
  await page.getByRole("button", { name: /demo-human/ }).click();
  await page.getByRole("menuitem", { name: /Escenario de demostración/ }).click();
  await page.getByRole("menuitemcheckbox", { name: "El agente falla al investigar" }).click();
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");

  await declare(page, "Pagos fallando en checkout");
  await expect(page.getByRole("heading", { name: "El agente no pudo empezar a investigar" })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText("Su identidad («incident-harness») está desactivada")).toBeVisible();
  await expect(page.getByText("Actívala en Gobierno de IA → Principals")).toBeVisible();
  await expectNoLeaks(page);
  await page.screenshot({ path: `${SCREENS}/11-falla-agente.png`, fullPage: true });

  await page.getByRole("button", { name: "Ya lo corregí, reintentar" }).click();
  await expect(page.getByRole("heading", { name: "El agente está investigando" })).toBeVisible();
  await expect(page).toHaveURL(/INC-12$/);
});

test("pedir cambios devuelve la propuesta al agente y la nueva explica qué ajustó", async ({ page }) => {
  await freshStart(page);
  await declare(page, "Pagos fallando en checkout");
  await expect(page.getByRole("heading", { name: "El agente propone una mitigación" })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Pedir cambios" }).click();
  await page.getByRole("textbox", { name: "¿Qué debería cambiar?" }).fill("Prefiero el restablecimiento completo de flags.");
  await page.getByRole("button", { name: "Enviar al agente" }).click();
  await expect(page.getByRole("heading", { name: "El agente está preparando otra propuesta" })).toBeVisible();
  await expect(page.getByText("Ajustada según tu comentario: «Prefiero el restablecimiento completo de flags.»")).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByText("Restaurar todos los flags a su configuración base").first()).toBeVisible();
  await page.screenshot({ path: `${SCREENS}/12-propuesta-revisada.png`, fullPage: true });
});

test("si la mitigación no funciona, «Sigue fallando» vuelve a investigar sin abrir otro incidente", async ({ page }) => {
  await freshStart(page);
  await declare(page, "Pagos fallando en checkout");
  await expect(page.getByRole("heading", { name: "El agente propone una mitigación" })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("button", { name: "Aprobar mitigación" }).click();
  await page.getByRole("button", { name: "Ya la apliqué" }).click();
  await page.getByRole("button", { name: "Sigue fallando" }).click();
  await expect(page.getByRole("heading", { name: "El agente está investigando de nuevo" })).toBeVisible();
  await expect(page.getByText("«paymentUnreachable» sigue activo").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Nueva propuesta: el cambio anterior no quedó aplicado.")).toBeVisible({ timeout: 30_000 });
  await expect(page).toHaveURL(/INC-12$/);
  await settle(page);
  await page.screenshot({ path: `${SCREENS}/13-sigue-fallando.png`, fullPage: true });
});

test("la bandeja dice qué hace el agente y permite vincular una alerta al incidente abierto", async ({ page }) => {
  await freshStart(page);
  await declare(page, "Pagos fallando en checkout");
  await expect(page).toHaveURL(/INC-12$/);
  await page.getByRole("link", { name: "Bandeja" }).first().click();
  await expect(page.getByRole("heading", { name: "El agente está trabajando" })).toBeVisible();
  await expect(page.locator("article", { hasText: "INC-12" }).getByText("El agente está investigando")).toBeVisible();

  await alertCard(page, "Errores intermitentes en anuncios").getByRole("button", { name: "Vincular a un incidente" }).click();
  await settle(page);
  await page.screenshot({ path: `${SCREENS}/14-bandeja-agente-y-vincular.png`, fullPage: true });
  await page.getByRole("option", { name: /INC-12/ }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("1 cosa necesita tu atención");

  await page.locator("article", { hasText: "INC-12" }).getByRole("link", { name: "Pagos fallando en checkout" }).click();
  await expect(page.getByText("Vinculaste la alerta «Errores intermitentes en anuncios»")).toBeVisible();

  // Los ids quedan disponibles para auditoría, fuera del camino.
  await page.getByRole("button", { name: "Más acciones" }).click();
  await page.getByRole("menuitem", { name: "Detalles técnicos" }).click();
  await expect(page.getByRole("dialog", { name: "Detalles técnicos" }).getByText(/^inc-/)).toBeVisible();
  await settle(page);
  await page.screenshot({ path: `${SCREENS}/15-detalles-tecnicos.png` });
  await page.keyboard.press("Escape");

  await page.keyboard.press("Control+k");
  await page.getByRole("dialog").getByRole("combobox").fill("recom");
  await settle(page);
  await page.screenshot({ path: `${SCREENS}/16-buscar.png` });
  await page.getByRole("option", { name: /Declarar: Recomendaciones lentas/ }).click();
  await expect(page.getByRole("dialog").getByText("Recomendaciones lentas en la tienda")).toBeVisible();
});

test("se ve bien en modo oscuro y en el celular", async ({ page }) => {
  await freshStart(page);
  await page.emulateMedia({ colorScheme: "dark" });
  await settle(page);
  await page.screenshot({ path: `${SCREENS}/20-oscuro-bandeja.png` });
  await declare(page, "Pagos fallando en checkout");
  await expect(page.getByRole("heading", { name: "El agente propone una mitigación" })).toBeVisible({ timeout: 60_000 });
  await settle(page);
  await page.screenshot({ path: `${SCREENS}/21-oscuro-propuesta.png` });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ colorScheme: "light" });
  await settle(page);
  await page.screenshot({ path: `${SCREENS}/22-movil-propuesta.png` });
  await page.getByRole("button", { name: "Abrir menú" }).click();
  await settle(page);
  await page.screenshot({ path: `${SCREENS}/23-movil-menu.png` });
});
