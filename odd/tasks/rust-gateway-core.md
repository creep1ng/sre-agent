# Rust-Owned Gateway and Core

## Objective

Move gateway and core behavior to Rust in reviewable vertical slices while preserving
the existing Python-facing contract through a PyO3/maturin adapter. Keep the current
Python tests as behavioral regressions and add Rust tests and installed-extension
import proof. The first slice moves `AuthorizationDecisionEngine` decision logic;
Python fact readers remain adapters during that slice.

## Problem and Why

The application currently owns its gateway and decision logic in Python. A wholesale
rewrite would obscure behavior changes and make regressions hard to localize. A staged
Clean Architecture migration gives Rust one policy authority at a time while keeping
HTTP, persistence, audit, and Python-import contracts observable at each boundary.

## Scope and Boundaries

- Build a Rust core with domain and use-case code independent of HTTP, database,
  Python, and provider SDKs. Implement those dependencies behind ports and adapters.
- Expose the required core capabilities to Python through a versioned PyO3 module
  built and installed with maturin. The Python package remains importable throughout.
- Start with authorization: Python obtains principal, resource, and grant facts using
  existing readers; Rust owns precedence, exact-grant validation, public decision,
  and audit-only denial cause. Do not leave two live decision authorities.
- Migrate remaining core use cases, persistence/provider integrations, and gateway
  routes incrementally, preserving externally observed behavior and the existing
  tests unless an explicit contract change is approved.
- Migrate the production gateway composition and packaging only after slices have
  contract and integration proof. Retire superseded Python implementations only
  after their Rust replacement is exercised by the same public entry points.

## Constraints and Authorized Scope

- Authorized local source scope: new Rust workspace/crates, `src/sre_agent/`
  gateway/core/adapters, package/build metadata, local Docker/Compose build paths,
  and focused tests/docs needed for this migration. Preserve unrelated runtime
  boundaries and existing tests.
- User authorized unauthenticated public artifact downloads from crates.io, PyPI,
  Docker Hub, and CDNs for local build/test work. This does **not** authorize remote
  push, PR creation, credential use, private endpoints, or other remote operations.
- No SDD phase is selected. This ODD task document tracks the direct staged work;
  repository OpenSpec remains the shared authority for existing public contracts.
- Strict TDD: observe a failing focused test (RED), implement (GREEN), then refactor
  and rerun applicable checks for each behavioral slice. Record actual commands and
  results; do not infer a RED or claim unavailable checks passed.
- Keep behavior, tests, and related documentation in each cohesive work unit.
  About 400 authored changed lines per task is an advisory planning heuristic, not
  a code-golf target or hard stop. PRs above the repository's 400-line policy need
  cohesive splitting or explicit maintainer exception; no PR is authorized here.
- Technical artifacts are in English. Do not commit secrets, generated traces, or
  credentials. Conventional commits only, without AI attribution, if later asked.

## TDD and Runners

- Mode: strict, enabled by the supplied `AGENTS.md` session instruction
  (`Strict TDD Mode: enabled`).
- Existing Python runner, focused authorization example:
  `docker compose --env-file .env.example --profile checks run --build --rm python-checks pytest -q tests/test_authorization.py`
- Existing broader Python runner:
  `docker compose --env-file .env.example --profile checks run --build --rm python-checks pytest -q tests`
- Rust runner: `cargo test --locked --manifest-path rust/Cargo.toml`.
- Native import proof: install the built maturin wheel into an isolated Python
  environment, then import and call the extension through the public Python adapter.
  Record the exact module name and command when the package contract is created.
- PR reproduction commands, if later requested, must use `docker compose` or
  `docker run`; package tools run inside those containers.

## Tasks

- [x] **RGC-01 — Lock the first-slice behavior and build boundary**
  - Characterize authorization precedence, exact active grants, mismatched facts,
    public denial shape, and audit-only cause in existing Python tests. Add a
    focused failing test for the Rust-backed adapter boundary before implementing.
  - Fix the Rust crate layout, Python module/API name, and build/import path in the
    same unit; record baseline test results and any environmental gaps.
  - Acceptance: RED is observed for the missing native path; existing behavior and
    Python import expectations are explicit; no policy logic is duplicated.
- [x] **RGC-02 — Ship the Rust authorization vertical slice**
  - Implement a dependency-free Rust authorization use case and Rust unit/property
    cases for fact ordering and exact grants; expose it via PyO3/maturin.
  - Have the Python adapter perform staged fact reads and invoke Rust exactly once
    per evaluation; retain existing public decision and audit behavior.
  - Acceptance: Rust tests, focused Python regressions, and installed-wheel import
    and invocation proof pass; the production authorization path uses Rust, not a
    Python policy fallback.
- [ ] **RGC-03 — Move remaining core use cases by domain**
  - Complete the bounded sub-slices below; unfinished domains remain explicitly
    Python-owned rather than partly rewritten.
  - Acceptance: each completed sub-slice has Rust and existing Python regression
    proof, one live authority, and a rollback boundary.
- [x] **RGC-03a — Project metadata-only responses audit policy in Rust**
  - Move `AuditProjector.event` projection decisions to dependency-free Rust:
    outcome, reference domains/correlation keys, evidence inclusion, and audit
    availability flags. Python retains HMAC key custody, UUID/time, DTO validation,
    persistence, and release gating. Keep `control_event` Python-owned.
  - Acceptance: native and Rust RED/GREEN, existing audit/responses regressions,
    and runtime import proof. No claim of content redaction or successful append.
- [ ] **RGC-03b — Move request and response normalization decisions**
  - Complete the bounded sub-slices below without changing public envelopes or
    provider calls. Keep unfinished normalization explicitly Python-owned.
- [x] **RGC-03b1 — Map provider failures in Rust**
  - Move only the `ProviderFailure.kind` to HTTP status, audit reason, and public
    error-code mapping from `ResponsesService.create` to dependency-free Rust.
    Keep `ProviderFailure`, consumption, `_finish`, FastAPI, audit persistence,
    retry behavior, public messages, and provider adapters unchanged.
  - Acceptance: Rust and native missing-symbol RED, mapping parity for known and
    unknown kinds, existing responses/ASGI/audit/import regressions, and runtime
    native import proof. Rollback restores the Python mapping without touching
    authorization or audit projection slices.
- [ ] **RGC-03b2 — Inventory remaining request normalization**
  - Characterize request validation and identifier normalization separately from
    the provider-failure mapping before selecting a Rust-owned policy boundary.
- [ ] **RGC-03b3 — Inventory remaining success-response normalization**
  - Characterize provider-result adaptation and response validation separately;
    do not change provider evidence or routing semantics before RGC-03e.
- [x] **RGC-03b3a — Project OpenRouter usage into Consumption in Rust**
  - Move contradictory token-total handling, timestamp-gated billed cost,
    complete/partial/absent/unavailable availability, failure-context absence,
    and null-field projection into dependency-free Rust and expose one PyO3 call.
  - Keep Python HTTP, JSON/Decimal lexical parsing, timestamp parsing, DTO
    construction, provider evidence, and audit release gating unchanged.
  - Acceptance: observe Rust/native RED before implementation, pass Rust and
    current Python OpenRouter/Responses/Audit regressions, static checks, full
    suite, isolated wheel import, and runtime native smoke. Do not claim the
    broader RGC-03b3 or RGC-03b complete.
- [x] **RGC-03b3b — Select completed OpenRouter assistant text in Rust**
  - Move root completed/list gating, completed assistant `output_text`
    selection, ordered newline aggregation, and no-qualifying-text rejection
    to dependency-free Rust through PyO3. Preserve Python Unicode objects,
    including lone surrogates, without extracting text into Rust UTF-8.
  - Keep HTTP/JSON parsing, provider evidence and catalog ordering,
    `ProviderResult` text bounds, public ID, consumption, audit, and release
    in Python. Current Python runtime/tests are the parity oracle; issue #345
    remains separate.
  - Acceptance: old-image missing-symbol RED (observed after the source edit),
    Rust/native/focused/full Python GREEN, static checks, isolated wheel and
    runtime smoke, and a narrow rollback boundary. Broader RGC-03b3 remains
    unfinished.
- [ ] **RGC-03c — Move administrative control decisions**
  - Separate control policy from current HTTP, repository, and `control_event`
    adapters, preserving authorization order and audit semantics.
- [x] **RGC-03c1 — Move terminal administrative audit policy to Rust**
  - Transfer `_finish` stage, reason, subject, and retryability decisions plus
    `control_event` outcome, grant, and resource metadata decisions into one
    dependency-free `project_control_audit` plan through PyO3.
  - Preserve current Python runtime and test parity, including hidden denial
    versus authorized target misses, fail-closed missing grants, HMAC resource
    input, audit-failure suppression, and no routing evidence. Python retains
    HMAC custody, UUID/time, DTO validation, append, and public release gating.
  - Acceptance: observed native/Rust RED, focused and full Python regressions,
    Rust/static checks, installed wheel and runtime import proof, and a narrow
    rollback boundary. No broader RGC-03c completion claim.
- [ ] **RGC-03d — Move incident use-case decisions**
  - Inventory incident workflows and move bounded policy transitions while keeping
    persistence, clocks, and transport behind adapters.
- [x] **RGC-03d1 — Move generic incident transition admission to Rust**
  - Move ordered source-state, actor, human principal reference, approval, and
    outcome selection from `IncidentRuntime._validate` into dependency-free Rust
    through one PyO3 call. Return a typed verdict and selected outcome; Python
    maps the verdict to existing exception classes/messages and uses the selected
    outcome in the reducer and decision document.
  - Preserve lock/idempotency replay before admission, workflow YAML lookup,
    stored-state checks, named preconditions, reducer/final invariants, and
    UoW/persistence/clock/IDs in Python. Read Python facts only after the prior
    Rust stage accepts, so rejected commands cannot trigger irrelevant reads.
  - Acceptance: observed Rust/native RED, focused and full incident/Python
    regressions, Rust/static checks, installed-wheel and runtime import proof,
    and a narrow rollback boundary. Do not claim RGC-03d complete.
- [x] **RGC-03e — Port current Python provider evidence behavior**
  - Complete the bounded evidence and catalog sub-slices below. Keep HTTP calls,
    credentials, JSON parsing, consumption, output text, DTOs, and public IDs in
    the Python adapter; Rust alone decides routing-evidence acceptance.
  - The divergence from the versioned `X-Generation-Id` lookup contract is tracked
    separately in https://github.com/creep1ng/sre-agent/issues/345. Do not use
    this Rust migration to change the contract, provider names, or routing behavior.
- [x] **RGC-03e1 — Move response and inline metadata evidence to Rust**
  - Add characterization and failing native/core tests first. Rust decides body
    `id`/`model`/`error`/`incomplete_details`, exact-one selected endpoint,
    optional one-attempt evidence, Python numeric equality, and provider
    casefold equality. The Python boundary only normalizes parsed JSON facts.
  - Acceptance: existing OpenRouter tests and new edge-case regressions pass,
    without a Python policy fallback or catalog/output-text order change.
- [x] **RGC-03e2 — Move conditional catalog confirmation to Rust**
  - Rust requests catalog only for a valid selected-model alias drift, then
    decides exact one catalog identity using case-sensitive tag/name rules.
    Python makes at most one existing catalog GET and passes its parsed facts.
  - Acceptance: Rust/native RED and GREEN, catalog unavailable/malformed/
    duplicate cases, full existing Python regressions, and runtime native
    import proof. Rollback restores only the prior OpenRouter evidence helpers.
- [x] **RGC-03e3 — Avoid eager provider-name normalization**
  - Correct the PyO3 fact reader so invalid body/catalog IDs and irrelevant
    endpoint entries do not trigger Unicode casefold. Rust remains the sole
    authority for relevance and final routing decisions.
  - Acceptance: observable native RED/GREEN with side-effecting string facts,
    existing parity tests, static gates, and runtime native import proof.
    Rollback is limited to this normalization correction and its regressions.
- [ ] **RGC-04 — Move infrastructure and gateway edges**
  - Replace Python-side persistence/provider/HTTP orchestration in bounded slices
    with Rust adapters and a Rust-owned gateway composition, preserving auth order,
    errors, OpenAPI-visible behavior, audit/telemetry, and database semantics.
  - Select and document concrete transport/build dependencies only when the first
    corresponding slice requires them; avoid framework selection by inertia.
  - Acceptance: existing gateway contract and integration tests exercise the Rust
    path; each replaced Python path is removed only after equivalent proof.
- [x] **RGC-04a — Compute ADR-005 audit-reference HMAC in a Rust adapter**
  - Move only `AuditProjector.reference` HMAC-SHA-256 computation through PyO3.
    Keep RustCrypto dependencies in `rust/python`, not dependency-free core.
    Python retains key loading, AuditRef validation, audit append/release gating,
    HTTP, and DB; keep the rest of RGC-04 explicitly pending.
  - Acceptance: native/Rust RED then GREEN, canonical UTF-8/domain/key-version
    and key-type parity, no Python crypto fallback, focused/full/static checks,
    isolated wheel and runtime import proof, and narrow rollback boundary.
- [x] **RGC-04a1 — Preserve whole-string UnicodeEncodeError diagnostics**
  - Encode the complete formatted ADR-005 input at the PyO3 boundary before
    Rust HMAC, preserving HEAD Python's error object, offsets, and format order.
  - Acceptance: observed focused RED/GREEN for malformed domains and values;
    valid digests, key-type boundary, and no Python crypto fallback remain intact.
- [ ] **RGC-05 — Package, verify, and cut over**
  - Produce reproducible native builds for supported environments; keep the
    Python-importable distribution and production startup working from clean builds.
  - Run Rust tests, installed-extension import smoke, existing Python suites,
    relevant containerized integration checks, formatting/static checks, and
    runtime smoke. Document skipped checks and platform gaps honestly.
  - Acceptance: Rust is the production gateway/core owner; the Python adapter is a
    compatibility boundary rather than a second implementation; rollback and
    deployment notes identify the exact cutover boundary.
- [x] **RGC-H1 — Record a repository-visible migration handoff**
  - Add a stable root architecture roadmap and a dated worktree snapshot that
    distinguish proven Rust policy slices from Python-owned effects and cutover.
  - Acceptance: both documents link this checklist, identify the next bounded
    action and rollback boundary, report only observed verification, and pass
    structural readback plus `git diff --check`. This is documentation only:
    branch upload, commit, PR, CI, and live provider checks are not implied.

## Acceptance Criteria

- Existing Python behavioral regressions continue to pass against the migrated
  implementation; intentional changes require separately approved contract updates.
- Rust unit tests cover moved decision logic, and a native wheel is installed and
  imported through Python in a clean environment.
- The first authorization slice preserves fact-read order, exact-grant matching,
  generic public denial, and audit-only detailed cause.
- Domain/use-case code stays independent of transport, database, provider, and
  Python bindings; adapters implement those boundaries.
- Production entry points and packaging are proven at cutover, with no duplicate
  live policy authority or silent Python fallback.
- Every completed task records observed RED/GREEN/REFACTOR and applicable check
  results, including failed, skipped, and pending checks.

## Progress and Verification Evidence

- RGC-01: read this document and full Engram observation #7225 before edits; they
  matched. Baseline SHA `137b101b6d1f294e7fcb302d4fd4bfeb7d760fa8` and the
  focused pre-change Docker check reported 20 passed in 1.66s.
- RGC-01 RED: with `tests/test_native_authorization.py` added first,
  `DOCKER_CONFIG=/tmp/sre-agent-rust-docker-config docker compose --env-file
  /tmp/sre-agent-rust-slice.env --profile checks run --build --rm python-checks
  pytest -q tests/test_native_authorization.py` failed as expected:
  `ModuleNotFoundError: No module named 'sre_agent._core'` (1 failed).
- Build boundary: `rust/core` is dependency-free; `rust/python` is the PyO3
  adapter; the Python module is `sre_agent._core` with `API_VERSION = 1` and
  `evaluate_authorization` accepting identity, resource fact, and grant fact
  tuples. Maturin packages the mixed `src/sre_agent` tree via `pyproject.toml`;
  `docker/api.Dockerfile` supplies Rust only to build/check stages and copies
  the built environment into the runtime image.
- Existing authorization behavior: inactive principal reads no facts; missing,
  mismatched, or inactive resource reads no grant; grant must match all fields
  exactly and be active/allow. Public deny always uses `no_matching_grant`,
  while `denial_cause` carries detailed audit cause. `ResourceType` includes
  `administrative_control` and `incident_workflow` beyond the original
  parameterized test list. No Python policy fallback is planned.
- Preliminary workspace compile: `cargo test --locked --manifest-path
  rust/Cargo.toml` passed with 0 tests before RGC-02 implementation; it does
  not prove behavior. The installed native import is still RED by design.
- RGC-02 Rust RED: `cargo test --locked --manifest-path rust/Cargo.toml`
  failed to compile the new tests with unresolved `evaluate_authorization`,
  `AuthorizationRequest`, `GrantFact`, and `ResourceFact` imports. Rust GREEN:
  the same command passed 4 core tests covering precedence, all seven resource
  kinds, mismatched resource facts, and every exact-grant field.
- RGC-02 Python GREEN: the observed native-import RED became 21 passed in the
  first Docker run. After expanding the resource cases and adding a once-per-
  evaluation native-call assertion, this exact focused command passed 26 tests:
  `DOCKER_CONFIG=/tmp/sre-agent-rust-docker-config docker compose --env-file
  /tmp/sre-agent-rust-slice.env --profile checks run --build --rm python-checks
  pytest -q tests/test_native_authorization.py tests/test_authorization.py
  tests/test_import_boundaries.py`.
- RGC-02 REFACTOR: isolated the Rust core from PyO3, preserved Python as a
  staged fact reader and DTO translator, added the `_core.pyi` type contract,
  pinned the Docker Rust image, and excluded `rust/target` from Git and Docker.
  Final `cargo test --locked --manifest-path rust/Cargo.toml` passed 4 tests;
  `cargo fmt --all --manifest-path rust/Cargo.toml -- --check`,
  `cargo clippy --locked --manifest-path rust/Cargo.toml --all-targets --
  -D warnings`, and `git diff --check` passed.
- Exact broader Docker command: `DOCKER_CONFIG=/tmp/sre-agent-rust-docker-config
  docker compose --env-file /tmp/sre-agent-rust-slice.env --profile checks run
  --build --rm python-checks sh -c 'ruff check --no-cache . && ruff format
  --check --no-cache . && mypy --cache-dir=/tmp/mypy
  src/sre_agent/incident/persistence.py src/sre_agent/incident/runtime.py
  src/sre_agent/governance/dto.py src/sre_agent/governance/authorization.py
  && lint-imports --no-cache && uv lock --check --no-cache && pytest -q
  tests/test_native_authorization.py tests/test_authorization.py
  tests/test_import_boundaries.py tests/test_responses.py
  tests/test_control_authorization_order.py tests/test_incident_authorization.py'`.
  Result: Ruff and format pass, mypy pass (4 files), Import Linter 4 contracts
  kept, uv lock check pass, 90 Python tests passed.
- Full behavioral oracle: `DOCKER_CONFIG=/tmp/sre-agent-rust-docker-config
  docker compose --env-file /tmp/sre-agent-rust-slice.env --profile checks run
  --rm python-checks pytest -q -rs tests` passed 987, skipped 1 in 28.49s.
  The skipped test requires `RUN_OPENROUTER_LIVE_SMOKE=1` and a live provider;
  no private credentials or external live call were authorized.
- Installed-wheel proof: in the checks container, `uv build --wheel --out-dir
  /tmp/native-wheels`, `python -m venv /tmp/native-wheel-venv`, and
  `PIP_CONFIG_FILE=/dev/null PIP_EXTRA_INDEX_URL= /tmp/native-wheel-venv/bin/pip
  install --no-input --index-url https://pypi.org/simple
  /tmp/native-wheels/sre_agent-*.whl` succeeded. From `/tmp`, the isolated
  interpreter confirmed `sre_agent.__file__` is in that venv, imported the
  adapter and `sre_agent._core`, and received an exact-grant allow tuple.
  A preliminary `--no-deps` install was insufficient to import the Python
  adapter because Pydantic was absent; the final clean install resolved it.
- Runtime image smoke: `docker compose --env-file
  /tmp/sre-agent-rust-slice.env build api` followed by `docker compose --env-file
  /tmp/sre-agent-rust-slice.env run --rm --no-deps api python -c 'from sre_agent
  import _core; from sre_agent.governance.authorization import
  AuthorizationDecisionEngine; assert _core.API_VERSION == 1'` passed.
  `DOCKER_CONFIG` pointed to an empty synthetic credentials configuration.
- Scope and rollback: only the authorization decision authority moved; other
  domains remain Python-owned. Rollback restores the prior Python authorization
  module and build metadata/Dockerfile, and removes `rust/`, `_core.pyi`, the
  native test, and related ignore entries. No commit, PR, hosted CI, or live
  service/request proof was performed. This cohesive build + behavior + test
  unit exceeds the ~400-line advisory heuristic because the native packaging,
  lockfile, and regressions are inseparable; no code was compressed to fit it.
- RGC-03 is decomposed before source edits. Audit projection is the first selected
  slice; normalization, control, incident, and provider-evidence slices remain
  pending. The provider-evidence slice is blocked on contract reconciliation.
- RGC-03a RED: `cargo test --locked --manifest-path rust/Cargo.toml --test
  audit_projection` failed with unresolved `sre_agent_core::audit`. The isolated
  Docker focused command for `tests/test_native_audit_projection.py` reported
  2 failed, 1 passed: `_core` lacked `project_responses_audit`. These were
  observed before implementation; existing Python assertions were not altered.
- RGC-03a GREEN: Rust core owns responses audit outcome (including any 403 as
  denied), identifier output-key normalization while retaining `_id` in HMAC
  domains, evidence inclusion and reference domains, fixed metadata redaction
  shape, and `audit_unavailable` accepted/suppressed projection flags. PyO3
  exposes a metadata-only reference plan; Python owns HMAC key custody and
  resolution, UUID/time, Pydantic validation, consumption passthrough, and
  persistence/release gating. `control_event` remains Python-owned. No runtime
  content redactor, append success, or OpenRouter/provider contract change is
  claimed.
- RGC-03a REFACTOR and checks: `cargo test --locked --manifest-path
  rust/Cargo.toml` passed 4 authorization plus 4 audit core tests;
  `cargo fmt --all --manifest-path rust/Cargo.toml -- --check` and
  `cargo clippy --locked --manifest-path rust/Cargo.toml --all-targets --
  -D warnings` passed. The rebuilt isolated Docker checks image ran Ruff lint
  and format (112 files), mypy (4 configured files), Import Linter (4 contracts),
  and `uv lock --check --no-cache` successfully. Focused `pytest -q` for native
  audit projection, audit, responses, responses ASGI errors, and import boundaries passed
  49 tests. Full `pytest -q -rs tests` passed 995, skipped 1; the skip is the
  credentialed OpenRouter live smoke, not authorized here. `git diff --check`
  passed after source normalization.
- Runtime image proof: rebuilt `api` image imported `_core`, called
  `project_responses_audit` (403 -> denied), and constructed a schema-valid
  validation-stage `AuditProjector.event`. An initial smoke fixture with a 403
  authorization stage and no identity/resource failed Pydantic as intended;
  the corrected fixture passed. No hosted CI or live provider was invoked.
- Final compatibility check: the Rust status input is signed so out-of-range
  statuses reach Pydantic's existing `AuditEvent` validation instead of failing
  prematurely at the PyO3 integer boundary; two new DTO rejection tests pass.
- RGC-03a scoped correction: independent verification found that Python status
  integers beyond signed 64-bit still raised PyO3 `OverflowError` before DTO
  validation. New tests for `2**63` and `-(2**63)-1` were RED (2 failed with
  `OverflowError`) against the unchanged checks image. The Python adapter now
  prevalidates status through a Pydantic `TypeAdapter` derived from the existing
  `AuditEvent.response_status` field metadata, with strict mode; it does not
  duplicate audit outcome policy or hard-code DTO bounds. Mounted-source GREEN
  passed 2 tests, then rebuilt-image focused passed 49 and full suite passed
  995 with the same live-provider skip. Rust 8 tests, fmt, Clippy, Ruff,
  configured mypy (4 files), Import Linter (4 contracts), uv lock, final runtime
  image native/adapter/exception smoke, and `git diff --check` passed.
- Additional diagnostic: explicitly running standalone mypy on
  `src/sre_agent/gateway/audit.py` failed with 17 typing errors; this module is
  not in the configured mypy file list. The new status adapter's annotation is
  typed; remaining DTO-dictionary/argument typing debt was not broadened into
  this scoped correction.
- Correction-only rollback removes the `TypeAdapter` status prevalidation from
  `AuditProjector.event` and the two extreme-integer regressions. That would
  reintroduce the observed `OverflowError`; it does not affect Rust projection
  policy, authorization, HMAC custody, or control-event behavior.
- RGC-03a rollback: remove `rust/core/src/audit.rs`, its Rust test, and the
  `lib.rs` module export; remove the PyO3 audit function and `_core.pyi`
  declaration, and restore only the
  previous `AuditProjector.event` implementation plus its new native test.
  Keep the RGC-02 authorization/core packaging unchanged. No commit or PR.
- RGC-04 through RGC-05 remain pending.
- RGC-03b was split before source edits after reconciling this file with full
  Engram observation #7225. RGC-03b1 is the selected mapping-only slice;
  RGC-03b2 and RGC-03b3 remain pending, as do RGC-03c/d/e and RGC-04/05.
- RGC-03b1 RED: `cargo test --locked --manifest-path rust/Cargo.toml --test
  provider_failure` failed with unresolved `sre_agent_core::provider_failure`.
  An isolated checks-image run of `pytest -q
  tests/test_native_provider_failure.py` failed 5 cases because `_core` lacked
  `map_provider_failure`. The first unprivileged Docker attempt could not access
  the local daemon; the same synthetic-env/empty-credentials command ran after
  local daemon access was granted.
- RGC-03b1 GREEN: dependency-free `rust/core` maps timeout to
  `(504, upstream_failed, upstream_timeout)`, unavailable to
  `(503, upstream_unavailable, upstream_unavailable)`, evidence_invalid to
  `(502, upstream_invalid, provider_evidence_invalid)`, and invalid_response
  or any unknown kind to `(502, upstream_invalid, upstream_invalid_response)`.
  PyO3 exposes `sre_agent._core.map_provider_failure`; the Python catch invokes
  it once with no fallback. `ProviderFailure`, `_finish`, consumption, retry
  handling, FastAPI, audit append, provider adapters, and messages did not move.
  Rebuilt isolated Compose checks passed 55 focused native/responses/ASGI/audit/
  import tests, including unknown-kind public/audit parity and native call count.
- RGC-03b1 REFACTOR/checks: `cargo fmt --all --manifest-path rust/Cargo.toml`,
  `cargo test --locked --manifest-path rust/Cargo.toml` (10 passed),
  `cargo clippy --locked --manifest-path rust/Cargo.toml --all-targets --
  -D warnings`, and `git diff --check` passed. Rebuilt isolated Compose checks
  passed Ruff lint and format (113 files), configured mypy (4 files), Import
  Linter (4 contracts), `uv lock --check --no-cache`, and full
  `pytest -q -rs tests` (1001 passed, 1 skipped). The skip is the credentialed
  live OpenRouter smoke and was not authorized. The rebuilt runtime `api`
  image imported the gateway and native extension, called known/unknown native
  mappings, and printed `runtime native provider failure smoke passed`.
- RGC-03b1 rollback: remove `rust/core/src/provider_failure.rs` and its Rust
  test/export, remove the PyO3 function and `_core.pyi` signature, restore only
  the prior mapping expression in `ResponsesService.create`, and remove the
  new native/unknown-kind Python tests. Keep authorization and audit projection
  slices intact. No commit, PR, hosted CI, or live provider request occurred.
- RGC-03b1 scoped correction RED: independent verification found the PyO3
  `&str` argument rejected hashable non-string `ProviderFailure.kind` values
  before `_finish`, bypassing the audit append that the prior Python `dict.get`
  fallback reached. New integration tests for `7`, `None`, and `b"timeout"`
  failed with `TypeError` (3 failed, 30 deselected); direct native tests failed
  the same three cases (3 failed, 5 deselected). Existing known/unknown-string
  mapping tests and production provider calls were not changed.
- RGC-03b1 scoped correction GREEN: PyO3 now accepts a Python object at the
  transport edge, extracts only actual strings, and passes a non-string or
  unextractable string as the Rust core's unknown kind. Rust still owns all
  status/audit/public-code decisions; Python has no mapping or fallback.
  The integration regression confirms a single provider call, one audit event
  correlated to the returned request ID, safe 502 envelope, non-retryability,
  and unavailable consumption for each malformed kind. The previous Python
  mapping threw for unhashable kinds; this boundary safely maps them too rather
  than preserving that exception.
- Correction verification: `cargo fmt --all --manifest-path rust/Cargo.toml`,
  `cargo test --locked --manifest-path rust/Cargo.toml` (10 passed), and
  `cargo clippy --locked --manifest-path rust/Cargo.toml --all-targets --
  -D warnings` passed. Rebuilt isolated Compose focused native/responses/ASGI/
  audit/import run passed 61 tests. Configured Ruff lint/format (113 files),
  mypy (4 files), Import Linter (4 contracts), and uv lock checks passed; full
  `pytest -q -rs tests` passed 1007, skipped 1 credentialed OpenRouter live
  smoke. After strengthening the test to require the current request's audit
  event, a mounted-current-test full run again passed 1007/skipped 1, and Ruff
  still passed. Rebuilt runtime image printed `runtime native malformed-kind
  smoke passed` after importing the gateway and mapping known/malformed kinds;
  Docker inspect reported exit code 0. Its transient `--rm` cleanup was slow
  but the Compose command ultimately exited 0. `git diff --check` passed. No
  hosted CI or live provider request occurred.
- Correction-only rollback restores the previous PyO3 `&str` argument and
  `_core.pyi` string signature, and removes the new malformed-kind regressions;
  it would reintroduce the observed unaudited error. The Rust taxonomy and
  Python native call remain otherwise unchanged.
- Provider evidence direction: the user selected current Python runtime/tests as
  the migration oracle. The difference from the published header-lookup fixture
  was reported as issue #345; that issue does not authorize a behavior change in
  this migration. RGC-03e was decomposed before source edits after matching this
  file with full Engram observation #7225. Both sub-slices are now complete.
- RGC-03e RED: `cargo test --locked --manifest-path rust/Cargo.toml --test
  provider_evidence` failed to compile with unresolved
  `sre_agent_core::provider_evidence` before implementation. The isolated
  Docker native test failed with missing `_core.inspect_provider_response`
  (1 failed, 14 deselected). Existing `tests/test_openrouter.py` was not edited.
- RGC-03e GREEN: dependency-free Rust owns body ID/model/error/incomplete
  acceptance, inline metadata selected-endpoint and attempts evidence, and
  staged `accept`/`reject(kind)`/`catalog_required(selected_model)` decisions.
  A second Rust decision confirms exactly one catalog identity. PyO3 only
  normalizes parsed JSON facts, including Unicode casefold and exact decimal
  representation; Python still owns one no-fallback POST, at most one catalog
  GET, API key, JSON parsing, consumption, output text, DTO, and public ID.
  The catalog decision precedes output-text validation as before. No header
  lookup or issue #345 contract change was made.
- RGC-03e parity edges: native and provider-path characterization covers
  `selected is True` (not numeric truthiness), `attempt == 1` accepting bool
  true and decimal/float one, status 200 rejecting bool true but accepting
  decimal/float 200, Unicode provider casefold, catalog tag/name case
  sensitivity, malformed mapping/list shapes, duplicate catalog identities,
  failure consumption, and exactly one POST plus conditional GET. The expanded
  native characterization file passed 26 tests; the rebuilt focused provider,
  responses, ASGI, audit, and import-boundary suite passed 100 before its last
  11 characterization cases were added.
- RGC-03e final checks: `cargo fmt --all --manifest-path rust/Cargo.toml`,
  `cargo test --locked --manifest-path rust/Cargo.toml` (13 Rust tests),
  `cargo clippy --locked --manifest-path rust/Cargo.toml --all-targets --
  -D warnings`, and `git diff --check` passed. The final rebuilt isolated
  Docker checks image passed Ruff lint/format (114 files), configured mypy
  (4 files), Import Linter (4 contracts), `uv lock --check --no-cache`, and
  full `pytest -q -rs tests` (1033 passed, 1 skipped). The skip is the
  credentialed live OpenRouter smoke; no credentials or live request were
  authorized. The rebuilt runtime image imported the gateway/native module
  and accepted a synthetic valid routing fact tuple.
- RGC-03e rollback: restore only the previous OpenRouter evidence helpers and
  adapter call chain; remove `rust/core/src/provider_evidence.rs`, its Rust
  test/export, the two PyO3 functions and `_core.pyi` declarations, and the
  native characterization test. Keep earlier authorization, audit projection,
  provider-failure mapping, build metadata, and Docker boundaries intact. No
  commit, PR, hosted CI, or live provider call was performed. This cohesive
  behavior/test slice exceeds the ~400-line advisory task heuristic because
  typed fact normalization and edge-case regressions are inseparable; no
  code-golf or artificial test omission was used.
- RGC-03e3 correction scope: independent verification found PyO3 eagerly
  casefolded unselected endpoint providers and catalog entries, even when the
  body/catalog ID already made acceptance impossible. This is avoidable work
  on untrusted JSON, not a known public decision mismatch. Add deterministic
  side-effecting-string RED tests before changing the fact reader; preserve
  current Python parity and issue #345 scope.
- RGC-03e3 RED: four new native tests with a side-effecting `str.casefold`
  subclass failed against the unchanged checks image. Invalid response ID
  called casefold 2 times instead of 0; 20 unselected endpoints caused 21
  calls instead of 1; invalid catalog ID called it 20 times instead of 0;
  and a nonmatching catalog model ID caused 2 calls instead of 1. Rust tests
  for the new relevance helpers failed to compile with unresolved imports
  before implementation.
- RGC-03e3 GREEN/REFACTOR: Rust now exposes body validity and inline/catalog
  fold plans. PyO3 defers metadata reading until valid body facts and casefolds
  only the Rust-selected endpoint, valid attempt, and catalog candidate model
  IDs. Catalog ID rejection skips endpoint normalization. Rust remains the
  only acceptance authority, while Python HTTP, consumption, output text,
  public ID, and issue #345 boundary are unchanged.
- RGC-03e3 checks: `cargo fmt --all --manifest-path rust/Cargo.toml`,
  `cargo test --locked --manifest-path rust/Cargo.toml` (15 Rust tests), and
  `cargo clippy --locked --manifest-path rust/Cargo.toml --all-targets --
  -D warnings` passed. Rebuilt isolated Docker focused native/OpenRouter/
  responses/ASGI/audit/import suite passed 115 tests. Final Docker checks
  passed Ruff lint/format (114 files), configured mypy (4 files), Import
  Linter (4 contracts), uv lock, and full `pytest -q -rs tests` (1037 passed,
  1 skipped credentialed live provider smoke). Rebuilt runtime image imported
  the gateway/native module and passed synthetic accept/reject smoke;
  `git diff --check` passed. No credentials, live call, commit, PR, or issue
  edit occurred.
- RGC-03e3 correction-only rollback removes Rust relevance helpers and the
  two-phase PyO3 normalization, restoring earlier eager fact extraction; it
  also removes the four new native and two Rust relevance regressions. Earlier
  RGC-03e decisions, Python adapter, and other migration slices stay intact.
- RGC-03b3a selected independently of unfinished RGC-03b2 and RGC-03b3.
  Reconciled this file with full Engram observation #7225 before edits. The
  current Python OpenRouter runtime/tests, not issue #345's divergent fixture,
  are the exact parity oracle. No provider evidence or routing change was made.
- RGC-03b3a RED: `cargo test --locked --manifest-path rust/Cargo.toml --test
  consumption` failed with unresolved `sre_agent_core::consumption`. The
  rebuilt isolated checks image ran `pytest -q
  tests/test_native_openrouter_consumption.py` and failed both cases because
  `_core.project_openrouter_consumption` was absent. A first unprivileged
  Docker attempt could not access the daemon; the explicitly authorized local
  Docker run provided the observed Python RED.
- RGC-03b3a GREEN: Rust core now decides contradictory totals using decimal
  digit arithmetic without fixed-width overflow, discards billed cost without
  a valid parsed timestamp, sets all null fields and billing-context presence,
  and chooses all four availability states, including absent→unavailable for
  failure context. PyO3 transports normalized fact triples. Python retains
  lexical token/Decimal and timestamp parsing, HTTP, DTO construction, provider
  evidence, and audit release gating; there is no Python projection fallback.
  Rebuilt focused native/OpenRouter/Responses/Audit/import suite: 113 passed.
- RGC-03b3a REFACTOR/checks: `cargo fmt --all --manifest-path
  rust/Cargo.toml -- --check`, `cargo test --locked --manifest-path
  rust/Cargo.toml` (18 Rust tests), `cargo clippy --locked --manifest-path
  rust/Cargo.toml --all-targets -- -D warnings`, and `git diff --check`
  passed. Final rebuilt checks image passed Ruff lint and format (115 files),
  configured mypy (4 files), Import Linter (4 contracts), uv lock, and full
  `pytest -q -rs tests` (1039 passed, 1 skipped). The skip is the credentialed
  OpenRouter live smoke, not authorized. An initial isolated wheel build failed
  on non-writable uv cache, then Cargo target; rerunning with `UV_CACHE_DIR`
  and `CARGO_TARGET_DIR` under `/tmp` built and installed the wheel into a
  fresh venv and printed `isolated wheel consumption smoke passed`. Rebuilt
  runtime `api` image imported the adapter/native module and printed `runtime
  native consumption smoke passed`. No hosted CI or live provider call ran.
- RGC-03b3a rollback: remove only `rust/core/src/consumption.rs`, its core
  export/test, the PyO3 function and `_core.pyi` declaration, restore the prior
  `_consumption`/`_failure_consumption` projection in `openrouter.py`, and
  remove its native characterization test. Earlier authorization, audit,
  provider-failure, and provider-evidence slices remain intact. No commit,
  push, PR, issue edit, credential use, or live provider call occurred.
- RGC-03c1 selected as a bounded control-audit slice without claiming the
  broader administrative control domain is complete. The full Engram task
  observation #7225 and this file were reconciled before edits; current Python
  runtime/tests remained the parity oracle.
- RGC-03c1 RED: `cargo test --locked --manifest-path rust/Cargo.toml --test
  control_audit` failed with unresolved `sre_agent_core::control_audit`.
  Rebuilt Docker `pytest -q tests/test_native_control_audit.py` reported
  missing `_core.project_control_audit` (2 symbol failures); one independent
  test fixture initially lacked `reason_code` and was corrected. A later
  focused non-authorization regression observed 503 instead of 422 because
  the first PyO3 fact adapter eagerly read an irrelevant malformed subject.
- RGC-03c1 GREEN: dependency-free Rust now owns terminal stage/reason,
  subject relevance, retryability, denied versus error outcome, grant and
  resource reference specifications, and denial-cause gating. PyO3 exposes
  one `project_control_audit` plan and lazily extracts subject facts only when
  the Rust core marks them relevant. `_finish` and `control_event` use that
  plan with no Python policy fallback; a successful `_finish` invokes it once.
  Python retains HMAC key custody and canonical digest computation, UUID/time,
  `AuditEvent` validation, transactional append, public error envelope and
  release gating. The hidden denied 404 remains distinct from an authorized
  missing-target 404; no LLM routing evidence is emitted.
- RGC-03c1 REFACTOR/checks: `cargo fmt --all --manifest-path rust/Cargo.toml`,
  `cargo test --locked --manifest-path rust/Cargo.toml` (21 Rust tests), and
  `cargo clippy --locked --manifest-path rust/Cargo.toml --all-targets --
  -D warnings` passed. Before the lazy fact correction, rebuilt focused
  native/control/audit/import tests passed 72. After correction, a rebuilt
  checks image passed Ruff lint and format (116 files), configured mypy
  (4 files), Import Linter (4 contracts), `uv lock --check --no-cache`, and
  full `pytest -q -rs tests` (1046 passed, 1 skipped). The skip is the
  credentialed live OpenRouter smoke, which was not authorized. A fresh
  container venv installed the built maturin wheel and printed `isolated
  wheel control audit smoke passed`; the rebuilt runtime `api` image imported
  the native module and adapter and printed `runtime native control audit
  smoke passed`. No hosted CI, credentialed/live call, commit, push, PR, or
  issue edit occurred.
- RGC-03c1 rollback: remove `rust/core/src/control_audit.rs`, its Rust test
  and core export, the PyO3 plan and `_core.pyi` declaration, restore only
  the previous `_finish` stage/reason/subject/retry logic and
  `AuditProjector.control_event` projection, and remove the native control
  characterization test. Earlier authorization, responses audit, provider,
  and consumption slices remain intact. The cohesive Rust/PyO3/adapter/tests
  unit exceeds the advisory ~400-line task heuristic without code-golf or
  omitted tests; no PR-size exception is inferred.
- RGC-03c1 independent parity correction RED: two new focused tests against
  the unchanged checks image failed (2 failed, 7 deselected). A permanently
  failing native plan was called twice: the second call escaped `_finish` as
  `RuntimeError` instead of returning the previous fail-closed 503. A
  duck-typed allow with `policy_id` but no `reason_code` was accepted by the
  PyO3 reader, whereas the prior Python projector raised `AttributeError`.
- RGC-03c1 correction GREEN: `_finish` now uses the Rust plan's retryability
  for normal attempts and a static retryable 503 public envelope if planning,
  projection, or append fails; it never re-invokes a failed plan. PyO3 reads
  `decision.reason_code` for historical duck-typed shape parity before
  forwarding only decision/policy facts to Rust. Rust remains the sole normal
  control-audit policy authority; the exception path is fail-closed public
  release gating, not a second normal policy implementation.
- Correction checks: `cargo fmt --all --manifest-path rust/Cargo.toml`, full
  `cargo test --locked --manifest-path rust/Cargo.toml` (21 Rust tests), Clippy
  with `-D warnings`, and `git diff --check` passed. Rebuilt focused control,
  audit, and import tests passed 76. Rebuilt full checks passed Ruff lint and
  format (116 files), configured mypy (4 files), Import Linter (4 contracts),
  uv lock, and `pytest -q -rs tests` (1048 passed, 1 skipped credentialed live
  provider smoke). A corrected fresh-venv wheel build/install/import printed
  `isolated wheel control correction smoke passed`; an initial wheel smoke
  invocation failed only because its shell-embedded Python contained escaped
  newline tokens, after build/install had succeeded. The rebuilt runtime `api`
  image printed `runtime native control correction smoke passed`. No hosted
  CI, credentials/live request, commit, push, PR, or issue edit occurred.
- Correction-only rollback restores the earlier exception-path second native
  invocation in `control/service.py`, removes the PyO3 `reason_code` shape
  read, and removes the two new focused tests; this would reintroduce both
  observed regressions and does not alter earlier migration slices.
- RGC-03d1 used current Python runtime/tests as parity oracle after reconciling
  this file and full Engram #7225. Lock/replay, stored-state checks, and workflow
  lookup precede native admission; named preconditions and reduction follow it.
- Initial RED: `cargo test --locked --manifest-path rust/Cargo.toml --test
  incident_admission` failed unresolved import. The unchanged Docker checks
  image with new tests mounted failed 2 native tests for missing
  `_core.admit_incident_transition`. An unprivileged Docker attempt lacked
  daemon access; an earlier daemon-enabled run omitted the newly mounted test.
- Initial GREEN: dependency-free Rust owns ordered source, actor, reference,
  approval, and outcome admission; one PyO3 call reads facts only after prior
  Rust acceptance. Python maps verdicts to existing exceptions and reuses the
  selected outcome in reducer/document. Side-effecting facts prove staged reads.
- Initial checks: Rust fmt/test (24 tests)/Clippy and `git diff --check` passed;
  rebuilt focused incident/native/persistence/contract/import tests passed 62.
  Ruff lint/format (117 files), configured mypy (4), Import Linter (4), uv lock,
  and full `pytest -q -rs tests` passed (1053, 1 skipped credentialed live
  OpenRouter smoke). Fresh-wheel install/import and rebuilt runtime API smoke
  passed with synthetic facts. Intermediate Ruff and mypy failures were fixed.
- Approval-read correction RED: a side-effecting native approval property
  failed against the unchanged image (1 failed, 2 deselected): PyO3 read it
  when Python short-circuited. Rust now marks approval relevance; PyO3 skips
  irrelevant reads. Initial final checks above included this correction.
- Malformed-fact correction RED: independent verification found actor `7`
  leaked raw `TypeError` rather than `InvalidTransitionError`; reference version
  or declared outcome `7` leaked `TypeError` rather than
  `PreconditionFailedError`. Six mounted native/runtime cases failed (6 failed,
  18 deselected). Two more RED cases showed that a truthy non-string outcome
  with no declared outcomes must survive in the decision document (2 failed,
  24 deselected). Dataclass annotations do not enforce runtime types.
- Correction GREEN: PyO3 classifies non-string facts without deciding
  admission; Rust returns typed actor/reference/outcome verdicts and selects
  raw pass-through for a truthy unconstrained outcome (null for falsey).
  Python has no admission fallback. Ordered reads and all retained Python
  runtime boundaries are unchanged.
- Correction final checks: Rust fmt/test (25 tests)/Clippy and `git diff
  --check` passed. Rebuilt checks image passed 70 focused tests; Ruff
  lint/format (117), configured mypy (4), Import Linter (4), uv lock, and
  full `pytest -q -rs tests` passed (1061, 1 skipped live provider smoke).
  A fresh-venv wheel install printed `isolated wheel malformed incident smoke
  passed`; rebuilt runtime API image printed `runtime native malformed incident
  smoke passed` with synthetic facts. One intermediate Clippy needless-borrow
  and one Ruff long-line failure were corrected and rerun. No hosted CI,
  credentials, live call, commit, push, PR, or issue edit occurred.
- RGC-03d1 rollback removes its Rust core module/export/test, PyO3 function,
  `_core.pyi` declaration, and new regressions, then restores the old Python
  generic checks and outcome selection in `_validate`, `_reduce`, and
  `_decision_document`. Earlier migration slices remain. Correction-only
  rollback of PyO3 malformed-fact handling reintroduces the observed parity
  failures. This cohesive unit exceeds the ~400-line advisory heuristic;
  no PR-size exception is inferred.
- RGC-04a contract: reconciled this file and full Engram observation #7225
  before edits. ADR-005 and the current projector hash
  `UTF8("sre-audit-v1\0" + domain + "\0" + exact formatted source value)`;
  `key_version` is only an `AuditRef` envelope field, not digest input.
  RustCrypto `hmac` 0.13 and `sha2` 0.11 were selected for the PyO3 adapter
  only; Python keeps secret loading, DTO validation, persistence, and release.
- RGC-04a RED: `cargo test --locked --manifest-path rust/Cargo.toml -p
  sre-agent-python audit_reference -- --nocapture` failed with unresolved
  `audit_reference` module. The unchanged Docker checks image with the new
  native test mounted reported 6 failed, 1 passed: missing
  `_core.audit_reference_digest` and observed Python `hmac.new` path.
  A second key-type parity test against the first GREEN checks image failed
  because generic `PyBuffer` incorrectly accepted `memoryview`.
- RGC-04a GREEN/REFACTOR: the PyO3 adapter formats Python facts,
  accepts only bytes/bytearray keys, and computes a streaming
  HMAC over the exact ADR-005 UTF-8 segments in Rust; it emits 64 lowercase
  hex digits. Python `AuditProjector.reference` invokes this native function
  once and constructs the unchanged `AuditRef`, with no Python HMAC fallback.
  Native vectors cover Unicode, embedded NUL, domain separation, and custom
  formatting; Python tests cover version-envelope invariance, invalid
  version/key behavior, and the absence of `hmac.new`. A synthetic lone
  surrogate raised `UnicodeEncodeError` in the rebuilt runtime image; that
  probe established the exception type, not full error-position parity.
- RGC-04a checks: `cargo fmt --all --manifest-path rust/Cargo.toml --
  --check`, full `cargo test --locked --manifest-path rust/Cargo.toml`
  (26 tests), `cargo clippy --locked --manifest-path rust/Cargo.toml
  --all-targets -- -D warnings`, and `git diff --check` passed. Rebuilt
  Docker focused native/audit tests passed 12. After correcting one Ruff
  UP012 test-only warning, the rebuilt checks image with the corrected
  test mounted passed Ruff lint/format (118 files), configured mypy (4),
  Import Linter (4 contracts), `uv lock --check --no-cache`, and full
  `pytest -q -rs tests` (1069 passed, 1 skipped credentialed live OpenRouter
  smoke). A fresh container venv installed the maturin wheel and printed
  `isolated wheel audit reference smoke passed`; the rebuilt runtime API
  image printed `runtime native audit reference smoke passed`. No hosted CI,
  credentialed/live call, commit, push, PR, or issue edit was performed.
- RGC-04a rollback: restore only the former Python HMAC body in
  `AuditProjector.reference`; remove the `audit_reference_digest` PyO3
  function, `rust/python/src/audit_reference.rs`, its Rust test, the two
  adapter-only dependencies and resulting Cargo lock entries, `_core.pyi`
  declaration, and new native characterization test. Retain every previous
  Rust core policy and gateway slice. RGC-04 gateway cutover remains pending;
  no PR-size exception or delivery authority is inferred.
- RGC-04a independent formatting correction RED: two new native/Python
  regressions mounted into the unchanged checks image failed (2 failed,
  8 deselected). Replacing `builtins.format` changed the digest although
  the original f-string ignores that binding; a lone-surrogate domain
  raised `UnicodeEncodeError` before a value's failing `__format__`, whereas
  the original f-string raises the value's `RuntimeError` first. The Python
  f-string oracle was also checked directly with both synthetic inputs.
- RGC-04a formatting correction GREEN: PyO3 now calls C-level
  `PyObject_Format` with an empty spec for each fact and holds both formatted
  Python objects until both calls finish; only then does it extract UTF-8
  strings for the Rust HMAC. This preserves the original formatting order
  and ignores monkeypatches of `builtins.format`, without adding Python
  cryptography or changing key-type, envelope, persistence, or release logic.
- Correction final checks: `cargo fmt --all --manifest-path rust/Cargo.toml
  -- --check`, full `cargo test --locked --manifest-path rust/Cargo.toml`
  (26 tests), `cargo clippy --locked --manifest-path rust/Cargo.toml
  --all-targets -- -D warnings`, and `git diff --check` passed. Rebuilt
  focused native/audit tests passed 15. Rebuilt checks image passed Ruff
  lint/format (118 files), configured mypy (4), Import Linter (4 contracts),
  uv lock, and full `pytest -q -rs tests` (1071 passed, 1 skipped credentialed
  live OpenRouter smoke). Fresh-venv wheel install printed `isolated wheel
  audit format smoke passed`; rebuilt runtime API image printed `runtime
  native audit format smoke passed`, both with the synthetic format override.
  No hosted CI, credentials, live request, commit, push, PR, or issue edit.
- Correction-only rollback restores the PyO3 `builtins.format` calls and
  removes the two formatting-order regressions; it reintroduces the observed
  digest tampering and exception-order failures. The earlier native HMAC
  slice and its key-type correction remain independent.
- RGC-04a1 RED: four parameterized regressions against the unchanged native
  image failed (4 failed, 10 deselected). The exception's `object` was only
  the surrogate-bearing segment, not HEAD's complete formatted string;
  its `start`/`end` were segment-relative. The oracle asserts encoding,
  object, start, end, and reason for domain and value surrogates at multiple
  positions. An initial unprivileged Docker call lacked daemon access.
- RGC-04a1 GREEN: PyO3 still calls `PyObject_Format` on domain then value,
  joins the exact ADR-005 input as Python Unicode, calls `.encode()` once on
  that whole string, and passes those bytes to RustCrypto HMAC. Key custody,
  bytes/bytearray-only key validation, no Python HMAC fallback, valid digest
  vectors, and the dependency-free `rust/core` boundary remain unchanged.
  Rebuilt focused native/audit tests passed 19.
- RGC-04a1 REFACTOR/checks: container Rust fmt, full Cargo test (26 tests),
  and Clippy `-D warnings` passed. The host lacked `cargo`; the slim checks
  image lacked Rustfmt/Clippy, so those two components were installed only in
  an ephemeral checks container. Ruff lint/format (118 files), configured
  mypy (4 files), Import Linter (4 contracts), uv lock, `git diff --check`,
  and full `pytest -q -rs tests` passed (1075 passed, 1 skipped credentialed
  live provider smoke). Fresh-venv wheel build/install/import and rebuilt
  runtime-image native/adapter smokes passed, including value error offset
  20 and whole-string `object`. The first wheel smoke had shell-escaped
  newline syntax, corrected on the next run; wheel build/install had passed.
  No hosted CI, credentials, live call, commit, push, PR, or issue edit.
- RGC-04a1 correction-only rollback restores the former segmented PyO3
  extraction and Rust digest arguments and removes the four new regression
  cases. It would reintroduce the observed diagnostic mismatch without
  reverting the earlier native HMAC or formatting-order corrections.
- RGC-03b3b is a bounded direct continuation. Before edits, this file's
  SHA-256 matched the concatenated full Engram mirror #7225/#7453
  (`87e7f344bcf87ed64827d5ef23983a3983b4b9b5b3b9eb6645ae0d74ab171d67`).
  Rust and native characterization tests were written first for completed/list
  gating, malformed/nonmatching entries, ordered text, one versus two empty
  strings, and lone-surrogate preservation. The host has no Cargo or pytest;
  `.venv/bin/python -m pytest` reported `No module named pytest`. A local
  Docker attempt reported daemon permission denied. The escalated Docker
  request hung and was interrupted. The parent later ran the new native tests
  against the pre-rebuild checks image: all 9 failed for missing
  `_core.completed_openrouter_output_text`. This was a real old-image RED,
  but observed after source implementation, not before it.
- RGC-03b3b source now has a dependency-free Rust index/separator plan and a
  PyO3 adapter that keeps selected `PyString` objects in Python until `join`.
  `_completed_output_text` invokes native selection with no Python policy
  fallback; Python still turns native rejection into `ProviderFailure` and
  retains provider evidence/catalog ordering, DTO text limits, consumption,
  audit, and release. The parent reported rebuilt focused Python GREEN
  (81 passed), full Python GREEN (1084 passed, 1 skipped credentialed live
  provider smoke), and full Cargo workspace tests (29 passed). The first
  static run found only two Ruff E501 lines in the new test; both were
  mechanically wrapped. After that correction, rebuilt checks passed Ruff
  lint/format, configured mypy, Import Linter, and uv lock. An isolated
  wheel build/install/import smoke passed. `git diff --check` and
  `python3 -m py_compile` passed locally. A rebuilt runtime API image passed
  synthetic native/adapter smoke after the first smoke input was corrected
  to include the required message `status: completed`; that first failure
  was a fixture error, not a source failure. The parent normalized Rust
  sources with pinned Rust 1.98.1 `cargo fmt`; post-normalization
  `cargo fmt --check` and `cargo clippy --locked --all-targets -- -D warnings`
  passed in a Python-capable checks image. The initial Clippy attempt in a
  slim Rust image failed because it lacked Python. A post-format rebuild
  passed full Python `pytest -q -rs tests` (1084 passed, 1 credentialed-live
  skip) and full Cargo workspace tests (29 passed); `git diff --check` also
  passed. Independent source review found no production-reachable
  parity/security defect; a low-severity direct
  helper-only custom Mapping/list-subclass difference is outside the plain
  dict/list JSON path.
- RGC-03b3b rollback removes only `rust/core/src/openrouter_output.rs`, its
  core export/test, the PyO3 function and module registration, `_core.pyi`
  declaration, and new native characterization test; restore the previous
  Python `_completed_output_text` body. Prior provider-evidence and
  consumption slices remain intact. No commit, push, PR, issue edit,
  credentials, or live provider call occurred.
- RGC-H1 (2026-09-26): created root `MIGRATION_PLAN.md` for the stable
  architecture/sequence and `MIGRATION_STATUS.md` for the dated local snapshot.
  Verified the current branch is `worktree/rapid-meadow-d2ee`; HEAD and local
  `main` merge-base are `137b101b6d1f294e7fcb302d4fd4bfeb7d760fa8`.
  That is the pre-migration base, not an immutable tested candidate SHA. The
  handoff records the previously observed post-Rustfmt 1084 Python passes
  with one credentialed-live skip, 29 Cargo passes, static checks, wheel
  install/import and runtime smoke, plus the RGC-03b3b RED chronology caveat.
  It does not assert these behavioral checks were rerun for the docs-only edit.
  Structural readback and `git diff --check` were observed for this handoff;
  no Docker, source/test change, commit, push, PR, CI, credentials, or live
  provider call was performed by RGC-H1.

## Next Step

Read root `MIGRATION_STATUS.md` and `MIGRATION_PLAN.md`, then inventory RGC-03b2
request normalization and the rest of RGC-03b3 success-response normalization
without changing provider evidence. The rest of RGC-03c, RGC-03d beyond generic
admission, RGC-04 beyond audit-reference HMAC, and RGC-05 remain pending. Do not
alter existing authorization/responses-audit boundaries. Remote delivery remains
a separate authorized step; it has not happened in this handoff.
