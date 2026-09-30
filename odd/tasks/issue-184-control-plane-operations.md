# Issue 184 — Control-plane operations

## Objective

Implement the authorized HTTP boundary for Resources, ModelAlias records, and direct Grants required by GitHub issue #184.

## Problem and rationale

Consumers must not duplicate authorization, lifecycle, idempotency, concurrency, secrecy, or audit rules. The runtime therefore needs to implement the accepted 2.2.0 contracts through the existing control-plane service and persistence boundaries.

## Authorized scope

- Local implementation and verification for issue #184.
- Reuse the authorization engine, idempotency records, and metadata-only audit pipeline.
- Preserve the owner boundaries and lifecycle defined by the 2.2.0 resource-catalog contract.
- Do not invent unresolved CAS or discoverability semantics.

## Constraints

- Strict TDD is enabled by `AGENTS.md`: every implementation task requires observed RED, GREEN, then REFACTOR.
- Keep secrets and provider configuration out of Resources, Grants, responses, logs, and audit content.
- Use cohesive work units; the approximately 400 authored-line target is advisory, not a reason to omit tests or compress code.
- PR reproduction evidence must use the existing Docker Compose checks boundary.
- RDD is disabled globally; ordinary repository review policy applies.
- Contract 2.2.0 is immutable. Any new audit operation must be published in an additive 2.3.0 full snapshot.
- Grant mutation and authoritative audit share PostgreSQL and must commit through one caller-owned transaction; no outbox is needed for this synchronous authority boundary.

## Verification

- Focused runner: `docker compose --profile checks run --build --rm python-checks pytest -q <focused tests>`
- Broader control-plane and authorization suites after each completed vertical slice.
- Contract/conformance checks when a published projection or fixture is affected.

## Checklist

- [x] **T1 — Grant revocation vertical slice.** Add authorized, idempotent, trace-preserving `DELETE /v1/grants/{id}` with metadata-only audit and prove that later authorization observes the revocation without restart.
- [x] **T2 — Grant creation and filtered listing.** Add idempotent create plus bounded listing with the contract-required principal/resource filter and non-enumerating authorization behavior.
- [x] **T3 — ModelAlias create and reads.** Add closed-body create, get, and bounded list operations while preserving assignment ownership and rejecting secret/arbitrary fields.
- [ ] **T4 — Resolve remaining contract decisions.** Obtain explicit decisions for ModelAlias mutation CAS transport/token, ResourceCatalogEntry discoverability source, and the owner coverage expected from #184.
- [ ] **T5 — Catalog and alias lifecycle completion.** Implement the approved catalog projections and ModelAlias assignment/status mutations with stale-write conflict handling, then complete integration, audit, contract, and isolated HTTP evidence.

## Acceptance criteria

- Unauthorized actors cannot enumerate or mutate Resources, ModelAliases, or Grants.
- Replayed mutations produce one logical result.
- Stale updates conflict without overwriting current state.
- Grant revocation preserves history and affects later authorization immediately.
- ModelAlias owns routing fields and accepts no provider secrets.
- Runtime behavior follows the 2.2.0 lifecycle and never relies on implicit seed repair.

## Progress

- Exploration confirmed #18 and #129 are merged and local `main` is synchronized to `07dbabe`.
- T1 has an implemented strict-TDD candidate: RED was observed for the missing route, audit rollback, and schema readiness; Ruff format/lint pass and 57 focused control, health, persistence, authorization, and acceptance tests pass.
- T1 is complete. The additive 2.3.0 contract admits `grants.revoke`, the real projected event validates with `reason_code="grant_matched"`, and frozen conformance evidence traces issue-184.
- The user authorized a 2.3.0 additive contract plus atomic mutation/audit boundary. Architecture exploration selected an explicit transactional audit-store protocol over an optional generic-store session argument. The full contract snapshot is expected to exceed 400 lines and still requires explicit maintainer approval for `size:exception` before publication.
- Runtime atomicity is implemented and independently reverified: grant mutation and authoritative audit now stage in the identical caller-owned PostgreSQL session. RED then GREEN proved session identity and rollback on audit rejection; Ruff/lint pass and 91 focused tests pass.
- The maintainer explicitly approved `size:exception` for the immutable full 2.3.0 contract snapshot. Keep that snapshot as a dedicated cohesive review slice.
- Independent final verification passed: the runtime preserves authorization-before-lookup and convergent revocation, mutation and metadata-only audit are atomic, 2.2.0 remains byte-identical, and the 2.3.0 manifest/evidence contains 187 artifacts and 11 checks.
- T2 is complete. Grant creation is closed, authorized, idempotent, and commits the Grant, idempotency binding, and metadata-only audit in one transaction; filtered listing requires exactly one principal/resource filter and returns stable bounded results without probing targets before authorization.
- T2 strict TDD evidence: the initial focused RED produced 9 failures for missing routes, service methods, and scope mappings; GREEN and refactor passed 18 focused tests and 37 broader control-plane tests. Independent hardening then observed 3 focused failures for schema-invalid success audit reasons and mutable replay, followed by 3 focused passes after the fix.
- T2 replay now returns the persisted original response after later Grant mutation without a second mutation or audit. Real persisted `grants.create` and `grants.list` success events validate against the 2.3.0 `AuditEvent` with `reason_code="grant_matched"`; an authorized idempotency conflict retains the public `idempotency_conflict` code and uses the contract-valid audit reason `status_conflict`.
- Final T2 verification passed the full Docker Compose Python lane with 812 passed and 1 skipped, all 89 contract-tooling tests, and immutable validation for every release from 1.0.0 through 2.3.0. The regenerated 2.3.0 evidence contains 189 artifacts and 12 checks, including the explicit `issue-184-t2` grant create/list result; 2.2.0 remains unchanged.
- T4 blocks the mutation half of ModelAlias and the final catalog projection; it does not block T1–T3.
- T3 is complete. POST /v1/model-aliases is closed (model_alias_id, alias, concrete_model, router, inference_provider), admin.write, Idempotency-Key required, stable replay + 409 idempotency_conflict, metadata-only audit, atomic alias+idempotency+audit with joint rollback. GET /v1/model-aliases is admin.read, limit 1-100 default 100, rejects cursor/page/offset/continuation_token/next/unknown, bounded items/limit/truncated, deterministic asc order. GET /v1/model-aliases/{id} authorizes before lookup, safe 404 for absent/inactive/not-visible, no secrets, metadata-only audit. No PUT assignment/status (T4 untouched, zero runtime hits).
- T3 strict TDD evidence: initial RED 37 failed (KeyError POST /v1/model-aliases, AttributeError create_alias); GREEN 65 passed focused+plane+order, 857 passed 1 skipped full Compose, 90 Node, validate 2.3.0 192 artifacts 13 checks, validate-all 1.0.0-2.3.0. Independent read-only verifier confirmed closed body, scopes, idempotency, auth ordering (3 new rows), atomic audit, real AuditEvent 2.3.0 validation, no T4 routes, 2.2.0 untouched, issue-184-t3 additive, 65 passed + 2.3.0 192/13 spot checks.
- T3 blocker fix: non-openrouter router passed Pydantic and failed at DB CK as 409 status_conflict. RED 1 failed (assert 409 == 422); fix Literal["openrouter"] in ModelAliasCreate matching RoutingEvidence + DB CK; GREEN 1 passed then 38 passed file, 66 passed focused, 858 passed 1 skipped full, Node 90, validate 2.3.0 192/13, validate-all 9 releases, ruff/format/mypy/boundaries/alembic/lock/diff-check PASS, 2.2.0 zero-change. No 2.3.0 regen needed.
- T3 risks: alias list orders by (model_alias_id, alias) asc (resources has no created_at) — deterministic/stable, pre-existing OpenAPI (created_at,id) text in 2.2.0/2.3.0 needs future additive text correction, non-blocking. Full-worktree diff ~2400 insertions includes prior T1/T2 work; commit slicing remains orchestrator call. skill_resolution paths-injected for go-testing, work-unit-commits, cognitive-doc-design.

## Next step

Start T4 decision capture (CAS transport/token, discoverability source, owner coverage). Do not implement T5 mutations until T4 is explicitly decided.
