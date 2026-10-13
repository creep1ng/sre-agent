import { randomUUID } from "node:crypto";
import { expect, route, test } from "./support/session-routes.mjs";

// #486, leaf 3 (ADR-009): Principals on the shared session, over the real proxy and API.
const keys = { admin: process.env.ADMIN_HUMAN_API_KEY, demo: process.env.DEMO_HUMAN_API_KEY };
test.skip(!keys.admin || !keys.demo, "requires ADMIN_HUMAN_API_KEY and DEMO_HUMAN_API_KEY");

async function open(context) {
  const page = await context.newPage();
  const output = [];
  page.on("console", (message) => output.push(message.text()));
  page.on("pageerror", (error) => output.push(String(error)));
  await page.goto("/public/admin/principals.html");
  return Object.assign(page, { output });
}

async function signIn(page, key) {
  await page.fill("#api-key", key);
  await page.click("#connect-button");
}

const view = (page) => page.locator("#principals-page");
const status = (page) => page.locator("#session-status");
const ready = (page) => expect(view(page)).toHaveAttribute("data-state", "ready", { timeout: 20_000 });

// Nothing of an earlier generation stays: no detail, no open dialog, no typed value.
async function nothingKept(page) {
  await expect(page.locator("[data-principal-detail], dialog[open]")).toHaveCount(0);
  for (const field of ["#create-principal-id", "#create-display-name", "#issue-expires-at", "#api-key"]) {
    await expect(page.locator(field)).toHaveValue("");
  }
}

// CA7: a key is nowhere a page can show or keep it.
async function keyNowhere(page, ...secrets) {
  const kept = await page.evaluate(() => JSON.stringify([{ ...localStorage }, { ...sessionStorage }, document.cookie]));
  const seen = [page.url(), await page.content(), kept, ...page.output].join("\n");
  for (const secret of secrets) expect(seen).not.toContain(secret);
}

test("one key serves every tab and survives reloading one of them", async ({ context }) => {
  const t1 = await open(context);
  await expect(status(t1)).toHaveText("No session.");
  await expect(t1.locator("#create-button")).toBeDisabled();
  await signIn(t1, keys.admin);
  await ready(t1);
  const t2 = await open(context);
  await t1.reload();
  for (const page of [t1, t2]) {
    await ready(page);
    await expect(status(page)).toHaveText("Signed in as admin-human.");
    await expect(page.locator("[data-principal-row='admin-human']")).toHaveCount(1);
    await expect(page.locator("#create-button")).toBeEnabled();
    await keyNowhere(page, keys.admin);
  }
});

test("clearing the session in one tab clears every tab, and nothing brings it back", async ({ context }) => {
  const [t1, t2, t3] = [await open(context), await open(context), await open(context)];
  await signIn(t1, keys.admin);
  for (const page of [t2, t3]) await ready(page);
  await t1.click("#create-button");
  await t1.fill("#create-display-name", "Left behind");
  await t2.click("[data-expand-principal='admin-human']");
  await t2.click("[data-issue-credential='admin-human']");
  await t2.fill("#issue-expires-at", "2031-01-02T03:04:05Z");
  await t3.goto("/index.html");
  // The open dialog blocks the pointer, so Clear goes straight to its handler.
  await t2.locator("#disconnect-button").dispatchEvent("click");
  for (const page of [t1, t2]) {
    await expect(status(page)).toHaveText("No session.");
    await nothingKept(page);
    await expect(page.locator("#api-key")).toBeFocused();
  }
  await t3.goBack();
  const t4 = await open(context);
  await t1.reload();
  for (const page of [t1, t3, t4]) {
    await expect(status(page)).toHaveText("No session.");
    await expect(view(page)).toHaveAttribute("data-state", "idle");
    await expect(page.locator("[data-principal-row]")).toHaveCount(0);
    await expect(page.locator("#principal-count")).toHaveText("Not loaded.");
  }
});

test("a new key drops what every tab showed before it applies; an invalid one restores nothing", async ({ context }) => {
  const [t1, t2] = [await open(context), await open(context)];
  await signIn(t1, keys.admin);
  await ready(t2);
  await t1.click("[data-expand-principal='admin-human']");
  await t1.click("#create-button");
  await t1.fill("#create-principal-id", "left-behind");
  await t1.fill("#create-display-name", "Left behind");
  // B's validation is held: while it is pending, the tabs show nothing of A.
  let release;
  const held = new Promise((resolve) => (release = resolve));
  route(t1, "**/api/v1/whoami", async (request) => (await held, request.continue()));
  await signIn(t2, keys.demo);
  for (const page of [t1, t2]) {
    await expect(status(page)).toHaveText("Validating the API key…");
    await expect(page.locator("[data-principal-row]")).toHaveCount(0);
    await nothingKept(page);
  }
  release();
  for (const page of [t1, t2]) {
    await expect(status(page)).toHaveText("Signed in as demo-human.");
    await expect(page.locator("#page-error-title")).toHaveText("Access unavailable", { timeout: 20_000 });
    await expect(page.locator("[data-principal-row]")).toHaveCount(0);
  }
  await signIn(t1, "sre_admn_0123456789abcdefghij");
  for (const page of [t1, t2]) {
    await expect(view(page)).toHaveAttribute("data-state", "error", { timeout: 20_000 });
    await expect(page.locator("#page-error-title")).toHaveText("Authentication required");
    await expect(status(page)).toHaveText("No session.");
    await expect(page.locator("[data-principal-row]")).toHaveCount(0);
    await keyNowhere(page, keys.admin, keys.demo);
  }
});

test("another key of the same principal is still a new session for every tab", async ({ context, request }) => {
  const headers = { Authorization: `Bearer ${keys.admin}`, "Idempotency-Key": randomUUID() };
  const issued = await request.post("/api/v1/principals/admin-human/credentials", { headers, data: {} });
  expect(issued.ok()).toBe(true);
  const second = (await issued.json()).key;
  const [t1, t2] = [await open(context), await open(context)];
  await signIn(t1, keys.admin);
  await ready(t2);
  await t1.click("[data-expand-principal='admin-human']");
  await t1.click("#create-button");
  await t1.fill("#create-display-name", "Left behind");
  await signIn(t2, second);
  for (const page of [t1, t2]) {
    await ready(page);
    await expect(status(page)).toHaveText("Signed in as admin-human.");
    await nothingKept(page);
    await keyNowhere(page, keys.admin, second);
  }
});
