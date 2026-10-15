# Same-origin browser–API seam

The browser always calls the relative `/api` base path. The web server proxies that path to the
real control-plane API, so local and demo deployments share one security model and no browser URL
or credential is compiled into the application.

## Quick path

1. Set the existing Compose variables from `.env.example` and run the stack.
2. Open `http://127.0.0.1:${WEB_PORT:-8080}`; browser clients resolve the API base from
   `public/api/runtime-config.js` as `/api`.
3. Create one `createMemoryCredentialStore`, set an API key issued by the existing #13 mechanism,
   and pass the store to `createAdministrativeApiClient`.

```js
import {
  createAdministrativeApiClient,
  createMemoryCredentialStore,
} from "/public/api/client.js";

const credentialStore = createMemoryCredentialStore();
credentialStore.set(keyEnteredForThisBrowserSession);
const controlApi = createAdministrativeApiClient({ credentialStore });
const principals = await controlApi.listPrincipals();
```

The store is closure-backed memory only. Reloading the page clears it. Application code MUST NOT
copy bearer credentials into URLs, cookies, Web Storage, fixtures, telemetry, or logs.

## Shared session

[ADR-009](adrs/ADR-009-browser-shared-session.md) moves the key into one `SharedWorker` per origin
and profile, `public/api/session-worker.js`, which also loads `runtime-config.js` (keep that file to
the config assignment). A page hands the key over once and keeps an opaque token that changes with
every generation. Principals uses it; the other pages move to it in the next leaves of #486.

```js
import { connectSharedSession, createAdministrativeApiClient } from "/public/api/client.js";

const session = connectSharedSession();
session.subscribe(({ token, phase, principalId, reason }) => render(token, phase));
session.setCredential(keyEnteredOnce);
const controlApi = createAdministrativeApiClient({ session });
```

- `phase` is `connecting`, `anonymous`, `validating`, `active`, `suspended` or `blocked`. `blocked`
  means the page and the worker speak different protocol versions, or the worker never answers,
  so the site's pages need a reload. A newer page makes an older worker step down, and its key
  goes with it.
- Setting a key, logging out and a 401 of the current generation each create a new token in every
  page, so the caller of that 401 sees `stale_session`. A request whose token is not current is
  refused, and a response that returns under an earlier token rejects with `stale_session`: drop
  it, and check the token before any write.
- The worker forwards only `/v1/` paths of the API base, `GET`, `POST`, `PUT` and `DELETE`, and the
  `Accept`, `Content-Type` and `Idempotency-Key` headers; anything else is `not_allowed`.
- URL parameters only select what to read, such as a deep link or a filter; a mutation always
  needs an action inside the page.
- A page drops everything bound to an earlier token (data, details, dialogs, typed values) as soon
  as the token changes, and offers no protected action until the session is `active`.
- A page entering the back/forward cache or being frozen (`pagehide`, `freeze`) is `suspended` and
  shows nothing protected. On `pageshow` or `resume` it asks the worker again, and shows its content
  once the token is confirmed, after a reset if the token changed.
- When a page connects or becomes visible, the worker checks an active session with `whoami` again
  if its last validation is older than 60 seconds; a 401 ends it in every page as
  `credential_rejected`.
- A validation the API cannot answer stays `validating` with reason `unreachable` until
  `session.retry()`.
- A page whose ping gets no answer within three seconds treats the worker as lost and connects
  again; if the worker was gone, the new one starts anonymous, with no fallback to an earlier key.

`tests/browser/shared-session.spec.js` exercises these rules in the packaged browser lane; its races
run through `web-held`, in front of `tests/browser/support/hold-upstream.mjs`, which holds answers.
`page.route` never sees a SharedWorker's requests, so specs that cut or fake API responses, or delay
them within one page, use `tests/browser/support/session-routes.mjs`: it intercepts `/api/v1/`
requests for the whole browser through CDP, for the worker and for pages alike.

## Topology

```mermaid
flowchart LR
    B[Browser] -->|same origin: /api/v1/*| W[Web reverse proxy]
    W -->|private runtime network: /v1/*| A[FastAPI control plane]
    A --> D[(PostgreSQL)]
```

| Environment | Browser base | Proxy upstream | Configuration |
|---|---|---|---|
| Local Compose | `/api` | `api:8000` | `API_UPSTREAM` image default |
| Demo | `/api` | deployment-private API address | override `API_UPSTREAM` |
| Consumer test | `/api` | `127.0.0.1:4174` | `BROWSER_API_UPSTREAM` |

`API_UPSTREAM` is expanded by the official Nginx entrypoint from
`docker/nginx.conf.template`. Keep it private; browsers never receive that address. A deployment may
replace `runtime-config.js`, but `apiBaseUrl` deliberately accepts only a same-origin absolute path.

## CORS and CSRF posture

This topology does not enable CORS. The proxy removes upstream CORS response headers and rejects
requests marked `Sec-Fetch-Site: cross-site`. Its Content Security Policy limits `connect-src` to
the same origin and forbids framing with `frame-ancestors 'none'`.

CSRF does not rely on a token because authentication has no ambient browser credential: the client
uses an explicit in-memory `Authorization: Bearer` header, sends `credentials: "omit"`, and the
proxy removes `Cookie` before forwarding. These controls MUST remain together; enabling cookies or
cross-origin API access requires a new threat-model decision.

## Error contract

`ApiClientError` exposes safe fields only: `kind`, `status`, `code`, `requestId`, and `retryable`.

| Condition | `kind` | Status |
|---|---|---|
| Missing, invalid, expired, or revoked credential | `authentication` | 401 |
| Authenticated but unauthorized principal | `authorization` | 403 |
| Hidden or absent resource | `not_found` | 404 |
| Concurrency or idempotency conflict | `conflict` | 409 |
| Fetch cannot obtain a response | `network` | none |
| The session changed, or is not active, before the response could apply | `stale_session` | none |
| The shared session refused the path, method or headers | `not_allowed` | none |

The adapter never returns an error response as successful data, so callers cannot show a false
confirmation after 409. Other HTTP failures use `api` and retain the server error code when safe.

## Real consumer test

The test is destructive by design and refuses to run unless the test and demo database identities
differ. It migrates and seeds the isolated database, runs the real eight-route FastAPI control
plane, and reaches it from Chromium through the same-origin proxy. It has no fixture fallback.

```sh
BROWSER_API_TEST_DATABASE_URL=postgresql://user@127.0.0.1:55432/browser_api_test \
DEMO_DATABASE_URL=postgresql://user@127.0.0.1:5432/sre_agent \
npm run test:browser-api
```

The runner generates disposable credentials without printing them. Traces and screenshots are off
for this suite so bearer values are not persisted as test artifacts. The assertions cover valid,
missing, invalid, and revoked authentication; 403 without mutation; 404; 409 without false state;
cross-site rejection; absent CORS allowance; network failure; and empty Web Storage.
