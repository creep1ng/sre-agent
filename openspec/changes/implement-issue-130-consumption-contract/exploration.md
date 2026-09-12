## Exploration: Issue #130 — versioned LLM token and cost consumption contract

### Current State

Issue #130 is a technical contract change for publishing request-level input, output, and total token usage together with estimated or billed cost. It explicitly makes #143 the downstream consumer and excludes #25 (audit UI) and #142 (budgets). The issue also requires provider evidence, adaptation, persistence/projection, schemas, examples, fixtures, conformance, and deterministic checks without prompts, outputs, provider bodies, or credentials.

The runtime currently exposes only response identity, model, provider, and text from `ProviderResult`; the OpenRouter adapter validates routing and completed output but does not model provider usage or pricing evidence. `ResponsesResponse` and `ResponseMetadata` are closed shapes with no consumption field. `AuditEvent` is metadata-only and currently persists routing/correlation metadata through a JSONB-backed `audit_events` table; it has no consumption projection. No usage, currency, pricing, or billing domain exists in the source tree.

The authoritative contract is the immutable `schemas/releases` tree. Release `2.0.0` is the current runtime version, with a full snapshot, OpenAPI/JSON Schemas, examples, fixtures, and consumer conformance. Release tooling has hardcoded consumer and version maps, so adding a consumption contract requires updating those validators rather than only adding application fields. Existing release precedent keeps prior snapshots byte-stable and creates a new version.

### Affected Areas

- `src/sre_agent/gateway/providers.py` — introduce a typed provider/domain representation for usage and cost evidence, including absent, partial, and invalid states without silently converting them to zero.
- `src/sre_agent/gateway/openrouter.py` — validate and adapt provider-native usage/cost evidence; preserve deterministic failure semantics and avoid retaining raw provider bodies.
- `src/sre_agent/gateway/responses.py` — project the contract into the public response metadata while preserving authorization-before-routing and existing error behavior.
- `src/sre_agent/governance/dto.py` and `src/sre_agent/gateway/audit.py` — define and project a metadata-only consumption object with protected correlation references.
- `src/sre_agent/persistence/models.py`, `src/sre_agent/persistence/repositories.py`, `src/sre_agent/persistence/projections.py`, and a new migration — persist and reconstruct the optional consumption projection without changing append-only guarantees.
- `schemas/releases/2.1.0/` — add a complete immutable release snapshot containing HTTP/domain schemas, OpenAPI, examples, positive/negative fixtures, and consumer conformance.
- `schemas/tooling/lib/release-validation.mjs` and `schemas/tooling/release.mjs` — register the new release, compatibility baseline, consumers, and validation policy.
- `src/sre_agent/release.py`, `src/sre_agent/application.py`, and focused tests — advertise the selected contract version and verify public, provider, persistence, schema, and deterministic negative paths.

### Approaches

1. **Additive 2.1.0 structured consumption contract (recommended)**
   - Pros: preserves the immutable `2.0.0` snapshot, gives #143 one versioned semantic object, supports absent/partial/invalid values explicitly, and keeps provider adaptation separate from consumer rendering. A nullable structured projection fits the existing metadata-only audit boundary and can be indexed or normalized later if aggregation requirements appear.
   - Cons: requires coordinated changes across the provider adapter, response/audit DTOs, persistence migration, release snapshot, tooling, and tests. Pricing source, precision, and estimated-versus-billed semantics must be decided before implementation.
   - Effort: High; likely above the ordinary 400-line review budget if delivered as one slice.

2. **Mutate `2.0.0` or attach an unversioned generic sidecar payload**
   - Pros: smaller immediate code diff and fewer release-tool changes.
   - Cons: violates the repository's immutable release convention, weakens schema/conformance guarantees, makes consumer compatibility ambiguous, and invites the exact failure the issue calls out (absence becoming zero or an estimate being mistaken for billing). This is not suitable for a public contract.
   - Effort: Medium initially, but creates migration and compatibility debt.

### Recommendation

Use a new additive `2.1.0` release on the existing `/v1` API path. Define one strict consumption object reused by public response metadata and the persisted audit projection. Every value must carry source/availability semantics; absence remains absent, and partial or invalid evidence must be represented explicitly rather than inferred from input/output text or latency. Cost must identify estimated versus billed, currency, precision, and a price snapshot/version. Keep request, alias, model, provider, incident, and period attribution in protected metadata references only.

The proposal/specification must resolve provider source authority, valid precision and currency rules, the total-token invariant, and timeout/error/cache/fallback semantics. It should add a full `2.1.0` snapshot while leaving `2.0.0` unchanged, register #130 as the contract producer/conformance obligation and #143 as the downstream consumer, and add sanitized positive/negative fixtures for complete, partial, absent, invalid, deny, timeout, upstream error, fallback, and cache cases. To stay within review limits, plan three cohesive slices: contract snapshot/tooling, provider/public projection, and persistence/audit projection with migration and deterministic checks.

### Risks

- The issue leaves source authority, estimated versus billed meaning, currency, precision, price snapshot, and failure/cache semantics open; implementing before deciding these would create an unstable contract.
- Provider-native usage can be absent, partial, or invalid, and a provider body must never be persisted or exposed as a substitute for normalized evidence.
- Adding a nullable audit projection requires model, migration, repository, and reconstruction consistency; schema-only changes would be incomplete.
- Release validation currently hardcodes versions and consumers, so a new snapshot can fail validation unless all registries and compatibility checks are updated together.
- The end-to-end change may exceed 400 changed lines; an explicit split is safer than an exception.

### Ready for Proposal

Yes. Repository and issue exploration is complete. Proposal work can proceed once it records the decisions above, confirms the exact `2.1.0` shape, and keeps the implementation bounded to #130 while treating #143 as the consumer rather than redefining its UI semantics.
