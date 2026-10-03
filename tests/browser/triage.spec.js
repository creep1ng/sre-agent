import { expect, test } from "@playwright/test";
const posted = [];
function ok(operation) {
  return {
    alert_id: "al-journey",
    status: operation === "triage_link" ? "linked" : "declared",
    incident_id: operation === "triage_link" ? "inc-journey" : "inc-made",
    expected_version: 2,
    actor: "op-human",
    decided_at: "2026-09-30T00:00:00Z",
  };
}

async function openTriage(page) {
  await page.route("**/v1/alerts/*/triage/commands", async (route) => {
    const body = route.request().postDataJSON();
    posted.push(body);
    await route.fulfill({ json: ok(body.operation) });
  });
  await page.goto("/public/admin/triage.html");
  await page.locator("#api-key").fill("sre_testkey_0123456789abcdef");
  await page.locator("#connect-button").click();
}
test("link then declare sends only each operation fields", async ({ page }) => {
  posted.length = 0;
  await openTriage(page);
  await page.locator("#alert-id").fill("al-journey");
  await page.locator("#command-operation").selectOption("triage_link");
  await page.locator("#command-reason").fill("Spike.");
  await page.locator("#command-target").fill("inc-journey");
  await page.locator("#submit-button").click();
  await expect(page.locator("#result-status")).toHaveText("linked");
  await page.locator("#command-operation").selectOption("triage_declare");
  await page.locator("#command-severity").selectOption("sev2");
  await page.locator("#submit-button").click();
  await expect(page.locator("#result-status")).toHaveText("declared");
  expect(posted[0]).toEqual({
    operation: "triage_link",
    expected_version: 1,
    reason: "Spike.",
    target_incident_id: "inc-journey",
  });
  expect(posted[1]).toEqual({
    operation: "triage_declare",
    expected_version: 2,
    reason: "Spike.",
    severity: "sev2",
  });
  await expect(page.locator("#expected-version")).toHaveValue("2");
});
