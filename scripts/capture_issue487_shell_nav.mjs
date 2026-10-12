// M2 shell-nav proof for issue #487: real click-through from the entry block,
// per-route reload survival, aria-current location, keyboard reachability and
// genuine screenshots. No credentials are typed; no API mutation is performed.
//
// Containerized usage (reviewer-repeatable, no host package tools):
//   docker run --rm --network sre-agent_runtime \
//     -v "$PWD/scripts/capture_issue487_shell_nav.mjs:/e2e/capture.mjs:ro" \
//     -v "$PWD/docs/evidence:/evidence" \
//     sre-agent-e2e:latest node /e2e/capture.mjs
// Substitute your checkout's Compose image and network names when they differ.
import { writeFileSync } from "node:fs";
import { chromium } from "playwright";

const base = "http://web";
const evidence = "/evidence";
const failures = [];
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` :: ${detail}` : ""}`);
  if (!ok) failures.push(name);
};

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
const pageErrors = [];
page.on("pageerror", (error) => pageErrors.push(String(error?.message ?? error)));

const entryRoutes = [
  { name: "Principals", href: "/public/admin/principals.html", h1: "Principals", current: "Principals" },
  { name: "Resources & aliases", href: "/public/admin/model-aliases.html", h1: "Resources & aliases", current: "Resources & aliases" },
  { name: "Grants", href: "/public/admin/grants.html", h1: "Grants", current: "Grants" },
  { name: "Audit & consumption", href: "/public/admin/consumption.html", h1: "Consumption", current: "Consumption" },
  { name: "Incident alerts", href: "/public/incident-ui/alerts.html", h1: null, current: null },
];

// Entry block: five real links, then screenshot the entry.
let response = await page.goto(`${base}/`, { waitUntil: "domcontentloaded" });
check("entry GET / is 200", response?.status() === 200, `got ${response?.status()}`);
const entryNav = page.getByRole("navigation", { name: "Operational entry" });
check("entry nav landmark visible", await entryNav.isVisible());
const entryLinks = await entryNav.getByRole("link").all();
check("entry exposes 5 links", entryLinks.length === 5, `got ${entryLinks.length}`);
const seen = [];
for (const link of entryLinks) {
  seen.push({ text: (await link.textContent()).trim(), href: await link.getAttribute("href") });
}
for (const route of entryRoutes) {
  const match = seen.find((item) => item.href === route.href);
  check(`entry links ${route.href}`, !!match && match.text === route.name, JSON.stringify(match ?? null));
}
await page.screenshot({ path: `${evidence}/issue-487-m2-entry.png` });

// Click-through from the entry on a fresh load per route, then reload survival.
for (const route of entryRoutes) {
  await page.goto(`${base}/`, { waitUntil: "domcontentloaded" });
  const link = entryNav.getByRole("link", { name: route.name });
  await Promise.all([page.waitForURL(`**${route.href}`), link.click()]);
  check(`click-through to ${route.href}`, page.url().endsWith(route.href), page.url());
  if (route.h1) {
    check(`h1 on ${route.href}`, ((await page.locator("h1").first().textContent()) ?? "").trim() === route.h1);
  } else {
    check(`title on ${route.href}`, (await page.title()).length > 0, await page.title());
  }
  const reload = await page.reload({ waitUntil: "domcontentloaded" });
  check(`reload survives on ${route.href}`, reload?.status() === 200, `got ${reload?.status()}`);
  if (route.current) {
    const current = page.getByRole("navigation", { name: "Control plane" }).locator("[aria-current='page']");
    check(`aria-current on ${route.href}`, ((await current.textContent()) ?? "").trim() === route.current);
  }
}

// Audit events surface: direct GET plus reload plus surface-level location.
response = await page.goto(`${base}/public/admin/audit-events.html`, { waitUntil: "domcontentloaded" });
check("direct GET audit-events.html is 200", response?.status() === 200, `got ${response?.status()}`);
const auditReload = await page.reload({ waitUntil: "domcontentloaded" });
check("reload survives on audit-events.html", auditReload?.status() === 200, `got ${auditReload?.status()}`);
const auditCurrent = page.getByRole("navigation", { name: "Control plane" }).locator("[aria-current='page']");
check(
  "audit-events marks Audit & consumption surface",
  ((await auditCurrent.textContent()) ?? "").trim() === "Audit & consumption",
);

// Grants surface screenshot (genuine pixels, no session data entered).
await page.goto(`${base}/public/admin/grants.html`, { waitUntil: "domcontentloaded" });
await page.screenshot({ path: `${evidence}/issue-487-m2-grants.png`, fullPage: true });

// Keyboard: Tab from the top must reach every entry link.
await page.goto(`${base}/`, { waitUntil: "domcontentloaded" });
const reached = new Set();
for (let i = 0; i !== 20; i += 1) {
  await page.keyboard.press("Tab");
  const active = await page.evaluate(() => {
    const el = document.activeElement;
    return {
      inEntry: !!el?.closest?.("nav[aria-label='Operational entry']"),
      label: (el?.textContent ?? "").trim().slice(0, 32),
    };
  });
  if (active.inEntry) reached.add(active.label);
}
check(
  "keyboard Tab reaches all 5 entry links",
  entryRoutes.every((route) => reached.has(route.name)),
  JSON.stringify([...reached]),
);

check("no page errors during proof", pageErrors.length === 0, JSON.stringify(pageErrors));
await browser.close();

writeFileSync(
  `${evidence}/issue-487-m2-nav-proof.json`,
  `${JSON.stringify({ failures, pageErrors }, null, 2)}\n`,
);
if (failures.length !== 0) process.exit(1);
console.log("M2-NAV-PROOF-OK");
