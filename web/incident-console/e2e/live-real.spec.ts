import { mkdirSync, writeFileSync } from "node:fs";
import { expect, test } from "@playwright/test";

/*
 * Opt-in journey against the real stack: OTel demo + setup_sre.py and an injected checkout
 * failure. Run it only with LIVE_INBOX=1 and the demo key while the failure is injected; the
 * test tolerates empty polls until the first alert. The log keeps statuses, counts and alert ids;
 * the key never reaches disk. With Grafana alert intake (#765) the card may arrive declared, and
 * the store's generic rules may fire for other services too: the checkout card is the one followed.
 */

const enabled = process.env.LIVE_INBOX === "1" && Boolean(process.env.DEMO_HUMAN_API_KEY);

test.use({ video: "off", trace: "off" });

test.describe("bandeja contra la pila real", () => {
  test.skip(!enabled, "Requiere LIVE_INBOX=1 y DEMO_HUMAN_API_KEY con la pila de demostración arriba");

  test("una falla real de checkout llega, se refresca y se filtra", async ({ page }) => {
    test.setTimeout(300_000);
    const key = process.env.DEMO_HUMAN_API_KEY!;
    const startedAt = new Date().toISOString();
    const started = Date.now();
    const polls: Array<{ at: string; status: number; count: number; alertIds: string[] }> = [];
    const seen: string[] = [];
    const dir = "e2e/artifacts/live";
    mkdirSync(dir, { recursive: true });

    page.on("response", async (response) => {
      if (!response.url().includes("/api/v1/alerts")) return;
      const status = response.status();
      let alertIds: string[] = [];
      try {
        const body = (await response.json()) as { alerts?: Array<{ alert_id: string }> };
        alertIds = (body.alerts ?? []).map((item) => item.alert_id);
      } catch {
        alertIds = [];
      }
      seen.push(...alertIds);
      polls.push({ at: new Date().toISOString(), status, count: alertIds.length, alertIds });
      writeFileSync(`${dir}/poll-log.json`, JSON.stringify({ sanitized: true, polls }, null, 2));
    });

    await page.goto("./");
    await page.getByRole("button", { name: "Conectar API" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Clave de API").fill(key);
    await dialog.getByRole("button", { name: "Conectar", exact: true }).click();

    const card = page.locator("article").filter({ hasText: "checkout" }).filter({ hasText: "SEV1" }).first();
    await expect(card).toBeVisible({ timeout: 240_000 });
    const elapsedMs = Date.now() - started;
    const cardId = (await card.getAttribute("data-alert-id"))!;

    await expect(card.getByText("checkout", { exact: true })).toBeVisible();
    await expect(card.getByText(/\d{2}:\d{2}/)).toBeVisible();
    await expect(card.getByText(/Nueva|En triage|Declarada|Vinculada|Descartada/)).toBeVisible();

    await page.screenshot({ path: `${dir}/inbox-live.png`, fullPage: true });

    await expect
      .poll(() => polls.filter((poll) => poll.status === 200).length, { timeout: 25_000 })
      .toBeGreaterThanOrEqual(2);
    const successful = polls.filter((poll) => poll.status === 200);
    // The card's episode keeps its id on every poll after it first appears.
    const firstAlert = successful.findIndex((poll) => poll.alertIds.includes(cardId));
    expect(firstAlert).toBeGreaterThanOrEqual(0);
    const afterAlert = successful.slice(firstAlert);
    expect(afterAlert.every((poll) => poll.alertIds.includes(cardId))).toBe(true);

    const filter = page.getByRole("button", { name: /Filtrar por servicio/ });
    await expect(filter).toBeVisible();
    await filter.click();
    await page.getByRole("menuitemradio", { name: /^checkout/ }).click();
    await expect(card).toBeVisible();

    expect(page.url()).not.toContain(key);
    const storage = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }));
    expect(storage).not.toContain(key);
    expect(await page.locator("body").innerText()).not.toContain(key);

    writeFileSync(
      `${dir}/verification.json`,
      JSON.stringify(
        {
          sanitized: true,
          startedAt,
          elapsedMs,
          polls: polls.length,
          alertIds: [...new Set(seen)],
        },
        null,
        2,
      ),
    );
  });
});
