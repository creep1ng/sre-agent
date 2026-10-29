import { mkdirSync, writeFileSync } from "node:fs";
import { expect, test, type APIRequestContext } from "@playwright/test";

/*
 * Issue #703 against the real stack: OTel demo with the checkout failure injected, setup_sre.py,
 * the web proxy, FastAPI and PostgreSQL. No route is answered by the test. Ways this can fail:
 * 1. the live card offers no declaration, or the dialog is not prefilled from the alert;
 * 2. the dialog declares in the browser only: the API has no triage decision or no incident;
 * 3. a version that went stale while the dialog was open ends in an error instead of one retry;
 * 4. the card does not show `Declarada` with a link to the incident, or forgets it on reload;
 * 5. the credential reaches the URL, Web Storage or the page.
 * One run declares one episode: a declared episode stays declared, so the next run needs
 * `demo_env.py reset` and `fail` for a new alert.
 */

const enabled = process.env.LIVE_DECLARE === "1" && Boolean(process.env.DEMO_HUMAN_API_KEY);
const BASE = process.env.BASE_URL ?? "http://127.0.0.1:8080";

test.use({ video: "off", trace: "off" });

interface Exchange {
  at: string;
  method: string;
  path: string;
  status: number;
  code?: string;
  expectedVersion?: number;
}

async function triageVersion(api: APIRequestContext, alertId: string): Promise<number> {
  const response = await api.get(`${BASE}/api/v1/alerts/${encodeURIComponent(alertId)}/triage/context`);
  expect(response.status()).toBe(200);
  const body = (await response.json()) as { triage_state: { expected_version: number } | null };
  return body.triage_state?.expected_version ?? 1;
}

test.describe("declarar desde la tarjeta contra la pila real", () => {
  test.skip(!enabled, "Requiere LIVE_DECLARE=1 y DEMO_HUMAN_API_KEY con la falla de checkout inyectada");

  test("la declaración llega a la API, sobrevive a una versión obsoleta y queda en la tarjeta", async ({
    page,
    playwright,
  }) => {
    test.setTimeout(420_000);
    const key = process.env.DEMO_HUMAN_API_KEY!;
    const dir = "e2e/artifacts/declare";
    mkdirSync(dir, { recursive: true });
    const api = await playwright.request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${key}` } });
    const exchanges: Exchange[] = [];

    page.on("response", async (response) => {
      const url = new URL(response.url());
      if (!url.pathname.includes("/triage/")) return;
      const entry: Exchange = {
        at: new Date().toISOString(),
        method: response.request().method(),
        path: url.pathname.replace(/^\/api/, ""),
        status: response.status(),
      };
      if (entry.method === "POST") {
        const sent = response.request().postDataJSON() as { expected_version?: number } | null;
        entry.expectedVersion = sent?.expected_version;
        try {
          entry.code = ((await response.json()) as { error?: { code?: string } }).error?.code;
        } catch {
          entry.code = undefined;
        }
      }
      exchanges.push(entry);
    });

    await page.goto("./");
    await page.getByRole("button", { name: "Conectar API" }).click();
    const connect = page.getByRole("dialog");
    await connect.getByLabel("Clave de API").fill(key);
    await connect.getByRole("button", { name: "Conectar", exact: true }).click();

    const card = page.locator("article").filter({ hasText: "Nueva" }).first();
    await expect(card).toBeVisible({ timeout: 300_000 });
    const alertId = await card.getAttribute("data-alert-id");
    expect(alertId).toMatch(/^alt-/);
    await page.screenshot({ path: `${dir}/1-inbox-before.png`, fullPage: true });

    await card.getByRole("button", { name: "Declarar incidente" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: "Declarar incidente" })).toBeVisible();
    await expect(dialog.getByLabel("¿Qué notan tus clientes?")).not.toHaveValue("");
    const impact = "Los clientes no pueden completar el pago en checkout.";
    await dialog.getByLabel("¿Qué notan tus clientes?").fill(impact);
    await expect.poll(() => exchanges.some((entry) => entry.path.endsWith("/triage/context"))).toBe(true);

    // Another operator opens triage while this dialog is open: the version the dialog read is stale.
    const before = await triageVersion(api, alertId!);
    const opened = await api.post(`${BASE}/api/v1/alerts/${encodeURIComponent(alertId!)}/triage/commands`, {
      headers: { "Idempotency-Key": `e2e-703-open-${Date.now().toString(36)}` },
      data: { operation: "open_triage", expected_version: before },
    });
    expect(opened.status()).toBe(200);
    expect(await triageVersion(api, alertId!)).not.toBe(before);
    await page.screenshot({ path: `${dir}/2-dialog-prefilled.png` });

    await dialog.getByRole("button", { name: /Declarar e investigar/ }).click();
    await expect(dialog).toBeHidden({ timeout: 30_000 });

    const posts = exchanges.filter((entry) => entry.method === "POST");
    expect(posts.map((entry) => entry.status)).toEqual([409, 201]);
    expect(posts[0].code).toBe("stale_version");

    const state = await api.get(`${BASE}/api/v1/alerts/${encodeURIComponent(alertId!)}/triage`);
    expect(state.status()).toBe(200);
    const triage = (await state.json()) as { status: string; incident_id: string; actor: string };
    expect(triage.status).toBe("declared");
    expect(triage.incident_id).toMatch(/^inc-/);
    const incident = await api.get(`${BASE}/api/v1/incidents/${encodeURIComponent(triage.incident_id)}`);
    expect(incident.status()).toBe(200);

    const declared = page.locator(`article[data-alert-id="${alertId}"]`);
    await expect(declared.getByText("Declarada")).toBeVisible();
    await expect(declared.getByRole("link", { name: "Ver incidente" })).toHaveAttribute(
      "href",
      new RegExp(`/incidentes/${triage.incident_id}$`),
    );
    await expect(declared.getByRole("button", { name: "Declarar incidente" })).toHaveCount(0);
    await page.screenshot({ path: `${dir}/3-card-declared.png`, fullPage: true });

    // The decision is server state: a new tab with a fresh connection still shows it.
    await page.reload();
    await page.getByRole("button", { name: "Conectar API" }).click();
    await page.getByRole("dialog").getByLabel("Clave de API").fill(key);
    await page.getByRole("dialog").getByRole("button", { name: "Conectar", exact: true }).click();
    await expect(page.locator(`article[data-alert-id="${alertId}"]`).getByText("Declarada")).toBeVisible({
      timeout: 30_000,
    });

    expect(page.url()).not.toContain(key);
    const storage = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }));
    expect(storage).not.toContain(key);
    expect(await page.locator("body").innerText()).not.toContain(key);

    writeFileSync(
      `${dir}/verification.json`,
      JSON.stringify(
        {
          sanitized: true,
          alertId,
          incidentId: triage.incident_id,
          actor: triage.actor,
          versionReadByDialog: before,
          exchanges,
        },
        null,
        2,
      ),
    );
    await api.dispose();
  });
});
