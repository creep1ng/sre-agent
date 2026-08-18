## Purpose

Defines append-only audit evidence and fail-closed redaction before any log, audit, telemetry, or persistence sink receives free content.

## ADDED Requirements

### Requirement: Correlated AuditEvent metadata
Every `AuditEvent` SHALL contain event ID/time, server `request_id`, closed operation/action/reason vocabularies, processing `stage`, outcome, redaction status/release-literal policy version, and safe technical correlation when present. `stage` SHALL be one of `validation|authentication|authorization|routing|upstream|response|audit` and SHALL determine which additional dimensions are valid.

AuditEvent SHALL NOT reuse canonical PrincipalContext, Resource, ModelAlias, PolicyDecision, routing strings, or source identifiers. Every source-derived identity, credential, resource, model, policy/grant, routing, correlation, or untrusted identifier SHALL be projected into its closed audit-local evidence field as `{"algorithm":"hmac-sha-256","key_version":1,"digest":"<64 lowercase hex>"}`; untrusted evidence SHALL additionally carry a closed `kind`. Producers SHALL compute `HMAC-SHA-256(audit key, UTF8("sre-audit-v1\0" + domain + "\0" + exact canonical source value))`, own canonical bytes/domain separation/key custody, and omit display names and unrelated timestamps. The schema proves envelope shape only, permits safe partial identity evidence for resolved 401s, requires complete identity evidence after authentication, preserves canonical resource type and closed router `openrouter`, and never serializes raw credentials, provider objects, or unrestricted canonical strings.

#### Scenario: Allowed inference is audited
- **GIVEN** completed allowed inference
- **WHEN** its event is produced
- **THEN** identity, decision, routing, correlation, and outcome remain distinct

#### Scenario: Pre-routing denial is audited
- **GIVEN** authorization denies
- **WHEN** its event is produced
- **THEN** protected reason exists and route outcome is absent

#### Scenario: Credential is audited
- **GIVEN** an authenticated request
- **WHEN** its event serializes
- **THEN** only safe credential ID appears

#### Scenario: Pre-auth validation fails
- **GIVEN** a request rejected with 422 before authentication
- **WHEN** its `stage=validation` event is formed
- **THEN** Principal, PrincipalContext, credential ID, Resource, ModelAlias, and PolicyDecision are absent while body identifiers remain sanitized and explicitly untrusted

#### Scenario: Authentication fails without resolved identity
- **GIVEN** a request rejected with 401 before any identity is safely resolved
- **WHEN** its `stage=authentication` event is formed
- **THEN** Principal, PrincipalContext, and credential ID are absent and no raw credential or invented identity is recorded

### Requirement: Redaction precedes every sink
Prompts/LLM input, LLM responses, MCP logs, sandbox/command output, tool-call arguments/results, and all free content SHALL undergo structural secret removal, known-secret matching, configured pattern detection, and free-content scanning before every sink. Tool-call schema version SHALL be safe metadata, not a redaction bypass. No sink SHALL receive raw content.

#### Scenario: Free content reaches a sink
- **GIVEN** any covered free-content class
- **WHEN** a sink is invoked
- **THEN** it receives only successfully redacted content

#### Scenario: Secret is embedded
- **GIVEN** content with Authorization, raw key, or known secret
- **WHEN** redaction runs
- **THEN** the value is absent from content and metadata

#### Scenario: Pre-redaction logging is attempted
- **GIVEN** raw free content
- **WHEN** direct sink output is attempted
- **THEN** output is rejected without persistence

### Requirement: Fail-closed redaction result
Redaction SHALL emit policy version, `success|failed`, source class, and safe category/count summary. Success SHALL store only redacted content with `content_state=redacted`. Error or uncertainty SHALL discard raw content and form only safe metadata with `content_state=redaction_failed`; execution MAY continue only after that safe event is durably accepted under the audit release gate.

#### Scenario: Redaction succeeds
- **GIVEN** a successful pass
- **WHEN** evidence persists
- **THEN** only redacted content and safe metadata persist

#### Scenario: Redaction fails
- **GIVEN** redactor error or uncertainty
- **WHEN** safe metadata-only evidence is formed
- **THEN** no raw or partial payload survives and any continued execution awaits durable acceptance of the metadata-only event

### Requirement: Metadata and content are separable
The schema SHALL separate mandatory event metadata, redaction metadata, and optional redacted content. `absent|redacted|redaction_failed` SHALL preserve event meaning when content is omitted. Control-plane reads MAY expose only that state; any request for raw or redacted content SHALL follow the uniform 422 rule without revealing whether retrievable content exists. Retention, expiration, and assignment of content-read authorization SHALL remain undefined.

#### Scenario: Metadata-only projection
- **GIVEN** an event with redacted content
- **WHEN** content is omitted
- **THEN** decision, outcome, correlation, and redaction state remain valid

#### Scenario: Event has no content
- **GIVEN** a metadata-only event
- **WHEN** it serializes
- **THEN** `content_state=absent` distinguishes it from failure

### Requirement: Runtime audit is durably accepted and append-only
`AuditStore` SHALL be an abstract authoritative contract without prescribing a database, outbox, or exporter implementation. Before releasing any ordinary success, deny, contract, or normalized upstream-error result, the gateway SHALL receive durable acceptance of its redacted or metadata-only AuditEvent. Accepted events SHALL NOT be updated or deleted; corrections SHALL be new events linked by safe event ID.

For the execution contract, “every outcome emits” means that no ordinary result is released before durable acceptance. If the authoritative store rejects or is unavailable, the gateway SHALL suppress the intended result, SHALL NOT use a raw fallback, and SHALL return safe retryable 503 `audit_unavailable`, distinct from upstream unavailable/no-route codes; `Retry-After` MAY appear only with a reliable estimate. A sanitized operational signal MAY be attempted best-effort but SHALL NOT claim persistence. Langfuse and other exporters SHALL consume accepted events downstream; exporter failure SHALL NOT alter a response already released after authoritative acceptance.

#### Scenario: Event mutation is requested
- **GIVEN** an accepted event
- **WHEN** update or deletion is requested
- **THEN** it is rejected unchanged

#### Scenario: Ordinary result awaits durable acceptance
- **GIVEN** a safe event for a success, deny, contract error, or normalized upstream error
- **WHEN** the gateway prepares the corresponding ordinary response
- **THEN** it releases that response only after the authoritative AuditStore durably accepts the event

#### Scenario: Authoritative audit store rejects
- **GIVEN** a redacted or metadata-only event for an intended ordinary result
- **WHEN** durable acceptance fails or the authoritative AuditStore is unavailable
- **THEN** the intended result is suppressed and safe retryable 503 `audit_unavailable` returns without raw fallback or false persistence claim

#### Scenario: Downstream exporter fails
- **GIVEN** an event was durably accepted and its response was released
- **WHEN** Langfuse or another downstream exporter fails
- **THEN** the already audited response remains unchanged and only a sanitized operational signal may report the export failure
