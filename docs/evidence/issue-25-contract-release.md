# Issue 25 audit event-ID contract 2.7.0

The historical audit-detail OpenAPI parameter used letter-leading generic `Id`,
although runtime accepts canonical UUIDs and permitted `cor_` IDs. This additive
release introduces `AuditEventId` only for audit detail. Its UUID alternative has
an explicit structural pattern: correctness does not depend on a validator
asserting `format: uuid`. The two `oneOf` alternatives are disjoint even when
format validation is disabled. Generic `Id` remains byte-identical to 2.6.0;
it retains its existing lowercase-leading behavior, including valid `cor_` IDs.

This snapshot derives from the actual published 2.6.0 release, preserving its
`POST /v1/grants` 404 response. Every prior release through 2.6.0 remains unchanged.
Draft PR492 reused an occupied immutable namespace and is superseded, not released.
Runtime configuration is not automatically upgraded. Clients deliberately adopt2.7.

The release format requires a complete self-contained snapshot, not inheritance.
The maintainer explicitly approved 2.7.0 and transfer of the release-only size
exception on2026-10-06: `size:exception-contract-update`. This does not waive size
policy for the audit runtime, UI, evidence or navigation units.

## Failure-first proof

Before source correction, the old proposed format-only parameter validated with
Ajv `validateFormats:false` rejected a valid `cor_` ID because both `oneOf`
alternatives matched. The new tests were authored before2.7 source. An absent
release failed; copying published2.6 then failed the dedicated parameter checks.
One already-authored assertion incorrectly expected generic `Id` to reject
`cor_`; its expectation was corrected to preserve the actual unchanged behavior.
This was not a source bug or added after-the-fact coverage.

The observed focused validator output and screenshot record 2 passing tests
(formats on/off and unchanged shared Id/grants404). The third full-release test
is retained and pending in the full suite at initial publication. Generation
produced 3 projection fixtures and manifest/evidence for204artifacts/17checks.
Full-suite checks are reported separately in the PR; do not infer completion
from generation or focused behavior checks.

## Containerized reproduction

Host prerequisites: Git checkout, Docker and a complete ignored `.env.worktree`
based on `.env.example` with synthetic local values for Compose interpolation.
Never source, print or upload that file. Harness uses pinned Node22.14 and the
committed tooling lockfile, copying read-only sources into a temporary filesystem.
Optional Redocly telemetry is disabled, without changing validation semantics.

```sh
docker compose --env-file .env.worktree -p audit25-contract --profile checks build harness
docker run --rm --network none -e REDOCLY_TELEMETRY=off --tmpfs /workspace:rw,nosuid,size=512m,uid=1000,gid=1000,mode=0755 -v "$PWD/schemas:/source/schemas:ro" -v "$PWD/scripts:/source/scripts:ro" audit25-contract-harness node --test --test-name-pattern="audit event IDs|broadens only" schemas/tooling/test/audit-event-id-release.test.mjs > docs/evidence/issue-25-contract-validation.log
docker run --rm --network none -e REDOCLY_TELEMETRY=off --tmpfs /workspace:rw,nosuid,size=512m,uid=1000,gid=1000,mode=0755 -v "$PWD/schemas:/source/schemas:ro" -v "$PWD/scripts:/source/scripts:ro" audit25-contract-harness node schemas/tooling/release.mjs validate-all
docker run --rm --network none -e REDOCLY_TELEMETRY=off --tmpfs /workspace:rw,nosuid,size=512m,uid=1000,gid=1000,mode=0755 -v "$PWD/schemas:/source/schemas:ro" -v "$PWD/scripts:/source/scripts:ro" audit25-contract-harness node schemas/tooling/release.mjs conformance --check coverage
docker compose --env-file .env.worktree -p audit25-review --profile e2e build e2e
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD/scripts/capture_issue25_contract.mjs:/e2e/capture_issue25_contract.mjs:ro" -v "$PWD/docs/evidence:/evidence" audit25-review-e2e node /e2e/capture_issue25_contract.mjs
```

Expected: canonical UUIDs and permitted correlation IDs pass with formats on/off;
malformed IDs fail; shared generic Id and existing grant404 remain unchanged.
The screenshot renders actual sanitized harness output, not a service simulation.
Pagination #470 and whole-issue acceptance remain outside this contract unit.
Rollback before acceptance: revert this proposal. After immutable publication,
publish another release; never overwrite2.7 or any prior version.
