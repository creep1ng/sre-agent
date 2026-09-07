# Design: Reusable Authorization Decision Engine

## Technical Approach

Add one async `AuthorizationDecisionEngine` in governance. It receives typed fact-reader ports, evaluates Principal, generic resource, then exact active grant, and returns one internal result containing the unchanged public `PolicyDecision` plus an audit-only denial cause. `ResponsesService` is the first adapter and preserves authorization before model-assignment resolution.

## Architecture Decisions

| Decision | Choice and rationale | Rejected alternative |
|---|---|---|
| Authority | `src/sre_agent/governance/authorization.py` owns precedence and constructs every runtime `PolicyDecision`; `GrantRepository` retains only `find_active()`. This prevents policy drift and keeps SQLAlchemy outside governance. | Repository-level `decide()` or caller composition creates competing authorities. |
| Generic facts | Define `ResourceAuthorizationFact(resource_type, resource_id, status)` plus `ResourceFactReader` and `GrantFactReader` protocols. `ResourceRepository.authorization_view()` already queries only generic `resources` columns for all current `ResourceType` values. No MCP/skill/BoK runtime consumer or store is invented; those consumers can use the same port when implemented. | `Resource` lacks status; `ModelAlias` leaks routing and is LLM-specific. |
| Internal result | A frozen `AuthorizationEvaluation(decision, denial_cause)` enforces allow→no cause and deny→exactly one of the four causes. Only the audit projector accepts the full evaluation; response behavior and ordinary logs receive `decision` only. | Widening `PolicyDecision.reason_code` leaks enumeration detail. |
| Compatible audit evolution | Publish immutable additive contract release `schemas/releases/1.3.0/`. Add nullable `authorization_denial_cause` to governed `AuditEvent`; legacy events remain readable, while new runtime/conformance tests require it on authorization denies. Responses OpenAPI/error envelopes and `PolicyDecision` remain unchanged. | Backfilling historical causes is impossible without inventing evidence. |

## Data and Transaction Flow

```text
authenticated Principal
  -> inactive? deny(principal_inactive), no fact reads
  -> ResourceFactReader.get(type,id)
       -> absent/inactive? deny(resource_missing/resource_inactive), no grant read
  -> GrantFactReader.find_active(exact tuple)
       -> absent? deny(grant_not_applicable)
       -> present? allow(grant_matched, grant_id)
  -> deny: AuditProjector(evaluation) -> one AuditRepository.append transaction -> uniform 403
  -> allow: resolve_assignment -> provider
```

The denied request creates one event ID and performs one append. `PostgresAuditStore` commits it before the 403; append failure retains the existing fail-closed 503 and never retries or duplicates the terminal attempt. The cause column is written only for an authorization-stage deny; routing fields remain null.

## Interfaces and Persistence

`evaluate(principal: Principal, action: str, resource_type: ResourceType, resource_id: str) -> AuthorizationEvaluation` short-circuits in the specified order. Migration `migrations/versions/20260901_03_add_authorization_denial_cause.py` adds nullable `varchar(32)` and `ck_audit_events_authorization_denial_cause`: values are closed, and non-null implies authorization/denied/`no_matching_grant`. Update `AuditEventRow`, `AuditEvent`, `AuditProjector`, `AuditRepository` serialization, and `project_audit_event` readback.

## File Changes

| Paths | Action |
|---|---|
| `src/sre_agent/governance/authorization.py` | Create engine, ports, facts, result, taxonomy. |
| `src/sre_agent/persistence/repositories.py` | Return generic resource facts; remove `decide()`. |
| `src/sre_agent/gateway/responses.py`, `gateway/audit.py` | Integrate evaluation; keep routing inaccessible before allow; project cause only to audit. |
| `src/sre_agent/governance/dto.py`, `persistence/models.py`, `persistence/projections.py`, migration above | Evolve audit storage/readback compatibly. |
| `schemas/releases/1.3.0/**` | Add governed audit field, fixtures, compatibility/evidence/manifest; leave public deny contract unchanged. |
| `tests/test_authorization.py`, `test_responses.py`, `test_audit.py`, `test_persistence_repositories.py`, `test_persistence_projections.py`, `test_governance_dto.py`, `test_migrations.py` | Add unit, integration, contract, and migration evidence. |

## Testing Strategy and Planned RED Evidence

- Unit: table-drive human/agent and all `ResourceType` values; exact allow; four causes; precedence; assert later readers are not called; names such as `admin-human` confer nothing.
- Persistence/contract: RED tests show repositories return facts only, audit cause round-trips, invalid cause/stage rows fail, legacy rows remain readable, and 1.3 fixtures validate.
- Responses: RED spies assert missing, inactive, inactive-principal, and no-grant cases share 403 payload/decision, persist one exact cause, and perform zero assignment/provider access; allow resolves routing only afterward.

## Threat Matrix

| Boundary | Applicability | Safe/failure behavior and planned RED test |
|---|---|---|
| Documentation-like paths | N/A | No executable classification changes. |
| Git repository selection | N/A | No Git invocation. |
| Commit state | N/A | No index/worktree behavior. |
| Push state | N/A | No push behavior. |
| PR commands | N/A | No PR automation. |
| LLM provider routing | Applicable | Routing lookup occurs only after allow; every deny returns uniform 403 with zero routing/provider calls. RED spies cover order and non-enumeration. |

## Migration / Rollback

Deploy 1.3 contract and nullable database migration before application writers, then deploy DTO/model/projection and engine integration together. Roll back application writers first, then drop the check and column; keep immutable 1.3 artifacts published. No policy rows or historical audit rows are rewritten.

## Open Questions

None.
