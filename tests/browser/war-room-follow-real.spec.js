import { expect, request, test } from "@playwright/test";
import { connectConsole } from "./support/console-session.mjs";

// The war room follows the run, against the REAL stack (web proxy, FastAPI, PostgreSQL); nothing
// is mocked. Seeds: scripts/seed_verification_close_demo.py. LIVE_STAMP is seeded with
// SEED_UNTIL=start_investigation (run investigating) and finished by a second seed run while this
// spec watches; SEED_STAMP is seeded complete (mitigating). Ways this can fail, written first:
// 1. while the agent investigates the operator must press Actualizar to see the hypothesis;
// 2. after the approval the war room points nowhere: verifying, resolved and postmortem need the
//    way to Decisiones and to the postmortem, with the right incident and run.
const STAMP = process.env.SEED_STAMP ?? "";
const LIVE_STAMP = process.env.LIVE_STAMP ?? "";
const DEMO_KEY = process.env.DEMO_HUMAN_API_KEY ?? "";
const BASE = process.env.PLAYWRIGHT_BASE_URL ?? "http://web";
const REAL = process.env.SRE_REAL_BACKEND === "1" && Boolean(DEMO_KEY && STAMP && LIVE_STAMP);
const STATEMENT = "The paymentFailure feature flag makes PaymentService/Charge fail.";

test.skip(!REAL, "requires SRE_REAL_BACKEND=1, the demo key, SEED_STAMP and LIVE_STAMP seeds");

test("while the agent investigates the view follows it without Actualizar", async ({ page }) => {
  test.setTimeout(150_000);
  await page.goto(`/public/incident-ui/war-room.html?incident_id=inc-vc-${LIVE_STAMP}`);
  await connectConsole(page, DEMO_KEY);

  await expect(page.locator("#reasoning-live")).toContainText("la vista se actualiza sola");
  await expect(page.locator("#reasoning-empty")).toBeVisible();
  // The second seed run records the hypothesis and the mitigation meanwhile.
  await expect(page.locator("#hypothesis-block")).toContainText(STATEMENT, { timeout: 120_000 });
  await expect(page.locator("#run-decide")).toBeVisible();
  await expect(page.locator("#reasoning-live")).not.toContainText("se actualiza sola");
});

test("after the approval the war room points to each next step", async ({ page }) => {
  const incident = `inc-vc-${STAMP}`;
  const run = `run_vc${STAMP.replaceAll("-", "")}`;
  const api = await request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${DEMO_KEY}` } });
  const url = (path) => `${BASE}/api/v1/incidents/${incident}${path}`;
  const command = async (name, key) => {
    const { version } = await (await api.get(url(""))).json();
    const response = await api.post(url(`/runs/${run}/commands`), {
      headers: { "idempotency-key": `${key}-${STAMP}-0001` },
      data: {
        command: name,
        expected_incident_version: version,
        actor: "human",
        actor_reference: { reference_version: "1.0.0", principal_id: "demo-human" },
      },
    });
    expect(response.status()).toBe(202);
  };
  const open = async () => {
    await page.goto(`/public/incident-ui/war-room.html?incident_id=${incident}`);
    if (await page.locator("#session-chip").getAttribute("data-phase") !== "active") {
      await connectConsole(page, DEMO_KEY);
    }
    await expect(page.locator("#war-room")).toHaveAttribute("data-state", "ready");
  };
  const next = page.locator("#run-decide");

  await command("approve_mitigation", "follow-approve");
  await open();
  await expect(page.locator("#run-pending")).toContainText("La mitigación quedó aprobada");
  await expect(next).toHaveText("Ir a Decisiones");
  await expect(next).toHaveAttribute("href", new RegExp(`view=decisions&incident_id=${incident}&run_id=${run}`));

  await command("verification_passed", "follow-verified");
  await open();
  await expect(page.locator("#run-pending")).toContainText("El servicio quedó verificado");
  await expect(next).toHaveText("Ir al postmortem");
  await expect(next).toHaveAttribute("href", new RegExp(`view=postmortem&incident_id=${incident}`));

  const started = await api.post(url("/runs"), {
    headers: { "idempotency-key": `follow-postmortem-${STAMP}-0001` },
    data: { workflow_version: "1.0.0", objective: "postmortem" },
  });
  expect(started.status()).toBe(201);
  await open();
  await expect(page.locator("#run-pending")).toContainText("El postmortem está abierto");
  await expect(next).toHaveText("Ir al postmortem");
  await next.click();
  await expect(page).toHaveURL(new RegExp(`view=postmortem&incident_id=${incident}`));
});
