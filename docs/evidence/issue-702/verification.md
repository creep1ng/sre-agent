# Issue #702 — live inbox evidence

- **Code under test**: `feat/702-live-shell-evidence` @ `60c6c0d01b8afcdae24200c862ddf51040d54284`
- **Date**: 2026-10-23
- **Environment**: Windows 11 + Docker Desktop 29.2.1, Docker Compose v5.0.2, Python 3.13.14.
  Setup projects `sre-702x` (API proof) and `sre-702z` (browser run), OpenTelemetry Demo
  `3.0.0` (`1755859a9de82c2e5e225be68abc401a5ebf2b4f`), `SRE_OTEL_MODE=local`.
- **Browser**: Playwright Chromium 1.63.0 in the `incident-console-e2e` container, 1440x920.

## Expected / actual

| Check | Expected | Actual |
| --- | --- | --- |
| Real alert reaches the inbox | `checkout` / `SEV1` card appears from `GET /v1/alerts` | Card visible; `alt-checkout-f350c6d98254` |
| Local time | `observed_at` rendered in local time | `hoy 00:52` (UTC-5); API `05:52Z` |
| Triage state | `new` rendered as `Nueva` | `Nueva` badge present |
| Polling | 15 s cadence, stable `alert_id` | 6 polls; first empty 05:51:30Z, first alert 05:52:45Z |
| Service filter | Single service still shows the filter | `Todos los servicios 1`; checkout filter works |
| Credential | Session shown only while connected | `Sesión de API / Conectada`; no credential in URL/storage |

Real browser run: **1 passed (1.3 min)**, browser open before injection. The failure was injected
**5.2 s after the session started**; the first alert became visible **72.2 s after injection**.
That misses the issue's <60 s criterion: detection is server-side (the fixed 2-minute rule and
OTel span-metric export), not the inbox. The UI polled every ~15 s and rendered the alert on the
first poll that contained it.

## Artifacts

`inbox-live.png` shows the real UI (header, live count, filter, `SEV1 · Crítica`, `checkout`,
`Nueva`, local time, title and summary); `poll-log.json` is an excerpt with the first empty poll
and the first alert; `verification.json` holds the run summary.

## Reproduction

Native Linux/macOS:

```sh
cp .env.example .env                 # fill DEMO_HUMAN_API_KEY and related values
python3 scripts/demo_env.py up
python3 scripts/setup_sre.py
python3 scripts/demo_env.py fail
LIVE_INBOX=1 docker compose --profile e2e run --build --rm \
  incident-console-e2e npx playwright test live-real
```

On this Windows host setup ran in a disposable container with the Docker socket and checkout
mounted at its VM path. The passing e2e run used the full setup compose set (`compose.yaml`,
`compose.mcp.yaml`, generated overlay); omitting the MCP overlay recreated the API without wiring.

## Direct API proof (same candidate, separate setup stack)

```text
GET /v1/alerts (no Authorization)
401 Unauthorized
WWW-Authenticate: Bearer
{"error":{"code":"authentication_failed","message":"Authentication failed."},"retryable":false}
GET /v1/alerts (valid seeded credential without alert.read)
403 Forbidden
{"error":{"code":"not_authorized","message":"Not authorized."},"retryable":false}
GET /v1/alerts (DEMO_HUMAN_API_KEY)
200 OK
{"evaluated_at":"2026-10-23T05:38:07Z",
 "rules":[{"rule_id":"checkout-payment-error-rate","state":"no_data","value":null}],
 "alerts":[{"alert_id":"alt-checkout-64e53f9a655a","service":"checkout","severity":"sev1",
            "status":"new","observed_at":"2026-10-23T05:37:17Z","triage_status":"new",
            "incident_id":null}]}
```

The excerpt shows the transition from an empty poll to one stable alert ID.

## Deterministic suite

```sh
LIVE_INBOX=0 docker compose --profile e2e run --build --rm \
  incident-console-e2e npx playwright test --reporter=line
```

Result: **19 passed, 1 skipped** (`live-real` is opt-in), 3.8 min. The eight `live-inbox` tests
cover no-credential, 401, 403, transient 503 + recovery, 15 s polling with stable ID, render/triage
counts, single-service filter, and empty payload.

## Sanitization

No API key, Authorization header, cookie, Web Storage value, request body or credential-bearing
URL is present in the artifacts. The poll log stores only timestamps, status codes, counts and
alert IDs. The screenshot shows the connected session label, not the credential.
