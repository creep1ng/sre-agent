import { mkdirSync, writeFileSync } from "node:fs";
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { freshEpisodes } from "./live-faults";

/*
 * Issue #703, dismiss and link from the live card against the live-triage stack
 * (compose.live-triage-e2e.yaml: the web proxy, FastAPI, PostgreSQL; stand-in model and Grafana
 * MCP). No route is answered by the test. LIVE_TRIAGE picks one scenario, and each opens its own
 * alert episode, so they run one after another on one stack. Ways this can fail:
 * 1. the card dismisses or links in the browser only: the API holds no decision;
 * 2. a version that went stale while the popover was open ends in an error instead of one retry;
 * 3. linking offers no real eligible incident, links to another one, or lists it without its
 *    service and summary;
 * 4. a refused decision shows a status code, a version or an operation instead of Spanish text.
 */

const scenario = process.env.LIVE_TRIAGE ?? "";
const FAULT_DIR = process.env.FAULT_DIR ?? "";
const enabled = ["dismiss", "link", "conflict"].includes(scenario) && Boolean(process.env.DEMO_HUMAN_API_KEY && FAULT_DIR);
const BASE = process.env.BASE_URL ?? "http://127.0.0.1:8080";
const DIR = `e2e/artifacts/triage-${scenario}`;

test.use({ video: "off", trace: "off" });

async function command(api: APIRequestContext, alertId: string, data: Record<string, unknown>) {
  const response = await api.post(`${BASE}/api/v1/alerts/${encodeURIComponent(alertId)}/triage/commands`, {
    headers: { "Idempotency-Key": `e2e-703-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}` },
    data,
  });
  return response;
}

async function version(api: APIRequestContext, alertId: string): Promise<number> {
  const response = await api.get(`${BASE}/api/v1/alerts/${encodeURIComponent(alertId)}/triage/context`);
  expect(response.status()).toBe(200);
  return ((await response.json()) as { triage_state: { expected_version: number } | null }).triage_state?.expected_version ?? 1;
}

async function connect(page: Page, key: string) {
  await page.getByRole("button", { name: "Conectar API" }).click();
  await page.getByRole("dialog").getByLabel("Clave de API").fill(key);
  await page.getByRole("dialog").getByRole("button", { name: "Conectar", exact: true }).click();
}

test.describe("descartar y vincular desde la tarjeta contra la pila real", () => {
  test.skip(!enabled, "Requiere LIVE_TRIAGE=dismiss|link|conflict, DEMO_HUMAN_API_KEY y FAULT_DIR");

  test(`escenario ${scenario}`, async ({ page, playwright }) => {
    test.setTimeout(scenario === "link" ? 900_000 : 420_000);
    const key = process.env.DEMO_HUMAN_API_KEY!;
    mkdirSync(DIR, { recursive: true });
    const api = await playwright.request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${key}` } });
    const posts: { status: number; code?: string }[] = [];
    page.on("response", async (response) => {
      if (response.request().method() !== "POST" || !response.url().includes("/triage/commands")) return;
      let code: string | undefined;
      try {
        code = ((await response.json()) as { error?: { code?: string } }).error?.code;
      } catch {
        code = undefined;
      }
      posts.push({ status: response.status(), code });
    });

    // One episode of one rule, so `link` sees exactly one new alert when it reopens the fault.
    let [alertId] = await freshEpisodes(api, BASE, ["checkout-payment-error-rate"]);
    await page.goto("./");
    await connect(page, key);
    let pinned = page.locator(`article[data-alert-id="${alertId}"]`);
    await expect(pinned).toBeVisible({ timeout: 60_000 });
    let destination: string | undefined;

    if (scenario === "link") {
      // Episode 1: its real alert is declared from the card and the declarant opens the investigation.
      const first = alertId;
      await pinned.getByRole("button", { name: "Declarar incidente" }).click();
      await page.getByRole("dialog").getByRole("button", { name: /Declarar e investigar/ }).click();
      await expect(page).toHaveURL(/\/incidentes\/inc-[^/]+$/, { timeout: 30_000 });
      destination = page.url().split("/").pop()!;
      await page.goBack();
      // Episode 2 of the same rule: the stand-in ends the failure and fires it again.
      [alertId] = await freshEpisodes(api, BASE, ["checkout-payment-error-rate"]);
      expect(alertId).not.toBe(first);
      pinned = page.locator(`article[data-alert-id="${alertId}"]`);
      await expect(pinned).toBeVisible({ timeout: 60_000 });
      await expect
        .poll(async () => {
          const eligible = await api.get(`${BASE}/api/v1/alerts/${alertId}/triage/eligible-incidents`);
          return ((await eligible.json()) as { items: { incident_id: string }[] }).items.map((item) => item.incident_id);
        })
        .toContain(destination);

      await pinned.getByRole("button", { name: "Vincular a un incidente" }).click();
      const option = page.getByRole("option").filter({ hasText: destination });
      await expect(option).toBeVisible({ timeout: 30_000 });
      // The incident reads as the alert that opened it, not only as inc-<hex>.
      await expect(option).toContainText("checkout");
      await page.screenshot({ path: `${DIR}/1-eligible.png` });
      await option.click();
    } else {
      await pinned.getByRole("button", { name: "Descartar" }).click();
      await page.getByRole("radio", { name: "Falsa alarma" }).click();
      // Another tab acts while the popover is open: it bumps the version, or decides first. An
      // untriaged alert and its first open_triage both read version 1, so it opens twice.
      const before = await version(api, alertId);
      if (scenario === "dismiss") {
        expect((await command(api, alertId, { operation: "open_triage", expected_version: before })).status()).toBe(200);
      }
      const raced =
        scenario === "dismiss"
          ? await command(api, alertId, { operation: "open_triage", expected_version: await version(api, alertId) })
          : await command(api, alertId, {
              operation: "triage_dismiss",
              expected_version: before,
              reason: "Descartada desde otra pestaña.",
            });
      expect(raced.status()).toBe(200);
      await page.getByRole("button", { name: "Descartar alerta" }).click();
    }

    if (scenario === "conflict") {
      const refusal = page.getByRole("alert").filter({ hasText: "Alguien más decidió sobre esta alerta" });
      await expect(refusal).toBeVisible({ timeout: 30_000 });
      expect(posts.map((post) => [post.status, post.code])).toEqual([[409, "terminal_decision"]]);
      const text = await page.locator("body").innerText();
      for (const leak of ["409", "terminal_decision", "expected_version", "triage_dismiss", "versión"]) {
        expect(text).not.toContain(leak);
      }
      await page.screenshot({ path: `${DIR}/2-refusal.png` });
    } else {
      const expected = scenario === "dismiss" ? ["dismissed", 200] : ["linked", 200];
      await expect.poll(() => posts.at(-1)?.status, { timeout: 30_000 }).toBe(expected[1]);
      if (scenario === "dismiss") expect(posts.map((post) => [post.status, post.code])).toEqual([[409, "stale_version"], [200, undefined]]);
      const state = (await (await api.get(`${BASE}/api/v1/alerts/${alertId}/triage`)).json()) as {
        status: string;
        incident_id: string | null;
      };
      expect(state.status).toBe(expected[0]);
      if (destination) expect(state.incident_id).toBe(destination);
      const label = scenario === "dismiss" ? "Descartada" : "Vinculada";
      await expect(pinned.getByText(label)).toBeVisible();
      await expect(pinned.getByRole("button", { name: "Descartar" })).toHaveCount(0);
      if (destination) {
        await expect(pinned.getByRole("link", { name: "Ver incidente" })).toHaveAttribute(
          "href",
          new RegExp(`/incidentes/${destination}$`),
        );
      }
      await page.screenshot({ path: `${DIR}/2-card-${expected[0]}.png`, fullPage: true });
    }

    writeFileSync(
      `${DIR}/verification.json`,
      JSON.stringify({ sanitized: true, scenario, alertId, destination: destination ?? null, posts }, null, 2),
    );
    await api.dispose();
  });
});
