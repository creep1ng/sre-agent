# ADR-005: Stage-aware audit and fail-closed redaction

- **Status:** Accepted
- **Contract version:** 1.0.0

## Context

Gateway outcomes need portable evidence without fabricating authority before authentication or exposing free-form content and secrets to logs, telemetry, persistence, or exporters.

## Decision

`AuditEvent` is a vendor-neutral, stage-aware, append-only closed evidence projection, not a reuse boundary for canonical objects or raw strings. Event/time, request UUID, closed stage/outcome/operation/action/reason/redaction vocabularies, status, and retryability remain direct; every source-derived identity, credential, resource ID, model alias/concrete model, policy/grant, provider, correlation, or untrusted identifier becomes `{"algorithm":"hmac-sha-256","key_version":1,"digest":"<64 lowercase hex>"}`. Producers compute `HMAC-SHA-256(secret audit key, UTF8("sre-audit-v1\0<domain>\0<exact canonical source value>"))`; producer vectors own exact bytes/domain separation, key versions, rotation, and custody, while Draft 2020-12 proves only the closed envelope. Display names and unrelated identity timestamps are omitted; resource type and router `openrouter` remain closed canonical vocabulary, and resolved 401 evidence may use the safe partial local identity projection.

Every free-content class passes through structural removal, known-secret matching, configured pattern detection, and scanning before any sink. Raw or arbitrary text has no sink-eligible representation. Successful pre-sink redaction permits only the closed `fully_redacted` structural marker plus safe metadata. Error or uncertainty is fail-closed: raw and partial content are discarded, the state becomes `redaction_failed`, and only safe category/count metadata remains.

The authoritative AuditStore must provide durable acceptance before an ordinary success, deny, contract error, or normalized upstream error is released. Rejection or unavailability suppresses that result and produces safe retryable 503 `audit_unavailable`; no raw fallback or false persistence claim is permitted. Accepted events cannot be updated or deleted. Corrections use a disjoint `cor_` event identity and link to a prior ordinary UUID event, making self-links structurally impossible. Downstream exporters consume only accepted events and cannot change an already released response.

Git owns contracts and evidence, databases own runtime records including AuditEvents, and secret stores or environment configuration own provider and deployment secrets. Lower-authority stores cannot redefine or receive content outside their matrix row.

## Consequences

Audit availability becomes a release dependency, redaction failures preserve evidence without preserving content, and provider-native objects, raw keys, Authorization values, and upstream secrets cannot serialize. The contract intentionally does not prescribe storage tables, an outbox, runtime adapters, or product sinks.

## Alternatives

Post-sink filtering, best-effort authoritative audit, mutable events, provider-native telemetry objects, and treating downstream exporters as the system of record were rejected because each permits leakage, evidence loss, or authority drift.

## Deferred

Retention, expiration, content-read authorization, product sink selection, database design, exporters, operational retry policy, and runtime redactor implementation are deferred.

## Supersedes

None.

## Links

- `openspec/changes/issue-9-gateway-boundary-contracts-and-adrs/specs/audit-redaction-contract/spec.md`
- `openspec/changes/issue-9-gateway-boundary-contracts-and-adrs/specs/contract-governance-conformance/spec.md`
- `schemas/releases/1.0.0/json-schema/domain/audit-event.schema.json`
- `schemas/releases/1.0.0/conformance/ownership-matrix.yaml`
