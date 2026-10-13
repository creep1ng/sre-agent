# ADR-009: Shared in-memory browser session coordinated by a SharedWorker

- **Status:** Accepted for the MVP by the maintainer on 2026-10-12, in
  [#486](https://github.com/creep1ng/sre-agent/issues/486#issuecomment-6128807717), with the
  continuity limit of section 9 as an explicit cut of CA1.
- **Issue:** [#486](https://github.com/creep1ng/sre-agent/issues/486) (HT-WEB-SHARED-SESSION),
  first of four leaves.
- **Location:** `docs/adrs/`, not `schemas/adrs/`. This decision evolves the browser–API seam
  of #148; it does not change a frozen gateway contract.
- **Evidence base:** the facts in *Context* were read on `main` at `23e1a42`.

## Context

The browser–API seam of #148 ([`docs/browser-api-seam.md`](../browser-api-seam.md)) keeps
one credential per page:

- [`public/api/client.js`](../../public/api/client.js) stores the key in a module-level
  `WeakMap` through `createMemoryCredentialStore()`. `createAdministrativeApiClient` accepts
  only such a store and sends each request to the same-origin `/api` base with
  `Authorization: Bearer`, `cache: "no-store"`, `credentials: "omit"`, `redirect: "error"`
  and `referrerPolicy: "same-origin"`.
- The seam forbids copying credentials into URLs, cookies, Web Storage, fixtures, telemetry
  or logs. Its CSRF defense is the absence of an ambient credential: enabling cookies or
  cross-origin API access "requires a new threat-model decision". The only Web Storage use
  today is the theme preference of the alerts and war room pages.
  [`tests/browser/api-seam.spec.js`](../../tests/browser/api-seam.spec.js) inspects Web
  Storage on one page, but its assertion fails only when every test key is stored, so it does
  not yet prove that no key is.
- [`docker/nginx.conf.template`](../../docker/nginx.conf.template) rejects
  `Sec-Fetch-Site: cross-site` on `/api/`, clears `Cookie` and `Origin` before proxying and
  hides the upstream `Access-Control-Allow-Origin` and `Access-Control-Allow-Credentials`
  headers. Static pages, not `/api/`, carry
  `Content-Security-Policy: default-src 'self'; connect-src 'self'; object-src 'none'`.
  Nothing forbids framing: there is no `frame-ancestors` and no `X-Frame-Options`.
- Nine pages create their own store and their own stale-response counter: `principals`,
  `grants`, `model-aliases`, `consumption`, `audit-events` and `triage` under
  `public/admin/`, and `war-room`, `review` and `postmortem` under `public/incident-ui/`.
  Each one asks for the key again, a reload loses it, and a change or logout in one tab never
  reaches the others. Each counter, such as `sessionGeneration` in the admin pages, protects
  only its own page.
- #419 publishes `GET /v1/whoami`
  ([`identity.py`](../../src/sre_agent/gateway/identity.py), `getWhoAmI()` in the client):
  only `principal_id`, `Cache-Control: no-store`, and one 401 for missing, invalid, revoked,
  expired or inactive credentials. No endpoint returns the effective capabilities of the
  caller: `GET /v1/grants` requires `admin.read`
  ([`scopes.py`](../../src/sre_agent/control/scopes.py)).

#486 asks for one session per origin and browser profile, shared by every tab, where
changing the credential or logging out applies everywhere, and where late responses,
suspended tabs and concurrent changes cannot leak the previous context (CA1–CA8). The
[DoR proposal](https://github.com/creep1ng/sre-agent/issues/486#issuecomment-6048574159)
was confirmed for capabilities, continuity and mechanism in the
[first DoR answer](https://github.com/creep1ng/sre-agent/issues/486#issuecomment-6089798985);
the maintainer accepts or amends this record in its pull request. It fixes the rules that
the implementation and its tests follow.

## Decision

### 1. One authority per origin and profile

A `SharedWorker`, served from `public/api/` by the same proxy, is the only holder of the
credential and of the session state: a random instance identifier, a generation counter, a
phase (`anonymous`, `validating` or `active`) and the `principal_id` returned by `whoami`.
Every page that uses the API connects to it, and no page creates its own credential store.
The worker URL and name are fixed, and each connection starts with a protocol version: a
page that meets another version stays blocked and asks for a reload, so a deploy never
leaves two authorities.

### 2. The key does not return to pages

A page passes the key to the worker once, when the person enters it, and discards it. From
then on the worker sends the API requests with the options the seam already uses and returns
status, headers and body to the page that asked. Pages hold only an opaque generation token;
there is no getter for the key, and no worker message, error or log carries it. The worker
accepts only paths under `/api/v1/`, a fixed set of methods and a small header allow-list
such as `Content-Type` and `Idempotency-Key`; it rejects absolute URLs and any
`Authorization` header sent by a page. It holds only the human credential the person
entered: agent, provider and MCP credentials never reach the browser.

### 3. Generations

The token is the worker instance identifier plus the counter, so a page never confuses a
generation of a restarted worker with the current one. Every accepted change creates a
generation: setting a credential, discarding it, and invalidating it after a 401. A→B, A→A2
(another key of the same principal) and A→B→A are distinct generations; comparing
`principal_id` or the key is never enough.

### 4. Ordering and concurrency

The worker applies commands in the order it receives them, and the last one wins. A
credential change first publishes its new generation in phase `validating`, so every page
drops the previous context at once, and only then calls `whoami`. A validation result
applies only if its generation is still current: one that returns after a later change or
logout is discarded and never restores an earlier context. Only a 200 makes the generation
`active`. A 401 ends it in `anonymous` with reason `invalid_credential`; a network failure
or a 5xx leaves it `validating` with a retry offered. Neither falls back to the previous key.

### 5. Requests carry their generation

Each request travels with the token of the page that sends it. The worker refuses it without
calling the API when the token is not current or the phase is not `active`. Every response
returns with the token it was sent under, and the page applies a success, an error, a
`finally`, a retry or an optimistic update only while its own token is still current.
`AbortController` saves work but is not the guarantee. There are no streams: run events use
polling ([ADR-008](ADR-008-run-events-transport.md)), and each poll is a request under this
rule.

### 6. Errors and revocation

| Signal | Effect |
|---|---|
| 401 on a request of the current generation | Session invalidated in every page: new generation, `anonymous`, reason `credential_rejected` |
| 401 on a request of an earlier generation | Ignored |
| 403 | "Not authorized" for that operation only; the session stays |
| Network failure | Shown as disconnected; the session stays |

The worker revalidates with `whoami` when a page connects and when a page becomes visible
again, if the last validation is older than 60 seconds. Revocation is therefore detected at
the next request or revalidation, never instantaneously.

### 7. Page lifecycle

A new, reloaded or restored page shows no protected data and allows no action until the
worker confirms the current token. Before entering the back/forward cache or being frozen
(`pagehide`, `freeze`), a page hides its protected content, so a restore paints nothing
stale while it asks. If the token changed, the page drops its previous context and loads
again. A page that gets no answer to a ping within a short timeout treats the worker as lost
and connects again; a new instance starts `anonymous`, so the key is asked again and an
earlier key is never reused.

### 8. Logout

Discarding the credential creates a new `anonymous` generation. It is a local discard, not
a revocation of the key on the server; it does not undo or resend a mutation the API already
accepted, and the late response of that mutation is ignored. A later authorized read shows
the durable state.

### 9. Continuity limit

The session lives while at least one page connected to the worker is open, because that is
the lifetime of a `SharedWorker`. Opening another tab or reloading one of several keeps it.
Closing every page or restarting the browser ends it. A browser may keep the worker alive
briefly while the only page reloads, but nothing guarantees it, so the tests treat that case
as ending the session. This is the continuity limit accepted for the MVP in the DoR answer:
it narrows CA1 for a reload of the only page.

### 10. Capabilities

The API decides. The session computes no permissions: each surface requests its data and
renders a 403 per operation. Because a credential change drops every generation-bound state
and loads again, a credential with fewer grants loses what it cannot read without any
capability endpoint.

### 11. Consumer cleanup contract

Each surface subscribes to generation changes. On a change it drops its data, form values,
selections, caches, timers and pending indicators bound to the previous generation before
rendering again. The worker does not know page fields; each surface proves its own cleanup
with a test.

### 12. Seam posture

No cookies, no Web Storage or IndexedDB for credentials and no CORS: the controls of #148
stay together. The page CSP already allows the worker, because `worker-src` falls back
through `child-src` and `script-src` to `default-src 'self'`, and the proxy serves the
worker script with the same policy, so its requests to `/api` stay within
`connect-src 'self'`. A session shared across pages makes framing and links riskier, so the
CSP gains `frame-ancestors 'none'`, and URL parameters only select what to read, such as a
deep link or a filter: a mutation always needs an action inside the page. The seam document,
its tests, the proxy and the browser boundary of
[`docs/security/threat-model.md`](../security/threat-model.md) change in the leaf that
introduces the worker, and the Web Storage assertion then fails on any single stored key.

## Consequences

- A key is entered once per browser session, and a change or logout reaches every page.
- The key leaves page scripts. A script injected into a page cannot read the stored key, but
  while its page is open it can send requests through the worker, capture the next key typed,
  force a logout or replace the session in every page. Output encoding and the CSP remain
  the XSS defense.
- One rule rejects stale responses everywhere instead of nine page-local counters.
- Closing every page, a lost worker or a browser restart asks for the key again, and there
  is no fallback to an earlier key.
- `SharedWorker` exists in current Chromium, Firefox and Safari 16 or later, but the packaged
  browser lane verifies Chromium only
  ([`playwright.production.config.js`](../../playwright.production.config.js)). Other
  browsers are not verified by this project, and mobile browsers are outside this MVP.
- The nine pages move from per-page stores to the shared session over the next leaves.

## Alternatives

- **Per-page stores (current).** Fail CA1–CA3: every tab asks for the key, and a change or
  logout stays local.
- **BroadcastChannel between pages, without a coordinator.** Every page holds the key, no
  single order decides concurrent changes (CA5), and a new tab depends on whichever page
  answers first.
- **Web Storage.** Contradicts #148, writes the credential to disk where any script reads it,
  and session restore can bring it back after the browser closes.
- **Backend session with an `HttpOnly` cookie.** Survives reloads, but turns the credential
  into an ambient one: CSRF must be redesigned, the proxy currently clears `Cookie`, and the
  gateway needs a session store and its revocation. Outside this cut.
- **Service Worker as the holder.** Its lifetime is not tied to open pages: the browser stops
  idle service workers and their memory with them, so it cannot be the authority.

## Delivery and verification

| Leaf | Content | Criteria exercised |
|---|---|---|
| 1 | This record | None; it fixes the rules the next leaves prove |
| 2 | Worker, protocol and client adapter; seam document, threat model, Web Storage assertion and proxy CSP | CA4–CA6: late success, error, retry and 401 of A after A→B, A→logout and A→B→A; simultaneous changes from two tabs; loss of the worker |
| 3 | Principals and war room on the shared session, on the packaged stack | CA1–CA3, CA7, CA8: continuity across tabs and reloads, except a reload of the only tab (section 9); change between two principals and between two keys of one principal; invalid key; global logout with Back/Forward and a suspended tab; secrets inspection; a mutation accepted before logout |
| 4 | Remaining surfaces, triage guards joined to the shared generation, full run on the final SHA | CA2 regression of the triage deep link, and every criterion again on the final SHA |

Identity and authorization are proven over real HTTP, with two principals holding different
grants and a second key of one of them. Races use responses held and released in a fixed
order by the test upstream behind the proxy, not by page-level routing in the browser, and
they are reported as UI concurrency evidence, never as enforcement. Every new browser spec
is added to `playwright.production.config.js`, which lists its specs explicitly.

## Deferred

- A source of effective capabilities; it would extend #419.
- Continuity of a single page across reloads or browser restarts. It needs a change to #148
  (Web Storage or a backend session) with its own threat model.
- The #487 shell, once it exists, consumes this session instead of creating a store.

## Links

- Issue [#486](https://github.com/creep1ng/sre-agent/issues/486), its
  [DoR proposal](https://github.com/creep1ng/sre-agent/issues/486#issuecomment-6048574159)
  and [first answer](https://github.com/creep1ng/sre-agent/issues/486#issuecomment-6089798985)
- Seam of #148: [`docs/browser-api-seam.md`](../browser-api-seam.md)
- Identity of #419: [`identity.py`](../../src/sre_agent/gateway/identity.py)
- Shell: [#487](https://github.com/creep1ng/sre-agent/issues/487)
