# Delta for MVP Security Evaluation

## MODIFIED Requirements

### Requirement: Non-enumerating resource denial

The resource-denial contract MUST return HTTP 403 with code `resource_unavailable` for missing/inactive resources, existing resources without an authorized grant, and unauthorized administration. Authorization MUST precede routing, repository business reads/writes, and provider/tool calls; all denied cases MUST expect zero business effects.
(Previously: denial covered only Responses resources and did not state the administrative 403 boundary.)

#### Scenario: Missing and unauthorized resources are indistinguishable

- GIVEN one request names a missing resource and another names an existing resource without a grant
- WHEN both requests execute
- THEN each returns 403 `resource_unavailable`, makes zero upstream calls, and exposes no existence distinction

#### Scenario: Authorized missing principal remains 404

- GIVEN an authenticated administrator has the exact existing administrative grant
- WHEN it requests a principal identifier that does not exist
- THEN the operation returns 404 `resource_not_found` only after authorization succeeds

### Requirement: Future-only MCP and administrative controls

MCP/tool authorization remains future-only until that runtime exists and MUST forbid role inference from principal names. Current principal administration MUST consume exact existing grants and preserve established allowed business behavior; it MUST NOT change grant provisioning or administration, roles, seeds, migrations, schema, or lifecycle management.
(Previously: MCP/tool and all administrative scenarios were future-only.)

#### Scenario: Existing administration stays behaviorally stable

- GIVEN an allowed principal-management request and the current grant provisioning/management behavior
- WHEN the governed check is applied
- THEN the established create/list/get business outcomes remain unchanged and no grant-management path is modified

#### Scenario: Future unauthorized MCP operation

- GIVEN a future MCP/tool request without an exact action/resource grant
- WHEN its runtime is implemented and the scenario executes
- THEN it returns a non-success authorization response, performs zero tool executions, and records safe audit evidence

## ADDED Requirements

### Requirement: Current administration and behavioral bypass coverage

The three current operations `POST /v1/principals`, `GET /v1/principals`, and `GET /v1/principals/{principal_id}` MUST authenticate from Bearer credentials, declare Bearer 401/403 security, use server-owned `admin.write` or `admin.read` plus `administrative_control`/`principals`, and deny before business execution. The evaluation MUST cover both route metadata and runtime enforcement.

#### Scenario: Create denial is uniform

- GIVEN a valid request without the exact `admin.write` grant
- WHEN `POST /v1/principals` executes
- THEN it returns 403 and performs no principal business write

#### Scenario: List denial is uniform

- GIVEN a credential without the exact `admin.read` grant
- WHEN `GET /v1/principals` executes
- THEN it returns 403 and performs no principal business read

#### Scenario: Get denial is uniform

- GIVEN a credential without the exact `admin.read` grant
- WHEN `GET /v1/principals/{principal_id}` executes
- THEN it returns 403 before target lookup and performs no principal business read

#### Scenario: Invalid credentials fail uniformly

- GIVEN any of the three operations with a missing, malformed, unknown, inactive, or revoked Bearer credential
- WHEN the request executes
- THEN it returns 401 `authentication_failed` before business reads or writes

#### Scenario: Missing governed declaration is rejected

- GIVEN a composed `/v1` route without Bearer security or governed-scope metadata
- WHEN architecture validation runs
- THEN validation fails closed

#### Scenario: Declared-secure route cannot skip authorization

- GIVEN a declared-secure route whose handler bypasses authentication/authorization
- WHEN it would reach a business adapter
- THEN the behavioral gate fails and the adapter is not allowed as a valid execution path

### Requirement: Governed extension guidance

The architecture guide MUST require future LLM, MCP, skill, and knowledge consumers to enter through a declared governed operation with Bearer security and exact grants. This change MUST add no endpoint or runtime for those future types.

#### Scenario: Future types stay documented only

- GIVEN a future consumer type is proposed
- WHEN the extension guidance is applied
- THEN it defines the governed entry rule without adding an endpoint, grant model, or implementation
