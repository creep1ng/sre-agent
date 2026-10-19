import { expect, test } from "@playwright/test";
import { answerWhoAmI, connectConsole } from "./support/console-session.mjs";

// Live inbox polling (#672). Failure modes, written before the change: a transient upstream
// error (502/503) wipes the list that was on screen; a denial (403) is hidden behind a stale
// list; an inbox that never loaded shows nothing; polling continues after an error.
const ALERT = {
  alert_id: "alt-checkout-0123456789ab",
  service: "checkout",
  severity: "sev1",
  status: "new",
  observed_at: "2026-10-19T05:05:00Z",
  summary: "checkout payment calls failing: 100% errors over the last 2m (threshold 5%)",
  source: "opentelemetry-demo",
  origin: { signal: "oteldemo.PaymentService/Charge", condition: "checkout-payment-error-rate: error ratio 1.00 > 0.05", detector: "sre-agent-alert-rules", observed_at: "2026-10-19T05:05:00Z" },
};
const firing = { evaluated_at: "2026-10-19T05:05:00Z", rules: [{ rule_id: "checkout-payment-error-rate", state: "firing", value: 1 }], alerts: [ALERT] };
const failure = (status, code) => ({ status, json: { error: { code, message: code }, request_id: "00000000-0000-4000-8000-000000000001", retryable: status === 503 } });

async function scriptAlerts(page, answers) {
  const seen = [];
  await page.route("**/api/v1/alerts", (route) => {
    const next = answers[Math.min(seen.length, answers.length - 1)];
    seen.push(next.status ?? 200);
    return route.fulfill(next.status ? next : { json: next });
  });
  return seen;
}

test.beforeEach(async ({ page }) => {
  await page.clock.install();
  await answerWhoAmI(page);
});

test("a transient upstream error keeps the live list and says it is retrying", async ({ page }) => {
  const seen = await scriptAlerts(page, [firing, failure(502, "alert_source_invalid"), firing]);
  await page.goto("/");
  await connectConsole(page);
  const card = page.locator(`#alert-list [data-alert-id="${ALERT.alert_id}"]`);
  await expect(card).toBeVisible();
  await page.clock.fastForward(15000);
  await expect.poll(() => seen.length).toBe(2);
  await expect(page.locator("#alert-inbox")).toHaveAttribute("data-state", "ready");
  await expect(card).toBeVisible();
  await expect(page.locator("#fixture-label")).toContainText("reintentando");
  const artifacts = process.env.LIVE_ALERTS_ARTIFACT_DIR;
  if (artifacts) await page.screenshot({ path: `${artifacts}/inbox-live-retrying.png` });
  await page.clock.fastForward(15000);
  await expect.poll(() => seen.length).toBe(3);
  await expect(page.locator("#fixture-label")).not.toContainText("reintentando");
});

test("a denial is never hidden behind the last list", async ({ page }) => {
  await scriptAlerts(page, [firing, failure(403, "alert_source_forbidden")]);
  await page.goto("/");
  await connectConsole(page);
  await expect(page.locator(`#alert-list [data-alert-id="${ALERT.alert_id}"]`)).toBeVisible();
  await page.clock.fastForward(15000);
  await expect(page.locator("#alert-inbox")).toHaveAttribute("data-state", "error");
  await expect(page.locator("#load-error-title")).toHaveText("Sin acceso a alertas en vivo");
});

test("an inbox that never loaded shows the error and keeps polling", async ({ page }) => {
  const seen = await scriptAlerts(page, [failure(503, "alert_source_unavailable"), firing]);
  await page.goto("/");
  await connectConsole(page);
  await expect(page.locator("#alert-inbox")).toHaveAttribute("data-state", "error");
  await expect(page.locator("#load-error-title")).toHaveText("Fuente de alertas no disponible");
  await page.clock.fastForward(15000);
  await expect.poll(() => seen.length).toBe(2);
  await expect(page.locator("#alert-inbox")).toHaveAttribute("data-state", "ready");
});
