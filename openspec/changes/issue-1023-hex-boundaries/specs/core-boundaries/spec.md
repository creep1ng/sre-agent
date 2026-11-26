# Core Boundaries Specification

## Purpose

Keep the core free of frameworks and adapters so that every interface reaches it through ports.

## ADDED Requirements

### Requirement: The core imports no framework and no adapter

A core module, as ADR-009 lists them, MUST NOT import a framework (SQLAlchemy, FastAPI,
Starlette, psycopg, httpx) or an adapter package (`persistence`, `gateway`, `control`, `gate`,
`cli`, `application`), directly or through another module, unless `.importlinter` lists that
import in the contract's `ignore_imports`, one importing module per line; the list MUST only
shrink.

#### Scenario: A new core module imports SQLAlchemy

- GIVEN the contracts of `.importlinter`
- WHEN a new module of `triage` or `chat` imports `sqlalchemy`
- THEN `lint-imports` reports that package's contract BROKEN and exits non-zero

#### Scenario: A core module imports a process entry point

- GIVEN the contracts of `.importlinter`
- WHEN a module of `triage` imports `sre_agent.cli`
- THEN `lint-imports` reports the triage contract BROKEN

#### Scenario: Today's tree

- GIVEN `main` with the listed exceptions
- WHEN `lint-imports --no-cache` runs in the checks image
- THEN every contract is KEPT and no listed exception is reported as unmatched

### Requirement: A port joins the transaction its caller owns

A core operation whose reads, locks and writes share one transaction today MUST reach them
through one unit of work opened once, whose SQL adapter binds every repository to one session.
No port signature MUST name a SQLAlchemy type.

#### Scenario: A triage declaration

- GIVEN a declaration of an alert as an incident
- WHEN the triage service runs it
- THEN the grant checks, the idempotency claim, the triage write, the incident and run inserts
  and the transition commit run in one transaction, and a failure in any of them leaves none

#### Scenario: A chat message is delivered

- GIVEN a due outbox row
- WHEN the Telegram process delivers it
- THEN the row is locked, rendered from state read in the same transaction, sent, and recorded
  before the lock is released

### Requirement: Only the entry point composes

Every package of `sre_agent` other than `sre_agent.main`, `sre_agent.cli` included, MUST NOT
import `sre_agent.application`.

#### Scenario: A process imports the composition root

- GIVEN the contracts of `.importlinter`
- WHEN a module of `sre_agent.cli` imports `sre_agent.application`
- THEN `lint-imports` reports "Only the entry point imports the composition root" BROKEN

### Requirement: Clients observe nothing

A change that moves code across the boundary MUST leave the runtime OpenAPI document (schema
names included), the governed routes' gate evidence, the responses to the same requests, the
Telegram messages, buttons and edits, and the command lines of the repository's callers
identical to `main`.

#### Scenario: A router moves

- GIVEN `main` and the candidate, each with every optional router mounted
- WHEN both dump `openapi.json` and sort it canonically
- THEN the two documents are byte-identical
