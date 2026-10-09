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
  await page.route("**/api/v1/whoami", async (route) => {
    const token = route.request().headers().authorization;
    await route.fulfill({ json: { principal_id: token?.endsWith("second") ? "other-human" : "demo-human" } });
  });
  await page.route("**/api/v1/incidents/**", async (route) => {
    const request = route.request();
    if (request.method() === "POST" && request.url().includes("/commands")) {
      await route.fallback();
      return;
    }
    await route.fulfill({ json: detail ?? detailPayload() });
  });
  await page.goto(`/public/incident-ui/review.html?incident_id=${INCIDENT}&run_id=${RUN}`);
  await page.locator("#credential-input").fill("sre_demo_token_demo_0001");
  await page.locator("#credential-form button[type=submit]").click();
}

test("offers only the mitigating review actions for workflow 1.0.0", async ({ page }) => {
  await openReview(page);

  await expect(page.locator("#actions-list button")).toHaveCount(3);
  await expect(page.locator("#actions-list")).toContainText("Aprobar mitigación");
  await expect(page.locator("#actions-list")).toContainText("Rechazar mitigación");
  await expect(page.locator("#actions-list")).toContainText("Solicitar corrección");
  for (const command of ["approve_mitigation", "reject_mitigation", "request_changes"]) {
    await expect(page.locator(`#actions-list button[data-command="${command}"]`)).toHaveCount(1);
  }
  for (const absent of ["cancel_run", "escalate", "propose_disposition", "close_incident"]) {
    await expect(page.locator("#actions-list")).not.toContainText(absent);
  }
  await expect(page.locator("#fact-incident")).toHaveText(INCIDENT);
  await expect(page.locator("#fact-run")).toHaveText(RUN);
  await expect(page.locator("#fact-incident-version")).toHaveText("4");
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

function acceptedPayload() {
  return {
    run_id: RUN,
    incident_id: INCIDENT,
    workflow_version: "1.0.0",
    status: "awaiting_human",
    current_state: "mitigating",
    pending_command: "approve_mitigation",
    cursor: "seq:7",
    terminated_reason: null,
    updated_at: "2026-08-24T14:20:00Z",
  };
}

async function mockCommands(page, handler) {
  const posted = [];
  await page.route("**/api/v1/incidents/**/commands", async (route) => {
    const request = route.request();
    posted.push({ headers: await request.allHeaders(), body: request.postDataJSON() });
    const { status, json } = await handler(posted.length);
    await route.fulfill({ status, json });
  });
  return posted;
}

async function decide(page, command, comment = "") {
  await page.locator(`#actions-list button[data-command="${command}"]`).click();
  if (comment) await page.locator("#decision-comment").fill(comment);
  await expect(page.locator("#decision-key")).not.toBeEmpty();
  await page.locator("#decision-submit").click();
}

test("records approval without claiming execution", async ({ page }) => {
  await openReview(page);
  const posted = await mockCommands(page, async () => ({ status: 202, json: acceptedPayload() }));
  await decide(page, "approve_mitigation", "Confirmed the flag rollback plan.");

  await expect(page.locator("#receipt-line")).toContainText("approve_mitigation");
  await expect(page.locator("#receipt-line")).toContainText("apply_mitigation");
  const body = (await page.locator("#review").textContent()) ?? "";
  expect(body).not.toMatch(/applied|ejecutada/i);
  expect(posted).toHaveLength(1);
  expect(posted[0].headers["idempotency-key"]).toMatch(/^[0-9a-f-]{10,}$/);
  expect(posted[0].body).toMatchObject({ command: "approve_mitigation", actor: "human" });
  expect(posted[0].body.expected_incident_version).toBe(4);
  expect(posted[0].body.actor_reference).toEqual({
    reference_version: "1.0.0",
    principal_id: "demo-human",
  });
});

test("rejects and requests changes with contractual bodies", async ({ page }) => {
  await openReview(page);
  const posted = await mockCommands(page, async () => ({ status: 202, json: acceptedPayload() }));
  await decide(page, "reject_mitigation");

  await expect.poll(() => posted.length).toBe(1);
  expect(posted[0].body).toMatchObject({
    command: "reject_mitigation",
    actor_reference: { reference_version: "1.0.0", principal_id: "demo-human" },
    authorization: { action: "run.approve" },
    expected_incident_version: 4,
  });

  await page.locator("#refresh-button").click();
  await expect(page.locator("#actions-list button")).toHaveCount(3);
  await decide(page, "request_changes");
  await expect.poll(() => posted.length).toBe(2);
  expect(posted[1].body).toMatchObject({
    command: "request_changes",
    authorization: { action: "run.command" },
    expected_incident_version: 4,
  });
});

test("uses the currently authenticated identity after changing credentials", async ({ page }) => {
  await openReview(page);
  const posted = await mockCommands(page, async () => ({ status: 202, json: acceptedPayload() }));
  await page.locator("#forget-credential").click();
  await page.locator("#credential-input").fill("sre_demo_token_second");
  await page.locator("#credential-form button[type=submit]").click();
  await expect(page.locator("#actions-list button")).toHaveCount(3);
  await decide(page, "approve_mitigation");

  await expect.poll(() => posted.length).toBe(1);
  expect(posted[0].body.actor_reference.principal_id).toBe("other-human");
});

test("does not submit an identity lookup made stale by clearing the credential", async ({ page }) => {
  await openReview(page);
  let release = () => {};
  const gate = new Promise((resolve) => { release = resolve; });
  await page.unroute("**/api/v1/whoami");
  await page.route("**/api/v1/whoami", async (route) => {
    await gate;
    await route.fulfill({ json: { principal_id: "demo-human" } });
  });
  const posted = await mockCommands(page, async () => ({ status: 202, json: acceptedPayload() }));
  await page.locator('#actions-list button[data-command="approve_mitigation"]').click();
  await page.locator("#decision-submit").click();
  await page.locator("#forget-credential").click();
  release();
  await page.waitForTimeout(50);
  expect(posted).toHaveLength(0);
  await expect(page.locator("#review")).toHaveAttribute("data-state", "auth");
});

test("keeps one submitted action stable while identity and command requests are pending", async ({ page }) => {
  await openReview(page);
  let releaseIdentity = () => {};
  const identityGate = new Promise((resolve) => { releaseIdentity = resolve; });
  let releaseCommand = () => {};
  const commandGate = new Promise((resolve) => { releaseCommand = resolve; });
  let lookups = 0;
  await page.unroute("**/api/v1/whoami");
  await page.route("**/api/v1/whoami", async (route) => {
    lookups += 1;
    await identityGate;
    await route.fulfill({ json: { principal_id: "demo-human" } });
  });
  const posted = await mockCommands(page, async () => {
    await commandGate;
    return { status: 202, json: acceptedPayload() };
  });
  await page.locator('#actions-list button[data-command="approve_mitigation"]').click();
  await page.locator("#decision-comment").fill("Original approval reason.");
  const submittedKey = await page.locator("#decision-key").textContent();
  await page.locator("#decision-submit").click();
  await expect.poll(() => lookups).toBe(1);

  await expect(page.locator('#actions-list button[data-command="reject_mitigation"]')).toBeDisabled();
  await expect(page.locator("#decision-comment")).toBeDisabled();
  await expect(page.locator("#decision-submit")).toBeDisabled();
  releaseIdentity();
  await expect.poll(() => posted.length).toBe(1);
  await expect(page.locator("#refresh-button")).toBeDisabled();
  await expect(page.locator("#decision-section")).toBeVisible();
  releaseCommand();
  await expect(page.locator("#receipt-line")).toContainText("approve_mitigation");
  await expect(page.locator("#refresh-button")).toBeEnabled();

  expect(lookups).toBe(1);
  expect(posted).toHaveLength(1);
  expect(posted[0].headers["idempotency-key"]).toBe(submittedKey);
  expect(posted[0].body).toMatchObject({
    command: "approve_mitigation",
    comment: "Original approval reason.",
  });
});

test("keeps a dispatched command locked after forgetting and reauthenticating", async ({ page }) => {
  await openReview(page);
  let releaseCommand = () => {};
  const commandGate = new Promise((resolve) => { releaseCommand = resolve; });
  const posted = await mockCommands(page, async () => {
    await commandGate;
    return { status: 202, json: acceptedPayload() };
  });
  await decide(page, "approve_mitigation");
  await expect.poll(() => posted.length).toBe(1);

  await page.locator("#forget-credential").click();
  await page.locator("#credential-input").fill("sre_demo_token_second");
  await page.locator("#credential-form button[type=submit]").click();
  await expect(page.locator("#review")).toHaveAttribute("data-state", "auth");
  await expect(page.locator("#command-status")).toContainText("no se puede cancelar");
  await expect(page.locator("#actions-section")).toBeHidden();
  expect(posted).toHaveLength(1);

  releaseCommand();
  await expect(page.locator("#actions-section")).toBeVisible();
  await expect(page.locator("#command-status")).toBeHidden();
  await expect(page.locator("#receipt-section")).toBeHidden();
  expect(posted).toHaveLength(1);
});

test("releases a forgotten command lock after an error and reloads with the new credential", async ({ page }) => {
  await openReview(page);
  let releaseCommand = () => {};
  const commandGate = new Promise((resolve) => { releaseCommand = resolve; });
  const posted = await mockCommands(page, async (count) => {
    if (count === 1) {
      await commandGate;
      return {
        status: 503,
        json: { error: { code: "service_unavailable", message: "unavailable" } },
      };
    }
    return { status: 202, json: acceptedPayload() };
  });
  await decide(page, "approve_mitigation");
  await expect.poll(() => posted.length).toBe(1);

  await page.locator("#forget-credential").click();
  await page.locator("#credential-input").fill("sre_demo_token_second");
  await page.locator("#credential-form button[type=submit]").click();
  await expect(page.locator("#review")).toHaveAttribute("data-state", "auth");
  await expect(page.locator("#command-status")).toContainText("no se puede cancelar");
  await expect(page.locator("#actions-section")).toBeHidden();
  releaseCommand();

  await expect(page.locator("#actions-section")).toBeVisible();
  await expect(page.locator("#command-status")).toBeHidden();
  await expect(page.locator("#error-503")).toBeHidden();
  await expect(page.locator("#receipt-section")).toBeHidden();
  await decide(page, "reject_mitigation");
  await expect.poll(() => posted.length).toBe(2);
  await expect(page.locator("#receipt-line")).toContainText("reject_mitigation");
  expect(posted[1].headers.authorization).toBe("Bearer sre_demo_token_second");
  expect(posted[1].headers["idempotency-key"]).not.toBe(posted[0].headers["idempotency-key"]);
  expect(posted[1].body.actor_reference.principal_id).toBe("other-human");
});

test("sends a single request while a submit is in flight", async ({ page }) => {
  await openReview(page);
  let release = () => {};
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const posted = await mockCommands(page, async () => {
    await gate;
    return { status: 202, json: acceptedPayload() };
  });
  await page.locator('#actions-list button[data-command="approve_mitigation"]').click();
  await page.locator("#decision-submit").click();
  await expect(page.locator("#decision-submit")).toBeDisabled();
  await expect.poll(() => posted.length).toBe(1);
  release();
  await expect(page.locator("#receipt-line")).toContainText("approve_mitigation");
  expect(posted).toHaveLength(1);
});

test("recovers from a 409 conflict keeping the written reason", async ({ page }) => {
  await openReview(page);
  await mockCommands(page, async () => ({
    status: 409,
    json: { error: { code: "command_not_permitted", message: "not permitted" } },
  }));
  await decide(page, "reject_mitigation", "Needs a second flag check.");

  await expect(page.locator("#error-409")).toBeVisible();
  await page.locator("#refresh-button").click();
  await expect(page.locator("#actions-list button")).toHaveCount(3);
  await expect(page.locator("#decision-comment")).toHaveValue("Needs a second flag check.");
});

test("restores the typed reason when reopening the same action after refresh", async ({ page }) => {
  await openReview(page);
  await mockCommands(page, async () => ({
    status: 409,
    json: { error: { code: "command_not_permitted", message: "not permitted" } },
  }));
  await decide(page, "reject_mitigation", "Needs a second flag check.");

  await expect(page.locator("#error-409")).toBeVisible();
  await page.locator("#refresh-button").click();
  await expect(page.locator("#actions-list button")).toHaveCount(3);
  await page.locator('#actions-list button[data-command="reject_mitigation"]').click();
  await expect(page.locator("#decision-comment")).toHaveValue("Needs a second flag check.");
});

test("keeps drafts isolated per action", async ({ page }) => {
  await openReview(page);
  await page.locator('#actions-list button[data-command="approve_mitigation"]').click();
  await page.locator("#decision-comment").fill("Approve reason.");
  await page.locator('#actions-list button[data-command="reject_mitigation"]').click();
  await expect(page.locator("#decision-comment")).toHaveValue("");
  await page.locator('#actions-list button[data-command="approve_mitigation"]').click();
  await expect(page.locator("#decision-comment")).toHaveValue("Approve reason.");
});

test("exposes no close controls and no editable authority", async ({ page }) => {
  await openReview(page);

  await expect(page.locator('input[name="actor"], input[name="principal"]')).toHaveCount(0);
  const labels = await page.locator("button").allTextContents();
  for (const label of labels) {
    expect(label).not.toMatch(/close|cierre|postmortem/i);
  }
});
