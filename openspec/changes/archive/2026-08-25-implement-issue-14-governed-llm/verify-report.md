```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:d53d6c5b35c7d632a44138c406b107fe775b6a4ff2aa6ef8e02b43a33cbe4816
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 10/10
scenarios: 17/17
test_command: "docker compose --profile checks run --build --rm python-checks && docker compose --profile issue-14 run --build --rm issue-14-harness && docker compose --profile issue-14 run --rm -v /tmp/issue14_verify_additional.py:/tmp/issue14_verify_additional.py:ro issue-14-harness python /tmp/issue14_verify_additional.py && docker compose --profile checks run --rm -e RUN_OPENROUTER_LIVE_SMOKE=1 python-checks pytest -q tests/test_openrouter_live.py"
test_exit_code: 0
test_output_hash: sha256:64b6c8b814aff522606db065a5468778443795178076edc28aad385899e471cf
build_command: "docker compose --profile checks run --build --rm harness sh -c 'npm --prefix schemas/tooling test && npm --prefix schemas/tooling run validate && npm --prefix schemas/tooling run validate:release -- --release 1.0.0 && npm --prefix schemas/tooling run validate:release -- --release 1.1.0 && npm --prefix schemas/tooling run validate:release -- --release 1.2.0 && npm --prefix schemas/tooling run lint:openapi && npm --prefix schemas/tooling run conformance -- --consumer issue-10 && npm --prefix schemas/tooling run conformance -- --consumer issue-11 && npm --prefix schemas/tooling run conformance -- --consumer issue-13 && npm --prefix schemas/tooling run conformance -- --consumer issue-14 && node --check scripts/showcase.js'"
build_exit_code: 0
build_output_hash: sha256:870f869429ce96694ceddbdbc037de174b04da335f7e91f28225b71351796106
```

## Verification Report

**Change**: `implement-issue-14-governed-llm`  
**Version**: HT-01 1.2.0  
**Mode**: Standard  
**Candidate**: `43ce16d0517827ea8ee8c30c1930fa0315167bf9` (`tree d8abaec8b003708ce128d214e22d3e88388dba35`)

The current candidate satisfies all ten requirements and all seventeen scenarios. Verification used only container-executed build, test, and runtime evidence. No provider secret was supplied, so the live-provider request remained correctly secret-gated and skipped; no real provider traffic was attempted.

### Completeness

| Metric | Value |
|---|---:|
| Tasks total | 10 |
| Tasks complete | 10 |
| Tasks incomplete | 0 |
| Requirements compliant | 10/10 |
| Scenarios compliant | 17/17 |

### Build and Test Execution

| Check | Result | Evidence |
|---|---|---|
| Full Python/container gate | PASS | Ruff check passed; 64 files were formatted; the lock resolved 37 packages; 308 tests passed and the live test skipped once; Alembic reported no new upgrade operations. |
| Deterministic issue-14 harness | PASS | Isolated PostgreSQL plus recording provider: 11 tests passed in 1.19s. |
| Supplementary runtime scenarios | PASS | Secret-free recording-provider probe proved inactive-resource denial, delayed latency, zero governance transactions during provider I/O, and exactly one terminal event for allow, deny, and failure attempts. Probe input hash: `sha256:f8b683373fc1b551b7c57e55d2dbbee99a19533272efe7244c212c723890897d`. |
| Live-smoke gate | PASS | Ordinary full-suite execution skipped the live test; explicit `RUN_OPENROUTER_LIVE_SMOKE=1` without provider configuration also skipped. No provider secret or traffic was used. |
| Contract/build gate | PASS | 68 contract-tooling tests passed; canonical schemas, immutable 1.0.0/1.1.0/1.2.0 releases, both OpenAPI documents, issue-10/11/13/14 conformance, and JavaScript syntax passed in the container. |
| Repository hygiene | PASS | `git diff --check HEAD` exited 0; the working tree remained unchanged apart from the legitimate untracked OpenSpec change directory and this admitted report. |

**Test command** (exit 0; output `sha256:64b6c8b814aff522606db065a5468778443795178076edc28aad385899e471cf`):

```text
docker compose --profile checks run --build --rm python-checks && docker compose --profile issue-14 run --build --rm issue-14-harness && docker compose --profile issue-14 run --rm -v /tmp/issue14_verify_additional.py:/tmp/issue14_verify_additional.py:ro issue-14-harness python /tmp/issue14_verify_additional.py && docker compose --profile checks run --rm -e RUN_OPENROUTER_LIVE_SMOKE=1 python-checks pytest -q tests/test_openrouter_live.py
```

**Build command** (exit 0; output `sha256:870f869429ce96694ceddbdbc037de174b04da335f7e91f28225b71351796106`):

```text
docker compose --profile checks run --build --rm harness sh -c 'npm --prefix schemas/tooling test && npm --prefix schemas/tooling run validate && npm --prefix schemas/tooling run validate:release -- --release 1.0.0 && npm --prefix schemas/tooling run validate:release -- --release 1.1.0 && npm --prefix schemas/tooling run validate:release -- --release 1.2.0 && npm --prefix schemas/tooling run lint:openapi && npm --prefix schemas/tooling run conformance -- --consumer issue-10 && npm --prefix schemas/tooling run conformance -- --consumer issue-11 && npm --prefix schemas/tooling run conformance -- --consumer issue-13 && npm --prefix schemas/tooling run conformance -- --consumer issue-14 && node --check scripts/showcase.js'
```

**Coverage**: Not configured. Scenario compliance is established by the full suite, deterministic PostgreSQL harness, contract conformance, and the bounded supplementary runtime probe.

### Spec Compliance Matrix

| Requirement | Scenario | Runtime coverage | Result |
|---|---|---|---|
| Ordered, correlated request handling | Invalid request is rejected before routing | `tests/test_responses.py::test_validation_and_authentication_fail_before_upstream`; deterministic harness | ✅ COMPLIANT |
| Ordered, correlated request handling | Authenticated allow reaches routing only after authorization | `tests/test_responses.py::test_allow_calls_once_outside_transactions_and_commits_protected_readback`; `tests/test_persistence_repositories.py::test_resource_authorization_view_precedes_assignment_resolution` | ✅ COMPLIANT |
| Authorize before routing and invocation | Restricted principal has no upstream traffic | `tests/test_responses.py::test_deny_and_missing_resources_are_indistinguishable_without_routing[triage-agent]`; deterministic harness | ✅ COMPLIANT |
| Authorize before routing and invocation | Missing or inactive resource is indistinguishable | Checked-in missing-resource case plus supplementary inactive-resource recording-provider probe | ✅ COMPLIANT |
| Resolve bounded routing evidence after allow | Alias resolves and evidence agrees | `tests/test_openrouter.py::test_create_uses_server_routing_once_without_fallback_or_storage`; allowed gateway case | ✅ COMPLIANT |
| Resolve bounded routing evidence after allow | Provider evidence is invalid | `tests/test_openrouter.py::test_invalid_or_extra_provider_evidence_fails_closed`; gateway `evidence_invalid` case | ✅ COMPLIANT |
| Normalize provider outcomes without hidden retries | Upstream failure taxonomy is stable | `tests/test_openrouter.py::test_error_taxonomy_and_retry_after_are_bounded`; `tests/test_responses.py::test_provider_failures_are_normalized_without_fallback` | ✅ COMPLIANT |
| Verification is deterministic with optional live smoke | Recording adapter proves deny behavior | Isolated issue-14 PostgreSQL harness: 11 passed, including deny zero-call and committed audit | ✅ COMPLIANT |
| Verification is deterministic with optional live smoke | Secret-gated live smoke | Default skip and explicit enable-without-secret skip passed; the operator-secret branch was intentionally not invoked | ✅ COMPLIANT |
| Record every terminal attempt | Allow is durably represented | Allowed gateway readback plus supplementary one-event cardinality probe | ✅ COMPLIANT |
| Record every terminal attempt | Deny is durably represented without routing | Denied gateway readback plus supplementary one-event cardinality probe | ✅ COMPLIANT |
| Project metadata safely | Redaction and HMAC projection | `tests/test_responses.py::test_allow_calls_once_outside_transactions_and_commits_protected_readback`; `tests/test_audit.py::test_audit_references_follow_adr_005_domain_separation` | ✅ COMPLIANT |
| Audit acceptance gates release | Audit failure suppresses success | `tests/test_responses.py::test_audit_commit_failure_suppresses_success_and_denial[incident-harness]` | ✅ COMPLIANT |
| Audit acceptance gates release | Audit failure suppresses denial | `tests/test_responses.py::test_audit_commit_failure_suppresses_success_and_denial[restricted-harness]` | ✅ COMPLIANT |
| Preserve request and transaction boundaries | Latency and ordering are durable | Supplementary delayed-provider probe recorded `latency_ms >= 20` before the response returned | ✅ COMPLIANT |
| Preserve request and transaction boundaries | Provider call does not hold governance transaction | Allowed gateway test and supplementary probe both observed zero checked-out governance connections during provider I/O | ✅ COMPLIANT |
| Verify durability and redaction deterministically | Deterministic audit readback | Issue-14 harness plus supplementary allow/deny/failure event-cardinality and protected-field probe | ✅ COMPLIANT |

**Compliance summary**: 17/17 scenarios compliant.

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|---|---|---|
| Ordered, correlated request handling | Implemented | `ResponsesService.create` assigns one UUID, validates/authenticates before safe reads, routes only after allow, and carries the UUID into response and audit. |
| Authorize before routing and invocation | Implemented | `authorization_view()` selects only resource type, ID, and status; deny exits before `resolve_assignment()` and provider invocation. |
| Bounded routing evidence | Implemented | `OpenRouterProvider` sends one selected provider with fallbacks/storage/streaming disabled and rejects absent, contradictory, multi-selected, or mismatched evidence. |
| Stable provider normalization | Implemented | Timeout, availability, invalid evidence, and invalid response map to the closed HT-01 taxonomy; no retry loop exists. |
| Deterministic verification/live smoke | Implemented | Recording-provider and isolated PostgreSQL services are provider-secret-free; the live test is separately and explicitly gated. |
| Record every terminal attempt | Implemented | Every terminal route passes through `_finish`; `PostgresAuditStore.append` commits in a short transaction before response construction returns. |
| Metadata-only HMAC projection | Implemented | `AuditProjector` uses ADR-005 domain-separated HMAC references, `content_state=absent`, and never accepts request/provider bodies. |
| Audit release gate | Implemented | Audit append failure suppresses intended 200/403/provider outcomes with retryable 503 `audit_unavailable`. |
| Request and transaction boundaries | Implemented | Governance sessions close before provider I/O; latency uses a monotonic timer from request entry through terminal normalization. |
| Deterministic durability/redaction proof | Implemented | PostgreSQL readback, migration, DTO, projection, repository, gateway, and isolated harness evidence passed. |

### Coherence (Design)

| Decision | Followed? | Notes |
|---|---|---|
| Direct async provider port | Yes | `LLMProvider.create` and one shared pinned `httpx.AsyncClient` isolate the adapter without SDK, retry, or fallback behavior. |
| Router-owned ordering | Yes | `responses_router(service)` delegates the complete ordered flow to `ResponsesService`; unrelated dependencies do not reorder governance. |
| Separated safe reads | Yes | Authorization and assignment queries are distinct, and the routing query is unreachable before allow. |
| Metadata-only audit | Yes | HMAC projections, closed audit DTOs, non-null persistence latency, and release gating match the design. |
| Immutable additive 1.2.0 | Yes | The self-contained release validates 142 artifacts and 8 checks; 1.1.0 remains the additive compatibility baseline. |

### Issues Found

**CRITICAL**: None.

**WARNING**:

1. **VER-01 — Persistent harness coverage is narrower than final proof.** The checked-in issue-14 harness does not explicitly assert the inactive-resource case, delayed latency, or per-attempt terminal-event cardinality. Final verification covered those cases with a secret-free container probe (`sha256:f8b683373fc1b551b7c57e55d2dbbee99a19533272efe7244c212c723890897d`), so the current candidate is proven; promoting those assertions into checked-in tests would prevent CI regression.

**SUGGESTION**: None.

### Canonical Verification Evidence Preimage

The following single-line JSON plus its trailing newline is the exact preimage for `sha256:d53d6c5b35c7d632a44138c406b107fe775b6a4ff2aa6ef8e02b43a33cbe4816`:

```json
{"artifact_store":"openspec","build":{"command":"docker compose --profile checks run --build --rm harness sh -c 'npm --prefix schemas/tooling test && npm --prefix schemas/tooling run validate && npm --prefix schemas/tooling run validate:release -- --release 1.0.0 && npm --prefix schemas/tooling run validate:release -- --release 1.1.0 && npm --prefix schemas/tooling run validate:release -- --release 1.2.0 && npm --prefix schemas/tooling run lint:openapi && npm --prefix schemas/tooling run conformance -- --consumer issue-10 && npm --prefix schemas/tooling run conformance -- --consumer issue-11 && npm --prefix schemas/tooling run conformance -- --consumer issue-13 && npm --prefix schemas/tooling run conformance -- --consumer issue-14 && node --check scripts/showcase.js'","exit_code":0,"output_hash":"sha256:870f869429ce96694ceddbdbc037de174b04da335f7e91f28225b71351796106","result":"68 contract-tooling tests, canonical validation, immutable releases 1.0.0/1.1.0/1.2.0, both OpenAPI checks, issue-10/11/13/14 conformance, and JavaScript syntax passed in the container"},"candidate":{"context_hashes":{"apply-progress.md":"sha256:60b8b846afd1753b546b12069b673ccdbaf48be3affc3518821dbacbc20f7c0a","design.md":"sha256:2a479ca2e0b89bbbc1386b7d872933450b363624e18909620429f59d55bb7ead","proposal.md":"sha256:d3896a13d0f33cad3b43bbab2d55e9a671c01f4a917b2a8ada2ff16fcdc46d3d","specs/governed-llm-responses/spec.md":"sha256:1ed09eab9b6110a862d8f163060380bbd673f40395debaee8000ce74ab1d2b80","specs/runtime-audit-evidence/spec.md":"sha256:98f473f8f6302d9b8194b78b7e98ab130bbe86d394f292986df25846618a858a","tasks.md":"sha256:aca34701026cfa7c42f6e215a95f143ffee71dc9249d82b1733567196badbbdb"},"head":"43ce16d0517827ea8ee8c30c1930fa0315167bf9","tracked_tree_listing_hash":"sha256:9b4ca4a3e2206f8fb8e03ee97bef663834b42b59f58cde2660077aa3f30c7689","tree":"d8abaec8b003708ce128d214e22d3e88388dba35"},"change":"implement-issue-14-governed-llm","live_smoke":{"provider_traffic":"not attempted because no operator provider secret was supplied","result":"ordinary full-suite skip and explicit enable-without-secret skip both passed"},"mode":"Standard","requirements":{"compliant":10,"total":10},"scenarios":{"compliant":17,"total":17},"schema":"gentle-ai.verification-evidence/v1","supplementary_probe":{"input_hash":"sha256:f8b683373fc1b551b7c57e55d2dbbee99a19533272efe7244c212c723890897d","result":"inactive-resource denial, delayed latency, no governance transaction during provider I/O, and one terminal event per allow/deny/failure attempt passed with the recording provider"},"tasks":{"complete":10,"total":10},"test":{"command":"docker compose --profile checks run --build --rm python-checks && docker compose --profile issue-14 run --build --rm issue-14-harness && docker compose --profile issue-14 run --rm -v /tmp/issue14_verify_additional.py:/tmp/issue14_verify_additional.py:ro issue-14-harness python /tmp/issue14_verify_additional.py && docker compose --profile checks run --rm -e RUN_OPENROUTER_LIVE_SMOKE=1 python-checks pytest -q tests/test_openrouter_live.py","exit_code":0,"output_hash":"sha256:64b6c8b814aff522606db065a5468778443795178076edc28aad385899e471cf","result":"308 passed and 1 secret-gated skip in the full container gate; deterministic issue-14 harness 11 passed; supplementary runtime scenarios passed; explicit missing-secret live smoke skipped"},"verdict":"pass_with_warnings","warnings":["VER-01: inactive-resource, delayed-latency, and exact terminal-event-cardinality assertions required a verifier-only container probe because the checked-in issue-14 harness does not assert those cases explicitly"]}
```

### Verdict

**PASS WITH WARNINGS**

All ten requirements and seventeen scenarios pass on the current candidate. The only warning is that three runtime assertions required a verifier-only container probe instead of the checked-in harness; it does not block archive readiness.
