# Incident run contract: consumer guide

The Incident Runs API is a **static contract and mock corpus**, not an implemented
HTTP service. Consumers may use the OpenAPI document and JSON examples to build or
test clients now; [#26](https://github.com/creep1ng/sre-agent/issues/26) owns the incident
workflow runtime and [#146](https://github.com/creep1ng/sre-agent/issues/146) owns durable
persistence and grant seeding.

## Quick path

1. Start or resume with `POST /v1/incidents/{incident_id}/runs` and an
   `Idempotency-Key`.
2. Poll the safe state and cursor-paginated events; use the separate context endpoint
   only when the caller holds `run.read_context`.
3. Send a human command only with the action selected by
   `agent/api/authorization.v1.yaml`'s `command_action_map`.

The OpenAPI response examples reference `agent/api/examples/http/`. Each JSON file
contains an OpenAPI `value` plus `x-http-mock.request` and `x-http-mock.response`, so
it is usable as a static client mock without a server.

## Decision semantics

| Situation | Contract rule |
| --- | --- |
| Command authorization | `approve_mitigation` and `reject_mitigation` resolve to `run.approve`; every other catalog command resolves to `run.command`. The authenticated principal and exact active grant are authoritative. |
| Claimed actor | `actor_reference` records attribution only. A claimed principal that differs from the authenticated identity is rejected; it never grants authority. |
| Disposition | `propose_disposition` requires a non-null `dismiss`, `link`, or `declare` value. Every other command requires `disposition: null` or omission. |
| Audit correlation | A `human_command` or `denial` event requires a concrete actor reference and `request_id`. Internal metadata-only audit retains `request_id`, `incident_id`, and `run_id`; `run_id` is null only before a run exists. There is no public `audit_event_id`. |
| Older generic events | Other event kinds may remain metadata-only (including system events), preserving generic event compatibility. |

## Boundaries

- Keep `turn_id` internal and map it to gateway-facing `task_id` as
  `agent/api/correlation-mapping.v1.yaml` specifies.
- Do not treat the fixtures as runtime evidence, create a router, or add UI behavior.
  Those semantics remain with [#26](https://github.com/creep1ng/sre-agent/issues/26) and
  [#146](https://github.com/creep1ng/sre-agent/issues/146).
- The error body is the frozen local `error-envelope:1.2.0` schema. The contract gate
  validates every external schema URN and every fixture response before publication.
