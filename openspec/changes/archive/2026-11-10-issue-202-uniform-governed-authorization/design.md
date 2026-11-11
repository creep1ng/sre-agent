# Design: Uniform Governed Authorization

## Technical Approach

Route the four existing operations through one credential-to-decision function after operation-owned validation and before any business lookup, write, routing, or provider call. The function reuses `CredentialRepository.resolve_authorization_context`, `ResourceRepository`, `GrantRepository`, and `AuthorizationDecisionEngine`; services retain HTTP mapping and audit-before-release. Existing grants and all provisioning, administration, schema, seed, and lifecycle behavior remain unchanged.

## Architecture Decisions

| Decision | Choice | Rejected alternative | Rationale |
|---|---|---|---|
| Shared boundary | Add `authorize_governed_access` beside bearer parsing in `gateway/authentication.py` | FastAPI authorization dependency | Responses must validate the body before authentication, and its resource ID is validated `body.model`. |
| Policy authority | Return the existing `PrincipalContext` and `AuthorizationEvaluation` | New policy/result hierarchy | The engine already owns exact-grant precedence and evidence. |
| Route declaration | Add Bearer security plus `x-governed-scope` metadata to each current route | New route class or registry | Existing FastAPI/OpenAPI metadata and `CONTROL_SCOPES` cover the four-route inventory. |
| Bypass proof | Use a test-only runtime probe with effect spies | Treat metadata scanning as enforcement proof | A declared route can still skip the shared function; only observed denied execution proves the adapter was not reached. |
| Control audit evidence | Record post-business control terminals at stage `response` and preserve context/resource/decision for `authorization` and `response` | Store allow evidence at stage `audit` | `AuditEvent` forbids subject evidence at `audit` but permits it at `response`; Responses already uses this contract. |

## Data Flow

    validate -> authorize_governed_access -> resolve/execute once -> append audit -> release
                         | deny/invalid                    | audit failure
                         +-> audit -> 401/403              +-> suppress -> 503

The shared function accepts the session provider, raw Authorization value, and server-owned `(action, resource_type, resource_id)`. Credential failure raises existing `AuthenticationFailed`. A valid credential returns `(PrincipalContext, AuthorizationEvaluation)` for either allow or deny; repository failures propagate to the caller's established failure handling. Inactive principals reach the engine, preserving its denial taxonomy. Callers translate denial to 403 `resource_unavailable`; only an allowed principal lookup may return 404.

## File Changes

| File | Action | Description |
|---|---|---|
| `src/sre_agent/gateway/authentication.py` | Modify | Reuse bearer parsing and add the shared governed-access function. |
| `src/sre_agent/gateway/responses.py` | Modify | Call the function after validation; declare Bearer and `invoke/llm_model/{body.model}` metadata. |
| `src/sre_agent/control/service.py` | Modify | Reuse the function for create/list/get, normalize denial, attach existing scopes, and retain allow evidence at `response`. |
| `tests/test_governed_authorization.py` | Create | Four-route inventory check and executable bypass probe. |
| `tests/test_responses_openapi.py` | Modify | Compare runtime Bearer security and 401/403 declarations with the released contract. |
| `tests/test_control_plane.py` | Modify | Verify 401/403/authorized-404 ordering, zero denied reads/writes, unchanged allows, and grant evidence. |
| `docs/architecture.md` | Modify | Document the governed-entry rule for future LLM, MCP, skill, and knowledge consumers. |

## Testing Strategy

Write RED tests first. A DB-independent inventory test composes the application, enumerates the four current `/v1` operations, and asserts each OpenAPI operation has Bearer security and exact governed scope metadata. A runtime probe accepts a `TestClient` request plus a recording business adapter and asserts denied status and zero effects. Its synthetic FastAPI route deliberately declares both metadata fields but calls the adapter directly; `pytest.raises(AssertionError)` proves the probe detects the bypass. This is targeted behavioral evidence, not a universal static gate.

Parameterized control tests spy on `PrincipalRepository.create/list/get`: invalid credentials yield 401 with zero calls, missing grants yield 403 with zero calls, and allowed calls occur once. Existing Responses tests remain the execution/routing proof; the OpenAPI test adds Bearer parity. Captured terminal events must contain the allowed grant reference, and a failing audit store must suppress the payload with 503.

## Threat Matrix

| Boundary | Applicability | Design response / RED tests |
|---|---|---|
| Documentation-like paths | N/A — no executable-file classification | None |
| Git repository selection | N/A — no Git invocation | None |
| Commit state | N/A — no VCS state handling | None |
| Push state | N/A — no push automation | None |
| PR commands | N/A — no PR automation | None |

## Migration / Rollout

No migration, flag, dependency, schema release, seed, or grant lifecycle change is required. Roll back the shared call sites and route metadata together.

## Open Questions

None. This document proposes implementation; it does not claim these changes exist yet.
