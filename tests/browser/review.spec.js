import { expect, test } from "@playwright/test";

const INCIDENT = "inc-demo";
const RUN = "run_demo0001";

function detailPayload(currentState = "mitigating", workflowVersion = "1.0.0") {
  return {
    incident_id: INCIDENT,
    workflow_version: workflowVersion,
    state: currentState,
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
      {
        run_id: RUN,
        version: 4,
        status: "awaiting_human",
        current_state: currentState,
        updated_at: "2026-08-24T14:20:00Z",
      },
    ],
  };
}

async function openReview(page, detail) {
  await page.route("**/api/v1/incidents/**", async (route) => {
    await route.fulfill({ json: detail ?? detailPayload() });
  });
  await page.goto(`/public/incident-ui/review.html?incident_id=${INCIDENT}&run_id=${RUN}`);
  await page.locator("#credential-input").fill("sre_demo_token_demo_0001");
  await page.locator("#credential-form button[type=submit]").click();
}

test("offers only the mitigating review actions for workflow 1.0.0", async ({ page }) => {
  await openReview(page);

  await expect(page.locator("#actions-list li")).toHaveCount(3);
  await expect(page.locator("#actions-list")).toContainText("Aprobar mitigación");
  await expect(page.locator("#actions-list")).toContainText("apply_mitigation");
  await expect(page.locator("#actions-list")).toContainText("request_changes");
  for (const absent of ["cancel_run", "escalate", "propose_disposition", "close_incident"]) {
    await expect(page.locator("#actions-list")).not.toContainText(absent);
  }
  await expect(page.locator("#fact-incident")).toHaveText(INCIDENT);
  await expect(page.locator("#fact-run")).toHaveText(RUN);
  await expect(page.locator("#fact-workflow")).toHaveText("1.0.0");
});

test("hides review actions for other states and versions", async ({ page }) => {
  await openReview(page, detailPayload("investigating"));
  await expect(page.locator("#actions-empty")).toBeVisible();
  await expect(page.locator("#actions-list li")).toHaveCount(0);

  await page.unroute("**/api/v1/incidents/**");
  await openReview(page, detailPayload("mitigating", "9.9.9"));
  await expect(page.locator("#actions-empty")).toBeVisible();
  await expect(page.locator("#actions-list li")).toHaveCount(0);
});

test("submits nothing and exposes no close controls", async ({ page }) => {
  let posted = 0;
  await page.route("**/api/v1/incidents/**/commands", async (route) => {
    posted += 1;
    await route.fulfill({ status: 202, json: {} });
  });
  await openReview(page);
  await expect(page.locator("#actions-list li")).toHaveCount(3);
  expect(posted).toBe(0);

  await expect(page.locator('input[name="actor"], input[name="principal"]')).toHaveCount(0);
  const labels = await page.locator("button").allTextContents();
  for (const label of labels) {
    expect(label).not.toMatch(/close|cierre|postmortem/i);
  }
});
