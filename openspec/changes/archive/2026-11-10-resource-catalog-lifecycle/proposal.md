# Proposal: Versioned Resource Catalog Contract on the 2.x Line

## Intent

Issue #129 adds a closed cross-owner catalog projection and lifecycle matrix as additive release `2.2.0`, based on verified `2.1.0` from #130 and the current `2.0.0` baseline. Branch `1.4.0` is not the release base. Do not publish `1.5.0`.

## Scope

### In Scope

- Publish `2.2.0` only after #130's `2.1.0` is complete and validated.
- Define `ResourceCatalogEntry`, bounded reads, owner matrix, fixtures, and conformance.
- Serialize tooling after #130 under user-approved auto-chain/stacked-to-main. `size:exception-contract-update` covers only the complete contract snapshot, tooling, and evidence; no runtime/persistence waiver.

### Out of Scope

- Runtime catalog/DB/UI, generic CRUD/CMDB, migrations, or new authorization rules.
- Editing immutable 1.x, `2.0.0`, or verified `2.1.0`.
- Claiming/publishing `2.1.0`, or creating `1.5.0`.

## Capabilities

### New Capabilities

- `resource-catalog-contract`: Closed projection, owner/lifecycle matrix, bounded discovery, non-enumeration, and lifecycle boundaries.

### Modified Capabilities

- None. `Resource` remains the exact authorization tuple; `Grant` and `ModelAlias` ownership are unchanged.

## Approach

1. Gate on #130: verify its `2.1.0` manifest, snapshot, validation, and shared-tooling changes from `2.0.0`; then derive `2.2.0`. Rebase/merge #129 tooling afterward; common validators are not edited in parallel.
2. Allow-list type/id, owner/source, status, and safe discoverability metadata. Exclude credentials, secrets, provider/routing fields, prompts, raw I/O, and arbitrary configuration. `ModelAlias` solely owns `concrete_model`, `router`, and `inference_provider`.
3. Bind LLM aliases, MCP server/tools, Skills, and BoK collections to owner-issued identities, states, operations, and actions; the catalog is never a second mutable authority.
4. Reuse authenticated discovery with limit 1–100 (default 100), deterministic ordering, explicit filters, no cursor/page/offset, and non-enumerating 401/403/404/422 behavior. Preserve idempotency and captured-snapshot in-flight semantics.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `schemas/releases/2.2.0/**` | New | Verified `2.1.0` sibling plus catalog schemas, reads, fixtures, matrix, and evidence. |
| `schemas/tooling/**` | Modified | Admit `2.2.0` only after #130 tooling lands. |
| `schemas/releases/{1.x,2.0.0,2.1.0}` | Preserved | Historical and dependency releases remain immutable. |

## Risks

| Risk | Mitigation |
|---|---|
| #130 is incomplete | Stop before snapshot creation and report the dependency. |
| Shared validator conflict | Serialize integration and rebase after #130. |
| Projection leaks or duplicates authority | Closed schemas, owner matrix, negative fixtures. |

## Rollback Plan

Remove only new `2.2.0` artifacts and post-`2.1.0` tooling changes; never rewrite prior releases. If the dependency is unverified, create no release snapshot.

## Dependencies

- #130's completed, validated `2.1.0` from `2.0.0`, including shared-tooling integration.

## Success Criteria

- [ ] `2.2.0` validates as an additive catalog release from verified `2.1.0`.
- [ ] 1.x, `2.0.0`, and `2.1.0` remain byte-identical; no `1.5.0` is published.
- [ ] Owner authority, Resource/Grant tuple, ModelAlias routing exclusivity, and non-enumerating discovery have conformance evidence.

