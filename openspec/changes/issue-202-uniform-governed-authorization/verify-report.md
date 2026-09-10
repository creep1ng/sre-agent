```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:5b2c60d6d43f2eff992aff32a35b67ad37dbae87f9e3838eb0497d53f14082d4
verdict: pass
blockers: 0
critical_findings: 0
requirements: 9/9
scenarios: 21/21
test_command: "scripts/worktree-compose --profile checks run --build --rm python-checks"
test_exit_code: 0
test_output_hash: sha256:74421565d60fca2985471e0910e6be9cc68d543db366781305dffb347b508697
build_command: "scripts/worktree-compose --profile checks run --build --rm python-checks"
build_exit_code: 0
build_output_hash: sha256:74421565d60fca2985471e0910e6be9cc68d543db366781305dffb347b508697
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

All proposal, exploration, specification, design, task, apply-progress, and previous verify-report artifacts were read. Native status reported `artifactStore: openspec`, `verify: ready`, and `taskProgress: 9/9`. Actual spec heading counts are 9 requirements and 21 scenarios. This report is freshly bound to the integrated candidate `b3619603387e77fe8678e20bb5f680de3f0fe785`, whose first parent is the previous verified stack report commit and whose synchronized ancestry incorporates current `origin/main` at `eb0d1c5a0edc7730c31c2bd15538ae8788bc8aff`.

### Candidate Identity and Scope

- Candidate commit: `b3619603387e77fe8678e20bb5f680de3f0fe785`.
- Candidate branch: `codex/issue-202-verify`; its local HEAD is the integrated synchronization candidate. The worktree has no tracked modifications before report persistence.
- Integrated base: `origin/main` at `eb0d1c5a0edc7730c31c2bd15538ae8788bc8aff`, including the merged PR #229 principal-management UI/API slice.
- Fresh evidence manifest: `sha256:5b2c60d6d43f2eff992aff32a35b67ad37dbae87f9e3838eb0497d53f14082d4`; it binds the candidate and integrated base, issue-202 changed files, fresh Python full/focused/coverage output, browser stack lifecycle output, and the principal Playwright output. This report is excluded to avoid a self-referential digest.
- No grant provisioning, grant administration, schema, seed, migration, lifecycle, MCP, skill, or knowledge runtime was added by issue #202. The integrated base's principal-management UI was exercised as a compatibility consumer, not modified by this candidate.

### Build & Tests Execution

**Build**: ✅ Passed

```text
Command: scripts/worktree-compose --profile checks run --build --rm python-checks
Exit code: 0
All configured checks passed. The checks image built successfully; formatting, import contracts,
static checks, dependency lock, migration/upgrade checks, and pytest completed successfully.
87 files were already formatted; 4 import contracts were kept and 0 broken.
Build/test output SHA256: sha256:74421565d60fca2985471e0910e6be9cc68d543db366781305dffb347b508697
```

**Tests**: ✅ 773 passed / ❌ 0 failed / ⚠️ 1 skipped

```text
Command: scripts/worktree-compose --profile checks run --build --rm python-checks
Collected 774 items
======================= 773 passed, 1 skipped in 11.99s ========================
The single skip is the explicitly opt-in live OpenRouter test.
Output SHA256: sha256:74421565d60fca2985471e0910e6be9cc68d543db366781305dffb347b508697
Full log: /tmp/issue202-integrated-full.log
```

**Focused authorization evidence**: ✅ 34 passed / ❌ 0 failed

```text
Command: scripts/worktree-compose --profile checks run --build --rm python-checks pytest -q tests/test_governed_authorization.py tests/test_control_plane.py tests/test_control_authorization_order.py tests/test_control_acceptance.py
34 passed in 3.79s
Output SHA256: sha256:e3f3f5bd38a9b8e1e6a64bbae9206bfc4764cdea5337db6542bf8bd92f03294e
Focused log: /tmp/issue202-integrated-focused.log
```

**Coverage**: 88% statement coverage for the four changed runtime modules; branch coverage is not configured.

```text
Command: scripts/worktree-compose --profile checks run --build --rm python-checks sh -c 'COVERAGE_FILE=/tmp/issue202-integrated.coverage coverage run --source=src/sre_agent -m pytest -q && COVERAGE_FILE=/tmp/issue202-integrated.coverage coverage report -m --include="src/sre_agent/gateway/authentication.py,src/sre_agent/gateway/responses.py,src/sre_agent/control/service.py,src/sre_agent/gateway/audit.py"'
773 passed, 1 skipped in 16.48s
Coverage output SHA256: sha256:13595ddee2ca0a86647a5254a8ce1dd29f89747c939a9b692a4f6c2e44433b73
Coverage log: /tmp/issue202-integrated-coverage.log
```

Changed runtime coverage:

| File | Statements | Missed | Line % | Branch % | Uncovered lines | Rating |
|------|-----------:|-------:|-------:|---------:|-----------------|--------|
| `src/sre_agent/control/service.py` | 413 | 74 | 82% | — | 232, 417-440, 475, 613, 623, 681, 713, 723, 733, 744-745, 791-836, 868, 880, 882-883, 920-932, 957, 967, 996-1008, 1028, 1038, 1048, 1059-1060, 1093-1181, 1262-1263, 1349-1350, 1357 | ⚠️ Acceptable |
| `src/sre_agent/gateway/audit.py` | 50 | 0 | 100% | — | — | ✅ Excellent |
| `src/sre_agent/gateway/authentication.py` | 36 | 2 | 94% | — | 70-71 | ✅ Excellent |
| `src/sre_agent/gateway/responses.py` | 142 | 2 | 99% | — | 204, 270 | ✅ Excellent |
| **Aggregate** | **641** | **78** | **88%** | — | — | ⚠️ Informational |

**Supplemental integrated browser evidence**: ✅ 8 passed / ❌ 0 failed

```text
Stack: disposable Compose project `issue202-integrated-e2e` using `compose.yaml` + `compose.e2e.yaml`; ephemeral credentials were supplied through `/tmp/issue202-integrated-e2e.env`.
Command: scripts/worktree-compose --env-file /tmp/issue202-integrated-e2e.env -f compose.yaml -f compose.e2e.yaml --project-name issue202-integrated-e2e --profile e2e run --build --rm e2e npx playwright test --config=playwright.production.config.js tests/browser/principals.spec.js
Running 8 tests using 1 worker
8 passed (7.7s)
Browser output SHA256: sha256:43ef5cfb66ecafee8a74b8f57bd4479ff13d6e3a8836783996250b9240cd6eb9
Startup output SHA256: sha256:e69e3318926865bed778a9d588675532179de5bdcae8fcb203001087515a229d
Cleanup output SHA256: sha256:1f17532f7b9c870b1fc9d38a40b5b953c2b3995c86c4afe4f830cbd055931738
```

The browser suite covered real principal listing, inline detail, invalid credential 401, restricted identity hiding, authorized missing-principal 404, stale list/detail session clearing, and offline recovery. The Compose stack and volume were removed successfully after the run.

### Spec Compliance Matrix

| Requirement | Scenario | Covering test/evidence | Result |
|-------------|----------|------------------------|--------|
| Ordered, correlated request handling | Invalid request is rejected before routing | `tests/test_responses.py::test_validation_and_authentication_fail_before_upstream`; `tests/test_governed_authorization.py::test_principal_validation_precedes_shared_authorization` | ✅ COMPLIANT |
| Ordered, correlated request handling | Authenticated allow reaches routing only after authorization | `tests/test_responses.py::test_allow_calls_once_outside_transactions_and_commits_protected_readback` | ✅ COMPLIANT |
| Authorize before routing and invocation | Restricted principal has no upstream traffic | `tests/test_responses.py::test_public_responses_credential_matrix`; `tests/test_governed_authorization.py::test_real_routes_stop_denied_credentials_before_business_effects` | ✅ COMPLIANT |
| Authorize before routing and invocation | Missing or inactive resource is indistinguishable | `tests/test_responses.py::test_deny_and_missing_resources_are_indistinguishable_without_routing`; `tests/test_responses.py::test_inactive_resource_stops_before_grant_and_routing_reads` | ✅ COMPLIANT |
| Bearer and governed-route contract | Runtime contract exposes security | `tests/test_responses_openapi.py::test_runtime_operation_declares_bearer_security_and_governed_scope`; `tests/test_governed_authorization.py::test_current_governed_operations_have_one_declared_contract` | ✅ COMPLIANT |
| Bearer and governed-route contract | Invalid credentials fail before effects | `tests/test_authentication.py::test_all_authentication_failures_are_uniform_and_stop_before_resources_or_upstream`; `tests/test_responses.py::test_public_responses_credential_matrix` | ✅ COMPLIANT |
| Non-enumerating resource denial | Missing and unauthorized resources are indistinguishable | `tests/test_responses.py::test_deny_and_missing_resources_are_indistinguishable_without_routing`; `tests/test_control_acceptance.py::test_conflict_inactive_auth_and_hidden_denial_audit` | ✅ COMPLIANT |
| Non-enumerating resource denial | Authorized missing principal remains 404 | `tests/test_control_plane.py::test_principal_operations_use_shared_governed_authorization_before_effects`; `tests/browser/principals.spec.js` hidden principal test | ✅ COMPLIANT |
| Future-only MCP and administrative controls | Existing administration stays behaviorally stable | `tests/test_control_acceptance.py::test_all_eight_routes_with_replays_expiry_and_revocation`; `tests/test_control_acceptance.py::test_conflict_inactive_auth_and_hidden_denial_audit`; principal browser suite | ✅ COMPLIANT |
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

**Compliance summary**: 21/21 scenarios compliant. The MCP scenario is explicitly future-only; no current MCP/tool runtime or endpoint was added.

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| Ordered, correlated request handling | ✅ Implemented | Responses and principal create/list/get validate client input before `authorize_governed_access`; one request ID remains attached to terminal audit events. |
| Authorize before routing and invocation | ✅ Implemented | The shared helper evaluates exact grants before Responses assignment/provider effects and before principal repository business effects. |
| Bearer and governed-route contract | ✅ Implemented | HTTP Bearer and server-owned `x-governed-scope` declarations cover the four issue-202 operations. |
| Non-enumerating resource denial | ✅ Implemented | Denied current operations return 403 `resource_unavailable`; only an authorized missing principal returns 404 `resource_not_found`. |
| Future-only MCP and administrative controls | ✅ Implemented | Existing grants are consumed; no grant provisioning/administration, role inference, schema, seed, migration, or lifecycle behavior was introduced. |
| Current administration and behavioral bypass coverage | ✅ Implemented | Runtime inventory, TestClient denial matrix, zero-effect spies, validation-order tests, synthetic bypass detection, and the integrated principal browser suite pass. |
| Governed extension guidance | ✅ Implemented | `docs/architecture.md` requires the shared governed entry rule and keeps future runtimes documentation-only. |
| Record every terminal attempt | ✅ Implemented | Responses/control audit tests cover allow, deny, invalid outcomes, correlation, latency, and protected matched-grant evidence. |
| Audit evidence covers every governed operation | ✅ Implemented | All four operations preserve validation → authentication → authorization → resolution/execution → audit/release; audit failure suppresses release. |

### Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| One shared credential-to-decision boundary | ✅ Yes | `authorize_governed_access` is used by Responses and the three issue-202 principal operations. |
| Operation validation before shared authorization | ✅ Yes | Remediation places create/list/get validation before the shared call while retaining authorization before business effects. |
| Existing decision engine and grant inventory remain authoritative | ✅ Yes | Existing repositories and `AuthorizationDecisionEngine` remain the only policy path; grants are neither provisioned nor administered here. |
| Bearer plus server-owned governed metadata on all four routes | ✅ Yes | Runtime OpenAPI and inventory tests pass for the exact four routes. |
| Audit-before-release and protected matched-grant evidence | ✅ Yes | Allowed control/Responses terminals preserve protected grant evidence; audit failure returns 503 and suppresses payloads. |
| Synthetic behavioral bypass proof | ✅ Yes | The direct-adapter synthetic route is declared secure but intentionally bypasses governance, and the probe detects the effect. |
| Future consumer guidance without speculative runtime | ✅ Yes | Documentation and executable guidance coverage add no MCP, skill, or knowledge endpoint. |

### Issues Found

**CRITICAL**: None.
**WARNING**: None.
**SUGGESTION**: Branch coverage is not configured. The browser principal suite was run as supplemental integrated evidence, while the required Python command remains the SDD verification authority.

### TDD Compliance

| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ✅ | `apply-progress.md` contains RED/GREEN/Triangulate/Safety Net/Refactor evidence for all 9 task rows plus remediation. |
| All tasks have tests | ✅ | 8/8 executable tasks have test files; task 3.3 is documentation-only and has an executable guidance contract test. |
| RED confirmed (tests exist) | ✅ | 8/8 executable task test files exist and reported RED evidence is present; the documentation task is N/A for RED. |
| GREEN confirmed (tests pass) | ✅ | Focused 34-test governance suite and full 773-test suite pass on the integrated candidate. |
| Triangulation adequate | ✅ | Responses, administration, invalid-order, route-inventory, denied-effect, audit-failure, and browser consumer cases cover distinct statuses and effects. |
| Safety net for modified files | ✅ | Existing-file safety nets are recorded; the new Unit 3 test file correctly reports N/A, and remediation records an 18-test pre-edit safety net. |
| Assertion quality | ✅ | Inspected changed tests contain no tautologies, ghost loops, assertion-free production paths, smoke-only checks, or unaccompanied empty-effect assertions. |

**TDD Compliance**: ✅ All applicable checks passed.

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Python unit/integration | 773 full-suite cases; 34 focused governance cases | Repository suite; 4 focused files | pytest, FastAPI TestClient/ASGI, PostgreSQL |
| E2E/browser | 8 principal-management cases passed | `tests/browser/principals.spec.js` | Playwright 1.63.0 in disposable production Compose topology |
| **Total executed** | **773 full-suite cases; 34 focused cases; 8 browser cases** | | |

The browser evidence uses the integrated API/web images and real same-origin proxy. The stack was removed after successful completion.

### Assertion Quality

**Assertion quality**: ✅ All inspected assertions verify real behavior. Effect-empty assertions are paired with requests, response/status assertions, and positive behavior coverage; no tautologies, ghost loops, smoke-only tests, or unaccompanied empty-effect assertions were found.

### Quality Metrics

**Linter**: ✅ Configured checks passed.
**Formatter**: ✅ Ruff format passed (`87 files already formatted`).
**Type checker**: ✅ Configured mypy source set passed.
**Import contracts**: ✅ 4 contracts kept, 0 broken.
**Dependency lock**: ✅ Locked dependencies resolved successfully.
**Migration/upgrade check**: ✅ No new upgrade operations detected.
**Diff hygiene**: ✅ `git diff --check` passed for non-report candidate files.

### Verdict

**PASS** — integrated candidate `b361960` satisfies all 9 requirements and 21 scenarios with fresh Docker-backed full, focused, coverage, and principal-browser evidence. The report is archive-ready; only the explicit branch-coverage suggestion remains.
