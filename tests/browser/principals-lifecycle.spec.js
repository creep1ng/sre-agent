import { randomUUID } from "node:crypto";
import { expect, route, test } from "./support/session-routes.mjs";

// #486, leaf 3c (ADR-009, sections 6 to 8): Principals across the page lifecycle, over the real proxy and API.
const adminKey = process.env.ADMIN_HUMAN_API_KEY;
test.skip(!adminKey, "requires ADMIN_HUMAN_API_KEY");

const pageErrors = [];
test.afterEach(() => expect(pageErrors.splice(0)).toEqual([]));

async function open(context, origin = "", path = "/public/admin/principals.html", before = async () => {}) {
  const page = await context.newPage();
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  await before(page);
  await page.goto(`${origin}${path}`);
  return page;
}

// A page that only connects to the shared session and sends no request of its own.
async function connect(context, origin = "") {
  const page = await open(context, origin, "/index.html");
  await page.evaluate(async () => {
    window.session = (await import("/public/api/client.js")).connectSharedSession();
  });
  return page;
}

async function signIn(page, key) {
  await page.fill("#api-key", key);
  await page.click("#connect-button");
}

const view = (page) => page.locator("#principals-page");
const status = (page) => page.locator("#session-status");
const ready = (page) => expect(view(page)).toHaveAttribute("data-state", "ready", { timeout: 20_000 });
const adminRow = (page) => page.locator("[data-principal-row='admin-human']");
// Headless Chromium neither freezes a page through CDP here (Page.setWebLifecycleState fires no
// freeze or resume) nor keeps a page with a SharedWorker in the back/forward cache, so the
// lifecycle events are dispatched in the page. Returns whether the page is suspended right after.
const fire = (page, name) =>
  page.evaluate((type) => {
    if (type.startsWith("page")) dispatchEvent(new PageTransitionEvent(type, { persisted: true }));
    else document.dispatchEvent(new Event(type));
    return document.getElementById("principals-page")?.hasAttribute("data-suspended") ?? null;
  }, name);

// Another key of admin-human, so a spec can revoke it or hold its requests without touching others.
async function secondKey(request) {
  const headers = { Authorization: `Bearer ${adminKey}`, "Idempotency-Key": randomUUID() };
  const issued = await request.post("/api/v1/principals/admin-human/credentials", { headers, data: {} });
  expect(issued.ok()).toBe(true);
  const { key, credential } = await issued.json();
  return { key, id: credential.credential_id };
}

async function revoke(request, credentialId) {
  const headers = { Authorization: `Bearer ${adminKey}` };
  expect((await request.delete(`/api/v1/credentials/${credentialId}`, { headers })).status()).toBe(204);
}

// Counts the whoami and list requests of every page and of the session worker.
function counted(page) {
  const seen = { whoami: 0, lists: 0 };
  route(page, "**/api/v1/whoami", (request) => ((seen.whoami += 1), request.continue()));
  route(page, (url) => url.pathname === "/api/v1/principals", (request) => {
    if (request.request().method() === "GET") seen.lists += 1;
    return request.continue();
  });
  return seen;
}

for (const [leave, back] of [["freeze", "resume"], ["pagehide", "pageshow"]]) {
  test(`${leave} hides the page and its dialog until the worker confirms the same token after ${back}`, async ({
    context,
  }) => {
    const t1 = await open(context);
    const seen = counted(t1);
    await signIn(t1, adminKey);
    await ready(t1);
    await t1.click("#create-button");
    await t1.fill("#create-display-name", "Typed before leaving");
    expect(await fire(t1, leave)).toBe(true);
    for (const shown of [adminRow(t1), t1.locator("#create-dialog")]) await expect(shown).toBeHidden();
    // Coming back only asks the worker: the page is still suspended when the event returns.
    expect(await fire(t1, back)).toBe(true);
    await expect(view(t1)).not.toHaveAttribute("data-suspended");
    for (const shown of [adminRow(t1), t1.locator("#create-dialog")]) await expect(shown).toBeVisible();
    // The same token keeps the page's context: the typed value stays and nothing is loaded again.
    await expect(t1.locator("#create-display-name")).toHaveValue("Typed before leaving");
    expect(seen.lists).toBe(1);
  });
}

test("a suspended tab learns on resume of a logout it missed, and shows nothing of it", async ({ context }) => {
  // While "frozen", t2 gets no session state from the worker, as a frozen page runs nothing.
  const drop = (page) =>
    page.addInitScript(() => {
      const property = Object.getOwnPropertyDescriptor(MessagePort.prototype, "onmessage");
      Object.defineProperty(MessagePort.prototype, "onmessage", {
        configurable: true,
        get: property.get,
        set(handler) {
          property.set.call(this, (event) => (window.frozen && event.data?.type === "session" ? null : handler(event)));
        },
      });
    });
  const [t1, t2] = [await open(context), await open(context, "", undefined, drop)];
  await signIn(t1, adminKey);
  for (const page of [t1, t2]) await ready(page);
  await t2.evaluate(() => (window.frozen = true));
  expect(await fire(t2, "freeze")).toBe(true);
  await t1.click("#disconnect-button");
  await expect(status(t1)).toHaveText("No session.");
  await expect(view(t2)).toHaveAttribute("data-suspended", "");
  await expect(adminRow(t2)).toBeHidden();
  await t2.evaluate(() => (window.frozen = false));
  expect(await fire(t2, "resume")).toBe(true);
  await expect(status(t2)).toHaveText("No session.");
  await expect(view(t2)).not.toHaveAttribute("data-suspended");
  await expect(t2.locator("[data-principal-row]")).toHaveCount(0);
  await expect(t2.locator("#principal-count")).toHaveText("Not loaded.");
});

test("a page that becomes visible past 60 s revalidates the session, and a revoked key ends it in every tab", async ({
  context,
  request,
}) => {
  test.setTimeout(120_000);
  const second = await secondKey(request);
  const t1 = await open(context);
  const seen = counted(t1);
  await signIn(t1, second.key);
  await ready(t1);
  const t2 = await open(context);
  await ready(t2);
  await revoke(request, second.id);
  // Within 60 s nothing asks the API again, so the revoked key is not noticed yet.
  await fire(t1, "visibilitychange");
  await t1.waitForTimeout(61_000);
  for (const page of [t1, t2]) await expect(status(page)).toHaveText("Signed in as admin-human.");
  expect(seen).toEqual({ whoami: 1, lists: 2 });
  await fire(t1, "visibilitychange");
  for (const page of [t1, t2]) {
    await expect(page.locator("#page-error-title")).toHaveText("Authentication required");
    await expect(status(page)).toHaveText("No session.");
    await expect(page.locator("[data-principal-row]")).toHaveCount(0);
  }
  // The revalidation found the revoked key, not a request of a page.
  expect(seen).toEqual({ whoami: 2, lists: 2 });
});

test("a page of another protocol version is blocked and offers nothing, while the session goes on", async ({
  context,
}) => {
  const t1 = await open(context);
  const seen = counted(t1);
  await signIn(t1, adminKey);
  await ready(t1);
  // page.route sees the page's own module request: this page speaks an older session protocol.
  const older = (page) =>
    page.route("**/public/api/client.js", async (request) => {
      const response = await request.fetch();
      const body = (await response.text()).replace("const SESSION_PROTOCOL = 1;", "const SESSION_PROTOCOL = 0;");
      await request.fulfill({ response, body });
    });
  const t2 = await open(context, "", undefined, older);
  await expect(status(t2)).toHaveText("Session unavailable. Reload the page.");
  await expect(view(t2)).toHaveAttribute("data-state", "blocked");
  for (const control of ["#api-key", "#connect-button", "#disconnect-button", "#create-button", "#refresh-button"]) {
    await expect(t2.locator(control)).toBeDisabled();
  }
  await expect(t2.locator("[data-principal-row]")).toHaveCount(0);
  // The worker still serves the current page: a refresh goes through it again.
  await t1.click("#refresh-button");
  await expect.poll(() => seen.lists).toBe(2);
  await ready(t1);
  await expect(status(t1)).toHaveText("Signed in as admin-human.");
  await expect(adminRow(t1)).toBeVisible();
});

// hold-upstream, behind the web-held proxy, holds an armed answer until the spec releases it.
test.describe("held by the test upstream", () => {
  const heldOrigin = process.env.PLAYWRIGHT_HELD_URL;
  const control = process.env.PLAYWRIGHT_HOLD_CONTROL;
  test.skip(!heldOrigin || !control, "requires web-held and hold-upstream from compose.yaml");
  const gate = async (request, action, data = {}) => (await request.post(`${control}/${action}`, { data })).json();

  test("a page that connects past 60 s revalidates the session, and the late 401 of an earlier key changes nothing", async ({
    context,
    request,
  }) => {
    test.setTimeout(120_000);
    const second = await secondKey(request);
    const t1 = await open(context, heldOrigin);
    const seen = counted(t1);
    await signIn(t1, second.key);
    await ready(t1);
    await revoke(request, second.id);
    await connect(context, heldOrigin);
    await t1.waitForTimeout(61_000);
    expect(seen.whoami).toBe(1);
    const label = `revalidation-${randomUUID().slice(0, 8)}`;
    await gate(request, "hold", { label, path: "/v1/whoami", key: second.key });
    await connect(context, heldOrigin);
    await expect.poll(() => gate(request, "held")).toContain(label);
    expect(seen.whoami).toBe(2);
    // A new key starts another generation while the 401 of the revoked one is still held.
    await signIn(t1, adminKey);
    await ready(t1);
    await gate(request, "release", { label });
    // Half a second for the released 401 to reach the worker, which drops it as stale.
    await t1.waitForTimeout(500);
    const listed = seen.lists;
    await t1.click("#refresh-button");
    await expect.poll(() => seen.lists).toBe(listed + 1);
    await ready(t1);
    await expect(status(t1)).toHaveText("Signed in as admin-human.");
    await expect(t1.locator("#page-error")).toBeHidden();
    expect(seen.whoami).toBe(3);
  });

  // S15 (CA8): the answer of a create the API accepted is held until after a logout.
  test("a create accepted before a logout is neither undone, sent again nor shown by the tabs", async ({
    context,
    request,
  }) => {
    const second = await secondKey(request);
    const [t1, t2] = [await open(context, heldOrigin), await open(context, heldOrigin)];
    let creates = 0;
    route(t1, (url) => url.pathname === "/api/v1/principals", (request) => {
      if (request.request().method() === "POST") creates += 1;
      return request.continue();
    });
    await signIn(t1, second.key);
    for (const page of [t1, t2]) await ready(page);
    const id = `accepted-${randomUUID().slice(0, 8)}`;
    const label = `create-${id}`;
    await gate(request, "hold", { label, path: "/v1/principals", key: second.key });
    await t1.click("#create-button");
    await t1.fill("#create-principal-id", id);
    await t1.fill("#create-display-name", "Accepted before logout");
    await t1.click("#create-submit");
    await expect.poll(() => gate(request, "held")).toContain(label);
    await t2.click("#disconnect-button");
    for (const page of [t1, t2]) await expect(status(page)).toHaveText("No session.");
    await gate(request, "release", { label });
    // The late 201 settles the request under a cleared generation: nothing shows it.
    await expect(t1.locator("#create-submit")).toBeEnabled();
    for (const page of [t1, t2]) {
      await expect(page.locator("[data-principal-row]")).toHaveCount(0);
      await expect(page.locator("#live-region")).not.toContainText(id);
    }
    // Logout discarded the key here without revoking it, and the API kept what it had accepted.
    const read = await request.get(`/api/v1/principals/${id}`, { headers: { Authorization: `Bearer ${adminKey}` } });
    expect(read.status()).toBe(200);
    await signIn(t2, second.key);
    for (const page of [t1, t2]) await ready(page);
    expect(creates).toBe(1);
  });
});
