# Proposal: Implement Reusable Authorization Decision Engine

## Intent

Create one reusable authority for Principal–action–resource grants. `/v1/responses` splits precedence across resource checks and `GrantRepository.decide()`, making reuse unsafe. The engine must default deny while preserving exact causes only in governed audit evidence.

## Scope

### In Scope
- Authorize any existing `resource_type/resource_id`; `/v1/responses` is the first consumer.
- Own precedence: `principal_inactive` → `resource_missing` → `resource_inactive` → `grant_not_applicable`.
- Return `PolicyDecision` always: denies remain `deny/no_matching_grant/null`; allows use `allow/grant_matched/<grant_id>`.
- Evolve governed audit contracts and persistence to store the exact internal cause.
- Migrate `ResponsesService`; remove or narrow `GrantRepository.decide()`.

### Out of Scope
- Roles, scopes, explicit denies, conditional/YAML runtime policy, groups, tenancy, or external policy engines.
- Exposing internal denial causes through APIs or operational logs.
- Reconciling stale OpenSpec context, tracked separately by issue #144.

## Capabilities

### New Capabilities
- `authorization-decision-engine`: Generic inputs, default deny, precedence, authority boundaries, and decision invariants.

### Modified Capabilities
- `governed-llm-responses`: Use the engine before routing while preserving uniform 403 and zero upstream calls on deny.
- `runtime-audit-evidence`: Persist a closed audit-only authorization denial cause without changing public `PolicyDecision`.

## Approach

Add a framework- and persistence-independent authorization service under `src/sre_agent/governance/` with injected fact readers. It alone applies precedence and constructs decisions. Persistence exposes facts. Governed audit projection records the closed taxonomy separately; API and ordinary logs retain the uniform denial.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/sre_agent/governance/` | New/Modified | Decision service and audit DTO |
| `src/sre_agent/persistence/` | Modified | Fact readers and audit migration |
| `src/sre_agent/gateway/responses.py` | Modified | First engine consumer |
| `schemas/releases/` | Modified | Audit contract |
| `tests/` | Modified | Precedence, non-enumeration, audit isolation |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Exact cause leaks publicly | Medium | Closed projections and negative API/log tests |
| Two decision authorities drift | Medium | Remove/narrow repository decision construction |
| Audit migration rejects events | Medium | Additive migration with readback tests |

## Rollback Plan

Revert service integration, audit migration, and contract release together; restore the previous Responses composition and repository method. No policy data migration is required.

## Dependencies

- HT-03 (#11) persistence and HT-04 (#13) authentication are prerequisites.

## Success Criteria

- [ ] All four denial causes follow the documented precedence but are externally indistinguishable.
- [ ] Governed audit readback retains the exact cause; API responses and ordinary logs never do.
- [ ] Human and agent principals behave identically across supported resource types.
- [ ] `/v1/responses` preserves authorize-before-routing, uniform 403, and zero provider calls on deny.
- [ ] One service constructs runtime decisions; persistence returns facts only.
