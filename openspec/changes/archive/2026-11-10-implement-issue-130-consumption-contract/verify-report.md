```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:b49565e891e5d4a6f90847ed63afd4bd218dc9895a6db57fe898dbcec022ab32
verdict: pass
blockers: 0
critical_findings: 0
requirements: 9/9
scenarios: 17/17
test_command: "docker compose --project-directory /home/creep/.codex/worktrees/38f2/sre-agent --env-file /home/creep/.codex/worktrees/38f2/sre-agent/.env.example --env-file /tmp/sre-agent-38f2.env -f /home/creep/.codex/worktrees/38f2/sre-agent/compose.yaml --project-name issue130-final-python --profile checks run --build --rm python-checks"
test_exit_code: 0
test_output_hash: sha256:caf1107f132e82617d05cc5010ab575d0ffa0e4e7b0eb1d2590d5e1c0d6ac243
build_command: "npm --prefix schemas/tooling run validate:releases"
build_exit_code: 0
build_output_hash: sha256:d1be6f1f0eee2b11713733390da5d245fe4cde465af909d6a8f211ea9e3d8336
```

## Verification Report

**Change**: `implement-issue-130-consumption-contract`
**Candidate**: `168f0348a4049eaf2bcc7f8d6a436d64599a96c5` (`codex/issue-130-apply-evidence`)
**Version**: `2.1.0` on `/v1`
**Mode**: Standard (strict TDD disabled)

### Completeness

| Metric | Value |
|---|---:|
| Tasks total | 14 |
| Tasks complete | 14 |
| Tasks incomplete | 0 |
| Requirements | 9/9 |
| Scenarios | 17/17 |

The candidate was clean at verification start and end. Native status reported `apply=all_done`, `verify=ready`, and no existing issue-130 verify report. No source, Git, PR, merge, or rebase changes were made by verification.

### Build & Tests Execution

**Full Docker Python checks**: ✅ 801 passed / 1 skipped / exit 0

Command output hash: `sha256:caf1107f132e82617d05cc5010ab575d0ffa0e4e7b0eb1d2590d5e1c0d6ac243`

The checks image completed isolation assertions, shellcheck, Ruff, format, locked-UV, import-lint, mypy, the full pytest suite, and `alembic check`; it ended with `No new upgrade operations detected.` The full suite included response OpenAPI parity, migration, provider consumption, persistence, authorization ordering, and the browser API seam test.

**Node contract tooling**: ✅ 78 passed / 0 failed / exit 0

Command: `npm --prefix schemas/tooling test`
Output hash: `sha256:b2f0171a6b4438f3890e356b0c798f298a2c03d673c5c0b850290571d9e0c931`

**Published releases**: ✅ all 7 releases validated / exit 0

Command: `npm --prefix schemas/tooling run validate:releases`
Output hash: `sha256:d1be6f1f0eee2b11713733390da5d245fe4cde465af909d6a8f211ea9e3d8336`

**OpenAPI**: ✅ default canonical checks and explicit 2.1.0 control-plane/responses bundles passed

- `npm --prefix schemas/tooling run lint:openapi` — exit 0; output hash `sha256:5332eb5a59a38337d3ae8ce27a6adcdc0ae8c8a21f00edf8234205957dba2086`.
- Explicit `runReleaseOpenapi(..., "2.1.0")` for both APIs — exit 0; output hash `sha256:3919be498347e6848be02ea9859519c1c2a945b6972cebed7bd903a90afd19e5`.

**Issue-130 conformance**: ✅ exit 0

- `npm --prefix schemas/tooling run conformance -- --consumer issue-130 --release 2.1.0` — output hash `sha256:89138b9fa10d7464ec7b62d04f931edf168c616be14c8911ee315d085be2d652`.
- Explicit 2.1.0 coverage — 7 consumers / 7 obligations; output hash `sha256:db0b3a17da70078c1d2970aae8c99f8f43dcd1bb1bfc35063763502c52d27e6e`.

**Issue-14 response/audit Compose harness**: ✅ 29 passed / exit 0

Successful isolated retry output hash: `sha256:93b872c5507ac3fec0b693712c54a95f63014f9c0818af9fc3341a5dc678cce0`.

The first network creation attempt failed before test execution because Docker's predefined address pools were exhausted. It did not execute candidate code; the same harness then passed on the already-created isolated verification network `issue130-final-python_runtime`.

**Coverage**: ➖ Not measured by the authorized full-check command.

### Spec Compliance Matrix

| Requirement / scenario | Covering runtime evidence | Result |
|---|---|---|
| Governed routing — alias resolves and selected-provider evidence agrees | `tests/test_openrouter.py::test_create_uses_server_routing_once_without_fallback_or_storage`; full Python suite | ✅ COMPLIANT |
| Governed routing — invalid/contradictory provider evidence | `tests/test_openrouter.py::test_invalid_or_extra_provider_evidence_fails_closed`; `test_incomplete_or_contradictory_completed_responses_fail_closed` | ✅ COMPLIANT |
| Authorized completion exposes normalized consumption | `tests/test_responses.py::test_authorized_completion_projects_the_same_consumption_to_public_and_audit` | ✅ COMPLIANT |
| Deny/failure expose no false usage | `tests/test_responses.py::test_deny_and_missing_resources_are_indistinguishable_without_routing`; `test_provider_failures_are_normalized_without_fallback` | ✅ COMPLIANT |
| 2.1.0 is additive and 2.0.0 remains immutable | `release-validation.test.mjs` 2.1 compatibility/additive tests; all-release validation; independent 156-file byte comparison (0 changed) | ✅ COMPLIANT |
| Closed projection rejects unknown/negative drift | `tests/test_governance_dto.py::test_consumption_is_closed_and_preserves_exact_decimal_text`; `test_consumption_rejects_invalid_invariants`; Node schema tests | ✅ COMPLIANT |
| Complete provider usage/billing is authoritative and exact | `tests/test_openrouter.py::test_create_normalizes_openrouter_usage_and_discards_raw_body`; `tests/test_openrouter_consumption_json.py`; exact decimal and timestamp assertions | ✅ COMPLIANT |
| Partial/malformed evidence remains explicit | `tests/test_openrouter.py::test_create_makes_missing_or_invalid_usage_explicit`; `test_create_discards_cost_without_valid_provider_timestamp`; DTO partial-billing rejection | ✅ COMPLIANT |
| Successful completion without usage is `absent` | `tests/test_responses.py::test_authorized_completion_without_evidence_is_absent_not_zero` | ✅ COMPLIANT |
| Timeout/error/cache/fallback evidence never becomes zero | `tests/test_openrouter.py::test_provider_failure_without_evidence_is_explicitly_unavailable`; response failure normalization; 2.1 unavailable fixtures | ✅ COMPLIANT |
| Public and audit projections are equal and metadata-only | response same-projection test; `tests/test_persistence_projections.py::test_audit_projection_round_trips_consumption_without_provider_content` | ✅ COMPLIANT |
| Pre-routing denial remains consumption-free | `tests/test_responses.py::test_denial_never_resolves_an_assignment`; denied DTO and release fixtures | ✅ COMPLIANT |
| Deterministic fixtures cover complete/partial/absent/unavailable/invalid/outcome states | explicit issue-130 conformance; `consumption.states`, negative invariant/partial/context/raw-body fixtures; all-release validation | ✅ COMPLIANT |
| Audit redaction/HMAC remains safe with consumption metadata | full audit/governance suite; 2.1 audit redaction and provider-content negative fixtures | ✅ COMPLIANT |
| Authorized complete/partial consumption round-trips through persistence | `tests/test_persistence_repositories.py::test_audit_repository_round_trips_consumption_and_keeps_denials_empty`; projection tests | ✅ COMPLIANT |
| Unavailable evidence is persisted explicitly | response failure tests; `audit.responses.consumption-unavailable` fixture; migration/repository checks | ✅ COMPLIANT |
| Audit failure suppresses release | `tests/test_responses.py::test_audit_commit_failure_suppresses_success_and_denial`; issue-14 harness | ✅ COMPLIANT |

**Compliance summary**: 17/17 scenarios have passing runtime or conformance coverage.

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|---|---|---|
| Immutable 2.1.0 contract | ✅ Implemented | Manifest is immutable/additive over 2.0.0; all 2.0.0 files match origin reference byte-for-byte; 2.1.0 release validation passes. |
| Authoritative provider evidence | ✅ Implemented | OpenRouter usage/cost is normalized once; invalid/missing timestamp cost is discarded; raw provider body is not carried across DTO boundaries. |
| Token/outcome semantics | ✅ Implemented | Non-negative nullable tokens, total invariant, absent/unavailable states, and no-zero failure semantics are enforced. |
| Shared safe projection | ✅ Implemented | One closed DTO is used by response/audit; JSONB persistence preserves exact strings/nulls/context and append-only controls. |
| Deterministic conformance | ✅ Implemented | 121 fixtures, 10 examples, 23 schemas, 2 OpenAPI documents, 7 conformance obligations, and immutable evidence validate. |
| Governed response ordering | ✅ Implemented | #202 shared validation/authn/authz flow remains before routing/provider; no fallback and zero-call denial remain covered. |
| Runtime audit gates | ✅ Implemented | HMAC metadata-only projection, additive migration `20260910_07`, audit-before-release, and failure suppression remain green. |

### Coherence (Design)

| Design decision | Result | Evidence |
|---|---|---|
| OpenRouter `usage` is sole evidence authority | ✅ Followed | Adapter tests and provider source inspect only validated usage/cost fields. |
| Billed cost requires provider timestamp/pricing context | ✅ Followed | DTO/schema allOf require complete billing context; missing timestamp invalidates cost; negative fixture and runtime test cover it. |
| One closed DTO for public/audit projections | ✅ Followed | Shared `Consumption` type and same-projection runtime/persistence tests. |
| Explicit active release, not highest-directory discovery | ✅ Followed | `CONTRACT_VERSION=2.1.0`; runtime parity requires the exact snapshot/manifest; release tests reject drift. |
| Preserve #202 authorization order | ✅ Followed | Full authorization/governed response suite and issue-14 harness pass. |
| Additive migration and immutable snapshots | ✅ Followed | Migration/readback tests and byte comparison pass. |

### Issues Found

**CRITICAL**: None.

**WARNING**: None affecting the candidate. The initial issue-14 Compose network-pool failure occurred before test execution and was resolved without changing source or candidate artifacts.

**SUGGESTION**: None.

### Verdict

**PASS** — all 14 apply tasks, 9 requirements, and 17 scenarios are complete with fresh full-suite, release, conformance, OpenAPI, persistence, and ordered response evidence. Issue #129 may proceed to its dependent contract-only 2.2.0 work; this verification made no changes to issue #129.

## Key Learnings

1. The final issue-130 candidate requires provider timestamp context whenever billed USD is present, and this invariant must remain identical in DTO, generated schema, and release fixtures.
2. Runtime contract parity must select explicit `CONTRACT_VERSION=2.1.0`, never infer the newest published directory.
3. Full Docker verification covered 801 Python tests, while Node contract tooling independently passed 78 tests and all seven published releases.
4. Docker network-pool exhaustion can occur before test execution; reusing an existing isolated verification network allowed the authorized issue-14 harness to complete without candidate changes.
