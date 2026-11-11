# Resource Catalog Contract Specification

## Purpose

Define 2.2.0 catalog projection from verified 2.1.0 without changing `Resource`, `Grant`, or 2.1.0 consumption/#202 authorization contracts.

## ADDED Requirements

### Requirement: Projection and owner matrix

`ResourceCatalogEntry` MUST be closed and contain only `resource_type`, owner ID/status, opaque `source`/`source_ref`, and discoverability metadata. It MUST exclude credentials, secrets, provider/routing data, prompts, raw I/O, and arbitrary configuration. `Resource` remains the `(resource_type, resource_id)` tuple; `ModelAlias` owns `concrete_model`, `router`, and `inference_provider`.

| Type | Owner/identity | States | Operations/actions |
|---|---|---|---|
| `llm_model` | ModelAlias alias ID | `active\|inactive` | create/assignment/status `admin.write`; read `admin.read`; invoke `invoke`; no revoke |
| `mcp_server`, `mcp_tool` | MCP #187 IDs; tool→server relation | `registered\|active\|inactive\|revoked` | register/update/deactivate/revoke `admin.write`; discovery/invoke `mcp.discovery\|mcp.invoke` |
| `skill` | Skills #31 immutable `skill_id@version` | `draft\|published\|active\|inactive\|revoked` | publish/version/deactivate/revoke `admin.write`; discovery/read/invoke `skill.discovery\|skill.read\|skill.invoke` |
| `bok_collection` | BoK #33 immutable `collection_id@version` | `draft\|indexing\|active\|inactive\|revoked` | publish/index/deactivate/revoke `admin.write`; discovery/search/read `bok.discovery\|bok.search\|bok.read` |

#### Scenario: Authority is preserved

- GIVEN a catalog entry and authorization tuple exist
- WHEN a lifecycle operation is requested
- THEN the matrix owner/action alone may perform it; projection metadata cannot change authorization

### Requirement: Bounded discovery/non-enumeration

Discovery/read MUST authenticate before lookup and use deterministic ordering with validated filters. `limit` is 1–100 (default 100); cursor, page, offset, continuation, unknown, or conflicting filters return 422. Authorized lists return visible entries or an empty 200. Hidden, absent, inactive, or filtered direct targets return 404 `resource_not_found`; denied list/mutation returns 403 `resource_unavailable`; authentication failure returns 401 `authentication_failed`. Execution denial remains 403 with zero upstream calls.

#### Scenario: Authorized bounded list

- GIVEN an authenticated principal has discovery permission
- WHEN it lists with valid filters and a limit at most 100
- THEN visible entries are returned in deterministic order, without continuation

#### Scenario: Direct reads do not enumerate

- GIVEN a target is absent, hidden, inactive, or filtered out
- WHEN it is read with valid authentication
- THEN the response is indistinguishable 404 `resource_not_found`

#### Scenario: Authentication and filter errors

- GIVEN credentials are missing, discovery is unauthorized, or filters are malformed
- WHEN discovery is requested
- THEN the result is respectively 401, 403 `resource_unavailable`, or 422, without lookup leakage

### Requirement: Idempotent mutations and lifecycle boundary

POST mutations MUST require a 16–128 printable-ASCII `Idempotency-Key`. Same-key/same-payload replay MUST return the original result without a second transition; changed payload/stale version returns 409 without mutation. Owner deactivation/revocation converges where permitted. A lifecycle change blocks later authorization, while an already-authorized in-flight request MAY finish with its captured snapshot; retroactive cancellation is not promised.

#### Scenario: Replay and in-flight behavior

- GIVEN a mutation succeeds and an invocation was authorized before deactivation
- WHEN replayed and later invocation starts
- THEN replay is stable, in-flight may finish, and the later request is denied before upstream execution

#### Scenario: Idempotency conflict does not mutate

- GIVEN a key is bound to one successful payload
- WHEN the same key is reused with another payload or stale version
- THEN 409 is returned and owner state is unchanged

### Requirement: Explicit demo reconciliation

Startup seed MUST detect incompatible persisted state and report conflict without repair. Only bounded authorized `demo.reconcile`/reset MAY restore fixtures; restart, migration rerun, or environment edits do not imply recovery.

#### Scenario: Drift requires explicit reset

- GIVEN persisted demo state conflicts with its fixture
- WHEN startup runs and reset is later requested
- THEN startup leaves state unchanged and reset restores the bounded fixture deterministically

### Requirement: Additive release conformance

Release 2.2.0 MUST include projection, OpenAPI reads, owner matrix, fixtures, conformance evidence, and tooling allow-list updates; it MUST preserve 2.1.0 consumption and #202 authorization contracts. 2.0.0 and 2.1.0 MUST remain byte-identical; never publish 1.5.0; corrections are additive.

#### Scenario: Historical release is preserved

- GIVEN 2.2.0 artifacts and immutable 2.0.0/2.1.0 snapshots
- WHEN schema, OpenAPI, fixture, release, and conformance validation runs
- THEN 2.2.0 passes; 2.0.0 and 2.1.0 bytes and hashes remain unchanged
