// The shared session's SharedWorker sends the API requests (ADR-009), and Playwright's page.route
// never sees a SharedWorker. This fixture turns on request interception for the whole browser
// through CDP before any worker starts, so a spec can still cut or fake API responses, or delay
// them within one page, for the worker and for pages alike.
import { test as base } from "@playwright/test";

export { expect } from "@playwright/test";

const routes = new WeakMap();
// A subset of Playwright globs (no {a,b} or escapes): ** crosses "/", * does not, the rest is literal.
const glob = (pattern) =>
  new RegExp(`^${pattern.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*\*?/g, (s) => (s === "*" ? "[^/]*" : ".*"))}$`);
const matches = (matcher, url) => (typeof matcher === "function" ? matcher(new URL(url)) : glob(matcher).test(url));

// The last route added wins, as with page.route.
export const route = (page, matcher, handler) => routes.get(page.context()).unshift({ matcher, handler });
export function unroute(page, matcher) {
  const list = routes.get(page.context());
  list.splice(0, list.length, ...list.filter((entry) => entry.matcher !== matcher));
}

function routed({ requestId, request }, cdp) {
  // A request that already went away (its page closed) needs no answer.
  const reply = (method, params = {}) => cdp.send(method, { requestId, ...params }).catch(() => {});
  const headers = Object.fromEntries(Object.entries(request.headers).map(([name, value]) => [name.toLowerCase(), value]));
  return {
    request: () => ({
      url: () => request.url,
      method: () => request.method,
      headerValue: async (name) => headers[name.toLowerCase()] ?? null,
    }),
    continue: () => reply("Fetch.continueRequest"),
    abort: () => reply("Fetch.failRequest", { errorReason: "Failed" }),
    fulfill: ({ status = 200, contentType, headers: extra = {}, body = "" }) =>
      reply("Fetch.fulfillRequest", {
        responseCode: status,
        responseHeaders: Object.entries({ ...extra, ...(contentType && { "content-type": contentType }) }).map(
          ([name, value]) => ({ name, value: String(value) }),
        ),
        body: Buffer.from(body).toString("base64"),
      }),
  };
}

export const test = base.extend({
  sessionRoutes: [
    async ({ browser, context }, use) => {
      const list = [];
      const failures = [];
      routes.set(context, list);
      const cdp = await browser.newBrowserCDPSession();
      cdp.on("Fetch.requestPaused", (paused) => {
        const answer = routed(paused, cdp);
        const entry = list.find(({ matcher }) => matches(matcher, paused.request.url));
        Promise.resolve(entry ? entry.handler(answer) : answer.continue()).catch((error) => failures.push(error));
      });
      // On the browser rather than on a worker, so it is in place whenever a worker starts.
      await cdp.send("Fetch.enable", { patterns: [{ urlPattern: "*/api/v1/*" }] });
      await use(list);
      await cdp.detach();
      if (failures.length > 0) throw failures[0];
    },
    { auto: true },
  ],
});
