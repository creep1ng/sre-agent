import { expect, test } from "@playwright/test";
import { connectConsole, logoutConsole } from "./support/console-session.mjs";

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
  await connectConsole(page);
}

// The console holds one session: changing identity is a logout and a new key, entered once.
async function reconnectAs(page, key) {
  await logoutConsole(page);
  await connectConsole(page, key);
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
  for (const absent of ["cancel_run", "escalate", "propose_disposition", "close_incident", "verification_passed", "verification_failed"]) {
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
  await reconnectAs(page, "sre_demo_token_second");
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
  await logoutConsole(page);
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

test("keeps a dispatched command locked after logging out and reconnecting", async ({ page }) => {
  await openReview(page);
  let releaseCommand = () => {};
  const commandGate = new Promise((resolve) => { releaseCommand = resolve; });
  const posted = await mockCommands(page, async () => {
    await commandGate;
    return { status: 202, json: acceptedPayload() };
  });
  await decide(page, "approve_mitigation");
  await expect.poll(() => posted.length).toBe(1);

  await reconnectAs(page, "sre_demo_token_second");
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

test("releases a command lock left by a logout after an error and reloads with the new credential", async ({ page }) => {
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

  await reconnectAs(page, "sre_demo_token_second");
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

function runStatePayload(currentState, over = {}) {
  return {
    run_id: RUN,
    incident_id: INCIDENT,
    workflow_version: "1.0.0",
    status: "awaiting_human",
    current_state: currentState,
    pending_command: null,
    cursor: "seq:7",
    terminated_reason: null,
    updated_at: "2026-08-24T14:20:00Z",
    ...over,
  };
}

// Like openReview, but the detail responses read a live getter: refreshes after a
// mocked command see the advanced version and state, like a real backend.
async function openMutableReview(page, detailGetter) {
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
    await route.fulfill({ json: detailGetter() });
  });
  await page.goto(`/public/incident-ui/review.html?incident_id=${INCIDENT}&run_id=${RUN}`);
  await connectConsole(page);
}

test("gates verification and closure actions to their contract states", async ({ page }) => {
  const cases = [
    ["verifying", ["verification_passed", "verification_failed"], ["close_incident"]],
    ["resolved", [], ["verification_passed", "verification_failed", "close_incident"]],
    ["postmortem", ["close_incident"], ["verification_passed", "verification_failed"]],
    ["investigating", [], ["verification_passed", "verification_failed", "close_incident"]],
    ["closed", [], ["verification_passed", "verification_failed", "close_incident"]],
  ];
  for (const [currentState, present, absent] of cases) {
    await page.unroute("**/api/v1/whoami");
    await page.unroute("**/api/v1/incidents/**");
    await openReview(page, detailPayload(currentState));
    for (const command of present) {
      await expect(page.locator(`#actions-list button[data-command="${command}"]`)).toHaveCount(1);
    }
    for (const command of absent) {
      await expect(page.locator(`#actions-list button[data-command="${command}"]`)).toHaveCount(0);
    }
  }
});

// Mocked end to end: the fixture backend advances the run through the contract
// transitions (resolved to postmortem comes from the agent objective). It proves
// the UI sequencing and draft durability, never a live transport.
test("walks the fixture journey mitigating to closed with an explicit closure approval", async ({ page }) => {
  let detail = detailPayload("mitigating");
  const posted = await (async () => {
    await openMutableReview(page, () => detail);
    return mockCommands(page, async (count) => {
      const nextState = ["verifying", "resolved", "closed"][count - 1];
      detail = detailPayload(nextState);
      detail.version += count;
      return { status: 202, json: runStatePayload(nextState) };
    });
  })();

  // mitigating → verifying happens through the published approval command.
  await decide(page, "approve_mitigation", "Flag rollback done, watching error rate.");
  await expect(page.locator("#receipt-line")).toContainText("verifying");
  await page.locator("#refresh-button").click();
  await expect(page.locator('#actions-list button[data-command="verification_passed"]')).toHaveCount(1);
  await expect(page.locator('#actions-list button[data-command="close_incident"]')).toHaveCount(0);

  // Verificación estable reaches resolved; the closure stays out of reach here.
  await page.locator('#actions-list button[data-command="verification_passed"]').click();
  await page.locator("#decision-comment").fill("Error rate flat for 20 minutes.");
  await expect(page.locator("#decision-approval-row")).toBeHidden();
  await page.locator("#decision-submit").click();
  await expect(page.locator("#receipt-line")).toContainText("resolved");

  await page.locator("#refresh-button").click();
  await expect(page.locator("#actions-empty")).toBeVisible();
  expect(posted).toHaveLength(2);

  // resolved → postmortem is an agent objective; the backend reports it on refresh.
  detail = detailPayload("postmortem");
  detail.version += 3;
  await page.locator("#refresh-button").click();
  await expect(page.locator('#actions-list button[data-command="close_incident"]')).toHaveCount(1);

  // The closure needs an explicit approval mark on this panel opening.
  await page.locator('#actions-list button[data-command="close_incident"]').click();
  await expect(page.locator("#decision-approval-row")).toBeVisible();
  await expect(page.locator("#decision-submit")).toBeDisabled();
  await page.locator("#decision-submit").click({ timeout: 300 }).catch(() => {});
  expect(posted).toHaveLength(2);
  await page.locator("#decision-comment").fill("Postmortem reviewed, closing incident.");
  await page.locator("#decision-approval").check();
  await page.locator("#decision-submit").click();

  await expect(page.locator("#receipt-line")).toContainText("close_incident");
  expect(posted).toHaveLength(3);
  expect(posted[2].body).toMatchObject({
    command: "close_incident",
    actor: "human",
    authorization: { action: "run.approve" },
    expected_incident_version: detail.version,
  });
  expect(posted[1].body).toMatchObject({
    command: "verification_passed",
    authorization: { action: "run.command" },
    expected_incident_version: 5,
  });
  for (const entry of posted) {
    expect(entry.body.actor_reference).toEqual({ reference_version: "1.0.0", principal_id: "demo-human" });
  }
  const seen = (await page.locator("#review").textContent()) ?? "";
  expect(seen).not.toMatch(/applied|ejecutada/i);

  // A reload re-derives the closed state and never mutates by itself.
  await page.reload();
  await connectConsole(page);
  await expect(page.locator("#actions-empty")).toBeVisible();
  expect(posted).toHaveLength(3);
});

test("a stale-version 409 on closure keeps the reason and never resends it", async ({ page }) => {
  let detail = detailPayload("postmortem");
  await openMutableReview(page, () => detail);
  const posted = await mockCommands(page, async (count) => {
    if (count > 1) return { status: 202, json: runStatePayload("closed") };
    detail.version += 1; // the backend and other actors advanced the incident
    return { status: 409, json: { error: { code: "incident_version_conflict", message: "stale version" } } };
  });
  await page.locator('#actions-list button[data-command="close_incident"]').click();
  await page.locator("#decision-comment").fill("Reviewed the postmortem draft, stable enough.");
  await page.locator("#decision-approval").check();
  await page.locator("#decision-submit").click();

  await expect(page.locator("#error-409")).toBeVisible();
  expect(posted).toHaveLength(1);
  await page.locator("#refresh-button").click();
  await expect(page.locator('#actions-list button[data-command="close_incident"]')).toHaveCount(1);
  expect(posted).toHaveLength(1); // recovery is manual: no automatic resend

  await page.locator('#actions-list button[data-command="close_incident"]').click();
  await expect(page.locator("#decision-comment")).toHaveValue("Reviewed the postmortem draft, stable enough.");
  await expect(page.locator("#decision-submit")).toBeDisabled(); // the approval starts unmarked
  await page.locator("#decision-approval").check();
  await page.locator("#decision-submit").click();
  await expect(page.locator("#receipt-line")).toContainText("close_incident");
  expect(posted).toHaveLength(2);
  expect(posted[1].body.expected_incident_version).toBe(detail.version);
});

test("a 403 rejection renders no success state on closure", async ({ page }) => {
  await openReview(page, detailPayload("postmortem"));
  const posted = await mockCommands(page, async () => ({
    status: 403,
    json: { error: { code: "not_authorized", message: "no run.approve grant" } },
  }));
  await page.locator('#actions-list button[data-command="close_incident"]').click();
  await page.locator("#decision-approval").check();
  await page.locator("#decision-submit").click();

  await expect(page.locator("#error-403")).toBeVisible();
  await expect(page.locator("#receipt-section")).toBeHidden();
  await expect(page.locator("#session-chip")).toHaveAttribute("data-phase", "active");
  expect(posted).toHaveLength(1);
});

test("offers no closure or verification from mitigating and keeps authority fixed", async ({ page }) => {
  await openReview(page);

  await expect(page.locator('input[name="actor"], input[name="principal"]')).toHaveCount(0);
  const labels = await page.locator("button").allTextContents();
  for (const label of labels) {
    expect(label).not.toMatch(/close|cierre|postmortem|verific/i);
  }
});
