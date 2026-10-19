// E2E artifact for the live alert inbox: real web + API + governed Grafana MCP.
// Run in the e2e image on the stack network, e.g.
//   docker run --rm --network host -e WEB=http://127.0.0.1:47732 -e DEMO_HUMAN_API_KEY \
//     -e OUT_DIR=/out -v "$PWD/out:/out" -v "$PWD/scripts:/s:ro" --entrypoint node <e2e-image> /s/capture_live_alerts.cjs
// Set DECLARE=1 to also declare the live alert through Triage (creates one incident).
const { chromium } = require("playwright");

const WEB = process.env.WEB ?? "http://web";
const OUT = process.env.OUT_DIR ?? "/out";
const KEY = process.env.DEMO_HUMAN_API_KEY;
const WAIT_MS = Number(process.env.WAIT_MS ?? 240000);

(async () => {
  if (!KEY) throw new Error("DEMO_HUMAN_API_KEY is required");
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const out = { started_at: new Date().toISOString(), polls: [] };
  let latest = null;
  page.on("response", async (response) => {
    if (new URL(response.url()).pathname !== "/api/v1/alerts") return;
    const body = await response.json().catch(() => null);
    out.polls.push({ at: new Date().toISOString(), status: response.status(), ids: body?.alerts?.map((a) => a.alert_id) ?? null });
    if (response.ok() && body?.alerts?.length) latest = body.alerts[0];
  });
  try {
    await page.goto(`${WEB}/`);
    await page.locator('#alert-inbox[data-state="locked"]').waitFor();
    await page.screenshot({ path: `${OUT}/live-alerts-locked.png` });
    await page.locator("#session-chip").click();
    await page.locator("#api-key").fill(KEY);
    await page.locator("#connect-button").click();
    const card = page.locator('#alert-list [data-alert-id^="alt-checkout-"]');
    await card.first().waitFor({ timeout: WAIT_MS });
    out.alert_visible_at = new Date().toISOString();
    out.alert_id = await card.first().getAttribute("data-alert-id");
    await page.screenshot({ path: `${OUT}/live-alerts-firing.png` });
    await page.waitForTimeout(16000);
    out.alert_id_after_next_poll = await card.first().getAttribute("data-alert-id");
    if (process.env.DECLARE === "1" && latest) {
      await page.locator("#start-triage").click();
      await page.locator("#command-operation").selectOption("triage_declare");
      await page.locator("#command-reason").fill("Live checkout payment alert; customers cannot pay.");
      await page.locator("#command-severity").selectOption(latest.severity);
      await page.locator("#command-impact").fill("Checkout cannot charge payments in the store.");
      await page.locator("#alert-context-service").fill(latest.service);
      await page.locator("#alert-context-summary").fill(latest.summary);
      await page.locator("#alert-context-observed-at").fill(latest.observed_at);
      await page.locator("#alert-context-source").fill(latest.source);
      await page.locator("#alert-context-severity").selectOption(latest.severity);
      await page.locator("#alert-context-confirmed").check();
      await page.locator("#submit-button").click();
      await page.locator("#result-status").filter({ hasText: "declared" }).waitFor({ timeout: 30000 });
      out.incident_id = (await page.locator("#result-incident").textContent()).trim();
      await page.screenshot({ path: `${OUT}/live-alerts-declared.png`, fullPage: true });
    }
  } catch (error) {
    out.error = String(error?.message ?? error).slice(0, 400);
    await page.screenshot({ path: `${OUT}/live-alerts-error.png` }).catch(() => {});
    process.exitCode = 1;
  }
  out.finished_at = new Date().toISOString();
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})();
