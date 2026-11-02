import { expect, request, test, type Page } from "@playwright/test";

/*
 * The RC-2 inbox (#870) against the REAL stack: web proxy, FastAPI, PostgreSQL, seeded by
 * e2e/run-inbox-real.sh (INBOX_STAMP). inc-vc-ip<stamp> opened last night and waits for a
 * mitigation decision; inc-vc-ir<stamp> opened last night and recovered this run; two change
 * events of checkout happened last night. Ways this can fail, written first:
 * 1. the pending decision is not first, not amber, or lacks its service, alert, proposal or an
 *    action that opens the incident;
 * 2. amber appears anywhere else on the page, or stays once the decision is taken;
 * 3. a section shows without data, or explains why it is empty;
 * 4. the recovered incident or last night's events are missing, out of order, or invented;
 * 5. the inbox breaks in the light theme or in English;
 * 6. a link does not open its incident.
 */
const STAMP = process.env.INBOX_STAMP ?? "";
const KEY = process.env.DEMO_HUMAN_API_KEY ?? "";
const BASE = process.env.BASE_URL ?? "http://web";
const PENDING = `inc-vc-ip${STAMP}`;
const RECOVERED = `inc-vc-ir${STAMP}`;
const SHOTS = "e2e/artifacts/inbox";

test.skip(process.env.INBOX_REAL !== "1" || !STAMP || !KEY, "run through e2e/run-inbox-real.sh");
test.use({ video: "off" });
test.describe.configure({ mode: "serial" });

async function open(page: Page, action = "Conectar API") {
  await page.goto("./");
  await page.getByRole("button", { name: action }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Clave de API").fill(KEY);
  await dialog.getByRole("button", { name: "Conectar", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).not.toHaveText(/API|bandeja|inbox/, { timeout: 30_000 });
}

/** Every element whose computed colours use --star or --star-ink, and whether it is the decision. */
function amberUse(page: Page) {
  return page.evaluate(() => {
    const probe = document.body.appendChild(document.createElement("i"));
    const tone = (name: string) => ((probe.style.color = `var(${name})`), getComputedStyle(probe).color);
    const amber = new Set([tone("--star"), tone("--star-ink")]);
    probe.remove();
    const properties = ["color", "background-color", "border-top-color", "border-left-color", "outline-color", "fill", "stroke"];
    return [...document.querySelectorAll("body *")].flatMap((element) => {
      const style = getComputedStyle(element);
      const property = properties.find((name) => amber.has(style.getPropertyValue(name)));
      return property ? [{ decision: Boolean(element.closest("[data-decision]")), property, text: element.textContent?.slice(0, 40) }] : [];
    });
  });
}

async function expectDecisionFirstInAmber(page: Page) {
  const decision = page.locator("article[data-decision]");
  await expect(decision).toHaveCount(1);
  await expect(decision).toContainText("paymentservice");
  await expect(decision).toContainText("Elevated error rate on paymentservice.");
  await expect(decision).toContainText("Turn the paymentFailure feature flag off.");
  // The decision comes before every other section.
  expect(await page.evaluate(() => document.querySelector("article[data-decision], main section")?.tagName)).toBe("ARTICLE");
  const star = await page.evaluate(() => {
    const probe = document.body.appendChild(document.createElement("i"));
    const tone = (name: string) => ((probe.style.color = `var(${name})`), getComputedStyle(probe).color);
    const tones = { star: tone("--star"), ink: tone("--star-ink") };
    probe.remove();
    return tones;
  });
  await expect(decision).toHaveCSS("border-left-color", star.star);
  await expect(decision.locator("div").first()).toHaveCSS("color", star.ink);
  const used = await amberUse(page);
  expect(used.filter((use) => !use.decision)).toEqual([]);
  expect(used.length).toBeGreaterThan(0);
}

for (const { locale, scheme, name, connect, texts } of [
  { locale: "es-CO", scheme: "dark", name: "es-night", connect: "Conectar API",
    texts: ["Una decisión te espera.", "Revisar y decidir", "Mientras te tomas el café, mira esto.", "paymentservice se recuperó.", "Anoche"] },
  { locale: "es-CO", scheme: "light", name: "es-day", connect: "Conectar API",
    texts: ["Una decisión te espera.", "Revisar y decidir", "Anoche"] },
  { locale: "en-US", scheme: "dark", name: "en-night", connect: "Connect API",
    texts: ["One decision is waiting for you.", "Review and decide", "While you have your coffee, look at this.", "paymentservice recovered.", "Last night"] },
  { locale: "en-US", scheme: "light", name: "en-day", connect: "Connect API",
    texts: ["One decision is waiting for you.", "Review and decide", "Last night"] },
] as const) {
  test.describe(name, () => {
    test.use({ locale, colorScheme: scheme });

    test(`${name}: the decision leads in amber, then the digest and last night`, async ({ page }) => {
      await open(page, connect);
      await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /^(?!.*dark)/);
      for (const text of texts) await expect(page.locator("main")).toContainText(text);
      await expectDecisionFirstInAmber(page);
      // Last night, in order: deploy 21:12, recovered incident 22:05, failed CI 22:40, pending 23:40.
      const rows = page.locator("main section ol > li");
      await expect(rows.locator("time")).toHaveText(["21:12", "22:05", "22:40", "23:40"]);
      await expect(rows.nth(0)).toContainText("checkout checkout:1.5.0.");
      await expect(rows.nth(2)).toContainText(locale === "es-CO" ? "Falló." : "Failed.");
      await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
    });
  });
}

test("three days later the digest and last night are gone, the decision still waits", async ({ page }) => {
  await page.clock.setFixedTime(Date.now() + 3 * 24 * 60 * 60 * 1000);
  await open(page);
  await expect(page.locator("article[data-decision]")).toContainText(/\d+\sd/);
  await expect(page.locator("main section")).toHaveCount(0);
  await expect(page.locator("main")).not.toContainText(/café|Anoche/);
});

test("each item opens its incident", async ({ page }) => {
  await open(page);
  await page.getByRole("link", { name: "Revisar y decidir" }).click();
  await expect(page).toHaveURL(new RegExp(`/app/incidentes/${PENDING}$`));
  await page.goBack();
  await page.locator(`a[href$="/incidentes/${RECOVERED}"]`).first().click();
  await expect(page).toHaveURL(new RegExp(`/app/incidentes/${RECOVERED}$`));
});

test("once the decision is taken, nothing waits and nothing is amber", async ({ page }) => {
  const api = await request.newContext({ extraHTTPHeaders: { authorization: `Bearer ${KEY}` } });
  const row = async () =>
    ((await (await api.get(`${BASE}/api/v1/incidents?status=open&limit=100`)).json()).incidents as { incident_id: string; pending_decision: { run_id: string; incident_version: number } | null }[])
      .find((item) => item.incident_id === PENDING);
  const decision = (await row())!.pending_decision!;
  const sent = await api.post(`${BASE}/api/v1/incidents/${PENDING}/runs/${decision.run_id}/commands`, {
    headers: { "idempotency-key": `inbox-approve-${STAMP}-0001` },
    data: {
      command: "approve_mitigation",
      expected_incident_version: decision.incident_version,
      actor: "human",
      actor_reference: { reference_version: "1.0.0", principal_id: "demo-human" },
    },
  });
  expect(sent.status()).toBe(202);
  await expect.poll(async () => (await row())?.pending_decision ?? null, { timeout: 30_000 }).toBeNull();
  await open(page);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Nada te espera.");
  await expect(page.locator("[data-decision]")).toHaveCount(0);
  expect(await amberUse(page)).toEqual([]);
  await page.screenshot({ path: `${SHOTS}/es-night-decided.png`, fullPage: true });
});
