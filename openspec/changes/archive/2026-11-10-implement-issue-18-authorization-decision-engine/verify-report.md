```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:d1aba8daa3e68c231fa97f34e40f91a4c4a6a624e2cea87ab793780ae2736602
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 8/8
scenarios: 16/16
test_command: TEST_DATABASE_URL=postgresql://sre_agent:local-development-only@127.0.0.1:49564/sre_agent UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q
test_exit_code: 0
test_output_hash: sha256:febc28e5ad12b077209bb7f28243c654143649fcc4ab195167efbd09f8bb08bd
build_command: UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src tests migrations && UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check src tests migrations && node schemas/tooling/release.mjs validate --release 1.3.0 && npm --prefix schemas/tooling test && DATABASE_URL=postgresql://sre_agent:local-development-only@127.0.0.1:49564/sre_agent UV_CACHE_DIR=/tmp/uv-cache uv run alembic check
build_exit_code: 0
build_output_hash: sha256:cda3806a1ead2398eab246c28ea9a14f2bd59e0f755958be4fdbdc4fe6f68847
```

## Verification Report

**Change**: implement-issue-18-authorization-decision-engine  
**Version**: 1.3.0  
**Mode**: Standard (the declared OpenSpec configuration still disables strict TDD; its stale repository description is separately tracked in issue #144).  
**Candidate**: `427f409` plus the uncommitted authorized remediation.

### Completeness

| Metric | Value |
|---|---:|
| Tasks total | 9 |
| Tasks complete | 9 |
| Tasks incomplete | 0 |

### Build & Tests Execution

**Build/static/release**: ✅ Passed. Ruff check passed; 44 files are formatted; immutable release 1.3.0 validated 145 artifacts and 8 checks; contract tooling passed 71/71; Alembic reported no new upgrade operations.

**Tests**: ✅ Passed — 432 passed, 1 skipped in 2.60s against isolated PostgreSQL. The independent issue-14 Responses harness also passed: 14 passed, 1 warning; output hash `sha256:1efa0afbfb0994f4b04d2d8ad2eb8dd14dd9d0a36b118b8c50ca708966668a5c`.

**Coverage**: ➖ Not available; no coverage command is configured for this repository.

### Spec Compliance Matrix

| Requirement | Scenario | Runtime evidence | Result |
|---|---|---|---|
| Generic governed resources | Same rule applies across resource types | `tests/test_authorization.py::test_exact_active_grant_allows_every_resource_for_humans_and_agents` | ✅ COMPLIANT |
| Deterministic denial precedence | Inactive Principal takes precedence | `tests/test_authorization.py::test_precedence_short_circuits_later_fact_readers` and `tests/test_responses.py::test_inactive_principal_reaches_the_engine_before_all_authorization_reads` | ✅ COMPLIANT |
| Deterministic denial precedence | Resource state precedes grant applicability | `tests/test_authorization.py::test_precedence_short_circuits_later_fact_readers` and `tests/test_responses.py::test_inactive_resource_stops_before_grant_and_routing_reads` | ✅ COMPLIANT |
| Exact active direct grant | Exact active grant allows | `tests/test_authorization.py::test_exact_active_grant_allows_every_resource_for_humans_and_agents` | ✅ COMPLIANT |
| Exact active direct grant | Revoked or mismatched grant denies | `tests/test_authorization.py::test_revoked_or_mismatched_grants_deny_as_not_applicable` | ✅ COMPLIANT |
| Bounded diagnostics and authority | Denial details do not leak | `tests/test_responses.py::test_deny_and_missing_resources_are_indistinguishable_without_routing` | ✅ COMPLIANT |
| Bounded diagnostics and authority | No second decision authority | `tests/test_persistence_repositories.py::test_grant_decision_matches_only_the_active_exact_direct_grant` | ✅ COMPLIANT |
| Responses authorize before routing | Restricted principal has no upstream traffic | `tests/test_responses.py::test_deny_and_missing_resources_are_indistinguishable_without_routing`; issue-14 harness | ✅ COMPLIANT |
| Responses authorize before routing | Missing or inactive resource is indistinguishable | `tests/test_responses.py::test_deny_and_missing_resources_are_indistinguishable_without_routing` and `test_inactive_resource_stops_before_grant_and_routing_reads` | ✅ COMPLIANT |
| Responses authorize before routing | Inactive Principal is denied before routing | `tests/test_responses.py::test_inactive_principal_reaches_the_engine_before_all_authorization_reads` | ✅ COMPLIANT |
| Responses single authority | Allowed request routes only after engine allow | `tests/test_responses.py::test_allow_calls_once_outside_transactions_and_commits_protected_readback` | ✅ COMPLIANT |
| Responses single authority | Denied request cannot reveal topology | `tests/test_responses.py::test_deny_and_missing_resources_are_indistinguishable_without_routing`; issue-14 harness | ✅ COMPLIANT |
| Terminal audit evidence | Allow is durably represented | `tests/test_responses.py::test_allow_calls_once_outside_transactions_and_commits_protected_readback` | ✅ COMPLIANT |
| Terminal audit evidence | Deny is durably represented without routing | `tests/test_responses.py::test_deny_and_missing_resources_are_indistinguishable_without_routing`, `test_inactive_principal_reaches_the_engine_before_all_authorization_reads`, and `test_inactive_resource_stops_before_grant_and_routing_reads` | ✅ COMPLIANT |
| Audit-only denial causes | Audit readback preserves the exact cause | `tests/test_audit.py::test_audit_projector_carries_the_exact_cause_only_for_authorization_denies`; `tests/test_persistence_projections.py::test_audit_projection_preserves_the_authorization_denial_cause`; release 1.3 null/missing negative fixtures | ✅ COMPLIANT |
| Audit-only denial causes | Non-audit projections omit the cause | `tests/test_responses.py::test_deny_and_missing_resources_are_indistinguishable_without_routing` | ✅ COMPLIANT |

**Compliance summary**: 16/16 scenarios compliant.

### Correctness and Design Coherence

| Item | Status | Notes |
|---|---|---|
| Generic single engine | ✅ Implemented | `AuthorizationDecisionEngine` owns precedence and the only production `PolicyDecision` construction; `GrantRepository.decide()` is absent. |
| Inactive Principal boundary | ✅ Implemented | Responses resolves a valid credential while preserving Principal status for the engine; generic `CredentialRepository.authenticate()` still returns `None` for an inactive Principal. |
| Denial short-circuiting | ✅ Implemented | Inactive Principal test proves zero resource, grant, routing, and provider access; inactive-resource test proves zero grant, routing, and provider access. |
| Exact audit cause | ✅ Implemented | Runtime events retain the winning cause; the immutable 1.3 schema requires one of the four non-null causes for an authorization-denied 403, while legacy persisted rows remain nullable/readable. |
| Public non-enumeration | ✅ Implemented | Denies remain `403 resource_unavailable` and `deny/no_matching_grant/null`; tests prove the audit-only field is absent from the API response. |

### Issues Found

**CRITICAL**: None.

**WARNING**:
- `openspec/config.yaml` still describes an obsolete no-backend/no-runner state and declares strict TDD disabled. This is outside the authorized change and remains separately tracked as issue #144.

**SUGGESTION**: None.

### Verdict

PASS WITH WARNINGS

All eight requirements and sixteen scenarios have passing runtime coverage. The warning is separately tracked configuration debt and does not contradict the implemented authorization contract.
