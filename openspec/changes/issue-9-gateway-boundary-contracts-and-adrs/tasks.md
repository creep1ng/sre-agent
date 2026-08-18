# Tasks: Gateway boundary contracts and ADRs

Planning only. No backend, database, FastAPI runtime, production CLI, real authentication/authorization, or OpenRouter integration belongs to this change.

## Apply gates

- Artifact store: OpenSpec; execution: autonomous for remaining work units; delivery: `force-chained`; chain: `stacked-to-main`.
- Before S1, local `main` was safely fast-forwarded by five commits to GitHub `main` at `71112f9`, including `.github/pull_request_template.md`, after checking incoming paths for untracked collisions.
- Issue-first is resolved: #9 plus native subissues #58–#67 and #72 retain `status:approved`; S1–S4 are closed by merged PRs, while A1/A2/B–F remain open. Each PR uses its real slice issue in `Closes #N` plus `Refs #9`; closing #9 remains reserved until every slice satisfies the tracker.
- Every PR uses exactly label `type:feature`, appends Chain Context to the repository template, and targets updated `main`. A1/A2/B–E execute autonomously and merge only after applicable checks pass, without admin bypass or force; F/#67 is opened last and remains unmerged for manual review.
- S1 isolated-INDEX gate: `openspec doctor --json` is healthy; `openspec status --change issue-9-gateway-boundary-contracts-and-adrs --json` is partial (proposal ready; specs/design/tasks blocked); strict validation must fail honestly with `Change must have at least one delta` until S2. `.atl/skill-registry.md`, backend/runtime code, generated bundles, `node_modules`, and secrets are excluded.

## Issue-first check

| Check | Read-only evidence | Gate/effect |
|---|---|---|
| Issue #9 | [Open and approved](https://github.com/creep1ng/sre-agent/issues/9); existing labels preserved | **Pass** |
| Premature closure | Eleven unique native subissues [#58](https://github.com/creep1ng/sre-agent/issues/58)–[#67](https://github.com/creep1ng/sre-agent/issues/67) plus [#72](https://github.com/creep1ng/sre-agent/issues/72) are approved and parented by #9; only a merged slice PR closes its own issue | Each PR closes only its real slice issue and references #9 |
| PR template | Exists on GitHub `main` at `.github/pull_request_template.md`; local `main` was five commits behind | Fast-forwarded safely before S1; preserve all template sections |
| Labels | `status:approved`, `size:exception`, and `type:feature` exist | Use exactly `type:feature`; no exception is currently justified |
| Rules/checks | Active ruleset requires a PR to default branch and merge commits; no required status checks/workflows or classic branch protection are visible | PR/merge gate applies; policy checks still require approved issue and one type label |

Gate evidence: S1=#58, S2=#59, S3=#60, S4=#61, A1=#62, A2=#72, B=#63, C=#64, D=#65, E=#66, F=#67. GitHub reports exactly eleven native subissues with parent #9; after S4 merge, no further decision is needed before autonomous slice A1.

## Review Workload Forecast

Estimated changed lines total: **3,420–3,800** (`additions + deletions`), including **1,240 OpenSpec planning lines across S1–S4** and seven remaining contract work units. The combined A candidate reached **400 staged/416 native** and had a bounded historical exception, but a fresh rereview after its one correction found the unguarded `externalValue` resolver surface. The split supersedes that candidate: A is not approved, and neither A1 nor A2 is forecast to require `size:exception`.

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

| Slice | Estimated + / - | Files / generated lines | Cognitive load / review | Start → end → rollback | 400-line budget risk | 800-line budget risk | Decision needed before apply | `size:exception` |
|---|---:|---|---|---|---|---|---|---|
| S1 SDD context | +388 / -0 | 2 / 0 | High / 45–55m | updated `main` → config+exploration tracked → revert docs commit | High | Low | No; base sync is procedural | No |
| S2 SDD core specs | +319 / -0 | 4 / 0 | Medium / 35–45m | S1 merged → proposal+3 specs → revert docs commit | Medium | Low | No after gate | No |
| S3 SDD audit/design | +315 / -0 | 3 / 0 | Medium / 35–45m | S2 merged → 2 specs+design → reverse dependent rollback before reverting S3 | Medium | Low | No after gate | No |
| S4 SDD tasks | +218 / -0 | 1 / 0 | Medium / 35–45m | S3 merged → executable plan tracked → revert docs commit | Low | Low | No after gate | No |
| A1 Schema tooling | +190–230 / -0–10 | 10 / ~110–115 lockfile | Medium / 35–45m | S4 merged → Ajv schema/fixture validator only → revert A1 | Medium | Low | No | No |
| A2 OpenAPI tooling | +285–380 / -0–10 | 10–15 / ~15 lockfile delta | High / 50–60m | A1 merged → offline all-locator OpenAPI gate + semantic diff → revert A2 | High | Low | No | No; split before 400 |
| B Shared schemas | +345–390 / -0–10 | 16–20 / 0 | High / 50–60m | A2 merged → shared authority validated → revert B | High | Low | No | No; split identity/policy if >400 |
| C Audit boundary | +325–380 / -0–10 | 11–14 / 0 | High / 50–60m | B merged → fail-closed audit contract → revert C | High | Low | No | No; split fixtures if >400 |
| D Control plane | +350–390 / -0–10 | 16–20 / 0 | High / 50–60m | C merged → complete control OAS/bootstrap → revert D | High | Low | No | No; split credential/bootstrap if >400 |
| E Responses | +350–390 / -0–10 | 14–18 / 0 | High / 50–60m | D merged → Responses/OpenRouter boundary → revert E | High | Low | No | No; split provider drift if >400 |
| F Conformance | +330–390 / -0–10 | 16–20 / 20–40 compact evidence | High / 50–60m | E merged → release manifest/evidence → revert F | High | Low | No | No; split projection evidence if >400 |

`Chained PRs recommended: Yes`. Any staged slice above 400 changed lines must split before review; no slice may exceed 800 without new approval. The historical combined-A exception documents prior accounting only and MUST NOT be applied to A1 or A2. Both require fresh review and an authored diff `<=400` with exactly one `type:*` label.

## Serial PR map

Planned PR count: **11**. All branch names match `^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)/[a-z0-9._-]+$`. The issue numbers below are distinct approved native subissues of #9.

| PR | Branch | Suggested work-unit commit(s) | Exactly one label / issue linkage | Chain diagram |
|---|---|---|---|---|
| S1 | `feat/issue-9-sdd-context` | `feat(sdd): publish issue 9 exploration context` | `type:feature`; `Closes #58`; `Refs #9` | `main ← 📍 S1` |
| S2 | `feat/issue-9-sdd-core-specs` | `feat(sdd): publish core gateway contract specs` | `type:feature`; `Closes #59`; `Refs #9` | `main+S1 ← 📍 S2` |
| S3 | `feat/issue-9-sdd-audit-design` | `feat(sdd): publish audit specs and contract design` | `type:feature`; `Closes #60`; `Refs #9` | `main+S1+S2 ← 📍 S3` |
| S4 | `feat/issue-9-sdd-tasks` | `feat(sdd): publish gateway contract task plan` | `type:feature`; `Closes #61`; `Refs #9` | `main+S1..S3 ← 📍 S4` |
| A1 | `feat/issue-9-contract-tooling` | `feat(contracts): add schema validation tooling` | `type:feature`; `Closes #62`; `Refs #9` | `main+S1..S4 ← 📍 A1` |
| A2 | `feat/issue-9-openapi-tooling` | `feat(contracts): add offline openapi tooling` | `type:feature`; `Closes #72`; `Refs #9` | `main+…+A1 ← 📍 A2` |
| B | `feat/issue-9-shared-contracts` | `feat(contracts): add shared governance schemas` | `type:feature`; `Closes #63`; `Refs #9` | `main+…+A2 ← 📍 B` |
| C | `feat/issue-9-audit-contract` | `feat(contracts): define audit redaction boundary` | `type:feature`; `Closes #64`; `Refs #9` | `main+…+B ← 📍 C` |
| D | `feat/issue-9-control-plane` | `feat(contracts): define control plane contract` | `type:feature`; `Closes #65`; `Refs #9` | `main+…+C ← 📍 D` |
| E | `feat/issue-9-responses-contract` | `feat(contracts): define responses gateway contract` | `type:feature`; `Closes #66`; `Refs #9` | `main+…+D ← 📍 E` |
| F | `feat/issue-9-conformance-evidence` | `feat(contracts): publish release conformance evidence` | `type:feature`; `Closes #67`; `Refs #9` | `main+…+E ← 📍 F` |

The design forecast is dependency-adjusted: A1 establishes only Ajv schema/fixture validation; A2 adds every OpenAPI resolver surface and semantic diff under a fresh review context; then B–F proceed unchanged. Audit schema C still precedes control/Responses OAS so external references resolve in every autonomous slice. The final chain is `S1–S4 → A1 → A2 → B → C → D → E → F`.

## Future per-slice delivery protocol

For each slice only: (1) fetch and fast-forward `main`; (2) create its branch from updated `main`; (3) implement only that work unit; (4) run exact validation below; (5) inspect requirements, diff, generated/semantic boundaries, and secrets in fresh context before commit/push/PR; (6) apply at most the authorized correction budget and create conventional commit(s) without `Co-Authored-By`; (7) push and open one template-based PR with Chain Context, approved issue, and exactly `type:feature`; (8) for A1/A2/B–E, wait boundedly for checks, merge by policy without admin/bypass/force, and verify updated `main` before the next slice. For F/#67, open the validated PR and stop for manual review without merging. Stop with state preserved if checks or GitHub fail; never open the next PR against stale `main`.

## PR S1 — OpenSpec context

- [x] **1.1 Track configuration and exploration only.** Files: `openspec/config.yaml`, `openspec/changes/issue-9-gateway-boundary-contracts-and-adrs/exploration.md`; coverage: traceability prerequisite for every requirement/scenario; precondition: issue/base gates, no prior slice.
  - Steps: stage only both paths, materialize the INDEX under `/tmp/kilo`, confirm at most 400 changed lines, and exclude `.atl/skill-registry.md`; verify there: `openspec doctor --json` is healthy, `openspec status --change issue-9-gateway-boundary-contracts-and-adrs --json` is partial (proposal ready; specs/design/tasks blocked), strict exits nonzero with `Change must have at least one delta` until S2, and staged `--check`/`--numstat`/`--name-only` checks pass.
  - Done: configuration and approved exploration are reviewable on updated `main` with honest partial/expected-strict-failure evidence and no implementation; rollback: revert this additive commit; commit/PR: `feat(sdd): publish issue 9 exploration context` / S1.

## PR S2 — Proposal and core specs

- [x] **2.1 Track proposal plus shared/control/Responses specs.** Files: `proposal.md`, `specs/{shared-governance-schemas,control-plane-contract,responses-gateway-contract}/spec.md`; coverage: all requirements/scenarios in those three capabilities; depends on S1.
  - Steps: stage only the four files and review requirement names, one-time secret reveal, metadata-only audit reads, entity lifecycles, and full S2 rollback against proposal scope; verify: `openspec validate issue-9-gateway-boundary-contracts-and-adrs --strict`, `git diff --cached --check`, `git diff --cached --numstat` (expected 319 additions).
  - Done: identity, control, and execution behavior are normative without code; rollback: revert S2; commit/PR: `feat(sdd): publish core gateway contract specs` / S2.

## PR S3 — Audit/conformance specs and design

- [x] **3.1 Track remaining specs and technical design.** Files: `specs/{audit-redaction-contract,contract-governance-conformance}/spec.md`, `design.md`; coverage: every audit/redaction/governance scenario plus all design decisions; depends on S2.
  - Steps: stage only these paths and confirm OAS 3.1.0, Draft 2020-12, release 1.0.0, future FastAPI projection boundaries, stage-aware AuditEvents without invented authority, `X-Generation-Id`-only provider fallback, durable audit acceptance, and reverse dependency rollback; verify: strict OpenSpec validation, `git diff --cached --check`, `git diff --cached --numstat` (expected 315 additions).
  - Done: all five specs and design are available on main; rollback: first remove S4 and any later dependent slices in reverse order, then revert S3; commit/PR: `feat(sdd): publish audit specs and contract design` / S3.

## PR S4 — Executable task plan

- [x] **4.1 Track this plan without implementation.** File: `tasks.md`; coverage: traceability and executable ordering for all requirements/scenarios; depends on S3.
  - Steps: stage only `tasks.md`, recount checkboxes/forecast, and confirm all eleven PR boundaries after the A1/A2 split; verify: `openspec status --change issue-9-gateway-boundary-contracts-and-adrs` shows `4/4`, strict validation passes, and `git diff --cached --check` passes.
  - Done: tasks are `done` and the next apply boundary is A1 after confirmed S4 merge; rollback: revert S4; commit/PR: `feat(sdd): publish gateway contract task plan` / S4.

## PR A1 — Schema/fixture tooling

- [x] **5.1 Add the minimal reproducible schema toolchain.** Files: `schemas/tooling/{package.json,package-lock.json,.gitignore}`; coverage: Versioned shared schemas/Portable evidence/Technology independence; depends on S4.
  - Steps: pin only dev-only `ajv@8.20.0` and `ajv-formats@3.0.1`, plus Node engines, schema scripts, and lockfile; no YAML parser is required because A1 consumes JSON-only schemas/fixtures; exclude Redocly, OpenAPI scripts/config/fixtures, semantic diff, locators, and `externalValue`; verify: `npm ci --prefix schemas/tooling && npm audit --prefix schemas/tooling --audit-level=moderate`.
  - Done: clean install has no production dependency or tracked `node_modules`, A1 is `<=400` without exception, and no OpenAPI surface exists; rollback: revert only A1 manifest/lock/config; commit/PR: `feat(contracts): add schema validation tooling` / A1 #62.

- [x] **5.2 Build strict Draft 2020-12 schema/fixture validation.** Files: `schemas/tooling/{validate.mjs,lib/schema-validation.mjs,test/schema-validation.test.mjs,test/fixtures/schema/*}`; coverage: Positive fixture drifts, Negative fixture validates, Canonical vocabulary; depends on 5.1.
  - Steps: use Ajv2020 strict mode, formats, immutable `$id` registry, closed schemas, and fixture metadata (`target/rule/status/version`); verify: `npm --prefix schemas/tooling test -- --test-name-pattern="schema|fixture"`.
  - Done: positives validate, named negatives fail for the expected rule, runtime harness is N/A, and A2 can add OpenAPI without changing A1 behavior; rollback: revert validator/fixtures independently from later OpenAPI tooling; commit: `feat(contracts): validate schemas and fixtures strictly` / A1 #62.

## PR A2 — Offline OpenAPI tooling and semantic diff

- [x] **5.3 Add deterministic offline OpenAPI lint/bundle with complete locator policy.** Files: `schemas/tooling/{package.json,package-lock.json,redocly.yaml,lib/openapi-validation.mjs,test/openapi-validation.test.mjs,test/fixtures/openapi/*}`; coverage: Versioned shared schemas/Technology independence plus the `externalValue` blocker; depends on A1.
  - Steps: add and pin `yaml@2.9.0` together with `@redocly/cli@2.46.1` only in A2; require OAS 3.1.0 and preflight every resolver-visible locator recursively before Redocly, including `$ref` and nested `externalValue`; reject network/protocol-relative/`file:`/absolute/parent traversal (direct or encoded) and `realpath`/symlink escapes, allow only fragments or regular files contained under the approved root, lint before bundle, and confine output to ignored `.tmp/`.
  - Verify: `npm --prefix schemas/tooling test -- --test-name-pattern="openapi|locator|externalValue"` plus independent probes proving zero remote request, zero outside-root sentinel read, rejection of parent/file/absolute/symlink cases, and acceptance of contained local files.
  - Done: unresolved locators, wrong OAS/version, lint errors, `externalValue` bypasses, network access, and containment escapes fail before Redocly; A2 remains `<=400` without exception; rollback: revert Redocly/config/preflight/tests while A1 remains installable; commit/PR: `feat(contracts): add offline openapi tooling` / A2 #72.

- [x] **5.4 Add the semantic projection-diff harness.** Files: `schemas/tooling/{diff-openapi.mjs,lib/openapi-normalize.mjs,test/openapi-diff.test.mjs,test/fixtures/openapi/*}`; coverage: Consumers conform/Internal model is shared/Adapter changes; depends on 5.3.
  - Steps: normalize ordering/format, compare paths, methods, inputs, statuses, media types, and schemas, and reject missing/extra behavior; verify: `npm --prefix schemas/tooling test -- --test-name-pattern="semantic diff"`.
  - Done: toy match passes; missing/extra and parameter/security/media/status/schema drift fail; runtime harness is N/A because the projection is a fixture and no FastAPI backend exists; rollback: revert diff/normalizer/fixtures without removing A1; commit: `feat(contracts): compare canonical and projected openapi` / A2 #72.

## PR B — Shared governance schemas and ADR-002/003/004

- [x] **6.1 Define Principal and credential boundaries.** Files: domain `principal`, `credential-reference`, `principal-context` schemas, identity fixtures, `adrs/ADR-002-principal.md`, `ADR-003-api-keys.md`; coverage: Principal/credential schemas and its four scenarios; depends on A2.
  - Steps: enforce human/agent, single workspace, entity-specific status/lifecycle, and reject key/Authorization from shared/persistent identity representations while reserving the dedicated one-time issuance exception for 8.3; verify: `npm --prefix schemas/tooling run validate -- --scope identity`.
  - Done: valid identities pass and legacy/secret fixtures fail; rollback: revert 6.1; commit: `feat(contracts): add principal and credential schemas` / B.

- [x] **6.2 Define governed model/resource boundaries.** Files: domain `model-alias` and `resource` schemas plus positive/negative fixtures; coverage: Model/resource/Grant requirement, Routing enters a Grant; depends on 6.1.
  - Steps: separate alias, concrete model, router, provider, status, and allowed resource types; verify: `npm --prefix schemas/tooling run validate -- --scope model-resource`.
  - Done: routing stays on ModelAlias and outside Principal/Resource authority; rollback: revert 6.2; commit: `feat(contracts): add model alias and resource schemas` / B.

- [x] **6.3 Define direct Grant and PolicyDecision.** Files: domain `grant` and `policy-decision` schemas, allow/default-deny fixtures, `adrs/ADR-004-grants.md`; coverage: Direct grant validates, Routing enters a Grant, No grant matches, Grant allows; depends on 6.2.
  - Steps: constrain direct allow, `active|revoked` Grant lifecycle with active-only matching, nullable persisted `policy_id`, and `no_matching_grant`; verify: `npm --prefix schemas/tooling run validate -- --scope policy`.
  - Done: allow references its Grant and default deny has null policy ID; rollback: revert 6.3; commit: `feat(contracts): add grant and policy decision schemas` / B.

- [x] **6.4 Add safe shared envelopes and vocabulary guards.** Files: domain `correlation` plus HTTP `error-envelope`/`list-envelope` schemas and safe/legacy fixtures; coverage: Audit/error/correlation, Safe error, Correlation claims authority, Legacy vocabulary scenarios; depends on 6.1–6.3.
  - Steps: close payloads, bound details/lists, separate IDs, and permit prohibited words only in marked negative fixtures; verify: `npm --prefix schemas/tooling run validate -- --scope shared && npm --prefix schemas/tooling test`.
  - Done: shared schema authority passes with no organization/tenant/user/role/scope fields; rollback: revert 6.4; commit: `feat(contracts): add safe envelopes and vocabulary lint` / B.

## PR C — Audit/redaction foundation and ADR-005

- [x] **7.1 Define complete stage-aware AuditEvent/redaction shape.** Files: domain `audit-event.schema.json` and audit examples; coverage: Correlated AuditEvent, Metadata/content separable, append-only requirements and their scenarios; depends on B.
  - Steps: define a closed audit-local projection: release-literal vocabularies plus domain-separated HMAC `auditRef` envelopes for every source identity/credential/resource/model/policy/grant/routing/correlation/untrusted value, stage-conditional evidence, structural fully-redacted content, and disjoint correction linkage; verify with plain strict Ajv, malformed-envelope probes, 33 carrier probes, and the stage/exporter matrices under `npm --prefix schemas/tooling run validate -- --scope audit`.
  - Done: allow, pre-route deny, pre-auth 422, unresolved-identity 401, metadata-only, and absent-content examples validate without fabricated authority, provider objects, or secrets; rollback: revert 7.1; commit: `feat(contracts): add correlated audit event schema` / C.

- [x] **7.2 Add pre-sink redaction fixtures.** Files: audit fixtures for LLM/MCP/sandbox/command/tool/free-content success and prohibited direct-sink/embedded-secret negatives; coverage: all Redaction precedes every sink scenarios; depends on 7.1.
  - Steps: encode structural removal, known-secret matching, pattern detection, and scanning outcomes; verify: `npm --prefix schemas/tooling run validate -- --scope redaction-success`.
  - Done: only redacted content reaches fixture sinks and raw values are absent; rollback: revert 7.2; commit: `feat(contracts): add pre-sink redaction fixtures` / C.

- [x] **7.3 Add fail-closed and audit-store fixtures.** Files: audit negative/positive fixtures for uncertain/error, partial payload, mutation/delete, durable acceptance failure, and downstream exporter failure; coverage: Redaction succeeds/fails, Event mutation, Audit store rejects, Exporter fails; depends on 7.1.
  - Steps: require metadata-only `redaction_failed`, discard raw/partial data, gate ordinary results on authoritative acceptance, map rejection/unavailability to safe retryable 503 `audit_unavailable`, and keep exporters downstream; verify: `npm --prefix schemas/tooling run validate -- --scope redaction-failure`.
  - Done: every failure fixture proves no raw payload or false persistence claim survives, while exporter failure does not alter an already audited response; rollback: revert 7.3; commit: `feat(contracts): prove fail-closed redaction behavior` / C.

- [x] **7.4 Record audit decision and ownership.** Files: `adrs/ADR-005-audit-redaction.md`, `releases/1.0.0/conformance/ownership-matrix.yaml`; coverage: Accepted ADRs, Ownership matrix/Content is misplaced; depends on 7.1–7.3.
  - Steps: mark the stage-aware redaction/durable-acceptance ADR accepted with deferred retention/access and encode Git/DB/secret-store required/prohibited placement; verify: `npm --prefix schemas/tooling run validate -- --scope governance`.
  - Done: ownership violations and secret placement fail; rollback: revert 7.4; commit: `feat(contracts): record audit and ownership governance` / C.

## PR D — Control plane and bootstrap contract

- [ ] **8.1 Publish canonical control-plane OAS.** Files: `releases/1.0.0/openapi/control-plane.yaml`, control examples; coverage: Control-plane matrix/Matrix operation succeeds, Safe errors/audit reads; depends on C.
  - Steps: define every Principal/Credential/ModelAlias/Grant/Audit operation, statuses, auth, errors, and external refs; verify: `npm --prefix schemas/tooling run lint:openapi -- --api control-plane`.
  - Done: Redocly lints/bundles the complete control OAS with no unresolved refs; rollback: revert 8.1; commit: `feat(contracts): publish control plane openapi` / D.

- [ ] **8.2 Contract POST/HTTP idempotency.** Files: HTTP `idempotency-record.schema.json` and replay/conflict/missing-key/repeated-delete fixtures; coverage: every POST idempotency and HTTP idempotency scenario; depends on 8.1.
  - Steps: encode scope/key digest, RFC-8785 payload hash, outcomes, 24h/lifetime binding, and convergent PUT/DELETE; verify: `npm --prefix schemas/tooling run validate -- --scope idempotency`.
  - Done: same-hash replay is stable, mismatch is 409, missing key is 400; rollback: revert 8.2; commit: `feat(contracts): define idempotent control mutations` / D.

- [ ] **8.3 Contract credential issuance and rotation.** Files: HTTP `credential-issuance.schema.json`, issue/list/revoke/rotate/replay/failure fixtures; coverage: Credential secrecy/rotation scenarios; depends on 8.2.
  - Steps: model one-time reveal, metadata-only replay, atomic replacement, and retained old credential on failure; verify: `npm --prefix schemas/tooling run validate -- --scope credentials`.
  - Done: no fixture stores hash/raw key and rotation replay mints nothing; rollback: revert 8.3; commit: `feat(contracts): define credential issuance and rotation` / D.

- [ ] **8.4 Add bootstrap seed/CLI contract fixtures only.** Files: HTTP `bootstrap-seed.schema.json`, bootstrap first/repeat/conflict fixtures and examples; coverage: Offline bootstrap/Bootstrap repeats/conflicts; depends on 8.3.
  - Steps: encode stable identity, first Principal/credential/direct Grants, one reveal, convergence, and secret-free conflict; verify: `npm --prefix schemas/tooling run validate -- --scope bootstrap`.
  - Done: fixture describes offline CLI I/O without executable product CLI; rollback: revert 8.4; commit: `feat(contracts): add bootstrap cli contract fixtures` / D.

- [ ] **8.5 Prove bounded lists and safe metadata-only audit reads.** Files: control fixtures for sort/limit/truncation, forbidden pagination, required filters, hidden resource, and unsupported audit-content retrieval; coverage: both bounded-list scenarios and both safe-error/audit-read scenarios; depends on 8.1.
  - Steps: encode limit 100/no continuation, deterministic order, 422 unsafe queries, indistinguishable 404, metadata/redaction-state-only audit reads, and uniform 422 for every content-retrieval parameter/field; verify: `npm --prefix schemas/tooling run validate -- --scope control && npm --prefix schemas/tooling run lint:openapi -- --api control-plane`.
  - Done: all control operations/examples/negative rules validate together; rollback: revert 8.5; commit: `feat(contracts): add control plane conformance fixtures` / D.

## PR E — Responses/OpenRouter boundary and ADR-001

- [ ] **9.1 Publish canonical Responses OAS and schemas.** Files: `openapi/responses.yaml`, HTTP `responses-request`/`responses-response` schemas, request/success examples; coverage: Textual subset and Non-streaming success scenarios; depends on D.
  - Steps: define OAS 3.1.0 POST only, textual limits, server request ID, completed response, concrete model, and flat routing metadata; verify: `npm --prefix schemas/tooling run lint:openapi -- --api responses`.
  - Done: minimal request/200 response bundle cleanly and streaming/nested metadata are absent; rollback: revert 9.1; commit: `feat(contracts): publish responses openapi` / E.

- [ ] **9.2 Add validation/auth/non-enumeration fixtures.** Files: Responses fixtures for unknown/unsupported fields, bad IDs/input, uniform 401, missing/inactive/unauthorized alias, and spoofed correlation; coverage: Unsupported field, Credential cannot authenticate, Missing versus unauthorized alias, Correlation spoofed; depends on 9.1.
  - Steps: encode 422-before-auth/upstream, 401-before-alias, and indistinguishable 403-before-routing; verify: `npm --prefix schemas/tooling run validate -- --scope responses-boundary`.
  - Done: fixtures prove validation/auth/allow ordering without runtime code; rollback: revert 9.2; commit: `feat(contracts): prove responses boundary ordering` / E.

- [ ] **9.3 Contract OpenRouter effective-provider extraction.** Files: selected-provider success, `X-Generation-Id` fallback, and missing/invalid/ambiguous/malformed metadata 502 fixtures; coverage: Allowed alias routes, Provider executes through router, OpenRouter alias boundary; depends on 9.1.
  - Steps: require opt-in metadata, concrete upstream model, exactly one selected endpoint on no-cache metadata success or one bounded `GET /api/v1/generation` keyed exclusively by upstream `X-Generation-Id`; map only provider, retain `router=openrouter`, distinguish Response body `id`, and reject raw metadata leakage; verify: `npm --prefix schemas/tooling run validate -- --scope openrouter-metadata`.
  - Done: missing/invalid header, failed/ambiguous lookup, and provider drift normalize to safe non-retryable 502 while successful dimensions remain separate; rollback: revert 9.3; commit: `feat(contracts): define openrouter metadata boundary` / E.

- [ ] **9.4 Add tracing and upstream-error fixtures.** Files: valid/invalid trace and 502/503/504/Retry-After fixtures; coverage: both Trace Context and all Error taxonomy scenarios; depends on 9.1.
  - Steps: encode bounded child/new trace behavior, safe envelopes, retryability, trustworthy Retry-After only, and upstream 503/504 paths that require neither selected-provider metadata nor generation lookup; verify: `npm --prefix schemas/tooling run validate -- --scope responses-errors`.
  - Done: no upstream body/URL/stack/secret/internal denial cause serializes; rollback: revert 9.4; commit: `feat(contracts): add responses tracing and error fixtures` / E.

- [ ] **9.5 Record accepted Responses decision.** File: `adrs/ADR-001-responses.md`; coverage: Accepted ADRs/ADR set checked; depends on 9.1–9.4.
  - Steps: document non-streaming subset, authorization-before-resolution, OpenRouter adapter boundary, alternatives/deferred work/supersession; verify: `npm --prefix schemas/tooling run validate -- --scope governance`.
  - Done: ADR-001..005 are accepted and linked to specs/evidence; rollback: revert 9.5; commit: `feat(contracts): record responses gateway decision` / E.

## PR F — Release manifest and cross-consumer conformance

- [ ] **10.1 Publish the immutable 1.0.0 manifest.** Files: `releases/1.0.0/{manifest.yaml,conformance/evidence.json}`; coverage: Versioned schemas, SemVer change process, Portable evidence; depends on E.
  - Steps: inventory every OAS/schema/example/fixture/ADR, dialect/version/`$id`, API major, hashes, and baseline; generate evidence first and manifest last to avoid circular hashes; verify: `npm --prefix schemas/tooling run validate:release -- --release 1.0.0`.
  - Done: release is complete, immutable, hash-consistent, and previous-major rules are testable; rollback: revert 10.1 (unpublishes only unreleased contracts); commit: `feat(contracts): publish release 1.0.0 manifest` / F.

- [ ] **10.2 Map every consumer to executable obligations.** Files: `conformance/{suite.yaml,consumers.yaml}` and coverage evidence; coverage: Consumers conform/Internal model is shared; depends on 10.1.
  - Steps: map #10 transport, #11 schema/persistence, #13 Bearer/context/401, #14 ordered flow/errors/audit, harness execution OAS, and UI control OAS to named fixtures/commands; verify: `npm --prefix schemas/tooling run conformance -- --check coverage`.
  - Done: no requirement/operation/type lacks an owner and no internal DTO/ORM/provider type is authority; rollback: revert 10.2; commit: `feat(contracts): map consumer conformance obligations` / F.

- [ ] **10.3 Add future FastAPI projection harness fixtures.** Files: normalized matching/missing/extra projection fixtures under `fixtures/{positive,negative}` and diff tests; coverage: Consumer conformance/Technology independence/Adapter changes; depends on A2 and both OAS files.
  - Steps: model future FastAPI `/openapi.json` as input fixture only, normalize semantic signatures, and test missing/extra behavior; verify: `npm --prefix schemas/tooling run diff:openapi -- --projection-fixture future-fastapi`.
  - Done: canonical-vs-projection match passes and drift fixtures fail without creating FastAPI/Python code; rollback: revert 10.3; commit: `feat(contracts): add fastapi projection conformance fixture` / F.

- [ ] **10.4 Generate compact, reproducible semantic evidence.** Files: `conformance/evidence.json`; temporary bundles: `schemas/tooling/.tmp/*` (generated, ignored); coverage: Portable evidence and SemVer scenarios; depends on 10.1–10.3.
  - Steps: lint/bundle both OAS, normalize, hash semantic outputs/ADRs/fixtures, run positive/negative checks, and record tool versions/results without timestamps or raw bundle text; verify: run `npm --prefix schemas/tooling run evidence` twice and `git diff --exit-code -- schemas/releases/1.0.0/conformance/evidence.json` after the second run.
  - Done: deterministic evidence changes only when semantics change; rollback: revert generated evidence with F; commit: `feat(contracts): generate deterministic conformance evidence` / F.

- [ ] **10.5 Run the complete release gate and inspect scope.** Files: all `schemas/**` plus OpenSpec artifacts already merged; coverage: every requirement/scenario across five specs; depends on 10.1–10.4.
  - Steps: run clean install, audit, tests, strict schema/fixture validation, Redocly lint/bundle, semantic diff, vocabulary/ownership/hash/coverage checks, OpenSpec strict/status, and secret scan; verify: `npm ci --prefix schemas/tooling && npm audit --prefix schemas/tooling --audit-level=moderate && npm --prefix schemas/tooling test && npm --prefix schemas/tooling run validate:release -- --release 1.0.0 && openspec validate issue-9-gateway-boundary-contracts-and-adrs --strict && openspec status --change issue-9-gateway-boundary-contracts-and-adrs`.
  - Done: all gates pass, status is 4/4, only compact evidence/lockfile are generated tracked lines, and #10/#11/#13/#14/harness/UI have explicit evidence; rollback: revert F only, preserving validated prior slices; commit: `feat(contracts): complete gateway contract conformance` / F.

## Next autonomous apply slice

S1–S4 and A1–C are complete through the current staged C candidate. The next autonomous work unit is **only PR D/#65 / tasks 8.1–8.5** on branch `feat/issue-9-control-plane`, and it starts from updated `main` only after C merges. Do not begin D from this unmerged C worktree.
