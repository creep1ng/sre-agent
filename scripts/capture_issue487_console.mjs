// Integrated console proof for issue #487 against the packaged stack (nginx CSP + real API):
// one entry at "/", both domains in one navigation, old addresses opening the same view,
// in-document navigation with Back/Forward, one session validated by the real whoami, and a
// theme preference shared by every view. The key comes from the runner's environment and is
// never printed, stored or written to the proof.
//
// Containerized usage (reviewer-repeatable, no host package tools):
//   docker compose --profile e2e run --rm \
//     -v "$PWD/scripts/capture_issue487_console.mjs:/e2e/capture.mjs:ro" \
//     -v "$PWD/docs/evidence:/evidence" e2e node /e2e/capture.mjs
import { writeFileSync } from "node:fs";
import { chromium } from "playwright";

const base = process.env.PLAYWRIGHT_BASE_URL ?? "http://web";
const evidence = process.env.EVIDENCE_DIR ?? "/evidence";
const key = process.env.ADMIN_HUMAN_API_KEY;
const checks = [];
const check = (name, ok, detail = "") => {
  checks.push({ name, result: ok ? "PASS" : "FAIL", ...(detail ? { detail } : {}) });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` :: ${detail}` : ""}`);
};

const browser = await chromium.launch();
// Reduced motion settles theme transitions before each screenshot.
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce" });
const pageErrors = [];
page.on("pageerror", (error) => pageErrors.push(String(error?.message ?? error)));

const entry = await page.goto(`${base}/`, { waitUntil: "networkidle" });
check("GET / is 200", entry?.status() === 200, `got ${entry?.status()}`);
check(
  "GET / carries the same-origin CSP",
  (entry?.headers()["content-security-policy"] ?? "").includes("default-src 'self'"),
);
const sections = {};
for (const name of ["Atención a incidentes", "Gobierno de IA"]) {
  sections[name] = (await page.getByRole("list", { name }).getByRole("link").allTextContents()).map((text) =>
    text.trim(),
  );
}
check(
  "incident response entries",
  JSON.stringify(sections["Atención a incidentes"]) ===
    JSON.stringify(["Alertas", "Triage", "War room", "Decisiones", "Postmortem"]),
  JSON.stringify(sections["Atención a incidentes"]),
);
check(
  "AI governance entries",
  JSON.stringify(sections["Gobierno de IA"]) ===
    JSON.stringify(["Principals", "Recursos y aliases", "Grants", "Auditoría y consumo"]),
  JSON.stringify(sections["Gobierno de IA"]),
);
await page.locator("#alert-inbox[data-state='ready']").waitFor();
check(
  "default view is Alertas and marked current",
  ((await page.locator("[data-console-nav][aria-current='page']").textContent()) ?? "").trim() === "Alertas",
);
check("one main landmark", (await page.getByRole("main").count()) === 1);
await page.screenshot({ path: `${evidence}/issue-487-console-alerts.png` });

await page.goto(`${base}/public/incident-ui/alerts.html?fixture=empty`, { waitUntil: "networkidle" });
check("old alerts address opens the console view", page.url() === `${base}/?view=alerts&fixture=empty`, page.url());
await page.locator("#alert-inbox[data-state='empty']").waitFor();
check("old address keeps its read parameter", true);

await page.goto(`${base}/?view=vista-inexistente`, { waitUntil: "networkidle" });
check(
  "unknown view renders an explicit state",
  ((await page.locator("#console-view h1").textContent()) ?? "").trim() === "Vista no encontrada",
);
await page.evaluate(() => {
  window.__sameDocument = true;
});
await page.getByRole("link", { name: "Ir a Alertas" }).click();
await page.locator("#alert-inbox[data-state='ready']").waitFor();
await page.goBack();
await page.locator("#console-view h1", { hasText: "Vista no encontrada" }).waitFor();
await page.goForward();
await page.locator("#alert-inbox[data-state='ready']").waitFor();
check(
  "in-console navigation, Back and Forward keep one document",
  (await page.evaluate(() => window.__sameDocument)) === true,
);

if (key) {
  await page.locator("#session-chip").click();
  await page.fill("#api-key", key);
  await page.click("#connect-button");
  await page.locator("#session-principal", { hasText: "admin-human" }).waitFor({ timeout: 20_000 });
  check("real whoami activates the console session", true);
  await page.getByRole("button", { name: "Oscuro" }).click();
  await page.locator("#session-chip").click();
  await page.screenshot({ path: `${evidence}/issue-487-console-session-dark.png` });
  await page.locator("#session-chip").click();
  const storage = await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }));
  check("the key is absent from the address and Web Storage", !page.url().includes(key) && !storage.includes(key));
  check("the input no longer holds the key", (await page.locator("#api-key").inputValue()) === "");
  await page.reload({ waitUntil: "networkidle" });
  check("theme persists across a reload", (await page.locator("html").getAttribute("data-theme")) === "dark");
  check(
    "a reload of the only tab asks for the key again (ADR-009, section 9)",
    (await page.locator("#session-chip").getAttribute("data-phase")) === "anonymous",
  );
  await page.getByRole("button", { name: "Claro" }).click();
} else {
  check("ADMIN_HUMAN_API_KEY is available to the runner", false);
}

check("no page errors", pageErrors.length === 0, pageErrors.join(" | "));
await browser.close();

const failures = checks.filter((item) => item.result === "FAIL").map((item) => item.name);
writeFileSync(
  `${evidence}/issue-487-console-shell-proof.json`,
  `${JSON.stringify({ issue: 487, base, checks, failures, pageErrors }, null, 2)}\n`,
);
process.exit(failures.length ? 1 : 0);
