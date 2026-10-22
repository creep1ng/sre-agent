import { writeFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { connectConsole } from "./support/console-session.mjs";

// Issue #717 against the REAL stack (web proxy, FastAPI, PostgreSQL, the governed gateway with a
// paid OpenRouter model and Grafana MCP evidence); nothing is mocked. EXPECTED_OUTPUT_LANGUAGE is
// the stack's INVESTIGATOR_OUTPUT_LANGUAGE. Ways this can fail, written before the change:
// 1. the hypothesis, the mitigation steps or the postmortem draft come out in the other language,
//    or mixed, whatever the configuration says;
// 2. translating the prose also translates the protocol (action names, low|medium|high, ids), so
//    the gateway rejects the reply and no hypothesis or mitigation is recorded;
// 3. switching to `en` needs more than the variable (a rebuild, a code edit, another prompt).
const DEMO_KEY = process.env.DEMO_HUMAN_API_KEY ?? "";
const EXPECTED = process.env.EXPECTED_OUTPUT_LANGUAGE ?? "";
const OUT = process.env.PLAYWRIGHT_OUTPUT_DIR || "test-results";
const REAL = process.env.SRE_REAL_BACKEND === "1" && Boolean(DEMO_KEY) && ["es", "en"].includes(EXPECTED);
const STAMP = `${EXPECTED}${Date.now().toString(36)}`;

test.skip(!REAL, "requires SRE_REAL_BACKEND=1, the demo key and EXPECTED_OUTPUT_LANGUAGE=es|en");

// Function words only: they say which language a sentence is written in, not what it is about.
const WORDS = {
  es: ["el", "la", "los", "las", "de", "del", "que", "en", "por", "para", "con", "una", "un", "se", "es", "al", "y"],
  en: ["the", "of", "and", "to", "is", "in", "for", "with", "a", "an", "on", "by", "that", "are", "from"],
};

function language(text) {
  const tokens = String(text).toLowerCase().match(/\p{L}+/gu) ?? [];
  const score = (lang) => tokens.filter((token) => WORDS[lang].includes(token)).length;
  const es = score("es");
  const en = score("en");
  return { detected: es === en ? "unknown" : es > en ? "es" : "en", es, en };
}

test("the investigation and its postmortem draft follow the workspace language", async ({ page }) => {
  test.setTimeout(900_000);
  const auth = { authorization: `Bearer ${DEMO_KEY}` };
  const api = (path) => `/api/v1${path}`;
  const shot = (name) => page.screenshot({ path: `${OUT}/${EXPECTED}-${name}.png`, fullPage: true });
  const alert = `alt-717-${STAMP}`;
  const triage = (data, step) =>
    page.request.post(api(`/alerts/${alert}/triage/commands`), {
      data,
      headers: { ...auth, "idempotency-key": `idem-717-${STAMP}-${step}` },
    });

  expect((await (await page.request.get("/workspace.json")).json()).output_language).toBe(EXPECTED);
  expect((await triage({ operation: "open_triage", expected_version: 1 }, "open")).status()).toBe(200);
  const declared = await triage(
    {
      operation: "triage_declare",
      expected_version: 1,
      severity: "sev1",
      reason: "Checkout orders fail at Place Order.",
      impact: "Customers cannot complete purchases in the store.",
      alert_context: {
        service: "checkout",
        summary: "checkout payment calls failing: orders error at the payment charge step",
        observed_at: new Date().toISOString(),
        source: "grafana-alerting",
        severity: "sev1",
      },
    },
    "declare",
  );
  expect(declared.status()).toBe(201);
  const incident = (await declared.json()).incident_id;

  // The investigation starts from the war room and runs against the real model.
  await page.setViewportSize({ width: 1280, height: 2400 });
  await page.goto(`/public/incident-ui/war-room.html?incident_id=${incident}`);
  await connectConsole(page, DEMO_KEY);
  const runs = async () => ((await (await page.request.get(api(`/incidents/${incident}`), { headers: auth })).json()).runs ?? []).map((item) => item.run_id);
  const before = await runs();
  await page.locator("#run-start").click();
  await expect.poll(async () => (await runs()).length, { timeout: 420_000, intervals: [5_000] }).toBe(before.length + 1);
  const run = (await runs()).find((id) => !before.includes(id));
  const context = async () => (await (await page.request.get(api(`/incidents/${incident}/runs/${run}/context`), { headers: auth })).json()).reasoning ?? {};
  // The run ends with the mitigation recorded, or with a receipt that says why it did not.
  const ended = async () => {
    const events = (await (await page.request.get(api(`/incidents/${incident}/runs/${run}/events`), { headers: auth })).json()).events ?? [];
    return events.some((event) => event.kind === "dispatch_receipt" && /ended/.test(event.summary ?? ""));
  };
  await expect.poll(async () => Boolean((await context()).mitigation_strategy) || (await ended()), { timeout: 420_000, intervals: [5_000] }).toBe(true);
  expect((await context()).mitigation_strategy, "the investigation proposed a mitigation").toBeTruthy();
  const { hypotheses, mitigation_strategy: mitigation } = await context();
  await page.reload();
  await connectConsole(page, DEMO_KEY);
  await expect(page.locator("#hypothesis-block")).toContainText(hypotheses.at(-1).statement);
  await shot("1-war-room-hypothesis");

  // Decisiones shows the mitigation steps; the human approves it and the verification passes.
  await page.goto(`/public/incident-ui/review.html?incident_id=${incident}&run_id=${run}`);
  await connectConsole(page, DEMO_KEY);
  await expect(page.locator("#mitigation-section")).toContainText(mitigation.steps[0]);
  await shot("2-decisiones-mitigation");
  await page.locator('#actions-list button[data-command="approve_mitigation"]').click();
  await page.locator("#decision-submit").click();
  await expect(page.locator("#receipt-line")).toContainText("verifying");
  await page.locator("#refresh-button").click();
  await page.locator('#actions-list button[data-command="verification_passed"]').click();
  await page.locator("#decision-submit").click();
  await expect(page.locator("#receipt-line")).toContainText("resolved");

  // The agent drafts the postmortem with the same language.
  await page.goto(`/?view=postmortem&incident_id=${incident}`);
  await connectConsole(page, DEMO_KEY);
  await page.locator("#start-postmortem").click();
  await expect(page.locator("#fact-state")).toHaveText("En postmortem");
  await page.locator("#agent-draft").click();
  await expect(page.locator("#agent-status")).toContainText("Borrador del agente", { timeout: 240_000 });
  await shot("3-postmortem-draft");
  const draft = {
    summary: await page.locator("#pm-summary").inputValue(),
    cause: await page.locator("#pm-cause").inputValue(),
  };

  const texts = {
    hypothesis: hypotheses.at(-1).statement,
    mitigation_description: mitigation.description,
    mitigation_steps: mitigation.steps.join(" "),
    verification_check: mitigation.verification_check,
    postmortem_summary: draft.summary,
    postmortem_cause: draft.cause,
  };
  const detected = Object.fromEntries(Object.entries(texts).map(([key, text]) => [key, language(text)]));
  writeFileSync(
    `${OUT}/${EXPECTED}-report.json`,
    JSON.stringify({ expected: EXPECTED, incident, run, confidence: hypotheses.at(-1).confidence, risk: mitigation.risk, texts, detected }, null, 2),
  );
  for (const [key, result] of Object.entries(detected)) expect(result.detected, key).toBe(EXPECTED);
  // The protocol stays in English whatever the prose language.
  expect(["low", "medium", "high"]).toContain(hypotheses.at(-1).confidence);
  expect(["low", "medium", "high"]).toContain(mitigation.risk);
});
