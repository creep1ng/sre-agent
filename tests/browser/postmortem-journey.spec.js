import { writeFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { connectConsole } from "./support/console-session.mjs";

// Real-stack journey (#43): a resolved incident to an approved postmortem in the console, then the
// close through the Decisiones link. Needs POSTMORTEM_INCIDENT (a resolved incident, e.g. from
// docs/evidence/43/to_resolved.py) and a demo-human key with run.read_context.
const INCIDENT = process.env.POSTMORTEM_INCIDENT;
const OUT = process.env.PLAYWRIGHT_OUTPUT_DIR || "test-results";
test.skip(!INCIDENT, "Set POSTMORTEM_INCIDENT to a resolved incident of the stack under test.");

test("de resuelto a postmortem aprobado, y el cierre lo comprueba el backend", async ({ page }) => {
  const auth = { Authorization: `Bearer ${process.env.DEMO_HUMAN_API_KEY}` };
  const read = async (path) => (await page.request.get(`/api/v1/incidents/${INCIDENT}${path}`, { headers: auth })).json();
  const shot = (name) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
  await page.setViewportSize({ width: 1280, height: 3600 });
  await page.goto(`/?view=postmortem&incident_id=${INCIDENT}`);
  await connectConsole(page, process.env.DEMO_HUMAN_API_KEY);

  await page.locator("#start-postmortem").click();
  await expect(page.locator("#fact-state")).toHaveText("En postmortem");
  await page.locator("#pm-pending").fill("Add a config lint for client timeouts.");
  await page.locator("#pm-unknowns").fill("Exact revenue impact.");
  await page.locator("#save-postmortem").click();
  await expect(page.locator("#fact-version")).toHaveText("1");
  await page.locator("#review-comment").fill("Matches the timeline.");
  await page.locator("#approve-postmortem").click();
  await expect(page.locator("#fact-review")).toContainText("Aprobada");
  await shot("journey-1-approved-v1");

  // An edit voids the approval: version 2 is pending until a human approves it.
  await page.locator("#pm-summary").fill("Checkout payments failed at the payment step after a config push.");
  await page.locator("#save-postmortem").click();
  await expect(page.locator("#fact-version")).toHaveText("2");
  await expect(page.locator("#fact-review")).toContainText("Pendiente de revisión");
  await expect(page.locator("#close-hint")).toBeHidden();
  await shot("journey-2-edit-voids-review");
  await page.locator("#approve-postmortem").click();
  await expect(page.locator("#fact-review")).toContainText("Aprobada");
  await expect(page.locator("#close-hint")).toBeVisible();
  await shot("journey-3-approved-v2");

  const detail = await read("");
  const run = detail.runs.find((entry) => entry.current_state === "postmortem").run_id;
  await expect(page.locator("#decisions-link")).toHaveAttribute("href", `/?view=decisions&incident_id=${INCIDENT}&run_id=${run}`);
  const approved = await read("/postmortem");
  expect(approved).toMatchObject({ version: 2, review: { status: "approved", reviewed_version: 2, reviewer_id: "demo-human" } });

  // The close happens in Decisiones, on the postmortem run the link carries; the backend checks
  // that the approved version is the current one.
  await page.locator("#decisions-link").click();
  await expect(page.locator("#fact-run")).toHaveText(run);
  await page.locator('#actions-list button[data-command="close_incident"]').click();
  await page.locator("#decision-approval").check();
  await page.locator("#decision-submit").click();
  await expect(page.locator("#receipt-line")).toContainText("close_incident");
  await shot("journey-4-closed-in-decisiones");
  await page.locator('[data-console-nav="postmortem"]').click();
  await expect(page.locator("#fact-state")).toHaveText("Cerrado");
  await expect(page.locator("#editor-section")).toBeHidden();
  await expect(page.locator("#review-section")).toBeHidden();
  await shot("journey-5-closed-read-only");
  const closed = await read("");
  writeFileSync(`${OUT}/journey.json`, JSON.stringify({ incident: INCIDENT, run, postmortem_id: approved.postmortem_id, version: approved.version, review: approved.review, state: closed.state }, null, 2));
});
