# Issue 25 audit event-ID contract 2.6.0

The historical audit-detail OpenAPI parameter used generic letter-leading `Id`,
although its event schema/runtime accepted UUIDs and `cor_` IDs. This new additive
release scopes `AuditEventId` to audit detail only; all other IDs remain restricted.
Prior immutable releases through2.5.0 remain byte-identical. Runtime settings and
release metadata are not silently upgraded; clients must deliberately use2.6.0.

The full self-contained snapshot is required by release tooling (no inheritance).
Maintainer explicitly approved a size exception on2026-10-06 for2.6.0 only, with
`size:exception-contract-update`; it is not a waiver for the UI/evidence PRs.

Failure-first cases: absent2.6 release fails; unchanged copied audit parameter
rejects digit-leading UUID; dedicated parameter accepts valid UUID variants and
correlation IDs, rejects malformed IDs and preserves the generic Id restriction.
Targeted checks: 10 passed. Independent parent validation: 3 passed in 115.8s.
Generation produced 3 projection fixtures and immutable
manifest/evidence covering 204 artifacts / 17 checks. Full tooling suite still pending
at candidate preparation; final PR will record its observed result separately.

## Containerized reproduction

Prerequisites: Git checkout, Docker, ignored complete local `.env.worktree` based
on `.env.example` (synthetic values only). No external provider or shared database.
Harness uses pinned Node 22.14 image and tooling lockfile; checks execute in tmpfs.
The screenshot renders actual successful validator output, not invented evidence.
Optional Redocly telemetry is disabled in replay commands to avoid external
network waits; validation remains unchanged.

```sh
docker compose --env-file .env.worktree -p audit25-contract --profile checks build harness
docker run --rm --network none -e REDOCLY_TELEMETRY=off --tmpfs /workspace:rw,nosuid,size=512m,uid=1000,gid=1000,mode=0755 -v "$PWD/schemas:/source/schemas:ro" -v "$PWD/scripts:/source/scripts:ro" audit25-contract-harness node --test schemas/tooling/test/audit-event-id-release.test.mjs > docs/evidence/issue-25-contract-validation.log
docker run --rm --network none -e REDOCLY_TELEMETRY=off --tmpfs /workspace:rw,nosuid,size=512m,uid=1000,gid=1000,mode=0755 -v "$PWD/schemas:/source/schemas:ro" -v "$PWD/scripts:/source/scripts:ro" audit25-contract-harness node schemas/tooling/release.mjs validate-all
docker run --rm --network none -e REDOCLY_TELEMETRY=off --tmpfs /workspace:rw,nosuid,size=512m,uid=1000,gid=1000,mode=0755 -v "$PWD/schemas:/source/schemas:ro" -v "$PWD/scripts:/source/scripts:ro" audit25-contract-harness node schemas/tooling/release.mjs conformance --check coverage
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/scripts/capture_issue25_contract.mjs:/e2e/capture_issue25_contract.mjs:ro" -v "$PWD/docs/evidence:/evidence" audit25-review-e2e node /e2e/capture_issue25_contract.mjs
```

Expected: valid event IDs admitted only on audit detail; malformed IDs rejected;
complete release validates additively; prior manifests remain unchanged.
Rollback: remove the unpublished2.6 unit; once accepted immutable, correct via a
new release rather than rewriting2.6. Pagination470 remains out of scope.
Human evidence acceptance and integration gates remain distinct from validator
results. Sanitized: yes; no credentials, headers or producer content in logs.
