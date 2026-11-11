# Proposal: Publish the LLM Consumption Contract (Issue #130)

## Intent

Publish a versioned metadata-only contract for token usage and provider cost. OpenRouter response `usage` is authoritative; billed USD remains an exact decimal with provider observation time. Missing or invalid evidence stays unavailable, never implicit zero, for downstream #143.

## Scope

### In Scope
- Add immutable release `2.1.0` on `/v1`, leaving every `2.0.0` artifact byte-identical.
- Define one closed object for public response metadata and audit projection, including availability/source, token invariants, billed cost, currency, precision, and pricing context.
- Adapt validated OpenRouter usage/cost evidence; preserve no-consumption for pre-routing deny and unavailable semantics for timeout, errors, cache, and fallback unless explicit provider evidence exists.
- Persist/reconstruct the optional projection through an additive migration; extend schemas, fixtures, conformance, tooling, and deterministic checks.

### Out of Scope
- Consumer UI/reporting for #143; this publishes the producer contract only.
- Budgets (#142), audit UI (#25), content/provider-body retention, or inferred usage/cost.
- Provider retry policy, pricing-service integration, or authorization-order changes.

## Capabilities

### New Capabilities
- `llm-consumption-contract`: Token/cost semantics, provider adaptation, projections, persistence, and immutable `2.1.0` conformance.

### Modified Capabilities
- `governed-llm-responses`: Include the projection only after authorized provider completion while preserving ordering/errors.
- `runtime-audit-evidence`: Persist consumption metadata without weakening metadata-only, HMAC, append-only, or audit gating.

## Approach

Introduce typed evidence states and a shared closed DTO. Validate OpenRouter usage/cost without retaining raw bodies; project it into response metadata and protected audit persistence. Add the complete `2.1.0` snapshot and register validators. Deliver contract/tooling, provider/public, and persistence/audit slices within the 400-line budget where possible.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/sre_agent/{gateway,governance,persistence}/` | Modified | Evidence, DTOs, projections, repositories, migration |
| `schemas/releases/2.1.0/`, `schemas/tooling/` | New/Modified | Snapshot, schemas, fixtures, validators |
| `src/sre_agent/release.py`, tests | Modified | Version and conformance |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Evidence becomes zero | High | Closed states and negative fixtures |
| Release/audit drift | Medium | Snapshot and readback validation |
| Diff exceeds budget | High | Three verifiable work units |

## Rollback Plan

Revert runtime, migration, and tooling slices in reverse; retain immutable `2.0.0` and existing audit rows. Never rewrite published snapshots.

## Dependencies

- Existing `2.0.0` contracts and OpenRouter response usage.
- #143 consumes this contract.

## Success Criteria

- [ ] `2.0.0` stays byte-identical and `2.1.0` validates as a complete release.
- [ ] Complete, partial, absent, invalid, deny, timeout, error, cache, and fallback cases have explicit deterministic semantics.
- [ ] Public response and audit persistence expose the same normalized projection without sensitive content.
- [ ] Authorization ordering, zero-call deny behavior, and audit-before-release guarantees remain green.
