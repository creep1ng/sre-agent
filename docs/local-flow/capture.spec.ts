import { mkdirSync, writeFileSync } from "node:fs";
import { expect, request, test, type Page } from "@playwright/test";

/*
 * Screenshots of the local full flow (docs/local-flow/README.md), against compose.local-flow.yaml: the real
 * API, console and Telegram gateway; Grafana, its MCP and the Bot API are stand-ins. It fires the
 * rule by writing its file in /flow (the stack's LOCAL_FLOW_DIR), follows the incident from the
 * landing to the decision, decides in Telegram or in the console (LOCAL_FLOW_DECIDE), then clears
 * the alert. Mounted into incident-console-e2e by the commands of docs/local-flow/README.md; the key stays in
 * this tab's memory and is never written.
 */

const KEY = process.env.DEMO_HUMAN_API_KEY ?? "";
const WEB = process.env.BASE_URL ?? "http://web";
const FAKE = "http://fake-telegram:8081";
const RULE = "checkout-orders-error-rate";
const DECIDE = process.env.LOCAL_FLOW_DECIDE === "console" ? "console" : "telegram";
const DIR = process.env.LOCAL_FLOW_SHOTS ?? "e2e/artifacts/local-flow";
const WAIT = Number(process.env.LOCAL_FLOW_WAIT_MS ?? 180_000);
const record: Record<string, unknown> = { decide: DECIDE };

test.use({ video: "off", trace: "off", viewport: { width: 1440, height: 960 } });
test.setTimeout(WAIT * 3);

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `${DIR}/${name}.png`, fullPage: true });
}

async function sent(): Promise<{ message_id: number; chat_id: number; text: string; buttons: [string, string][][] }[]> {
  return (await (await request.newContext()).get(`${FAKE}/_test/sent`)).json();
}

test("local full flow, from the alert to the decision", async ({ page }) => {
  test.skip(!KEY, "needs DEMO_HUMAN_API_KEY");
  mkdirSync(DIR, { recursive: true });
  writeFileSync(`/flow/${RULE}`, "ok\n");

  await page.goto(`${WEB}/`);
  await shot(page, "01-landing");
  await page.getByRole("link", { name: /Abrir la consola/ }).first().click();
  await expect(page).toHaveURL(/\/app\//);
  await page.getByRole("button", { name: "Conectar API" }).click();
  await page.getByRole("dialog").getByLabel("Clave de API").fill(KEY);
  await page.getByRole("dialog").getByRole("button", { name: "Conectar", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).not.toHaveText(/API/, { timeout: 30_000 });
  await shot(page, "02-inbox-quiet");

  const before = (await sent()).length;
  writeFileSync(`/flow/${RULE}`, "firing\n");
  record.fired_at = new Date().toISOString();
  const review = page.getByRole("link", { name: "Revisar y decidir" }).first();
  await expect(review).toBeVisible({ timeout: WAIT });
  record.decision_in_inbox_at = new Date().toISOString();
  await shot(page, "03-inbox-decision");

  await expect.poll(async () => (await sent()).slice(before).filter((m) => m.buttons.length).length, { timeout: WAIT }).toBe(1);
  const messages = (await sent()).slice(before);
  record.telegram_messages = messages.map((m) => ({ text: m.text, buttons: m.buttons.flat().map(([label]) => label) }));
  const telegram = await page.context().newPage();
  await telegram.goto(`${FAKE}/_test/transcript`);
  await shot(telegram, "04-telegram-decision");

  await review.click();
  await expect(page.getByRole("button", { name: "Aprobar" })).toBeVisible({ timeout: 30_000 });
  await shot(page, "05-incident-proposal");

  if (DECIDE === "telegram") {
    const decision = messages.find((m) => m.buttons.length)!;
    const approve = decision.buttons.flat().find(([label]) => /Aprobar/.test(label))!;
    const tapped = await (await request.newContext()).post(`${FAKE}/_test/taps`, {
      data: { chat_id: decision.chat_id, message_id: decision.message_id, data: approve[1] },
    });
    expect(tapped.ok()).toBe(true);
    await expect.poll(async () => (await (await request.newContext()).get(`${FAKE}/_test/answers`)).json().then((a) => a.answers.length), { timeout: 30_000 }).toBeGreaterThan(0);
    await telegram.reload();
    await shot(telegram, "06-telegram-approved");
  } else {
    await page.getByRole("button", { name: "Aprobar" }).click();
  }
  await expect(page.getByRole("button", { name: "Aprobar" })).toBeHidden({ timeout: 60_000 });
  await shot(page, "07-incident-approved");

  writeFileSync(`/flow/${RULE}`, "ok\n");
  record.cleared_at = new Date().toISOString();
  await page.waitForTimeout(8_000);
  await page.goto(`${WEB}/app/`);
  await page.getByRole("button", { name: "Conectar API" }).click();
  await page.getByRole("dialog").getByLabel("Clave de API").fill(KEY);
  await page.getByRole("dialog").getByRole("button", { name: "Conectar", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).not.toHaveText(/API/, { timeout: 30_000 });
  await shot(page, "08-inbox-after");
  writeFileSync(`${DIR}/local-flow.json`, JSON.stringify(record, null, 2));
});
