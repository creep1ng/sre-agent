# Design: Resource Catalog Contract and Lifecycle Ownership

## Technical Approach

Publish additive immutable `2.2.0` from the exact, verified `2.1.0` release produced by #130, itself derived from `2.0.0`. Before any `2.2.0` snapshot is materialized, validate the #130 candidate manifest, compatibility evidence, snapshots, and shared-tooling tests. Then rebase #129 on that verified head and integrate shared tooling serially. The executable contract baseline is the `origin/main` `2.0.0` tree; legacy `1.x` artifacts are historical and never a release base. This change adds only a closed catalog contract, owner matrix, bounded reads, fixtures, and conformance; no runtime, database, UI, or authorization changes.

## Architecture Decisions

| Decision | Choice | Alternatives rejected | Rationale |
|---|---|---|---|
| Release lineage | `2.2.0` follows verified `2.1.0`; prior snapshots stay immutable | New `1.5.0`; rewriting `2.0.0` or `2.1.0` | Preserves the approved 2.x chain and reproducible compatibility evidence. |
| Catalog authority | Closed read projection assembled from owner authorities; no shared catalog store | Enrich `Resource`; generic CRUD/CMDB | Prevents policy coupling, duplicate lifecycle state, and secret/config leakage. |
| Integration order | Validate #130 first, then rebase and integrate #129 shared tooling once | Parallel edits to release validators | Avoids conflicting version maps and proves the baseline before snapshot creation. |
| Compatibility boundary | Keep #130 consumption and #202 governed-auth semantics unchanged; keep exact `Resource` tuple, direct `Grant`, and alias-owned routing | New authorization or routing rules | #129 is contract-only and must not become a second policy or routing authority. |

Normative owner matrix:

| Type | Owner/identity | States | Owner operations/actions |
|---|---|---|---|
| LLM alias | ModelAlias alias ID | `active|inactive` | Assignment/status/read/invoke via existing owner actions |
| MCP server/tool | MCP owner-issued server/tool IDs | `registered|active|inactive|revoked` | Register/update/deactivate/revoke/discover/invoke |
| Skill | Immutable `skill_id@version` | `draft|published|active|inactive|revoked` | Publish/version/deactivate/revoke/discover/read/invoke |
| BoK collection | Immutable `collection_id@version` | `draft|indexing|active|inactive|revoked` | Publish/index/deactivate/revoke/discover/search/read |

## Data Flow

```text
origin/main 2.0 -> verified #130 2.1 gate -> serialized tooling -> 2.2 catalog snapshot
owner authorities -> closed projection -> authenticate -> exact action/grant -> bounded list/read
                                                      \-> 401/403/404/422
```

Discovery uses `limit` 1–100 (default 100), deterministic ordering, and validated type/owner/status/visibility filters; cursor, page, offset, and continuation are forbidden. Authentication precedes lookup. Invalid credentials return 401; denied lists return 403 `resource_unavailable`; hidden, absent, inactive, or filtered direct targets return indistinguishable 404 `resource_not_found`; malformed filters return 422. Execution denial remains 403 with zero upstream calls. Any future owner mutation reuses the existing 16–128 printable-ASCII `Idempotency-Key` contract and returns 409 without mutation on payload/version conflict.

## File Changes

| File | Action | Description |
|---|---|---|
| `schemas/releases/2.2.0/**` | Create | Verified `2.1.0` sibling plus closed projection, read schemas, owner matrix, fixtures, conformance, evidence, and manifest. |
| `schemas/tooling/release.mjs`, `lib/{release-validation,governance-validation}.mjs`, focused tests | Modify | Admit `2.2.0`, pin its `2.1.0` baseline, and validate matrix, hashes, and compatibility only after #130 lands. |
| `schemas/releases/2.0.0/**`, `2.1.0/**`, `1.x/**`; `src/**` runtime | Preserve | No historical snapshot, provider/audit implementation, persistence, seed, UI, or authorization code changes. |

## Interfaces / Contracts

`ResourceCatalogEntry` is closed and allow-listed: resource type/id, owner/source identity, lifecycle status, opaque source reference, and safe discoverability metadata only. It excludes credentials, secrets, `concrete_model`, `router`, `inference_provider`, prompts, raw I/O, and arbitrary configuration. `Resource` remains exactly `(resource_type, resource_id)`; `Grant` and `ModelAlias` remain authoritative for authorization and routing. The list envelope is `items`, `limit`, `truncated`, with no continuation token.

## Testing Strategy

| Layer | What to test | Approach |
|---|---|---|
| Baseline gate | #130 `2.1.0` integrity | Validate its manifest, compatibility, snapshot, and tooling before creating any `2.2.0` bytes; stop on failure. |
| Contract | Closed fields, owner states, bounds, errors, non-enumeration | AJV/Redocly plus positive/negative fixtures and deterministic projection checks. |
| Release | Additive compatibility and immutability | Validate `2.2.0`; compare `2.0.0`/`2.1.0` bytes and hashes; run tooling/conformance tests. |

## Threat Matrix

| Boundary | Applicability | Safe/failure behavior and RED tests |
|---|---|---|
| Documentation-like paths | N/A — no executable-file classification | None |
| Git repository selection | N/A — no Git invocation | None |
| Commit state | N/A — no VCS state handling | None |
| Push state | N/A — no push automation | None |
| PR commands | N/A — no PR automation | None |

Existing fixed Redocly subprocess invocation is reused; no new command composition or process boundary is introduced.

## Migration / Rollout

No runtime or data migration. Materialize `2.2.0` only after the #130 gate; rollback removes only new `2.2.0` artifacts and post-`2.1.0` tooling changes. Prior releases remain byte-identical.

## Open Questions

None.

