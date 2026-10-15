import { expect, test } from "@playwright/test";
import { randomUUID } from "node:crypto";

// #486, leaf 2 (ADR-009): the shared session core over the real proxy and API.
const adminKey = process.env.ADMIN_HUMAN_API_KEY;
test.skip(!adminKey, "requires ADMIN_HUMAN_API_KEY");

async function admin(request, method, path, data) {
  const headers = { Authorization: `Bearer ${adminKey}`, "Idempotency-Key": randomUUID() };
  const response = await request.fetch(`/api${path}`, { method, headers, data });
  expect(response.status(), `${method} ${path}`).toBeLessThan(300);
  return response.status() === 204 ? null : response.json();
}

// A key of a new principal without grants, or another key of an existing principal.
async function credential(request, principalId) {
  const id = principalId ?? `session-${randomUUID().slice(0, 8)}`;
  const body = { principal_id: id, kind: "human", display_name: "Shared session test" };
  if (!principalId) await admin(request, "POST", "/v1/principals", body);
  const issued = await admin(request, "POST", `/v1/principals/${id}/credentials`, {});
  return { principalId: id, key: issued.key, id: issued.credential.credential_id };
}

// A page served with the production CSP, connected to the shared session.
async function tab(context, origin = "") {
  const page = await context.newPage();
  await page.goto(`${origin}/index.html`);
  await page.evaluate(async () => {
    const client = await import("/public/api/client.js");
    const session = client.connectSharedSession();
    const states = [];
    session.subscribe((next) => states.push(next));
    window.harness = { session, states, api: client.createAdministrativeApiClient({ session }) };
  });
  return page;
}

const state = (page) => page.evaluate(() => window.harness.session.state);
const reached = (page, field, value) =>
  page.waitForFunction(([k, v]) => window.harness.session.state[k] === v, [field, value]);
const set = (page, key) =>
  page.evaluate((value) => window.harness.session.setCredential(value), key);
const call = (page, name, ...values) =>
  page.evaluate(async ([method, args]) => {
    try {
      return { value: await window.harness.api[method](...args) };
    } catch (error) {
      return { kind: error.kind, status: error.status };
    }
  }, [name, values]);
const stale = { kind: "stale_session", status: null };

test("a key set once serves every page and stays in the worker", async ({ context, request }) => {
  const [t1, t2] = [await tab(context), await tab(context)];
  await set(t1, adminKey);
  await reached(t1, "phase", "active");
  await reached(t2, "phase", "active");
  const active = await state(t1);
  expect(await state(t2)).toEqual(active);
  expect(active.principalId).toBe("admin-human");
  const listed = (await call(t2, "listPrincipals")).value.items;
  expect(listed.map((principal) => principal.principal_id)).toContain("admin-human");
  const id = `session-${randomUUID().slice(0, 8)}`;
  const body = { principal_id: id, kind: "human", display_name: "Created through the worker" };
  const [first, again] = [randomUUID(), randomUUID()];
  expect((await call(t2, "createPrincipal", body, first)).value.principal_id).toBe(id);
  const replay = await call(t2, "createPrincipal", { ...body, display_name: "Changed" }, first);
  expect(replay).toEqual({ kind: "conflict", status: 409 });
  const issued = (await call(t1, "issueCredential", id, {}, again)).value.credential;
  expect(await call(t1, "revokeCredential", issued.credential_id)).toEqual({ value: null });
  for (const page of [t1, t2]) {
    const exposed = await page.evaluate(() =>
      JSON.stringify([window.harness.states, { ...localStorage }, { ...sessionStorage }]),
    );
    expect(exposed + (await page.evaluate(() => document.cookie))).not.toContain(adminKey);
  }
  const worker = await request.get("/public/api/session-worker.js");
  expect(worker.headers()["content-security-policy"]).toContain("frame-ancestors 'none'");
  await t2.evaluate(() => window.harness.session.logout());
  await reached(t1, "reason", "logout");
  expect(await state(t1)).toMatchObject({ phase: "anonymous", principalId: null });
  expect((await state(t1)).token).not.toBe(active.token);
});

test("every change is a new generation, even for one principal", async ({ context, request }) => {
  const a = await credential(request);
  const a2 = await credential(request, a.principalId);
  const [t1, t2] = [await tab(context), await tab(context)];
  await set(t1, a.key);
  await reached(t2, "phase", "active");
  const first = await state(t2);
  const racing = await t1.evaluate((key) => {
    window.harness.session.setCredential(key);
    return window.harness.api.getWhoAmI().then(() => "applied", (error) => error.kind);
  }, a2.key);
  expect(racing).toBe("stale_session");
  await t2.waitForFunction((old) => window.harness.session.state.token !== old, first.token);
  await reached(t2, "phase", "active");
  const second = await state(t2);
  expect(second).toMatchObject({ principalId: a.principalId, phase: "active" });
  const phases = await t2.evaluate(
    (token) => window.harness.states.filter((s) => s.token === token).map((s) => s.phase),
    second.token,
  );
  expect(phases).toEqual(["validating", "active"]);
  await set(t2, "sre_invalid_0123456789abcdefghijklmnop");
  await reached(t1, "reason", "invalid_credential");
  const anonymous = await state(t1);
  expect(anonymous).toMatchObject({ phase: "anonymous", principalId: null });
  expect(await call(t1, "getWhoAmI")).toEqual(stale);
  expect(await state(t1)).toEqual(anonymous);
});

test("a 403 stays in its call; a current 401 ends every page", async ({ context, request }) => {
  const b = await credential(request);
  const [t1, t2] = [await tab(context), await tab(context)];
  await set(t1, b.key);
  await reached(t1, "phase", "active");
  await reached(t2, "phase", "active");
  const before = await state(t1);
  expect(await call(t1, "listPrincipals")).toEqual({ kind: "authorization", status: 403 });
  expect(await state(t2)).toEqual(before);
  await admin(request, "DELETE", `/v1/credentials/${b.id}`);
  expect(await call(t2, "getWhoAmI")).toEqual(stale);
  await reached(t1, "reason", "credential_rejected");
  expect(await state(t1)).toMatchObject({ phase: "anonymous", principalId: null });
});

test("the worker forwards only allowed requests", async ({ context }) => {
  const t1 = await tab(context);
  await set(t1, adminKey);
  await reached(t1, "phase", "active");
  const verdicts = await t1.evaluate(async () => {
    const worker = new SharedWorker("/public/api/session-worker.js", { name: "sre-agent-session" });
    const own = { port: worker.port, replies: [] };
    own.port.onmessage = ({ data }) => own.replies.push(data);
    own.port.postMessage({ type: "hello", version: 1 });
    const wait = async (check) => {
      while (!check()) await new Promise((resolve) => setTimeout(resolve, 20));
    };
    await wait(() => own.replies.some((reply) => reply.type === "session"));
    const { token } = own.replies.find((reply) => reply.type === "session");
    const attempts = [
      ["https://example.org/v1/whoami", "GET", {}],
      ["/health", "GET", {}],
      ["/v1/../health", "GET", {}],
      ["/v1/%2e%2e/health", "GET", {}],
      ["/v1//whoami", "GET", {}],
      ["/v1/a%2fb", "GET", {}],
      ["/v1/a%5cb", "GET", {}],
      ["/v1/whoami", "PATCH", {}],
      ["/v1/whoami", "GET", { authorization: "Bearer page-supplied" }],
      ["/v1/whoami", "GET", {}, `${token}0`],
      ["/v1/whoami", "GET", { accept: "application/json" }],
    ];
    attempts.forEach(([path, method, headers, sent = token], id) =>
      own.port.postMessage({ type: "request", id, token: sent, path, method, headers }),
    );
    const responses = () => own.replies.filter((reply) => reply.type === "response");
    await wait(() => responses().length === attempts.length);
    const results = responses().sort((x, y) => x.id - y.id).map((r) => r.refused ?? r.status);
    return { results, own: own.replies };
  });
  expect(verdicts.results).toEqual([...Array(9).fill("not_allowed"), "stale_session", 200]);
  expect(JSON.stringify(verdicts.own)).not.toContain(adminKey);
  expect(await state(t1)).toMatchObject({ phase: "active", principalId: "admin-human" });
});

test("the worker refuses an older page and steps down for a newer one", async ({ context }) => {
  const t1 = await tab(context);
  await set(t1, adminKey);
  await reached(t1, "phase", "active");
  const before = await state(t1);
  const replies = await t1.evaluate(async () => {
    const url = "/public/api/session-worker.js";
    const { port } = new SharedWorker(url, { name: "sre-agent-session" });
    const seen = [];
    port.onmessage = ({ data }) => seen.push(data);
    port.postMessage({ type: "hello", version: 0 });
    port.postMessage({ type: "logout" });
    const request = { id: 1, token: null, path: "/v1/whoami", method: "GET", headers: {} };
    port.postMessage({ type: "request", ...request });
    while (seen.length < 2) await new Promise((resolve) => setTimeout(resolve, 20));
    port.postMessage({ type: "hello", version: 2 });
    return seen;
  });
  expect(replies).toEqual([
    { type: "hello", version: 1 },
    { type: "response", id: 1, token: null, refused: "stale_session" },
  ]);
  expect(await call(t1, "listPrincipals")).toEqual(stale);
  await reached(t1, "phase", "anonymous");
  expect((await state(t1)).token.split(":")[0]).not.toBe(before.token.split(":")[0]);
});

test("a lost worker is replaced by an anonymous one", async ({ browser, context }) => {
  const [t1, t2] = [await tab(context), await tab(context)];
  await set(t1, adminKey);
  await reached(t1, "phase", "active");
  await reached(t2, "phase", "active");
  const before = await state(t1);
  const { targetInfo } = await (await context.newCDPSession(t1)).send("Target.getTargetInfo");
  const cdp = await browser.newBrowserCDPSession();
  const worker = (await cdp.send("Target.getTargets")).targetInfos.find(
    (target) =>
      target.type === "shared_worker" && target.browserContextId === targetInfo.browserContextId,
  );
  await cdp.send("Target.closeTarget", { targetId: worker.targetId });
  for (const page of [t2, t1]) {
    expect(await call(page, "listPrincipals")).toEqual(stale);
    await reached(page, "phase", "anonymous");
  }
  const after = await state(t1);
  expect(await state(t2)).toEqual(after);
  expect(after.principalId).toBeNull();
  expect(after.token.split(":")[0]).not.toBe(before.token.split(":")[0]);
});

// Races (S07–S13): hold-upstream, behind the web-held proxy, holds chosen answers until released.
const heldOrigin = process.env.PLAYWRIGHT_HELD_URL;
const control = process.env.PLAYWRIGHT_HOLD_CONTROL;
const gate = async (request, action, data = {}) =>
  (await request.post(`${control}/${action}`, { data })).json();
const hold = (request, label, path, key) => gate(request, "hold", { label, path, key });
const holding = (request, label) => expect.poll(() => gate(request, "held")).toContain(label);
const release = (request, label, cut = false) => gate(request, "release", { label, cut });
const start = (page, name, label) =>
  page.evaluate(([method, slot]) => {
    const outcomes = (window.harness.outcomes ??= {});
    window.harness.api[method]().then(
      (value) => (outcomes[slot] = { value }),
      (error) => (outcomes[slot] = { kind: error.kind, status: error.status }),
    );
  }, [name, label]);
const outcome = async (page, label) =>
  (await page.waitForFunction((slot) => window.harness.outcomes?.[slot], label)).jsonValue();

test.describe("races held by the test upstream", () => {
  test.skip(!heldOrigin || !control, "requires web-held and hold-upstream from compose.yaml");

  test("late success and error of A reach neither B nor a logout", async ({ context, request }) => {
    const [a, b] = [await credential(request), await credential(request)];
    const [t1, t2] = [await tab(context, heldOrigin), await tab(context, heldOrigin)];
    await set(t1, a.key);
    await reached(t2, "phase", "active");
    await hold(request, "a-success", "/v1/whoami", a.key);
    await hold(request, "a-error", "/v1/principals", a.key);
    await start(t1, "getWhoAmI", "a-success");
    await start(t1, "listPrincipals", "a-error");
    await holding(request, "a-success");
    await holding(request, "a-error");
    await set(t2, b.key);
    await reached(t1, "principalId", b.principalId);
    const current = await state(t1);
    await release(request, "a-success");
    await release(request, "a-error");
    expect(await outcome(t1, "a-success")).toEqual(stale);
    expect(await outcome(t1, "a-error")).toEqual(stale);
    expect(await state(t1)).toEqual(current);
    await hold(request, "b-success", "/v1/whoami", b.key);
    await start(t1, "getWhoAmI", "b-success");
    await holding(request, "b-success");
    await t2.evaluate(() => window.harness.session.logout());
    await reached(t1, "reason", "logout");
    const loggedOut = await state(t1);
    await release(request, "b-success");
    expect(await outcome(t1, "b-success")).toEqual(stale);
    expect(await state(t1)).toEqual(loggedOut);
  });

  test("an answer of the first A is refused after A→B→A", async ({ context, request }) => {
    const [a, b] = [await credential(request), await credential(request)];
    const [t1, t2] = [await tab(context, heldOrigin), await tab(context, heldOrigin)];
    await set(t1, a.key);
    await reached(t2, "phase", "active");
    await hold(request, "first-a", "/v1/whoami", a.key);
    await start(t1, "getWhoAmI", "first-a");
    await holding(request, "first-a");
    await set(t2, b.key);
    await reached(t1, "principalId", b.principalId);
    await set(t2, a.key);
    await reached(t1, "principalId", a.principalId);
    const third = await state(t1);
    await release(request, "first-a");
    expect(await outcome(t1, "first-a")).toEqual(stale);
    expect(await state(t1)).toEqual(third);
  });

  test("a late validation never overrides a later change", async ({ context, request }) => {
    const [a, b] = [await credential(request), await credential(request)];
    const [t1, t2] = [await tab(context, heldOrigin), await tab(context, heldOrigin)];
    await hold(request, "validate-a", "/v1/whoami", a.key);
    await set(t1, a.key);
    await holding(request, "validate-a");
    await reached(t2, "phase", "validating");
    expect(await call(t2, "getWhoAmI")).toEqual(stale);
    await set(t2, b.key);
    await reached(t1, "principalId", b.principalId);
    const chosen = await state(t1);
    await release(request, "validate-a");
    expect((await call(t1, "getWhoAmI")).value.principal_id).toBe(b.principalId);
    expect(await state(t1)).toEqual(chosen);
    await hold(request, "validate-b", "/v1/whoami", b.key);
    await set(t1, b.key);
    await holding(request, "validate-b");
    await t2.evaluate(() => window.harness.session.logout());
    await reached(t1, "reason", "logout");
    const { token } = await state(t1);
    await release(request, "validate-b");
    await set(t2, a.key);
    await reached(t1, "principalId", a.principalId);
    const afterLogout = await t1.evaluate(
      (old) => window.harness.states.slice(window.harness.states.findIndex((s) => s.token === old)),
      token,
    );
    expect(afterLogout.map((s) => s.principalId)).not.toContain(b.principalId);
    const counter = Number((await state(t1)).token.split(":")[1]);
    await Promise.all([set(t1, b.key), set(t2, a.key)]);
    const latest = expect.stringMatching(`:${counter + 2}$`);
    const last = expect.objectContaining({ phase: "active", token: latest });
    await expect.poll(async () => [await state(t1), await state(t2)]).toEqual([last, last]);
    expect(await state(t2)).toEqual(await state(t1));
  });

  test("a late 401 of an earlier generation leaves the current session alone", async ({
    context,
    request,
  }) => {
    const [a, b] = [await credential(request), await credential(request)];
    const [t1, t2] = [await tab(context, heldOrigin), await tab(context, heldOrigin)];
    await set(t1, a.key);
    await reached(t2, "phase", "active");
    await admin(request, "DELETE", `/v1/credentials/${a.id}`);
    await hold(request, "revoked-a", "/v1/whoami", a.key);
    await start(t1, "getWhoAmI", "revoked-a");
    await holding(request, "revoked-a");
    await set(t2, b.key);
    await reached(t1, "principalId", b.principalId);
    const current = await state(t1);
    await release(request, "revoked-a");
    expect(await outcome(t1, "revoked-a")).toEqual(stale);
    expect(await state(t1)).toEqual(current);
  });

  test("a cut answer is a network failure; an unanswered validation waits for retry", async ({
    context,
    request,
  }) => {
    const [a, b] = [await credential(request), await credential(request)];
    const [t1, t2] = [await tab(context, heldOrigin), await tab(context, heldOrigin)];
    await set(t1, b.key);
    await reached(t2, "phase", "active");
    const current = await state(t1);
    await hold(request, "cut", "/v1/whoami", b.key);
    await start(t1, "getWhoAmI", "cut");
    await holding(request, "cut");
    await release(request, "cut", true);
    expect(await outcome(t1, "cut")).toEqual({ kind: "network", status: null });
    expect(await state(t1)).toEqual(current);
    await hold(request, "validate-cut", "/v1/whoami", a.key);
    await set(t1, a.key);
    await holding(request, "validate-cut");
    await release(request, "validate-cut", true);
    await reached(t2, "reason", "unreachable");
    expect(await state(t2)).toMatchObject({ phase: "validating", principalId: null });
    await t2.evaluate(() => window.harness.session.retry());
    await reached(t1, "principalId", a.principalId);
  });
});
