```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:f016b3f1c6d3ae5f6442e88ff8b41e41e229a65659f6b1b9b1b00352950672ad
verdict: pass
blockers: 0
critical_findings: 0
requirements: 9/9
scenarios: 21/21
test_command: "scripts/worktree-compose --profile checks run --build --rm python-checks"
test_exit_code: 0
test_output_hash: sha256:bc7d27cc827eccf0f8ae9dfa8a012e02dee9bcd77f462f06815b2b901e6bd0f5
build_command: "scripts/worktree-compose --profile checks run --build --rm python-checks"
build_exit_code: 0
build_output_hash: sha256:bc7d27cc827eccf0f8ae9dfa8a012e02dee9bcd77f462f06815b2b901e6bd0f5
```

## Verification Report

**Change**: issue-202-uniform-governed-authorization  
**Version**: OpenSpec delta; runtime contract version 2.0.0  
**Mode**: Strict TDD

### Completeness

| Metric | Value |
|--------|-------|
| Requirements total | 9 |
| Requirements complete | 9 |
| Scenarios total | 21 |
| Scenarios compliant | 21 |
| Tasks total | 9 |
| Tasks complete | 9 |
| Tasks incomplete | 0 |

All proposal, exploration, specification, design, task, apply-progress, and previous verify-report artifacts were read. Native status reported `artifactStore: openspec`, `verify: ready`, and `taskProgress: 9/9`. The previous failed report remains historical evidence; this report is a fresh independent candidate.

### Candidate Identity and Scope

- Candidate commit: `105edfbb41ef06202f7b29fa373e1ae06fb461f0`.
- Working-tree remediation and Unit 3 changes were inspected without modification by this verification.
- Fresh evidence manifest: `sha256:f016b3f1c6d3ae5f6442e88ff8b41e41e229a65659f6b1b9b1b00352950672ad`; it binds the current candidate head, relevant changed-file hashes, and fresh focused/full output hashes.
- No grant provisioning, grant administration, schema, seed, migration, or lifecycle file was changed by the issue-202 candidate.

### Build & Tests Execution

**Build**: ✅ Passed

```text
Command: scripts/worktree-compose --profile checks run --build --rm python-checks
Exit code: 0
All checks passed. Ruff check and format, import contracts, mypy, dependency lock,
and Alembic checks completed successfully before pytest.
```

**Tests**: ✅ 773 passed / ❌ 0 failed / ⚠️ 1 skipped

```text
Command: scripts/worktree-compose --profile checks run --build --rm python-checks
Collected 774 items
======================= 773 passed, 1 skipped in 13.29s ========================
No new upgrade operations detected.
The one skipped test is the explicitly opt-in live OpenRouter test.
Output SHA256: sha256:bc7d27cc827eccf0f8ae9dfa8a012e02dee9bcd77f462f06815b2b901e6bd0f5
Full log: /tmp/issue202-final-reverify-full.log
```

**Focused runtime evidence**: ✅ 34 passed / ❌ 0 failed

```text
Command: scripts/worktree-compose --profile checks run --build --rm python-checks pytest -q tests/test_governed_authorization.py tests/test_control_plane.py tests/test_control_authorization_order.py tests/test_control_acceptance.py
34 passed in 4.13s
Output SHA256: sha256:55f94540a4e1c73b57fccae4e1305841fabeb9e30e3e8dadefce82c830153e32
Focused log: /tmp/issue202-final-reverify-focused.log
```

The focused runtime suite re-proved validation before shared authentication/authorization for create/list/get; denied and unknown credentials stop before provider or principal repository effects; authorized missing reads remain 404; allowed control evidence carries a protected `grant_ref`; and the documentation-only future-consumer contract is executable. The synthetic declared-secure route probe detects a direct adapter bypass.

**Coverage**: 88% statement coverage for the four changed runtime modules; branch coverage not configured.

```text
Command: scripts/worktree-compose --profile checks run --build --rm python-checks sh -c 'COVERAGE_FILE=/tmp/issue202-final-reverify.coverage coverage run --source=src/sre_agent -m pytest -q && COVERAGE_FILE=/tmp/issue202-final-reverify.coverage coverage report -m --include="src/sre_agent/gateway/authentication.py,src/sre_agent/gateway/responses.py,src/sre_agent/control/service.py,src/sre_agent/gateway/audit.py"'
773 passed, 1 skipped in 18.26s
Coverage output SHA256: sha256:2dc9bc4dc96ecfab8408c2f74e442c73cd2aecfeb847c430cb36933347763edf
Coverage log: /tmp/issue202-final-reverify-coverage.log
```

### Spec Compliance Matrix

| Requirement | Scenario | Covering test/evidence | Result |
|-------------|----------|------------------------|--------|
| Ordered, correlated request handling | Invalid request is rejected before routing | `tests/test_responses.py::test_validation_and_authentication_fail_before_upstream` | ✅ COMPLIANT |
| Ordered, correlated request handling | Authenticated allow reaches routing only after authorization | `tests/test_responses.py::test_allow_calls_once_outside_transactions_and_commits_protected_readback` | ✅ COMPLIANT |
| Authorize before routing and invocation | Restricted principal has no upstream traffic | `tests/test_responses.py::test_public_responses_credential_matrix`; `tests/test_governed_authorization.py::test_real_routes_stop_denied_credentials_before_business_effects` | ✅ COMPLIANT |
| Authorize before routing and invocation | Missing or inactive resource is indistinguishable | `tests/test_responses.py::test_deny_and_missing_resources_are_indistinguishable_without_routing`; `tests/test_responses.py::test_inactive_resource_stops_before_grant_and_routing_reads` | ✅ COMPLIANT |
| Bearer and governed-route contract | Runtime contract exposes security | `tests/test_responses_openapi.py::test_runtime_operation_declares_bearer_security_and_governed_scope`; `tests/test_governed_authorization.py::test_current_governed_operations_have_one_declared_contract` | ✅ COMPLIANT |
| Bearer and governed-route contract | Invalid credentials fail before effects | `tests/test_authentication.py::test_all_authentication_failures_are_uniform_and_stop_before_resources_or_upstream`; `tests/test_responses.py::test_public_responses_credential_matrix` | ✅ COMPLIANT |
| Non-enumerating resource denial | Missing and unauthorized resources are indistinguishable | `tests/test_responses.py::test_deny_and_missing_resources_are_indistinguishable_without_routing`; `tests/test_control_acceptance.py::test_conflict_inactive_auth_and_hidden_denial_audit` | ✅ COMPLIANT |
| Non-enumerating resource denial | Authorized missing principal remains 404 | `tests/test_control_plane.py::test_principal_operations_use_shared_governed_authorization_before_effects` | ✅ COMPLIANT |
| Future-only MCP and administrative controls | Existing administration stays behaviorally stable | `tests/test_control_acceptance.py::test_all_eight_routes_with_replays_expiry_and_revocation`; `tests/test_control_acceptance.py::test_conflict_inactive_auth_and_hidden_denial_audit` | ✅ COMPLIANT |
| Future-only MCP and administrative controls | Future unauthorized MCP operation | No MCP runtime exists by explicit scope; future-only scenario is intentionally N/A until that runtime exists | ✅ COMPLIANT (future-only) |
| Current administration and behavioral bypass coverage | Create denial is uniform | `tests/test_governed_authorization.py::test_real_routes_stop_denied_credentials_before_business_effects`; `tests/test_control_plane.py::test_principal_operations_use_shared_governed_authorization_before_effects` | ✅ COMPLIANT |
| Current administration and behavioral bypass coverage | List denial is uniform | `tests/test_governed_authorization.py::test_real_routes_stop_denied_credentials_before_business_effects`; `tests/test_control_plane.py::test_principal_operations_use_shared_governed_authorization_before_effects` | ✅ COMPLIANT |
| Current administration and behavioral bypass coverage | Get denial is uniform | `tests/test_governed_authorization.py::test_real_routes_stop_denied_credentials_before_business_effects`; `tests/test_control_plane.py::test_principal_operations_use_shared_governed_authorization_before_effects` | ✅ COMPLIANT |
| Current administration and behavioral bypass coverage | Invalid credentials fail uniformly | `tests/test_governed_authorization.py::test_real_routes_stop_denied_credentials_before_business_effects`; `tests/test_control_plane.py::test_principal_operations_use_shared_governed_authorization_before_effects` | ✅ COMPLIANT |
| Current administration and behavioral bypass coverage | Missing governed declaration is rejected | `tests/test_governed_authorization.py::test_current_governed_operations_have_one_declared_contract` | ✅ COMPLIANT |
| Current administration and behavioral bypass coverage | Declared-secure route cannot skip authorization | `tests/test_governed_authorization.py::test_declared_secure_route_probe_detects_direct_adapter_bypass` | ✅ COMPLIANT |
| Governed extension guidance | Future types stay documented only | `tests/test_governed_authorization.py::test_future_consumer_guidance_is_documentation_only` | ✅ COMPLIANT |
| Record every terminal attempt | Allow is durably represented | `tests/test_responses.py::test_allow_calls_once_outside_transactions_and_commits_protected_readback`; `tests/test_responses.py::test_public_responses_credential_matrix` | ✅ COMPLIANT |
| Record every terminal attempt | Deny is durably represented without routing | `tests/test_responses.py::test_deny_and_missing_resources_are_indistinguishable_without_routing`; `tests/test_responses.py::test_public_responses_credential_matrix` | ✅ COMPLIANT |
| Audit evidence covers every governed operation | Allowed control operation retains its grant | `tests/test_control_plane.py::test_principal_operations_use_shared_governed_authorization_before_effects`; `tests/test_control_acceptance.py::test_conflict_inactive_auth_and_hidden_denial_audit` | ✅ COMPLIANT |
| Audit evidence covers every governed operation | Audit failure suppresses release | `tests/test_responses.py::test_audit_commit_failure_suppresses_success_and_denial`; `tests/test_control_acceptance.py::test_audit_append_failure_suppresses_ordinary_secret` | ✅ COMPLIANT |

**Compliance summary**: 21/21 scenarios compliant. The MCP scenario is explicitly future-only and no current runtime or endpoint was added, as required by the specification.

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| Ordered, correlated request handling | ✅ Implemented | Responses validates `ResponsesRequest` before `authorize_governed_access`; control create/list/get validate idempotency/body/query/path input before the shared boundary. Correlation remains in terminal audit events. |
| Authorize before routing and invocation | ✅ Implemented | `authorize_governed_access` evaluates before Responses assignment/provider effects; denied administration returns before principal repository access. |
| Bearer and governed-route contract | ✅ Implemented | Shared bearer parsing, `HTTPBearer`, and server-owned `x-governed-scope` declarations cover the four issue-202 operations. |
| Non-enumerating resource denial | ✅ Implemented | Denied current operations return 403 `resource_unavailable`; only an authorized missing principal returns 404 `resource_not_found`. |
| Future-only MCP and administrative controls | ✅ Implemented | Existing grants are consumed; no grant provisioning/administration, role inference, schema, seed, migration, or lifecycle behavior was introduced. |
| Current administration and behavioral bypass coverage | ✅ Implemented | Inventory, real TestClient denial matrix, zero-effect spies, validation-order tests, and synthetic direct-adapter bypass detection pass. |
| Governed extension guidance | ✅ Implemented | `docs/architecture.md` requires future consumers to use the shared governed entry rule and explicitly keeps future runtimes documentation-only; executable contract test passes. |
| Record every terminal attempt | ✅ Implemented | Existing Responses and control audit tests cover allow, deny, invalid outcomes, correlation, latency, and protected matched-grant evidence. |
| Audit evidence covers every governed operation | ✅ Implemented | All four operations preserve validation → authentication → authorization → resolution/execution → audit/release; audit failure suppresses release. |

### Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| One shared credential-to-decision boundary | ✅ Yes | `authorize_governed_access` is used by Responses and the three issue-202 principal operations. |
| Operation validation before shared authorization | ✅ Yes | Current remediation places create/list/get validation before the shared call while retaining authorization before business effects. |
| Existing decision engine and grant inventory remain authoritative | ✅ Yes | The existing repositories and `AuthorizationDecisionEngine` remain the only policy path; grants are neither provisioned nor administrated here. |
| Bearer plus server-owned governed metadata on all four routes | ✅ Yes | Runtime OpenAPI and inventory tests pass for the exact four routes. |
| Audit-before-release and protected matched-grant evidence | ✅ Yes | Allowed control and Responses terminals preserve protected grant evidence; audit failure returns 503 and suppresses payloads. |
| Synthetic behavioral bypass proof | ✅ Yes | The direct-adapter synthetic route is declared secure but intentionally bypasses governance, and the probe fails closed by detecting the effect. |
| Future consumer guidance without speculative runtime | ✅ Yes | Documentation and executable contract coverage add no MCP, skill, or knowledge endpoint. |

### Issues Found

**CRITICAL**: None.  
**WARNING**: None.  
**SUGGESTION**: Branch coverage was not configured for this repository check; add it only if a future quality threshold requires branch-level evidence.

### TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | `apply-progress.md` contains RED/GREEN/Triangulate/Safety Net/Refactor evidence for all 9 task rows plus the remediation cycle. |
| All tasks have tests | ✅ | 8/8 executable tasks have test files; task 3.3 is documentation-only and has the executable guidance contract test. |
| RED confirmed (tests exist) | ✅ | 8/8 executable task test files exist and the reported RED evidence is present; the documentation task is N/A for RED. |
| GREEN confirmed (tests pass) | ✅ | Focused 34-test remediation suite and full 773-test suite pass on the current candidate. |
| Triangulation adequate | ✅ | Responses, administration, invalid-order, route-inventory, and denied-effect matrices cover distinct statuses and effects. |
| Safety net for modified files | ✅ | Existing-file safety nets are recorded; the new Unit 3 test file correctly reports N/A, and remediation records an 18-test pre-edit safety net. |
| Assertion quality | ✅ | Inspected changed tests contain no tautologies, ghost loops, assertion-free production paths, smoke-only checks, or unaccompanied empty-effect assertions. |

**TDD Compliance**: ✅ All applicable checks passed.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Python unit/integration | 773 full-suite cases; 34 focused governance cases | Repository suite; 4 focused files | pytest, FastAPI TestClient/ASGI, PostgreSQL |
| E2E/browser | Not part of the required Python verification command | Existing Playwright files were not needed for the four-route SDD matrix | Playwright (not invoked) |
| **Total executed** | **773 full-suite cases; 34 focused cases** | | |

The runtime evidence uses the composed FastAPI application and PostgreSQL boundary. No claim is made that the exact Python verification command executes the separate browser workflow.

### Changed File Coverage

| File | Line % | Branch % | Uncovered Lines | Rating |
|------|--------|----------|-----------------|--------|
| `src/sre_agent/control/service.py` | 82% | — | 232, 417-440, 475, 613, 623, 681, 713, 723, 733, 744-745, 791-836, 868, 880, 882-883, 920-932, 957, 967, 996-1008, 1028, 1038, 1048, 1059-1060, 1093-1181, 1262-1263, 1349-1350, 1357 | ⚠️ Acceptable |
| `src/sre_agent/gateway/audit.py` | 100% | — | — | ✅ Excellent |
| `src/sre_agent/gateway/authentication.py` | 94% | — | 70-71 | ✅ Acceptable |
| `src/sre_agent/gateway/responses.py` | 99% | — | 204, 270 | ✅ Excellent |
| **Aggregate** | **88% statements (641 total; 78 missed)** | — | — | ⚠️ Informational |

Coverage was generated by the supplemental full pytest run and is not a delivery threshold in `openspec/config.yaml`.

### Assertion Quality

**Assertion quality**: ✅ All inspected assertions verify real behavior. Effect-empty assertions are paired with requests or production calls and positive behavior checks; no tautologies, ghost loops, smoke-only tests, or mock-heavy test-file violation was found.

### Quality Metrics

**Linter**: ✅ Ruff check passed.  
**Formatter**: ✅ Ruff format check passed (`87 files already formatted`).  
**Type checker**: ✅ Configured mypy source set passed.  
**Import contracts**: ✅ 4 contracts kept, 0 broken.  
**Dependency lock**: ✅ `uv lock --check` passed.  
**Migration check**: ✅ Alembic reported no new upgrade operations.  
**Diff hygiene**: ✅ `git diff --check` passed.

### Execution Environment Notes

- Verification used the current worktree `/home/creep/.codex/worktrees/ed92/sre-agent` and candidate commit `105edfbb41ef06202f7b29fa373e1ae06fb461f0`.
- The first unprivileged Docker invocation was denied by the host socket permission; the same exact required command was rerun with Docker access and exited 0. This is host setup evidence, not a candidate failure.
- Compose `--rm` removed each one-shot check container. The reusable checks database service remained managed by the checks profile; no test process was left running.
- No source, test, configuration, PR, commit, push, merge, archive, or ruleset changes were made by this verification. The only project-file write permitted after admission is replacement of this `verify-report.md` with these identical bytes.
