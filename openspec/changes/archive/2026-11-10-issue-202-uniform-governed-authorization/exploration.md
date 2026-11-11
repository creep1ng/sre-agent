## Exploration: Uniform governed-resource authorization for issue #202

### Current State

The live issue is ready and has no open product decisions. The current repository is materially
newer than `openspec/config.yaml`: FastAPI, PostgreSQL, Responses, three principal administration
operations, audit persistence, and a containerized Python test runner now exist.

`POST /v1/responses` already validates input, resolves a bearer credential to a Principal, evaluates
`AuthorizationDecisionEngine` with server-owned `invoke + llm_model + body.model`, resolves routing
only after allow, and records zero provider calls for rejected paths. Its runtime OpenAPI route does
not attach FastAPI bearer security even though the released 1.4.0 Responses contract does.

The implemented administrative operations repeat the same authentication and authorization sequence
inside `ControlService`. `CONTROL_SCOPES` already supplies their server-owned scopes:

| Implemented operation | Scope |
| --- | --- |
| `POST /v1/responses` | `invoke + llm_model + validated body.model` |
| `POST /v1/principals` | `admin.write + administrative_control + principals` |
| `GET /v1/principals` | `admin.read + administrative_control + principals` |
| `GET /v1/principals/{principal_id}` | `admin.read + administrative_control + principals` |

The control router already projects bearer security. However, an authorization denial on the
single-principal read returns 404 rather than the issue's uniform 403, and successful control audit
events use stage `audit`, which intentionally removes the matched grant evidence. There is no
architecture check binding the current `/v1` inventory to both enforcement metadata and bearer
security.

### Affected Areas

- **Planned:** `src/sre_agent/gateway/authentication.py` — add one small governed-access function
  that reuses bearer parsing, `CredentialRepository.resolve_authorization_context`, repository facts,
  and the existing decision engine.
- **Planned:** `src/sre_agent/gateway/responses.py` — call the shared function after request
  validation; declare bearer security and the server-owned scope in route metadata.
- **Planned:** `src/sre_agent/control/service.py` — replace duplicated authentication/authorization
  calls with the shared function, normalize engine denials to 403, attach scope metadata, and retain
  matched-grant evidence on successful terminal audit events.
- **Planned:** `tests/test_governed_authorization.py` — verify trusted scope construction and the
  architecture gate, including a synthetic insecure `/v1` route that must fail.
- **Planned:** `tests/test_responses_openapi.py` — assert runtime bearer security matches the released
  contract.
- **Planned:** `tests/test_control_plane.py` — prove rejected administration stops before business
  reads/writes and allowed administration retains the applied grant in audit evidence.
- **Planned:** `docs/architecture.md` — add the short extension rule for future LLM, MCP, skill, and
  knowledge consumers without designing their endpoints.

Existing `tests/test_responses.py` already covers invalid credentials, inactive Principals,
missing/inactive resources, missing grants, no routing, zero provider calls, and exactly one allowed
provider call; it should be reused rather than duplicated. No schema release, migration, dependency,
new policy engine, role model, or future resource endpoint is planned.

### Approaches

1. **Shared function plus executable route metadata** — centralize credential-to-decision handling,
   keep validation and public error/audit rendering in each existing service, and treat every current
   `/v1` route's bearer security plus governed-scope metadata as the explicit inventory.
   - Pros: Reuses the existing engine and repositories; preserves validation-first ordering; small
     call-site changes; a synthetic route can prove the architecture gate fails closed.
   - Cons: Services still translate the common outcome into their established public error and audit
     shapes; the `/v1`-means-governed convention would need revisiting only if a public ungoverned
     `/v1` operation is introduced.
   - Effort: Medium

2. **FastAPI authorization dependency or decorator** — make FastAPI authenticate and authorize before
   entering each endpoint.
   - Pros: Compact endpoint signatures and automatic OpenAPI security.
   - Cons: Risks authenticating before body validation, makes the Responses resource identifier
     awkward because it comes from the validated body, and would require custom exception/audit
     plumbing to preserve current contracts.
   - Effort: Medium/High

3. **New registry/router enforcement framework** — introduce custom route classes and a global
   governed-resource registry for present and future resource types.
   - Pros: Strong declarative centralization.
   - Cons: Duplicates `CONTROL_SCOPES`, adds a parallel framework before future endpoints exist, and
     increases code and review surface without improving current runtime outcomes.
   - Effort: High

### Recommendation

Use approach 1. The smallest root-cause fix is one shared governed-access function called only after
each operation validates its client input. The Principal comes only from the credential lookup;
action and resource type remain server constants; only the already-validated logical identifier is
passed by the operation. Keep the existing `AuthorizationDecisionEngine` as the sole policy authority
and the current services as the owners of public errors and audit release gating.

Use existing scope declarations and route metadata instead of adding a second registry. The
architecture test should scan the composed current `/v1` operations for bearer security and governed
scope metadata, and demonstrate failure with one synthetic route lacking them. Behavioral tests then
prove the shared function runs before repositories/adapters can perform business work. This is the
Ponytail boundary: no speculative MCP, skill, or knowledge implementation and no new framework.

### Risks

- Changing the single-principal authorization denial from 404 to the issue-mandated 403 must preserve
  404 only for a target that is absent after a successful administrative authorization.
- Control success events currently discard policy evidence; moving their terminal audit stage to an
  existing evidence-bearing stage must be checked against the current AuditEvent contract.
- A route-metadata architecture gate enforces today's `/v1` convention, not arbitrary Python calls
  outside the composed gateway. The extension guide must require future governed consumers to enter
  through a declared `/v1` operation; broader static-analysis machinery is intentionally deferred.
- The OpenSpec config's old statement that no backend or test runner exists is stale and must not be
  used as implementation evidence; current source, Compose, and CI are authoritative for this change.

### Ready for Proposal

Yes. The proposal can freeze the four-operation current inventory and the minimal reuse strategy
above. All issue acceptance criteria remain mandatory; Ponytail removes duplicate authentication,
parallel policy machinery, speculative endpoints, and redundant tests rather than weakening security.
