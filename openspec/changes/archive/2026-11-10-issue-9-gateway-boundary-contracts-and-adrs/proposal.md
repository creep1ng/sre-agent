## Why

Issue #9 must establish one versioned language before backend work. Success means #10, #11, #13, and #14 implement against tested contracts without redefining governance or gateway boundaries.

## What Changes

**In scope**
- Publish portable `/schemas` contracts following the Semantic Versioning 2.0.0 standard, initially at contract version `1.0.0`: single-workspace `Principal` (`human|agent`), API-key credential reference/`PrincipalContext`, `ModelAlias`, direct `Grant`/`PolicyDecision`, `AuditEvent`, safe errors, and correlation. Missing grants deny with `no_matching_grant` and null `policy_id`.
- Define textual, non-streaming `POST /v1/responses`. Request `model` is an alias such as `triage-agent`; authorize before routing; response `model` is concrete with flat string metadata `requested_model_alias`, `router`, `inference_provider`. Domain IDs are body fields; the server generates `request_id`; Trace Context is validated/generated/propagated. Unknown fields yield 422; unsafe/unadaptable, unavailable/no-route, and timeout upstream failures yield safe 502/503/504 errors.
- Contract control-plane operations for Principals, credentials, ModelAliases, grants, and audit, without pagination but with idempotency/errors; include idempotent offline seed/CLI bootstrap that reveals a key once and stores only hash/prefix.
- Record the Git/DB/secrets ownership matrix and accepted ADR-001..ADR-005. Provide examples, fixtures, and conformance tests as evidence for consumers.
- Support OpenRouter contractually as initial router while separating it from effective provider and deferring its production adapter.

**Out of scope:** FastAPI/Pydantic, database, real authentication/authorization/routing, streaming, roles, organizations/multitenancy, OAuth/JWT, OPA/Casbin/Keycloak/Langfuse dependencies, audit-content retention/access, and future entities such as `AgentProfile`.

## Capabilities

### New Capabilities
- `shared-governance-schemas`: Domain, error, and correlation types.
- `control-plane-contract`: Operations, idempotency, and bootstrap.
- `responses-gateway-contract`: Responses, non-enumeration, routing, OpenRouter.
- `audit-redaction-contract`: AuditEvent; fail-closed redaction of inputs, responses, MCP/sandbox/command outputs, and tool calls before sinks; secrets never serialize.
- `contract-governance-conformance`: ADRs, ownership, fixtures, consumer evidence.

### Modified Capabilities

None; `openspec/specs/` is empty.

## Impact

#10 consumes fixtures; #11 schemas/persistence boundaries; #13 credential-to-PrincipalContext; #14 the composed flow. Harness/SDKs consume execution; UI/persistence consume control-plane contracts. No product migration exists; legacy UI roles/organizations are non-authoritative and excluded from schemas/fixtures.

## Risks and Controls

- Hide absent versus unauthorized resources externally; preserve protected audit detail.
- Treat correlation as untrusted; bind it to the Principal and constrain tracing/sampling.
- Redact before sinks and fail closed.
- Keep authorization on `ModelAlias` before routing, and alias/model/router/provider as separate dimensions.
- Preserve SDK shape through standard `model`; reject unsupported extensions explicitly.

## Delivery Forecast

Stacked-to-main, each target `<=400` changed lines: (1) shared schemas + ADR-002/003/004; (2) control plane + bootstrap; (3) Responses/OpenRouter + ADR-001; (4) audit/redaction/ownership + ADR-005; (5) cross-consumer conformance. Ordering is provisional, not a task plan.

## Readiness and Rollback

Ready when capability boundaries, approved decisions, and consumer evidence are reviewable; exact paths/idempotency pass to specs/design, while retention stays OUT. Rolling back S2 removes this proposal and its three core delta specs; no runtime/data exists.
