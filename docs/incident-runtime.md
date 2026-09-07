# Incident command runtime

Issue #26 provides a deliberately bounded runtime for
`agent/workflows/incident-response.yaml`. It is not a reusable workflow engine and
does not expose HTTP routes.

## Boundary

- `incident.workflow` loads only the explicitly supported workflow identity and
  version (`incident-response@1.0.0`) and indexes its named transitions.
- `incident.runtime` validates and reduces commands. SQL and transaction mechanics
  remain outside the domain.
- `incident.persistence` defines the repository and unit-of-work ports. The
  PostgreSQL adapter from issue #146 implements those ports.
- The run-command HTTP contract from issue #145 is an adapter-facing contract. An
  adapter maps its command vocabulary to a named workflow transition before calling
  this runtime.

## Executing a transition

Construct `IncidentRuntime` with the loaded workflow and an
`IncidentUnitOfWork` factory. Submit an `IncidentCommand` with:

- stable `command_id` (the idempotency identity);
- `incident_id` and `run_id`;
- an exact transition ID from the loaded workflow;
- actor type and a concrete `ActorReference` for every human action;
- the declared outcome when a transition branches;
- explicit human approval for protected transitions;
- transition inputs, such as severity or a target incident ID.

The runtime rejects unsupported versions, unknown transitions, wrong source states,
unauthorized actor types, missing human attribution, missing approvals, and named
precondition failures before calling `persist_transition`.

The runtime implements only the guards in the current incident workflow:

- linking requires a target incident;
- declaration requires severity;
- continued investigation requires remaining step budget;
- mitigation requires a hypothesis with cited evidence;
- mitigation handling requires an existing strategy;
- verification requires evidence and a verification check;
- closure requires a postmortem.

It does not interpret arbitrary guard prose as a DSL.

## Atomicity and idempotency

A successful command passes the new incident state, run state, attributed decision,
ordered event drafts, and optional snapshot to one `persist_transition` call. The
PostgreSQL unit of work commits or rolls back this set atomically and uses optimistic
aggregate versions to reject stale concurrent writers.

Before validating a new transition, the runtime asks the unit of work for a retained
result under `(incident_id, command_id, payload_sha256)`. An exact retry returns that
result with `replayed=True`, even after the aggregate moved to a new state. Reusing the
same command ID with different content is a conflict and never writes.

## Replay and restart

The first successful runtime transition creates a snapshot; later snapshots follow
the configured interval. Every `state_change` event carries the accepted workflow
identity, named transition, decision reference, and deterministic resulting states.

`IncidentRuntime.reconstruct()` loads the newest snapshot and applies ordered events
after its sequence. It rejects missing snapshots, mismatched aggregate identity,
unsupported workflow versions, and incident/run state divergence. Therefore a new
runtime process using the same persistence adapter reconstructs the same current
state without relying on UI or process memory.

## Expected errors

- `InvalidTransitionError`: unsupported stored state/version, unknown transition,
  wrong source state, wrong actor, or incident/run state divergence.
- `PreconditionFailedError`: required domain input or human attribution is absent.
- `ApprovalRequiredError`: a protected transition lacks explicit human approval.
- `IncidentIdempotencyConflictError`: command ID reused with different content.
- `IncidentStaleWriteError`: a concurrent writer already advanced the aggregate.
