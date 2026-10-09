# Issue #454 — Historical request attribution design

**Status:** implementation decision recorded before production edits; independent
human review remains pending. No source, schema, or published API change is
implied. This design records the backend/consumer
boundary approved in [#454 comment 6073849454](https://github.com/creep1ng/sre-agent/issues/454#issuecomment-6073849454)
and [#143 comment 6073854153](https://github.com/creep1ng/sre-agent/issues/143#issuecomment-6073854153).
The eventual additive API is a new **2.8.0** contract; published releases stay immutable.

## Decision

Keep AuditEvent as the existing metadata-only, HMAC-protected append-only
evidence projection. Add a distinct immutable per-request attribution snapshot
and expose it only through an authorized, bounded GET /v1/usage/requests
projection. Do not add raw attribution to AuditEvent, change its HMAC domains,
or infer historical routing by looking up today's alias.

The snapshot records the exact alias assignment loaded for the request at the
provider-invocation boundary: requested alias, requested concrete model,
requested provider, and router. Store credited model/provider separately and
only when the provider adapter returns explicit, validated evidence. An
unverified or missing value is explicitly unavailable, not copied from the
request fields. The OpenRouter adapter currently validates selected endpoint
metadata (and checks canonical-model changes against its endpoint catalog), but
its ProviderResult presently returns request.model and request.provider;
it therefore loses verified canonical selected-model evidence today. Preserve
and pass that evidence through a future adapter change before claiming distinct
credit. (See gateway/openrouter.py and gateway/providers.py.)

## Capture and acceptance semantics

| Request path | Attribution snapshot | Response audit |
| --- | --- | --- |
| Rejected before provider invocation (validation, authentication/authorization denial, missing assignment, admission denial, invalid routed request) | No snapshot; no provider invocation occurred | Existing audit behavior remains |
| Provider invocation reached and succeeds | Snapshot the exact loaded request assignment; record credited model/provider only from validated adapter evidence; otherwise explicit unavailable | Persist snapshot and associated response AuditEvent together |
| Provider invocation reached and fails/times out | Snapshot the exact loaded request assignment; credited model/provider unavailable unless explicit validated evidence exists | Persist snapshot and associated failure AuditEvent together |
| Historical/legacy response with no snapshot | No attribution; report unavailable/legacy, never reconstruct it | Existing audit/consumption evidence remains readable |

Capture the immutable request-side values from the already-resolved assignment
passed into ProviderRequest, before calling the provider; never re-resolve
the alias after that point. One request UUID identifies at most one snapshot.
The separate snapshot and associated responses.create AuditEvent must be
inserted in one transaction on the existing PostgreSQL audit path. If either
insert or commit fails, neither is accepted and the API fails closed with the
existing sanitized audit-unavailable response (no successful output is released).
Provider calls and quota admission/settlement are external/separate effects and
are not rolled back by this transaction; this is an acknowledged boundary, not a
claim of distributed atomicity.

The current PostgresAuditStore.append opens its own transaction, while
AuditRepository.append can append using a caller's session
(responses.py:172-180, repositories.py:1065-1090). Implementation must
add the snapshot and event through one caller-owned session/transaction in that
existing path; do not write the snapshot in an earlier independent transaction.
Preserve the existing settlement policy: only complete exact consumption settles
(responses.py:324-336).

## Bounded read contract (future 2.8.0)

/v1/usage/requests is a new closed response filter/projection, not an extension
of the published aggregate response. Require the same governed
administrative_control/usage admin.read grant and exactly one existing
selector: request_id, incident_id, or UTC month. Reuse the current usage
projection's evidence selection, canonical request de-duplication,
1,000-row fail-rather-than-truncate bound, and conflict/coverage rules
(gateway/usage.py:176-407, 518-555). Factor shared authoritative selection
and per-request reconciliation rather than copying query/accounting logic.
Do not add pagination, free-form filters, body/content, HMAC values, or
unbounded identifiers.

Each unique request item should have:
- request_id and the existing canonical UTC month;
- requested assignment (alias, model, provider, router) with
  explicit available|unavailable state;
- credited model and provider, each explicitly available only from
  verified provider evidence; otherwise unavailable (including legacy);
- attribution_status: available|partial|unavailable|legacy;
- per-request consumption and its availability, selected/reconciled by the
  existing usage evidence rules (do not recompute or invent token/cost values);
- navigation.status=unsupported and no destination URL for incident/run
  navigation in this release.

Use strict closed schemas and sanitized fail-closed errors; authorize before
revealing whether a selector matches. The request list must not return prompt,
input/output, provider payload, credentials, or HMAC digests. Read attempts
must not create attribution or consumption evidence. Preserve the existing
/v1/usage/consumption aggregate behavior.

## Navigation decision

Current admin audit evidence carries opaque HMAC incident/run/task references,
and the existing UI intentionally renders those as inert text rather than
turning them into links; the observed request-ID “View correlated events”
navigation points to a fixed same-origin audit destination and does not decode
references. See [issue-25 correlation navigation evidence](../evidence/issue-25-correlation-link.md)
and gateway/audit_reads.py. Existing incident/run API routes
(gateway/incidents.py:383-412) do not establish a usage-attribution link
contract. Therefore this 2.8.0 projection explicitly reports incident/run
navigation unsupported. Do not synthesize links from HMACs, expose digests, or
claim navigation that the consumer contract has not admitted. Revisit only with
a separately approved consumer contract.

## Evidence and implementation gates

Relevant current implementation: gateway/responses.py:210-324 resolves an
assignment and performs the provider call before appending the event;
gateway/audit.py projects routing/model alias references as HMACs;
governance/dto.py:445-475 defines consumption availability;
persistence/models.py stores AuditEvent rows; persistence/repositories.py
provides the append boundary. ADR-005 requires source-derived identity,
resource, alias/model/provider/correlation IDs to remain HMAC references and
keeps content out of audit evidence
([ADR-005](../../schemas/adrs/ADR-005-audit-redaction.md)). The new snapshot is
a separate, authorized usage artifact, not an exception that alters ADR-005.

Before production edits, resolve effective TDD mode and exact runner from
project/session configuration; it remains unresolved in
odd/tasks/issue-454-historical-attribution.md. Then pre-author real HTTP /
PostgreSQL scenarios for alias reassignment, canonical OpenRouter evidence,
provider failure, pre-invocation denial, legacy rows, selector bounds,
authorization, sanitized failures, and transaction rollback. This document is
design only: it does not claim a 2.8.0 schema, route, migration, demonstration,
published PR, CI result, or human acceptance exists.
