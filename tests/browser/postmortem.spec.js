import { expect, test } from "@playwright/test";

const INCIDENT = "inc-demo";

function detailPayload() {
  return {
    incident_id: INCIDENT,
    workflow_version: "1.0.0",
    state: "investigating",
    severity: "sev2",
    impact: "Checkout failing at payment.",
    alert: {
      alert_id: "alt-payment-error-rate",
      service: "paymentservice",
      severity: "sev2",
      status: "triaged",
      observed_at: "2026-08-24T14:05:00Z",
      summary: "Elevated error rate on paymentservice.",
      source: "grafana-alerting",
    },
    approvals: [],
    version: 4,
    updated_at: "2026-08-24T14:20:00Z",
    runs: [
      { run_id: "run_demo0001", version: 4, status: "running", current_state: "investigating", updated_at: "2026-08-24T14:20:00Z" },
    ],
  };
}

async function openPostmortem(page, status = 200) {
  await page.route("**/api/v1/incidents/**", async (route) => {
    if (status === 200) return route.fulfill({ json: detailPayload() });
    return route.fulfill({ status, json: { error: { code: "not_authorized" } } });
  });
  await page.goto(`/public/incident-ui/postmortem.html?incident_id=${INCIDENT}`);
  await page.locator("#credential-input").fill("sre_demo_token_demo_0001");
  await page.locator("#credential-form button[type=submit]").click();
}

test("renders the minimum sections with explicit unknowns", async ({ page }) => {
  await openPostmortem(page);

  await expect(page.locator("#fact-incident")).toHaveText(INCIDENT);
  await expect(page.locator("#fact-state")).toHaveText("investigating");
  await expect(page.locator("#fact-artifact")).toContainText("pm_demo0001");
  await expect(page.locator("#fact-artifact")).toContainText("draft");
  await expect(page.locator("#fixture-banner")).toContainText("#335");
  for (const section of ["Resumen", "Impacto conocido", "Hipotesis o causa", "Certeza", "Estrategia", "Verificacion", "Pendientes"]) {
    await expect(page.locator("#artifact-sections")).toContainText(section);
  }
  await expect(page.locator("#artifact-sections")).toContainText("Desconocido");
  await expect(page.locator("#artifact-sections")).toContainText("Pendiente");
});

test("reloads the same fixture and never closes", async ({ page }) => {
  await openPostmortem(page);
  await expect(page.locator("#artifact-sections")).toContainText("Resumen");

  await page.reload();
  await expect(page.locator("#credential-section")).toBeVisible();
  await expect(page.locator("#close-incident")).toHaveCount(0);
  const labels = await page.locator("button").allTextContents();
  for (const label of labels) {
    expect(label).not.toMatch(/close|cierre/i);
  }
});

test("shows the forbidden state without content", async ({ page }) => {
  await openPostmortem(page, 403);

  await expect(page.locator("#error-403")).toBeVisible();
  await expect(page.locator("#context-section")).toBeHidden();
  await expect(page.locator("#artifact-section")).toBeHidden();
});
