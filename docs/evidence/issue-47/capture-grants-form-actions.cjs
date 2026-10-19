/* Capture evidence for the #47 finding-1 Grants-UI fix (action mirror + resource).
 *
 * Runs inside the e2e service of the composed stack, as admin-human, AFTER the
 * documented provisioning step (runbook "Optional: provision a triage-capable
 * operator") created the active incident_workflow/incident-response catalog row.
 * It records the real create-form options, expands the two native selects so a
 * screenshot can show every option, and performs one real governed create of the
 * previously unofferable action incident.declare.
 *
 * Usage (from the repository root, with .env as compose.yaml documents):
 *   docker compose -f compose.yaml -f compose.e2e.yaml -f compose.capture.yaml \
 *     --project-name <your-project> --profile e2e run --rm e2e \
 *     sh -c 'NODE_PATH=/e2e/node_modules node /capture/capture-grants-form-actions.cjs'
 * (NODE_PATH points at the e2e image's node_modules; the script itself lives on
 * the bind-mounted evidence folder.)
 */
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");

const BASE = process.env.PLAYWRIGHT_BASE_URL || "http://web";
const KEY = process.env.ADMIN_HUMAN_API_KEY || "";
const OUT = process.env.CAPTURE_OUT_DIR || "/capture";
const EXPECTED = [
  "run.start",
  "run.read",
  "run.command",
  "run.approve",
  "run.read_context",
  "alert.read",
  "alert.triage",
  "alert.dismiss",
  "alert.associate",
  "incident.declare",
];

const proof = {
  page: `${BASE}/public/admin/grants.html`,
  capturedAt: new Date().toISOString(),
  consoleErrors: [],
};

function save() {
  fs.writeFileSync(
    path.join(OUT, "grants-action-mirror-proof.json"),
    JSON.stringify(proof, null, 2) + "\n",
  );
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.on("pageerror", (error) => proof.consoleErrors.push(String(error.message || error)));
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().includes("Content Security Policy")) {
      proof.consoleErrors.push(message.text());
    }
  });
  try {
    await page.goto(proof.page);
    await page.waitForSelector("#grants-page[data-state='idle']");
    await page.fill("#api-key", KEY);
    await page.click("#connect-button");
    await page.waitForFunction(() => !document.querySelector("#create-grant-button").disabled, null, {
      timeout: 20000,
    });

    await page.click("#create-grant-button");
    await page.waitForSelector("#create-dialog[open]");

    const values = await page
      .locator("#create-resource option")
      .evaluateAll((options) => options.map((option) => option.value).filter(Boolean));
    proof.createResourceOptions = values;
    const workflows = values.filter((value) => value.startsWith("incident_workflow/"));
    if (workflows.length !== 1) {
      throw new Error(`expected exactly one incident_workflow resource option, got ${JSON.stringify(workflows)}`);
    }
    proof.incidentWorkflowResource = workflows[0];

    // Screenshot 1: the real resource select expanded over its options.
    await page.locator("#create-resource").evaluate((el) => {
      el.size = el.options.length;
    });
    await page.locator("#create-resource").scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(OUT, "grants-create-resource-options.png"), fullPage: true });
    await page.locator("#create-resource").evaluate((el) => {
      el.removeAttribute("size");
    });

    await page.selectOption("#create-resource", workflows[0]);
    const actions = await page
      .locator("#create-action option")
      .evaluateAll((options) => options.map((option) => option.value).filter(Boolean));
    proof.actions = actions;
    proof.expectedActions = EXPECTED;
    proof.actionsMatch = JSON.stringify(actions) === JSON.stringify(EXPECTED);
    if (!proof.actionsMatch) {
      throw new Error(`action mirror mismatch: ${JSON.stringify(actions)}`);
    }

    // Screenshot 2: the real action select expanded over its ten admitted options.
    await page.locator("#create-action").evaluate((el) => {
      el.size = el.options.length;
    });
    await page.locator("#create-action").scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(OUT, "grants-incident-workflow-actions.png"), fullPage: true });
    await page.locator("#create-action").evaluate((el) => {
      el.removeAttribute("size");
    });

    // Real governed create: a previously unofferable action now grants via the form.
    await page.fill("#create-grant-id", "grant-incident-harness-incident-declare-incident-response");
    await page.selectOption("#create-principal", "incident-harness");
    await page.selectOption("#create-action", "incident.declare");
    await page.click("#create-submit");
    await page.waitForSelector("#create-dialog[open]", { state: "hidden", timeout: 20000 });
    await page.waitForFunction(() => document.querySelector("#live-region").textContent.includes("ready (201"), null, {
      timeout: 20000,
    });
    const row = page.locator("[data-grant-row='grant-incident-harness-incident-declare-incident-response']");
    await row.waitFor({ timeout: 20000 });
    proof.create = {
      grantId: "grant-incident-harness-incident-declare-incident-response",
      principal: "incident-harness",
      action: "incident.declare",
      resource: workflows[0],
      announce: await page.locator("#live-region").textContent(),
      rowText: await row.textContent(),
    };
    await page.screenshot({ path: path.join(OUT, "grants-incident-declare-created.png"), fullPage: true });

    save();
    console.log(JSON.stringify({ ok: true, proof }, null, 2));
    await browser.close();
  } catch (error) {
    proof.error = String(error);
    save();
    console.error(`capture failed: ${error}`);
    await browser.close();
    process.exit(1);
  }
})();
