# Tasks: Resource Catalog Contract and Lifecycle Ownership

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 2,800–3,600 authored lines, including 2.2.0 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | Planning update → one complete 2.2.0 contract PR → independent verify/handoff; no publishable intermediate |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |
| Snapshot exception | `size:exception-contract-update`; no runtime waiver |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal / likely PR | Focused test | Runtime harness | Rollback boundary |
|---|---|---|---|---|
| 1 | Planning update after the #130 gate; create no 2.2.0 bytes or source changes | `git diff --check -- openspec/changes/resource-catalog-lifecycle/tasks.md` and ID/checkbox count | N/A — planning only | Revert this `tasks.md` change |
| 2 | One complete PR from verified #130 `2.1.0`: full `2.2.0` snapshot, catalog, tooling, fixtures, conformance, manifest/evidence; retain #130 and add version-aware #129 consumer; exception only | `npm --prefix schemas/tooling test`; `npm --prefix schemas/tooling run validate:releases`; `npm --prefix schemas/tooling run lint:openapi`; release-targeted #130/#129 conformance; historical byte/hash check | N/A — contract-only; runtime remains 2.1 while 2.2 is available | Remove `schemas/releases/2.2.0/**` and post-2.1 tooling/tests |
| 3 | Handoff: verify complete contract/evidence independently; no runtime activation | `sdd-verify` and `gentle-ai sdd-verify-validate` | N/A — no owner runtime | Remove handoff/evidence docs only |

Gate 2.2.0 creation on independent #130 PASS. Runtime stays active at 2.1 while 2.2 is available. Retain the #130 consumer and add a version-aware #129 consumer with paths/commands; generate evidence/manifest after source/tooling validation.

## Phase 1: Release Contract Foundation

- [x] 1.1 Gate on verified #130 `2.1.0` (read-only), copy its sibling to `schemas/releases/2.2.0/**`, and preserve `schemas/releases/2.0.0/**` (read-only) plus all 1.x bytes.
- [x] 1.2 Add closed `ResourceCatalogEntry` and bounded-list schemas under `schemas/releases/2.2.0/json-schema/**`; exclude secrets, prompts, raw I/O, routing/provider fields, and arbitrary config.
- [x] 1.3 Add authenticated catalog reads/examples under `schemas/releases/2.2.0/openapi/**` and `schemas/releases/2.2.0/examples/**`, with deterministic ordering, 1–100 limits, filters, no continuation, and 401/403/404/422 behavior.

## Phase 2: Ownership, Lifecycle, and Fixtures

- [x] 2.1 Encode LLM/MCP/Skill/BoK owner/state/action matrix/evidence under `schemas/releases/2.2.0/conformance/**`; retain Resource/Grant/ModelAlias authority and #202 authorization.
- [x] 2.2 Add positive fixtures for discovery, states, replay, in-flight snapshots, and reconciliation under `schemas/releases/2.2.0/fixtures/positive/**`.
- [x] 2.3 Add negative fixtures for closed fields, bounds, non-enumeration, errors, conflicts, stale versions, and drift under `schemas/releases/2.2.0/fixtures/negative/**`; threat rows are N/A, so no RED task.
- [x] 2.4 Register obligations and prohibited authorities in `schemas/releases/2.2.0/conformance/{suite.yaml,consumers.yaml}`.

## Phase 3: Tooling and Regression Coverage

- [x] 3.1 Serially extend `schemas/tooling/release.mjs`, `schemas/tooling/lib/{release-validation,governance-validation}.mjs`, and 2.2.0 tests from 2.1.0; do not alter history.
- [x] 3.2 Add tests for closed projection, owner states, errors, fixture coverage, #130 consumption, #202 authorization, and historical hashes.

## Phase 4: Evidence and Verification

- [x] 4.1 Generate deterministic `schemas/releases/2.2.0/conformance/{compatibility.json,evidence.json}` and `schemas/releases/2.2.0/manifest.yaml` only after source validation; never regenerate immutable releases.
- [x] 4.2 Run catalog, tooling, release, and byte/hash validation; record runtime N/A: #129 changes no runtime, persistence, seed, UI, or authorization.
