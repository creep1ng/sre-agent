# Apply Progress: Resource Catalog Contract and Lifecycle Ownership

**Change**: `resource-catalog-lifecycle`
**Mode**: Standard (strict TDD is disabled in `openspec/config.yaml`)
**Delivery**: `auto-chain`, `stacked-to-main`
**Current work unit**: One complete 2.2.0 contract snapshot, catalog tooling, fixtures, conformance, manifest/evidence, and review evidence.
**Snapshot exception**: `size:exception-contract-update` applies only to this complete contract snapshot/tooling/evidence unit; it grants no runtime, persistence, migration, seed, UI, authorization, or provider waiver.
**Contract lineage**: 2.2.0 is additive over verified 2.1.0 (`01683e34eb18b8ef3eb5cebec7dfe0b1ee210d27`); active runtime remains 2.1.0.
**Frozen source commit**: `1e576f216fc5a126b20c490bc411e0095e03b026` (`188` files, `5,898` changed lines including the approved exception unit).

## Completed Tasks

- [x] 1.1 Gate on verified #130 `2.1.0`, copy its sibling to `schemas/releases/2.2.0/**`, and preserve `2.0.0` plus all 1.x bytes.
- [x] 1.2 Add the closed `ResourceCatalogEntry` and bounded-list schemas under `schemas/releases/2.2.0/json-schema/**`.
- [x] 1.3 Add authenticated catalog reads/examples with deterministic ordering, bounded limits, filters, no continuation, and 401/403/404/422 behavior.
- [x] 2.1 Encode the LLM/MCP/Skill/BoK owner/state/action matrix and evidence while retaining Resource/Grant/ModelAlias authority and #202 authorization.
- [x] 2.2 Add positive discovery, lifecycle, replay, in-flight snapshot, and reconciliation fixtures.
- [x] 2.3 Add negative closed-field, bound, non-enumeration, error, conflict, stale-version, and drift fixtures.
- [x] 2.4 Register obligations and prohibited authorities in `conformance/{suite.yaml,consumers.yaml}`.
- [x] 3.1 Extend release/tooling validators and tests version-aware for 2.2.0 without changing historical releases.
- [x] 3.2 Add closed-projection, owner-state, error, fixture, #130 consumption, #202 authorization, and historical-hash regression coverage.
- [x] 4.1 Generate deterministic 2.2.0 compatibility/evidence and immutable manifest after source validation.
- [x] 4.2 Run catalog, tooling, release, OpenAPI, conformance, and historical byte/hash validation; record runtime as N/A.

## Work Unit Evidence

| Evidence | Exact result |
|---|---|
| Reproduction command (equivalent); recovered output from original `issue129-contract` harness | The displayed `issue129-contract-checks` Docker command is an equivalent reproduction, not the exact command that produced `/tmp/issue129-contract-harness.log`; the recovered original harness recorded Node tests **82/82**, all eight releases, explicit 2.2.0 **186 artifacts / 10 checks**, and issue-129/issue-130 conformance PASS. |
| OpenAPI and coverage checks from the same frozen harness | PASS: both 2.2.0 control-plane/responses bundles linted; the coverage command reported its **default registry count of 6 consumers**, not the 2.2.0 release consumer count. |
| Semantic catalog focused checks | PASS: `node --check` for schema/release validators; Docker schema-validation suite **35/35**; issue-129 resource-catalog conformance PASS; release test result was **18/19** before immutable manifest generation, then the frozen manifest validation passed. |
| MCP relation focused checks | PASS: all catalog JSON fixtures **27 fixtures / 2 examples**, issue-129 release consumer PASS; explicit `relation: server_id` and nested MCP tool `source_ref` are present. |
| Historical byte check performed at handoff | `git diff --quiet 01683e34 HEAD -- schemas/releases/1.0.0 schemas/releases/1.1.0 schemas/releases/1.2.0 schemas/releases/1.3.0 schemas/releases/1.4.0 schemas/releases/2.0.0 schemas/releases/2.1.0` → **PASS**. Release tree object IDs for all seven historical trees also matched exactly. |
| Evidence artifact | `/tmp/issue129-contract.png` was visually inspected at high detail; repository copy is `docs/evidence/issue-129-catalog-contract.png`, SHA-256 `57983d747708652af8e4d676fd867de4bad62a6dd218a3108627dbef64572120`. |
| Runtime harness | **N/A by design** — issue #129 is contract-only; no catalog runtime, persistence, migration, seed, UI, authorization, provider, or live service behavior changed. |
| Rollback boundary | Revert only the frozen 2.2.0 contract/evidence/tooling commit and this apply bookkeeping; delete `schemas/releases/2.2.0/**` and post-2.1.0 tooling/docs changes if rollback is required. Never rewrite 1.x, 2.0.0, or 2.1.0. |

## Immutable Evidence Hashes

- `schemas/releases/2.2.0/manifest.yaml`: `14d6563c81cf77c9cc01a1444b1a738848ce82c3e2ac77a28a06a0f9d86a45c8`
- `schemas/releases/2.2.0/conformance/compatibility.json`: `a2d49e89b080ec50c680c853a0c403d934490324b08a1386e96a84936cc7def5`
- `schemas/releases/2.2.0/conformance/evidence.json`: `fbb39badbc6bacd40e62570b840419f0c91803445ce8e7362e759d614f9ddceb`
- `schemas/releases/2.2.0/conformance/resource-catalog-evidence.json`: `b519995953d8a9bc4663a0a273d5bad79fa78258083094299ca6e68d468168ac`

## Interrupted Duplicate Runs

The agent interruption did not stop the original long-running `issue129-contract-harness-run-4a040754938b`; its output was recovered from `/tmp/issue129-contract-harness.log`, and no environment-teardown causality is asserted. A final scoped `docker ps -a` check found no matching `issue129`, `catalog`, or `contract-harness` container; the root-owned `issue129-final` duplicate was intentionally SIGTERM-canceled after evidence recovery, not because of a source failure.

## Remaining Tasks

None. All 11 implementation tasks are checked in `tasks.md`; the next phase is independent `sdd-verify`. Do not archive or activate runtime from this apply handoff.

## Status

**11/11 tasks complete. Ready for independent SDD verification.**
