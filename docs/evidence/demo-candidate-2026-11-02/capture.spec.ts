import { mkdirSync, writeFileSync } from "node:fs";
import { expect, request, test, type Page } from "@playwright/test";

/*
 * The 2026-11-04 demo path on the candidate (README.md), after flag_set_e2e.py ran `flow` with
 * DECIDE=telegram and the verification was recorded: the RC-2 incident page with the executor's
 * receipt, /app/acciones with checkout · flag.set and its run, the chat transcript, and the Bot
 * API calls the fake recorded. Connects with DEMO_HUMAN_API_KEY, kept in this tab's memory only.
 */
const KEY = process.env.DEMO_HUMAN_API_KEY ?? "";
const INCIDENT = process.env.INCIDENT_ID ?? "";
const WEB = process.env.BASE_URL ?? "http://web";
const FAKE = "http://fake-telegram:8081/_test";
const DIR = process.env.SHOTS ?? "e2e/artifacts/demo-candidate";

test.use({ video: "off", trace: "off", viewport: { width: 1440, height: 1100 } });

async function shot(page: Page, name: string) {
  await page.mouse.move(0, 0);
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${DIR}/${name}.png`, fullPage: true });
}

async function route(page: Page, path: string) {
  // A reload would drop the key: route inside the app instead.
  await page.evaluate((to) => {
    history.pushState({}, "", to);
    dispatchEvent(new PopStateEvent("popstate"));
  }, path);
}

test("demo path: receipt on the incident page, the run in the catalog, the chat edits", async ({ page }) => {
  test.skip(!KEY || !INCIDENT, "needs DEMO_HUMAN_API_KEY and INCIDENT_ID");
  mkdirSync(DIR, { recursive: true });
  const fake = await request.newContext();
  const sent = await (await fake.get(`${FAKE}/sent`)).json();
  const { answers, edits } = await (await fake.get(`${FAKE}/answers`)).json();
  const decision = sent.filter((m: { text: string }) => m.text.includes(INCIDENT));
  writeFileSync(`${DIR}/telegram.json`, JSON.stringify({ sent: decision, answers, edits: edits.filter((e: { text: string }) => e.text.includes(INCIDENT)) }, null, 2));
  expect(decision).toHaveLength(1);
  const lines = decision[0].text.split("\n");
  expect(lines[0]).toBe(`Decisión tomada: ${INCIDENT}`);
  expect(decision[0].text).toContain("Detalle: el ejecutor aplica flag.set en checkout");
  expect(decision[0].text).toMatch(/Aprobada por Demo human desde Telegram/);
  expect(lines.at(-1)).toMatch(/^Resuelto a las \d\d:\d\d UTC.* tras la mitigación que aprobaste/);

  await page.goto(`${WEB}/app/`);
  await page.getByRole("button", { name: "Conectar API" }).click();
  await page.getByRole("dialog").getByLabel("Clave de API").fill(KEY);
  await page.getByRole("dialog").getByRole("button", { name: "Conectar", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).not.toHaveText(/API/, { timeout: 30_000 });
  await route(page, `/app/incidentes/${INCIDENT}`);
  await expect(page.getByText(/flag\.set/).first()).toBeVisible({ timeout: 30_000 });
  await shot(page, "incident");

  await page.getByRole("complementary").getByRole("link", { name: "Acciones" }).click();
  // The service is its card's header and the runs stay folded until asked for (#964).
  await expect(page.locator('[data-service="checkout"] header')).toContainText("checkout");
  const flagSet = page.locator('[data-operation="checkout:flag.set"]');
  await expect(flagSet).toContainText("flag.set");
  const runs = flagSet.locator("details");
  await expect(runs.locator("summary")).toHaveText("Ejecuciones recientes (1)", { timeout: 20_000 });
  await runs.locator("summary").click();
  await expect(flagSet.getByRole("listitem")).toHaveCount(1);
  await expect(flagSet.getByRole("link", { name: "Ver el incidente" })).toHaveAttribute("href", `/app/incidentes/${INCIDENT}`);
  await shot(page, "acciones");

  const chat = await page.context().newPage();
  await chat.goto(`${FAKE}/transcript`);
  await shot(chat, "telegram-transcript");
});
