## Exploration: Issue #129 — Resource Catalog Contract and Lifecycle

### Current State

Issue #129 is a contract-and-ownership clarification, not a request to build productive catalogs, a generic CMDB, or a control-plane UI. The repository has a closed authorization Resource tuple and owner-specific LLM alias routing, but no versioned common catalog projection or lifecycle matrix for LLM, MCP, Skill, and BoK owners.

The active 2.x lineage is resolved:

- Issue #202 establishes the governed runtime flow on 2.0.0.
- Issue #130 publishes additive 2.1.0 from 2.0.0, including the normalized LLM consumption contract.
- Issue #129 publishes additive 2.2.0 from the exact verified 2.1.0 snapshot.
- The historical 1.4.0 release remains immutable evidence only. The earlier 1.5.0 recommendation is superseded and MUST NOT be implemented or published.

Planning may proceed in parallel, but #129 snapshot creation and shared-tooling integration wait for the #130 2.1.0 gate. The #130 design requires the runtime baseline to contain #202's ordering: validation -> authorize_governed_access -> alias resolution -> routing -> provider -> consumption normalization -> audit append -> response release. #129 does not modify that runtime flow.

Historical contract boundaries remain valid: Resource is a closed (resource_type, resource_id) reference; Grant is a direct Principal–Action–Resource allow; and ModelAlias owns alias, concrete_model, router, inference_provider, and status. The catalog MUST NOT become a second policy, routing, or mutable lifecycle authority.

Existing implementation evidence supports a safe projection: ResourceRow contains authorization identity/status plus nullable LLM assignment data, while ResourceRepository.authorization_view() exposes only authorization-safe facts and resolve_assignment() is used only after authorization. Strict DTOs and projection tests reject extra fields and prevent raw keys, hashes, provider values, and other sensitive persistence data from leaking.

Accepted #9 contracts provide reusable bounds and semantics: authenticated bounded lists with limit default/max 100, deterministic ordering, no cursor/page/offset protocol, explicit filters, direct grants with default deny, authentication before authorization, and idempotent mutation rules. Demo seeding detects incompatible persisted state and raises SeedConflict rather than silently repairing it; a future catalog contract must preserve that explicit-reconciliation boundary.

The old openspec/config.yaml still describes a pre-backend repository. Live 2.x source, release manifests, and conformance evidence are authoritative for this exploration.

### Affected Areas

- schemas/releases/2.2.0/** — create a complete immutable sibling of verified 2.1.0 with the closed catalog projection, read surface, owner matrix, examples, positive/negative fixtures, conformance, compatibility evidence, and manifest.
- schemas/tooling/release.mjs and schemas/tooling/lib/{release-validation,governance-validation}.mjs — admit 2.2.0, pin its additive baseline to 2.1.0, and validate owner authority, compatibility, hashes, and immutable coverage.
- schemas/tooling/test/** — cover closed fields, owner states, bounded filters, non-enumeration, 2.1.0 compatibility, and historical immutability.
- schemas/releases/1.x/**, schemas/releases/2.0.0/**, and verified schemas/releases/2.1.0/** — preserve byte identity; do not create 1.5.0 or mutate prior snapshots.
- src/sre_agent/gateway/responses.py, gateway/audit.py, provider adapters, persistence, and authorization modules — preserve #202/#130 runtime behavior; #129 adds no runtime, database, migration, seed, UI, or authorization changes.
- src/sre_agent/governance/dto.py, persistence/projections.py, and existing projection tests — provide strict closed-field and safe-projection patterns, not new catalog authority.
- Existing release/conformance fixtures and the stale openspec/config.yaml — use current 2.x evidence and do not infer implementation capability from the old context text.
- Consumers #20, #28, #31, #33, #184, and #187 — remain owners of type-specific identifiers, states, operations, and data.

### Approaches

1. **Derive additive 2.2.0 from verified 2.1.0** — gate on #130, rebase #129 onto that verified head, then add only catalog contract and conformance artifacts.
   - Pros: follows the confirmed current lineage; keeps 2.0.0 and 2.1.0 immutable; isolates catalog semantics from consumption and runtime authorization.
   - Cons: requires a verified #130 handoff and serialized edits to shared release tooling.
   - Effort: Medium.

2. **Create the historical 1.5.0 sibling from 1.4.0** — superseded historical context; do not execute.
   - Pros: matches the original pre-2.0 wording.
   - Cons: forks the catalog away from the active 2.x line and requires a second port or duplicate authority.
   - Effort: High; superseded.

3. **Implement a runtime catalog or generic CMDB now** — reject.
   - Pros: would provide immediate runtime reads and mutations.
   - Cons: out of scope, creates a mutable authority, couples policy to catalog metadata, and expands review risk without owner runtimes.
   - Effort: Very high; reject.

### Recommendation

Use approach 1. Treat #130 as a hard baseline gate: validate its 2.1.0 manifest, compatibility evidence, complete snapshot, conformance, and shared-tooling tests. If that gate fails, create no 2.2.0 snapshot bytes. Rebase the #129 worktree onto the verified #130 head and serialize shared release-tooling edits; do not edit 1.x, 2.0.0, or 2.1.0.

Keep ResourceCatalogEntry closed and allow-listed: resource type/id, owner/source identity, lifecycle state, opaque safe source reference, and bounded discoverability metadata only. Exclude credentials, secrets, provider/routing fields, prompts, raw I/O, and arbitrary configuration. Resource remains the exact authorization tuple, Grant remains the direct authorization relation, and ModelAlias remains the sole routing authority.

The owner matrix is normative for LLM aliases, MCP servers/tools, Skills, and BoK collections. Each owner retains its identifiers, lifecycle states, mutations, and required actions; the catalog is a read projection rather than a mutable lifecycle store. Reuse authenticated discovery with limit 1–100 (default 100), deterministic ordering, explicit validated filters, no cursor/page/offset/continuation, and non-enumerating 401/403/404/422 behavior. Future owner mutations reuse the existing idempotency contract. Startup seed remains conflict-detecting; only an explicit bounded reconciliation/reset may repair demo fixtures.

Safe coordination order is #202 runtime -> verified #130 runtime and 2.1.0 -> #129 2.2.0 contract/tooling. Planning may proceed in parallel, but the shared release validator has one serialized owner. Delivery follows the user-approved auto-chain with stacked-to-main targets. `size:exception-contract-update` applies only to the complete contract snapshot, shared tooling, and conformance evidence; it does not waive review limits for runtime or persistence changes. Generated snapshot/evidence files remain part of immutable release identity even when excluded from authored-risk counting.

### Risks

- #130 2.1.0 artifacts or tooling may not yet be verified; the dependency gate must fail closed.
- Parallel edits to release version maps, compatibility baselines, and manifest validation can silently produce the wrong lineage; rebase and serialize them.
- Copying catalog routing/provider data would duplicate ModelAlias authority or expose topology.
- A universal lifecycle state would erase MCP registration, Skill publication/versioning, and BoK indexing semantics; keep owner-specific states.
- Filters, counts, or distinct errors can enumerate hidden resources; retain indistinguishable direct-read behavior.
- Historical 1.x snapshots and hard-coded release tooling make 2.2.0 a coordinated change; do not patch historical artifacts or revive 1.5.0.
- The full 2.2.0 snapshot and fixtures can exceed the review budget if authored source and generated evidence are bundled into one slice; keep the contract-only `size:exception-contract-update` boundary explicit and split any runtime or persistence work into normally reviewed slices.
- The stale OpenSpec config can mislead downstream phases about backend/test capabilities; use current 2.x source and conformance evidence.

### Ready for Proposal

Yes. The active proposal and design already encode the resolved 2.2.0 lineage and verified-2.1.0 gate. Proceed to specification/task refinement only after that gate is available; do not revive the superseded 1.5.0 plan.

