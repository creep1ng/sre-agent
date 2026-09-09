# Proposal: Uniform Governed Authorization

## Intent

Make authorization fail-closed across four issue #202 operations: `POST /v1/responses`, `POST /v1/principals`, `GET /v1/principals`, and `GET /v1/principals/{principal_id}`. Regression coverage must prove a declared-secure route cannot bypass authorization and reach business code.

## Scope

### In Scope
- Reuse one governed-access function and keep `AuthorizationDecisionEngine` as the sole policy authority.
- Preserve ordering: validation, authentication, authorization, resolution/execution, then audit-gated release.
- Derive `Principal` from credentials; keep action and type server-owned. Responses uses validated `body.model`; administration uses `admin.read`/`admin.write + administrative_control + principals`.
- Enforce Bearer security, governed-scope metadata, and behavioral bypass coverage.
- Standardize invalid credentials to 401 and denials to non-enumerating 403; retain 404 only for a missing principal after valid authorization.
- Preserve matched-grant evidence on allowed terminal audit events.

### Out of Scope
- New endpoints, dependencies, policy engines, roles, frameworks, or MCP/skill/knowledge implementations.
- Unrelated control-plane operations.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `governed-llm-responses`: Require Bearer security and governed authorization with validated `body.model` before routing or invocation.
- `mvp-security-evaluation`: Make the three administration scenarios current and require structural and behavioral bypass regressions.
- `runtime-audit-evidence`: Preserve matched-grant evidence for allowed governed operations while retaining audit-before-release behavior.

## Approach

Centralize credential resolution and authorization in `src/sre_agent/gateway/authentication.py`; keep validation, responses, execution, and audit gating in existing services. Existing scopes remain the inventory. Combine metadata checks with a synthetic declared-secure route that skips authorization and must fail upon business-adapter access.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/sre_agent/gateway/{authentication,responses}.py` | Modified | Shared access, trusted scope, Bearer declaration |
| `src/sre_agent/control/service.py` | Modified | Shared access, denial, grant evidence |
| `tests/test_{governed_authorization,responses_openapi,control_plane}.py` | Modified | Architecture, OpenAPI, behavior regressions |
| `docs/architecture.md` | Modified | Extension rule for future governed consumers |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Metadata gives false assurance | Medium | Require a bypass test that observes adapter/business execution |
| Denial leaks existence | Low | Assert identical 403 before target lookup; reserve authorized missing-target 404 |
| Audit loses grant evidence | Medium | Assert matched grant on allowed terminal events |

## Rollback Plan

Revert shared call sites and metadata together; retain per-service authorization until regressions pass. No data rollback is required.

## Dependencies

- Existing repositories, scopes, decision engine, FastAPI security, and audit.

## Success Criteria

- [ ] All four operations preserve ordering, correct 401/403/authorized-404 outcomes, zero denied effects, one allowed execution, and matched-grant evidence.
- [ ] Runtime OpenAPI declares Bearer 401/403, and both missing-metadata and declared-secure authorization-bypass regressions fail closed.
- [ ] Architecture guidance covers future LLM, MCP, skill, and knowledge consumers without adding endpoints.
