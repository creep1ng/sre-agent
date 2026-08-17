## Purpose

Defines ownership, accepted decisions, portable evidence, consumer conformance, vocabulary controls, and SemVer governance.

## ADDED Requirements

### Requirement: Ownership matrix
Artifacts SHALL follow this authority matrix; lower-authority stores SHALL NOT redefine contracts.

| Owner | Required | Prohibited |
|---|---|---|
| Git | OpenAPI, schemas, ADRs, examples, fixtures, seeds, conformance | Raw keys/Authorization, runtime records |
| DB | Principals, credential ID/hash/prefix/status, aliases, Grants, AuditEvents, idempotency | Raw keys/upstream secrets, contract definitions |
| Secret store/env | Provider/deployment secrets | Policy, Grants, schemas, audit content |

#### Scenario: Content is misplaced
- **GIVEN** secret, runtime, or contract material
- **WHEN** ownership validation runs
- **THEN** placement outside its row fails

### Requirement: Accepted ADRs
Git SHALL contain accepted: ADR-001 non-streaming `/v1/responses`, pre-resolution authorization, initial OpenRouter adapter; ADR-002 single workspace and `Principal(human|agent)` without organization/role/scope; ADR-003 Bearer key to PrincipalContext, one-time reveal, hash/prefix storage; ADR-004 direct allow Grants/default deny, engine-independent; ADR-005 stage-aware safe AuditEvents without fabricated authority, pre-sink fail-closed redaction, durable authoritative acceptance before ordinary-result release, append-only events, downstream exporters, and deferred retention/access. Accepted ADRs SHALL be superseded, never silently rewritten.

#### Scenario: ADR set is checked
- **GIVEN** governance artifacts
- **WHEN** ADR-001..005 are validated
- **THEN** each is accepted with its approved decision and deferrals

### Requirement: Portable evidence
Git SHALL publish version-aligned OpenAPI, JSON Schemas, executable positive/negative examples for each operation/type. Fixtures SHALL cover schema/safe errors, non-enumeration, idempotency conflict, invalid trace, correlation spoofing, stage-aware pre-auth 422/401 without invented authority, redaction failure, rotation replay, duplicate bootstrap, OpenRouter metadata success/fallback/error paths, explicit separation of public Response body `id` from upstream `X-Generation-Id`, missing/invalid generation header and provider-drift 502, authoritative audit-store rejection 503, downstream exporter failure, and upstream 503/504 without provider lookup. Every fixture SHALL name its contract version.

#### Scenario: Positive fixture drifts
- **GIVEN** a positive fixture
- **WHEN** strict validation fails
- **THEN** conformance fails

#### Scenario: Negative fixture validates
- **GIVEN** a fixture invalid for a named rule
- **WHEN** validation accepts it
- **THEN** conformance fails

### Requirement: Consumer conformance
Suites SHALL verify #10 fixture transport, #11 schema/persistence mapping, #13 Bearer-to-PrincipalContext and 401, and #14 authorize-resolve-invoke-normalize-redact-durably-accept-before-release. Harness SHALL use execution OpenAPI/fixtures; UI SHALL use control-plane OpenAPI/fixtures. Consumers SHALL NOT make framework DTOs, ORM/database models, or provider SDK types contract authority.

#### Scenario: Consumers conform
- **GIVEN** #10/#11/#13/#14, harness, or UI implementation
- **WHEN** matching-version suites run
- **THEN** required positive/negative boundaries pass without reinterpretation

#### Scenario: Internal model is shared
- **GIVEN** harness or UI imports an internal model as authority
- **WHEN** conformance runs
- **THEN** it fails

### Requirement: Technology independence
Normative contracts SHALL NOT depend on FastAPI, Pydantic, database engines, OpenRouter SDK, OPA, Casbin, Keycloak, or Langfuse. Non-normative adapter mappings SHALL NOT alter portable semantics or authority.

#### Scenario: Adapter changes
- **GIVEN** a conforming technology replacement
- **WHEN** observable behavior stays stable
- **THEN** the suite still passes

### Requirement: Canonical vocabulary
Positive schemas, OpenAPI, examples, fixtures, and normative ADR text SHALL use Principal, ModelAlias, direct Grant, and single workspace. Lint SHALL reject identity/authorization fields `organization|organization_id|tenant|tenant_id|user|user_id|role|roles|scope|scopes`, except marked negative legacy fixtures.

#### Scenario: Legacy vocabulary appears
- **GIVEN** a prohibited field in a positive artifact
- **WHEN** lint runs
- **THEN** it fails naming artifact and field

#### Scenario: Legacy negative fixture exists
- **GIVEN** a marked legacy fixture
- **WHEN** conformance runs
- **THEN** it remains evidence only when schema rejects it

### Requirement: SemVer change process
Contracts SHALL follow the Semantic Versioning 2.0.0 standard and initially publish at `1.0.0`. Within a major, changes SHALL be additive and preserve valid instances/semantics. Breaking changes SHALL publish new major `$id` and OpenAPI, retain prior major during migration, document consumers/migration, add cross-version fixtures, and pass #10/#11/#13/#14 plus harness/UI before becoming default.

#### Scenario: Compatible addition occurs
- **GIVEN** an optional meaning-preserving field
- **WHEN** minor validation runs
- **THEN** prior fixtures and consumers pass

#### Scenario: Breaking change lacks migration
- **GIVEN** removal, rename, requirement, narrowing, or semantic change
- **WHEN** no new major/migration exists
- **THEN** publication fails
