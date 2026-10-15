import { expect, test } from "@playwright/test";

// Inbox → triage handoff contract (HU-OPS-01 / issue #23 consumers, shell #487
// must preserve it). The alerts surface is fixture-driven and has no credential
// flow, so these journeys are independent of the future shared session (#486):
// they pin the navigation contract the shell will reuse (selected alert crosses
// into triage.html as ?alert_id=, no incident is created or associated here).

test("lists fixture alerts without any credential flow", async ({ page }) => {
  await page.goto("/public/incident-ui/alerts.html");
  await expect(page.locator("#alert-count")).toContainText("4", { timeout: 15000 });
  await expect(page.locator("#alert-list button")).toHaveCount(4);
  await expect(page.locator('input[type="password"], #credential-input')).toHaveCount(0);
});

test("selecting an alert arms the triage handoff for that alert", async ({ page }) => {
  await page.goto("/public/incident-ui/alerts.html");
  await page.locator("#alert-list button").first().waitFor({ timeout: 15000 });
  await page.locator("#alert-list button").first().click();

  await expect(page.locator("#detail-content")).toBeVisible();
  await expect(page.locator("#detail-id")).toContainText("alert-");
  const alertId = (await page.locator("#detail-id").textContent()) ?? "";
  expect(alertId).toMatch(/^[a-z][a-z0-9_-]{2,63}$/);
  await expect(page.locator("#start-triage")).toHaveAttribute("data-alert-id", alertId.trim());
});

test("starting triage emits the handoff event and navigates with the alert id", async ({ page }) => {
  await page.goto("/public/incident-ui/alerts.html");
  await page.locator("#alert-list button").first().waitFor({ timeout: 15000 });
  await page.locator("#alert-list button").first().click();
  const alertId = ((await page.locator("#detail-id").textContent()) ?? "").trim();
  const service = ((await page.locator("#detail-service").textContent()) ?? "").trim();
  expect(service).toMatch(/^[a-z][a-z0-9_-]{2,63}$/);

  // One synchronous turn: listeners run (feedback set, navigation queued)
  // before the browser commits to triage.html, so nothing races here.
  const snapshot = await page.evaluate(() => {
    let detail = null;
    document.addEventListener("midnight:triage-requested", (event) => {
      detail = event.detail;
    });
    document.querySelector("#start-triage").click();
    const feedback = document.querySelector("#triage-feedback");
    return {
      detail,
      feedbackText: feedback?.textContent ?? "",
      feedbackVisible: feedback !== null && !feedback.hidden,
    };
  });

  expect(snapshot.feedbackVisible).toBe(true);
  expect(snapshot.feedbackText).toContain(alertId);
  expect(snapshot.feedbackText).toContain("No se creó ni asoció un incidente");
  expect(snapshot.detail).toMatchObject({ alert_id: alertId, service, source: "hu-ops-01-alert-inbox" });

  await expect.poll(() => page.url(), { timeout: 15000 }).toContain(
    `/public/admin/triage.html?alert_id=${encodeURIComponent(alertId)}`,
  );
});
