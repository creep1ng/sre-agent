import { expect, test, type Page } from "@playwright/test";

/*
 * The inbox reads GET /api/v1/alerts through the same-origin proxy. These journeys answer that
 * route directly, so they need no OTel demo. The credential is typed in the real dialog; there
 * is no production hook for tests.
 */

test.use({ video: "off", trace: "off" });

const bogota = new Intl.DateTimeFormat("es-CO", {
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
  timeZone: "America/Bogota",
});

function alert(overrides: Record<string, unknown> = {}) {
  return {
    alert_id: "alt-checkout-abc123",
    service: "checkout",
    severity: "sev1",
    status: "new",
    observed_at: new Date(Date.now() - 60_000).toISOString(),
    summary: "Checkout payment calls failing: 100% errors over the last 2m (threshold 5%). Evidence: Prometheus.",
    source: "otel-demo",
    triage_status: "new",
    incident_id: null,
    ...overrides,
  };
}

function answer(alerts: unknown[]) {
  return {
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ evaluated_at: new Date().toISOString(), rules: [], alerts }),
  };
}

async function connect(page: Page, key = "test-only-key") {
  await page.getByRole("button", { name: "Conectar API" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Clave de API").fill(key);
  await dialog.getByRole("button", { name: "Conectar", exact: true }).click();
}

test("sin credencial pide conectar y no llama a la API", async ({ page }) => {
  let requested = false;
  await page.route("**/api/v1/alerts", (route) => {
    requested = true;
    return route.fulfill(answer([]));
  });
  await page.goto("./");

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Conecta una credencial");
  await expect(page.getByRole("button", { name: "Conectar API" })).toBeVisible();
  expect(requested).toBe(false);
});

test("una clave inválida se explica sin códigos y no deja la clave en el navegador", async ({ page }) => {
  let authorization = "";
  await page.route("**/api/v1/alerts", (route) => {
    authorization = route.request().headers()["authorization"] ?? "";
    return route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ error: { code: "authentication_failed" } }) });
  });
  await page.goto("./");
  await connect(page);

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("La API rechazó la credencial");
  expect(authorization).toBe("Bearer test-only-key");
  const text = await page.locator("body").innerText();
  expect(text).not.toContain("401");
  expect(text).not.toContain("authentication_failed");
  const storage = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }));
  expect(storage).not.toContain("test-only-key");
});

test("sin permiso de lectura se explica y la lista anterior desaparece", async ({ page }) => {
  await page.clock.install();
  let forbidden = false;
  await page.route("**/api/v1/alerts", (route) =>
    forbidden
      ? route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ error: { code: "not_authorized" } }) })
      : route.fulfill(answer([alert()])),
  );
  await page.goto("./");
  await connect(page);
  await expect(page.getByRole("heading", { name: "Checkout payment calls failing" })).toBeVisible();

  forbidden = true;
  await page.clock.fastForward(15_000);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Sin acceso a las alertas");
  await expect(page.getByRole("heading", { name: "Checkout payment calls failing" })).toHaveCount(0);
  expect(await page.locator("body").innerText()).not.toContain("403");
});

test("un fallo transitorio conserva la lista y se recupera en el siguiente sondeo", async ({ page }) => {
  await page.clock.install();
  let phase = 0;
  await page.route("**/api/v1/alerts", (route) => {
    if (phase === 1) {
      return route.fulfill({ status: 503, headers: { "Retry-After": "15" }, contentType: "application/json", body: "{}" });
    }
    return route.fulfill(answer([alert()]));
  });
  await page.goto("./");
  await connect(page);
  const card = page.getByRole("heading", { name: "Checkout payment calls failing" });
  await expect(card).toBeVisible();

  phase = 1;
  await page.clock.fastForward(15_000);
  await expect(page.getByText("No pudimos actualizar las alertas. Se reintenta automáticamente.")).toBeVisible();
  await expect(card).toBeVisible();

  phase = 2;
  await page.clock.fastForward(15_000);
  await expect(page.getByText("No pudimos actualizar las alertas. Se reintenta automáticamente.")).toHaveCount(0);
  await expect(card).toBeVisible();
});

test("sondea cada 15 s y conserva el mismo alert_id", async ({ page }) => {
  await page.clock.install();
  const ids: string[] = [];
  await page.route("**/api/v1/alerts", (route) => {
    ids.push(alert().alert_id);
    return route.fulfill(answer([alert()]));
  });
  await page.goto("./");
  await connect(page);
  await expect(page.getByRole("heading", { name: "Checkout payment calls failing" })).toBeVisible();
  expect(ids).toHaveLength(1);

  await page.clock.fastForward(15_000);
  await expect.poll(() => ids.length).toBe(2);
  expect(new Set(ids).size).toBe(1);
});

test("muestra servicio, severidad, hora local y estado de triage; solo new y triaging cuentan", async ({ page }) => {
  const observedAt = new Date(Date.now() - 60_000).toISOString();
  const alerts = [
    alert({ alert_id: "alt-checkout-1", observed_at: observedAt }),
    alert({ alert_id: "alt-checkout-2", severity: "sev2", triage_status: "triaging" }),
    alert({ alert_id: "alt-payments-3", service: "payments", triage_status: "declared" }),
  ];
  await page.route("**/api/v1/alerts", (route) => route.fulfill(answer(alerts)));
  await page.goto("./");
  await connect(page);

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("2 cosas necesitan tu atención");
  const first = page.locator("article", { has: page.getByRole("heading", { name: "Checkout payment calls failing" }) }).first();
  await expect(first).toContainText("checkout");
  await expect(first).toContainText("SEV1");
  await expect(first).toContainText(bogota.format(new Date(observedAt)));
  await expect(first.getByText("Nueva", { exact: true })).toBeVisible();
  await expect(page.getByText("En triage", { exact: true })).toBeVisible();
  await expect(page.getByText("Declarada", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Alertas en vivo" })).toBeVisible();
});

test("el filtro aparece con un solo servicio y filtra de verdad", async ({ page }) => {
  await page.route("**/api/v1/alerts", (route) =>
    route.fulfill(
      answer([
        alert({ alert_id: "alt-checkout-1" }),
        alert({ alert_id: "alt-payments-2", service: "payments", severity: "sev2" }),
      ]),
    ),
  );
  await page.goto("./");
  await connect(page);

  const filter = page.getByRole("button", { name: /Filtrar por servicio/ });
  await expect(filter).toContainText("Todos los servicios");
  await filter.click();
  await expect(page.getByRole("menuitemradio", { name: /^checkout/ })).toBeVisible();
  await page.getByRole("menuitemradio", { name: /^checkout/ }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("1 cosa necesita tu atención");
  await expect(page.locator("article")).toHaveCount(1);
  await expect(filter).toContainText("checkout");
});

test("una respuesta vacía deja un estado claro", async ({ page }) => {
  await page.route("**/api/v1/alerts", (route) => route.fulfill(answer([])));
  await page.goto("./");
  await connect(page);

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Todo en orden");
  await expect(page.getByText("No hay alertas activas")).toBeVisible();
  await expect(page.getByText(/^Actualizado \d{2}:\d{2}$/)).toBeVisible();
  await expect(page.locator("article")).toHaveCount(0);
});
