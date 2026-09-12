# Design: Publish the LLM Consumption Contract (2.1.0)

## Technical Approach

Publish an additive, immutable 2.1.0 snapshot on /v1 while leaving every 2.0.0 byte unchanged. Normalize OpenRouter response evidence once into the closed consumption object specified by the sibling specs, then pass that object to both the public response metadata and the metadata-only audit event.

The apply baseline MUST first contain issue #202's governed flow from /home/creep/.codex/worktrees/ed92/sre-agent: validation -> `authorize_governed_access` -> alias resolution -> routing -> provider -> normalization -> audit append -> release. Do not reintroduce the old ResponsesService-local authentication/authorization path; #130 extends the shared boundary and preserves zero-call denial and audit-before-release.

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|---|---|---|---|
| Evidence authority | OpenRouter `usage` is the only source for token and billed USD values; discard the provider body after adaptation. | Text, latency, SDK types, or inferred estimates | Prevents false zeroes and sensitive-body retention. |
| Normalized shape | Add one strict, closed `Consumption` DTO with availability/source, nullable token dimensions, exact-decimal `billed_usd`, currency, precision, and `pricing_context`; reuse it in response metadata and AuditEvent. | Separate public/audit shapes or an untyped JSON sidecar | Keeps #143's projection identical and rejects drift. |
| Billing context | Preserve provider observation time and use that billed-response instant as the temporal price snapshot/version. | Floating-point amounts or a fabricated external pricing-registry ID | The runtime has no pricing registry; exact provider evidence remains authoritative. |
| Outcome handling | Complete/partial/absent/unavailable are explicit. Invalid, timeout, upstream error, cache, and fallback without evidence become unavailable; deny has no consumption projection. | Null-as-zero or a synthetic receipt-time estimate | Makes failure and pre-routing semantics deterministic. |
| Release coordination | Start apply from #202's shared auth helper and route metadata, then add #130 fields without duplicate orchestration. | Applying against the old ResponsesService | The old branch would conflict and can regress validation -> authn -> authz ordering. |

## Data Flow

```
request
  -> validate
  -> shared governed authn/authz (#202)
  -> resolve alias/router
  -> OpenRouter (direct, no fallback)
  -> normalize usage/cost; drop raw body
  -> public consumption + audit consumption (same DTO)
  -> append audit (release gate)
  -> release response
```

Malformed routing evidence remains non-retryable 502. Malformed consumption evidence does not become zero; retain only valid dimensions as partial or mark unavailable per the spec.

## File Changes

| File | Action | Description |
|---|---|---|
| `src/sre_agent/governance/dto.py` | Modify | Add closed consumption DTO and AuditEvent projection field. |
| `src/sre_agent/gateway/providers.py` | Modify | Carry normalized consumption and optional explicit failure evidence. |
| `src/sre_agent/gateway/openrouter.py` | Modify | Validate usage, exact decimal billing, observation time, and pricing context; never retain raw body. |
| `src/sre_agent/gateway/responses.py`, `gateway/audit.py` | Modify | Project the same object; preserve #202 helper, ordering, and audit gate. |
| `src/sre_agent/persistence/{models,repositories,projections}.py` + new migration | Modify/Create | Add nullable JSONB consumption, round-trip nulls/decimal text, and preserve append-only controls. |
| `schemas/releases/2.1.0/`, `schemas/tooling/{lib/release-validation.mjs,release.mjs}` | Create/Modify | Full immutable snapshot, fixtures, conformance, and 2.0.0 compatibility baseline. |
| `src/sre_agent/release.py` and focused tests | Modify | Advertise 2.1.0 and cover provider, flow, persistence, and release invariants. |

## Interfaces / Contracts

`ProviderResult` returns normalized `Consumption` for completed calls; provider failures may carry only validated explicit evidence. `ResponsesResponse.metadata.consumption` is required for successful completion, including `absent`; audit consumption is present for authorized provider outcomes and `unavailable` for evidence-less timeout/error/cache/fallback. Denial remains consumption-free.

## Testing Strategy

- Provider RED tests: complete, partial, absent, invalid, exact decimal text, invariant violation, provider observation time, and raw-body exclusion.
- Flow RED tests: #202 validation/authn/authz ordering, zero-call deny, no fallback, same public/audit projection, unavailable failure states, and audit failure suppressing release.
- Persistence RED tests: migration constraints and JSONB readback preserving nulls, availability, decimal text, and pricing context.
- Release RED tests: 2.0.0 byte identity, complete 2.1.0 snapshot, and explicit fixtures for complete/partial/absent/unavailable/invalid/deny/timeout/error/cache/fallback.

## Threat Matrix

| Boundary | Applicability | Design response / RED tests |
|---|---|---|
| Documentation-like paths | N/A — no executable classification | None |
| Git repository selection | N/A — no Git invocation | None |
| Commit state | N/A — no index handling | None |
| Push state | N/A — no push automation | None |
| PR commands | N/A — no PR automation | None |

## Migration / Rollout

Run the additive migration before the runtime; legacy audit rows remain NULL and immutable. Publish 2.1.0 after schema/tooling conformance. Roll back runtime first if needed; never rewrite 2.0.0 or existing audit rows.

## Open Questions

None; provider observation time is the temporal pricing version, not an external registry identifier.