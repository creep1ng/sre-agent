## Purpose

Defines portable governance types shared by control and execution consumers without importing persistence, framework, or provider models.

## ADDED Requirements

### Requirement: Versioned shared schemas
OpenAPI and JSON Schema SHALL live under repository-root `/schemas`, follow the Semantic Versioning 2.0.0 standard, and initially publish at contract version `1.0.0`. Initial OpenAPI `info.version` SHALL be `1.0.0`; each initial JSON Schema SHALL have immutable `$id=urn:sre-agent:schema:<name>:1.0.0`. Within a major, changes SHALL preserve prior valid instances and meaning. Removal, rename, new required fields, narrowing, or semantic change SHALL use a new major while retaining the prior major.

#### Scenario: Versioned schema resolves
- **GIVEN** a shared schema
- **WHEN** it resolves from `/schemas`
- **THEN** OpenAPI `info.version` and the absolute schema `$id` identify `1.0.0`

#### Scenario: Breaking revision increments the major
- **GIVEN** a published `1.x` schema and a breaking schema change
- **WHEN** the breaking revision is published
- **THEN** it uses major `2` or later and retains the prior major during migration

### Requirement: Principal and credential schemas
`Principal` SHALL contain ID, `kind=human|agent`, display name, and `active|inactive` status. `CredentialReference` SHALL expose credential ID, Principal ID, non-secret prefix, `active|revoked` status, and lifecycle metadata including expiry when applicable. `PrincipalContext` SHALL bind an authenticated Principal to credential ID. Principal, CredentialReference, PrincipalContext, storage/list/replay/audit/error representations SHALL NOT serialize raw keys or `Authorization`; storage MAY retain only a one-way hash. The sole exception is a dedicated successful first-issuance `CredentialIssuance` response or bootstrap equivalent, which MAY reveal one raw key exactly once outside CredentialReference; replay SHALL set `secret_revealed=false` and omit the key.

#### Scenario: Single-workspace Principal validates
- **GIVEN** a human or agent Principal without tenant fields
- **WHEN** schema validation runs
- **THEN** it validates

#### Scenario: Legacy identity is supplied
- **GIVEN** `organization_id`, `tenant_id`, `user_id`, `role`, or `scope`
- **WHEN** Principal validation runs
- **THEN** it fails

#### Scenario: Secret reaches a persistent or shared representation
- **GIVEN** a raw key or Authorization value in Principal, CredentialReference, PrincipalContext, storage/list/replay/audit, or error data
- **WHEN** serialization runs
- **THEN** serialization fails

#### Scenario: Dedicated first issuance reveals once
- **GIVEN** successful first credential issuance or bootstrap
- **WHEN** the dedicated issuance response and a later replay serialize
- **THEN** only the first response may contain one raw key outside CredentialReference and replay returns `secret_revealed=false` without the key

### Requirement: Model, resource, and grant schemas
`ModelAlias` SHALL separate stable alias, concrete model, router, inference provider, and `active|inactive` status. `Resource` SHALL contain type and ID; type SHALL be `llm_model|mcp_server|mcp_tool|skill|bok_collection`. `Grant` SHALL represent one direct `allow` over Principal, action, and Resource with `active|revoked` status; only active Grants SHALL participate in allow. Routing, organization, role, scope, and tenant authority SHALL NOT appear.

#### Scenario: Direct grant validates
- **GIVEN** an active Principal-action-Resource Grant
- **WHEN** it is validated
- **THEN** `effect=allow` validates

#### Scenario: Routing enters a Grant
- **GIVEN** a Grant with model, router, or provider selection
- **WHEN** validation runs
- **THEN** it fails

### Requirement: Default-deny decision
`PolicyDecision` SHALL contain `allow|deny`, stable `reason_code`, and nullable `policy_id`. No matching Grant SHALL yield `deny`, `no_matching_grant`, and null `policy_id`; an ID SHALL identify only the persisted Grant/policy that caused a decision.

#### Scenario: No grant matches
- **GIVEN** no active matching Grant
- **WHEN** authorization runs
- **THEN** it returns deny, `no_matching_grant`, and null `policy_id`

#### Scenario: Grant allows
- **GIVEN** an active matching Grant
- **WHEN** authorization runs
- **THEN** allow references that Grant

### Requirement: Audit, error, and correlation schemas
`AuditEvent` SHALL carry dimensions required by the audit contract. `ErrorEnvelope` SHALL contain only `error.code`, safe `error.message`, server `request_id`, boolean `retryable`, and bounded safe details. `Correlation` SHALL separate server `request_id`, optional `incident_id|run_id|task_id`, and technical trace ID; none SHALL encode identity, tenancy, credentials, or permission.

#### Scenario: Safe error validates
- **GIVEN** a normalized error
- **WHEN** validation runs
- **THEN** stack, upstream body, URL, and secrets are absent

#### Scenario: Correlation claims authority
- **GIVEN** only a domain or trace ID
- **WHEN** access is evaluated
- **THEN** it grants nothing
