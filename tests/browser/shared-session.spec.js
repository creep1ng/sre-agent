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
async function tab(context) {
  const page = await context.newPage();
  await page.goto("/index.html");
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
    own.port.postMessage({ type: "hello" });
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
