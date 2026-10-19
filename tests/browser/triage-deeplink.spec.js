import { expect, test } from "@playwright/test";
import { answerWhoAmI, connectConsole } from "./support/console-session.mjs";

// A deep link into Triage preloads its alert. Canceling it before connecting must also clear the
// address: otherwise Back would bring the canceled alert back. The console shares no fixture of
// its own here, so whoami is answered by the suite like the rest of the mocked console specs.
const ALERT = "alert-cart-004";

const contextRequests = (page) => {
  const urls = [];
  page.on("request", (request) => {
    if (request.url().includes("/triage/context")) urls.push(request.url());
  });
  return urls;
};

test("cancelar el deep link de una alerta antes de conectar la retira de la dirección", async ({ page }) => {
  await answerWhoAmI(page);
  const reads = contextRequests(page);

  await page.goto(`/?view=triage&alert_id=${ALERT}`);
  await expect(page.locator("#alert-id")).toHaveValue(ALERT);

  // The person clears the field before connecting: the pending deep link is canceled.
  await page.locator("#alert-id").fill("");
  await connectConsole(page);
  await expect(page.locator("#alert-id")).toHaveValue("");
  expect(new URL(page.url()).searchParams.has("alert_id")).toBe(false);
  expect(reads).toEqual([]);

  // Leaving Triage and coming back: the canceled alert cannot return through the address.
  await page.route("**/api/v1/alerts", (route) =>
    route.fulfill({ json: { evaluated_at: "2026-10-19T04:00:00Z", rules: [], alerts: [] } }),
  );
  await page.locator('[data-console-nav="alerts"]').click();
  await expect(page.locator("#alert-inbox")).toHaveAttribute("data-state", "empty");
  await page.goBack();
  await expect(page.locator("[data-console-view='triage'] #alert-id")).toHaveValue("");
  expect(new URL(page.url()).searchParams.has("alert_id")).toBe(false);
  expect(reads).toEqual([]);
});

test("el deep link vigente sí precarga su alerta al conectar", async ({ page }) => {
  await answerWhoAmI(page);
  const reads = contextRequests(page);
  await page.route("**/api/v1/alerts/*/triage/context", (route) =>
    route.fulfill({
      json: { alert_id: ALERT, triage_state: null, allowed_actions: ["open_triage"] },
    }),
  );

  await page.goto(`/?view=triage&alert_id=${ALERT}`);
  await connectConsole(page);

  await expect(page.locator("#alert-id")).toHaveValue(ALERT);
  await expect(page.locator("#triage-state")).toContainText(`La alerta ${ALERT}`);
  expect(new URL(page.url()).searchParams.get("alert_id")).toBe(ALERT);
  expect(reads).toHaveLength(1);
});
