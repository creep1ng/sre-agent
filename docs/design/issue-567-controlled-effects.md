# Issue #567: controlled external-effect verification

## Boundary and route

Direct, evidence-first work against main
`763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9`, including #580. No production
change is justified yet. #567 is Todo in Projects #8, outside Sprint 5; this
exercise does not change planning or close the original CA6.

Use the existing Compose python-checks and python-checks-db services. The real
application, HTTP run routes, investigator, durable intent/outcome transactions,
authentication, idempotency and PostgreSQL locks remain unchanged. A separate
process serves a **controlled external gateway**, not a live provider. Discovery
returns no tools; the model action is a deterministic synthetic conclusion. This
deliberately does not demonstrate Grafana, OpenRouter or mitigation execution.

The controlled gateway receives the real investigator HTTP request, records only
its synthetic incident/run/task IDs and its own request UUID, and increments a
durable SQLite counter. This counter mutation is the external effect under test;
the receiver commits it independently of the runtime. Only the receiver writes
its store. GET /observations queries both operation records and the actual counter.
A local dispatch receipt or a received-request record alone is not effect proof.
The counter deliberately has **no deduplication**: a repeated dispatch increments
it again, making accidental retries observable rather than masking them.

## Acceptance and failure modes (before implementation)

| Scenario | Receiver evidence | Expected durable runtime outcome |
| --- | --- | --- |
| Applied, acknowledged | One sent operation, counter 1, correlated UUID | success |
| Sent request explicitly rejected | Operation rejected with 403, counter 0, correlated UUID | confirmed_failure / governed_call_denied |
| Harness not configured | No discovery or operation, counter 0 | confirmed_failure / harness_not_configured; pre-dispatch only |
| 5xx after applying | Counter 1 despite 503 | unknown, no transient retry |
| Response lost after applying | Counter 1 despite transport failure | unknown, no transient retry |
| Timeout before applying | Initially counter 0; receiver later applies once | unknown remains unknown |
| Kill before producer dispatch | Discovery held after durable intent; no operation | pending, then unknown on exact replay |
| Kill after dispatch before effect | Operation received; delayed counter changes 0 to 1 | unknown remains unknown |
| Kill after effect before response | Counter 1; response held | pending, then unknown on exact replay |
| Kill after response before outcome commit | Counter 1; real PostgreSQL insertion blocked | pending, then unknown on exact replay; no partial result |
| Concurrent exact start | One operation held; other requests replay the active run | pending remains pending; one eventual success |

Kill only the owned application child process with SIGKILL, preserve the receiver
and database, then start a new application process. For the persistence window,
hold a PostgreSQL table lock after the external effect, release the HTTP response,
observe the application's INSERT waiting for that lock, and kill before commit.
Do not patch the runtime, fabricate an intent or change production timeouts.
The timeout scenario uses a shorter GatewaySettings timeout only in its fixture.

Failure modes: lost/unmatched correlation, received-but-not-applied conflation,
5xx/timeout incorrectly proving no effect, duplicate dispatch during active replay,
read recovery restarting a producer, partial outcome transactions, and late effects
overwriting terminal unknown. E2E assertions compare HTTP responses, actual receiver
SQL state and real runtime SQL receipts/counts, not implementation text.

## Recovery and guarantee limits

GET and resume_from_run_id recover persisted state without executing the producer
or changing pending to terminal. After a crash, exact start replay detects the
orphaned intent and records unknown, never redispatching. Terminal receipts are
immutable. Receiver knowledge is deliberately not fed back to the runtime.
No external exactly-once, cross-system atomicity, cancellation of sent requests,
reconciliation mechanism, paid-provider integration or production safety is claimed.
An explicit controlled 403 proves this receiver rejected that sent operation; it
does not prove how another provider handles failures after its own dispatch.

## Environment and delivery

Synthetic identities reuse the existing E2E seed constants; no new external
credential is provisioned. Local-only internal subnet override handles this host's
exhausted Docker pools without touching existing networks. No production access.
Export sanitized JSON and receiver SQLite stores through a dedicated output mount;
never export headers, input prompts, model text, .env or raw application logs.
Keep source work and evidence/documentation in cohesive local delivery units of
at most 400 added-plus-deleted lines each. No remote publication is authorized.
Human acceptance is pending even if all automated checks pass.
