import { mkdirSync, writeFileSync } from "node:fs";
import { expect, test, type APIRequestContext } from "@playwright/test";
import { freshEpisodes } from "./live-faults";

/*
 * Issue #703 against the live-triage stack (compose.live-triage-e2e.yaml: FastAPI, PostgreSQL and
 * the web proxy; stand-in model and Grafana MCP). The spec opens its own alert episode. Only one
 * route is touched, to drop the answer of a POST the server did process. Ways this can fail:
 * 1. the live card offers no declaration, or the dialog is not prefilled from the alert;
 * 2. the dialog declares in the browser only: the API has no triage decision or no incident;
 * 3. a version that went stale while the dialog was open ends in an error instead of one retry;
 * 4. after a lost answer, the operator's retry sends a new key and reads as someone else's decision;
 * 5. the console does not land on the declared incident's route;
 * 6. the card does not show `Declarada` with a link to the incident.
 */

const enabled = process.env.LIVE_DECLARE === "1" && Boolean(process.env.DEMO_HUMAN_API_KEY && process.env.FAULT_DIR);
const BASE = process.env.BASE_URL ?? "http://127.0.0.1:8080";

test.use({ video: "off", trace: "off" });

type Exchange = { at: string; method: string; path: string; status: number; code?: string; expectedVersion?: number; key?: string };

async function triageVersion(api: APIRequestContext, alertId: string): Promise<number> {
  const response = await api.get(`${BASE}/api/v1/alerts/${encodeURIComponent(alertId)}/triage/context`);
  expect(response.status()).toBe(200);
  const body = (await response.json()) as { triage_state: { expected_version: number } | null };
  return body.triage_state?.expected_version ?? 1;
}

test.describe("declarar desde la tarjeta contra la pila real", () => {
  test.skip(!enabled, "Requiere LIVE_DECLARE=1, DEMO_HUMAN_API_KEY y FAULT_DIR (compose.live-triage-e2e.yaml)");

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
        entry.key = response.request().headers()["idempotency-key"];
        try {
          entry.code = ((await response.json()) as { error?: { code?: string } }).error?.code;
        } catch {
          entry.code = undefined;
        }
      }
      exchanges.push(entry);
    });

    const [fresh] = await freshEpisodes(api, BASE, ["checkout-payment-error-rate"]);
    await page.goto("./");
    await page.getByRole("button", { name: "Conectar API" }).click();
    const connect = page.getByRole("dialog");
    await connect.getByLabel("Clave de API").fill(key);
    await connect.getByRole("button", { name: "Conectar", exact: true }).click();

    const alertId = fresh;
    const card = page.locator(`article[data-alert-id="${alertId}"]`);
    await expect(card).toBeVisible({ timeout: 60_000 });
    await page.screenshot({ path: `${dir}/1-inbox-before.png`, fullPage: true });

    await card.getByRole("button", { name: "Declarar incidente" }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: "Declarar incidente" })).toBeVisible();
    await expect(dialog.getByLabel("¿Qué notan tus clientes?")).not.toHaveValue("");
    const impact = "Los clientes no pueden completar el pago en checkout.";
    await dialog.getByLabel("¿Qué notan tus clientes?").fill(impact);
    await expect.poll(() => exchanges.some((entry) => entry.path.endsWith("/triage/context"))).toBe(true);

    // Another operator works the alert while this dialog is open: the version the dialog read is
    // stale. An untriaged alert and its first open_triage both read version 1, so open it twice.
    const before = await triageVersion(api, alertId!);
    for (const attempt of [1, 2]) {
      const opened = await api.post(`${BASE}/api/v1/alerts/${encodeURIComponent(alertId!)}/triage/commands`, {
        headers: { "Idempotency-Key": `e2e-703-open-${attempt}-${Date.now().toString(36)}` },
        data: { operation: "open_triage", expected_version: await triageVersion(api, alertId!) },
      });
      expect(opened.status()).toBe(200);
    }
    expect(await triageVersion(api, alertId!)).not.toBe(before);
    await page.screenshot({ path: `${dir}/2-dialog-prefilled.png` });

    // The retry after the stale version reaches the server, but its answer is lost on the way back.
    let lost: { key?: string; status: number } | undefined;
    await page.route("**/triage/commands", async (route) => {
      const response = await route.fetch();
      if (response.status() !== 201 || lost) return route.fulfill({ response });
      lost = { key: route.request().headers()["idempotency-key"], status: response.status() };
      await route.abort("connectionreset");
    });
    await dialog.getByRole("button", { name: /Declarar e investigar/ }).click();
    await expect(dialog.getByRole("alert")).toHaveText("No pudimos declarar el incidente. Vuelve a intentarlo.");
    await page.screenshot({ path: `${dir}/3-lost-answer.png` });
    await page.unroute("**/triage/commands");
    await dialog.getByRole("button", { name: /Declarar e investigar/ }).click();
    await expect(dialog).toBeHidden({ timeout: 30_000 });

    // 409 stale (key A), 201 lost (key B), then the operator's retry: key B again, replayed as 201.
    const posts = exchanges.filter((entry) => entry.method === "POST");
    expect(posts.map((entry) => entry.status)).toEqual([409, 201]);
    expect(posts[0].code).toBe("stale_version");
    expect(posts[1].key).toBe(lost!.key);
    expect(posts[0].key).not.toBe(lost!.key);

    const state = await api.get(`${BASE}/api/v1/alerts/${encodeURIComponent(alertId!)}/triage`);
    expect(state.status()).toBe(200);
    const triage = (await state.json()) as { status: string; incident_id: string; actor: string };
    expect(triage.status).toBe("declared");
    expect(triage.incident_id).toMatch(/^inc-/);
    expect((await api.get(`${BASE}/api/v1/incidents/${triage.incident_id}`)).status()).toBe(200);

    // The console lands on the declared incident's route; reading it live is #708.
    await expect(page).toHaveURL(new RegExp(`/incidentes/${triage.incident_id}$`));
    await page.goBack();

    const declared = page.locator(`article[data-alert-id="${alertId}"]`);
    await expect(declared.getByText("Declarada")).toBeVisible();
    await expect(declared.getByRole("link", { name: "Ver incidente" })).toHaveAttribute(
      "href",
      new RegExp(`/incidentes/${triage.incident_id}$`),
    );
    await expect(declared.getByRole("button", { name: "Declarar incidente" })).toHaveCount(0);
    await page.screenshot({ path: `${dir}/5-card-declared.png`, fullPage: true });

    const verification = { sanitized: true, alertId, incidentId: triage.incident_id, actor: triage.actor, lostAnswer: lost };
    writeFileSync(`${dir}/verification.json`, JSON.stringify({ ...verification, versionReadByDialog: before, exchanges }, null, 2));
    await api.dispose();
  });
});
