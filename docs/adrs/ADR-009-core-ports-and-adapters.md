# ADR-009: The core depends on ports; SQL, HTTP and processes are adapters

- **Status:** Proposed (#1023); accepted when the first pull request of its stack merges
- **Location:** `docs/adrs/`, like ADR-007 and ADR-008. `schemas/adrs/` is pinned by every
  contract release: the tooling hashes each `ADR-*.md` there into release 1.0.0's inventory
  (`schemas/tooling/lib/release-validation.mjs`), so a new file fails
  `validate:releases:locked`. This decision does not change a contract.

## Context

Measured on `main` `dce0dc31` (the audit of 2026-11-09 was on `0cb2ad44`):

- Still true: `triage/service.py` imports SQLAlchemy and `persistence`, and its `_SessionUnits`
  (`:118`) subclasses `PostgresIncidentUnitOfWork`; `chat/outbox.py` has 21 `text(` calls and its
  renderers read `incident.*` tables; `bok/retrieval.py` holds a FastAPI router, SQL
  (`BoKOwnerRepository`) and gateway audit; `executor/app.py:234` passes FastAPI's `Request`
  into the decision; `persistence/seeds.py` (a CLI) imports `bok.owner` and `mcp.owner`;
  `AuditStore` lives in `gateway/responses.py:177`; `create_application` (`application.py:55`,
  237 lines) builds `OperationExecutor` twice and repeats
  `lambda: PostgresIncidentUnitOfWork(database)` 7 times; `execution.py` opens a new
  `httpx.AsyncClient` per call (3 sites); seven lines read `os.environ` in `chat/telegram.py` and
  `chat/outbox.py`; `persistence/seeds.py:118,163` and `investigator/client.py:49` declare their
  own settings classes.
- Changed: `gateway/` has 30 modules, 11 import SQLAlchemy; the governed routes run on one gate
  (`gate/pipeline.py`, whose result is a FastAPI `Response`) and the control plane is one module
  per resource (`control/`, #1022); `sessions: Any` appears 17 times in `gateway/`;
  `.importlinter` had 6 contracts, none on `triage`, `chat` or `bok`; `triage/` had no
  `__init__.py`, so no contract could see it.
- The investigator runs inside the API process: `gateway/investigation.py:62` imports
  `investigator.loop.investigate` and runs it in `asyncio` tasks; `investigator/client.py` calls
  the same API back over HTTP with the client `application.py:130` builds.
- Several core paths work inside one transaction they do not own: triage
  (`triage/service.py:321-595`), the Telegram outbox (`chat/outbox.py:200-257`, a row held with
  `FOR UPDATE SKIP LOCKED` while it renders and sends) and `enqueue`, which runs in its producer's
  transaction (`gateway/reinvestigation.py:76`, `chat/taps.py:157`).
- Indicators at `dce0dc31`: I06 237, I07 9, I08 2, I09 8, I10 11, I17 185.

## Decision

### Core, ports, adapters

**Core** imports no SQLAlchemy, FastAPI, Starlette, psycopg or httpx, and no `persistence`,
`gateway`, `control`, `gate`, `cli` or `application`: `vocabulary`, `governance`, `incident`,
`investigator`, `triage`, `chat`, `bok`, `mcp`, and the deploy-executor's decisions (`catalog`,
`operations`, `signature`, and the `decisions`, `ports` modules this stack adds). `settings.py`
reads configuration and imports no adapter. The core set of `scripts/quality_indicators.py`
(`CORE`) stays as it is.

**Ports** are `Protocol`s, with the value types and errors they carry, in a `ports` module of the
package that owns the need: `incident/ports.py` (today's `incident/persistence.py`),
`governance/ports.py` (`AuditStore`), `triage/ports.py`, `chat/ports.py`, `bok/ports.py`,
`executor/ports.py`, `mcp/owner.py` (`MCPOwnerStore`, kept), `investigator/ports.py` (kept),
`gateway/usecases/ports.py` (today's `gateway/providers.py`, the MCP upstream, the endpoint
catalog and the executor client).

**Adapters** implement ports or receive requests; they may import the core, never the reverse.
`persistence/` holds every SQLAlchemy statement; `gate/`, `control/` and `gateway/http/` receive
HTTP; `gateway/adapters/` and the executor's `docker.py`, `flags.py` and `journal.py` call out;
`cli/` and `executor/app.py` are processes; `application/` composes.

### Ports inside a transaction the caller owns

A port whose statements must share one transaction is a **unit of work**, as
`IncidentUnitOfWork` already is: the core receives a factory, opens it with `async with`, and
reaches every repository it needs as a property of the open unit. The SQL adapter opens one
session with `session.begin()` and builds every property over that session, so each statement,
each lock (`FOR UPDATE`) and each write the core makes through the unit belongs to one
transaction, held until the core leaves the `async with`. A unit can also be bound to a session
an adapter already holds (`PostgresIncidentUnitOfWork.bound(session)`, today's `_SessionUnits`):
then it neither begins nor commits. A database error the core must answer (a unique violation)
is translated by the adapter into an error declared in the port module. The core never sees a
session, and no port signature names SQLAlchemy.

- **Triage.** `TriageService` receives a factory of `TriageUnitOfWork` (`triage/ports.py`):
  the grant and resource fact readers its `AuthorizationDecisionEngine` evaluates, the
  idempotency claims, the alert triage store, `lock_incident_state` (the `FOR UPDATE`),
  `investigation_run_id`, the eligible-incident list, `declare` (incident and run rows; a unique
  violation becomes `IdentifiersTaken`, answered 409 `idempotency_conflict` as today) and an
  `IncidentUnitOfWork` bound to the same session for the runtime's transition and run start. One
  `async with` per command, as today's one `transaction()`.
- **Chat.** Renderers read through `ChatReads`; `enqueue(outbox, ...)` writes through a
  `ChatOutbox` bound to the producer's session, so a message still commits or rolls back with
  its producer. `deliver_next` opens a `ChatDelivery` unit: it takes the due row with
  `FOR UPDATE SKIP LOCKED`, renders through the unit's `ChatReads` (same transaction, under the
  lock), sends or edits, records the result, and commits on leaving, in today's order. Taps,
  decisions, digests and links get units of the same shape.
- **Audit.** `AuditStore.append(event)` moves to `governance/ports.py`; the core only appends.
  `TransactionalAuditStore.append_in_transaction(event, session)` is used only by `control/`, an
  inbound adapter that owns its transaction (`control/governed.py:176`): it moves with
  `PostgresAuditStore` to `persistence/audit.py`, unchanged.

### What clients read stays

FastAPI names a colliding schema after the module that defines it
(`sre_agent__gateway__responses__ErrorEnvelope`). The models of `gateway/responses.py`
(`ResponsesRequest` to `ErrorEnvelope`) stay defined in `sre_agent.gateway.responses`, as the
control plane's stay in `control/service.py`; the router and service move to
`gateway/http/responses.py`. Operation ids derive from the endpoint function's name and route, so
endpoint functions keep their names. Log records keep their logger names: a module that moves
names its logger with the old dotted string, so `caplog` filters, scripts and logs read the same
names.

### `gateway/` by role, and where each module ends

A service that runs on the gate is inbound, because the gate's result is an HTTP response: it
moves whole with its router to `gateway/http/`. Use cases without HTTP go to `gateway/usecases/`,
which imports no FastAPI, Starlette, `gate` or `gateway.http`. Until the use cases receive
injected readers, they build them from the session factory and reach SQLAlchemy through
`persistence/`.

| Module (`src/sre_agent/`) | Role | Where it ends |
| --- | --- | --- |
| `main.py` | entry point | stays |
| every package's `__init__.py`; `bok/otel_demo_store.json` | — | stay |
| `application.py` | composition | package `application/`: a container built once and one wiring function per plane; `create_application`, its signature, `application.state` and `REPOSITORY_ROOT` stay importable from `sre_agent.application` |
| `settings.py` | configuration | stays; gains `GatewaySettings` (from `investigator/client.py`) and the Telegram, seed, routing and executor settings; imports no adapter |
| `release.py`, `vocabulary.py` | core | stay; `vocabulary.py` gains `OutputLanguage` (from `investigator/contract.py`) |
| `governance/authorization.py`, `dto.py`, `resources.py` | core | stay |
| `gateway/audit.py` | core | `governance/audit.py` (`AuditProjector`) |
| `incident/persistence.py` | port | `incident/ports.py` |
| `incident/` other 9 modules | core | stay |
| `investigator/contract.py`, `fixtures.py`, `loop.py`, `ports.py`, `postmortem.py`, `prompt.py` | core | stay |
| `investigator/client.py` | outbound adapter of the API process | `gateway/adapters/investigator.py` |
| `triage/service.py` | core | stays, on `triage/ports.py` |
| `triage/store.py` | SQL | `persistence/triage.py` |
| `chat/outbox.py`, `digest.py`, `decisions.py`, `taps.py` | core | stay, on `chat/ports.py`; their SQL to `persistence/chat.py`; `taps.py` reaches run commands through a `RunCommands` port |
| `chat/telegram.py` | process and Bot API client | `cli/telegram.py` |
| `bok/owner.py`, `publication.py` | core | stay, on `bok/ports.py`; their SQL to `persistence/bok.py`; `otel_demo_store.json` stays beside `owner.py` |
| `bok/retrieval.py` | inbound, on the gate | `gateway/http/bok.py`; `BoKOwnerRepository` to `persistence/bok.py` |
| `mcp/owner.py` | core | stays |
| `executor/catalog.py`, `operations.py`, `signature.py` | core | stay; `operations.py` on a container-engine port |
| `executor/app.py` | process | keeps the FastAPI app; the decision (`Executor`) to `executor/decisions.py` without `Request`, `Journal` to `executor/journal.py` |
| `executor/docker.py`, `flags.py` | outbound adapters | stay |
| `gate/` (4 modules) | inbound | stay |
| `control/` (14 modules) | inbound | stay (`service.py` keeps the control schemas) |
| `persistence/` (10 modules) | SQL | stay, plus `audit.py`, `triage.py`, `chat.py`, `bok.py` and the readers taken out of `gateway/`; `api_keys.py` stays |
| `persistence/seeds.py` | process | `cli/seeds.py` |
| `gateway/providers.py` | port | `gateway/usecases/ports.py` |
| `gateway/openrouter.py`, `endpoint_catalog.py` | outbound adapters | `gateway/adapters/` (the catalog's types and errors to the ports module) |
| `gateway/mcp.py` | inbound, on the gate | router and service to `gateway/http/mcp.py`; `GrafanaMCPClient` to `gateway/adapters/mcp.py`; its port `MCPUpstreamClient` and the `MCPUpstream*` errors to the ports module |
| `gateway/execution.py` | use case and outbound | `OperationExecutor` to `gateway/usecases/execution.py`; the three HTTP calls to `gateway/adapters/executor.py`, one client per call as today |
| `gateway/authentication.py` | inbound and use case | `authorize_governed_access` to `gateway/http/`; `authorize_governed_access_for_context` to `gateway/usecases/access.py` |
| `gateway/investigation.py`, `reinvestigation.py`, `attribution.py`, `consumption_admission.py`, `consumption_affordability.py` | use cases | `gateway/usecases/`, their SQL to `persistence/` |
| `gateway/responses.py` | inbound, on the gate | router and service to `gateway/http/responses.py`; the models stay |
| `gateway/` `action_catalog`, `alert_intake`, `alerts`, `audit_reads`, `changes`, `event_decisions`, `health`, `identity`, `incidents`, `postmortems`, `run_context`, `runs`, `skills`, `triage`, `usage`, `usage_requests`, `usage_requests_models` | inbound | `gateway/http/`, each moved once and whole, their SQL to `persistence/` first |

Configuration is read in `settings.py`; variable names, defaults and precedence do not change.
The chat renderers receive the time zone and console URL from the process that runs them.

## Consequences

Telegram, the console, MCP and the API reach the same core through adapters (value 5). Each
layer of the stack shows the runtime `openapi.json` and the gate route evidence identical to
`main`, and compares requests, Telegram transcripts or command lines where it moves them. Moving
`persistence/seeds.py` and `chat/telegram.py` changes their `python -m` paths; every caller in the
repository changes in the same layer. The executor keeps one HTTP client per call: a pooled
connection could fail a mitigation `POST` that a fresh one does not.

## Alternatives

- Moving SQL to packages the indicators do not count while the core still reaches it
  (re-export, lazy import): the indicators would improve and the code would not.
- Ports that open their own session per call: simpler, but a grant revoked between the check and
  the write would no longer stop a declaration, and a message could render from state its lock
  does not cover.
- A gate without FastAPI, so that governed services become use cases: it redoes #1021's gate.
- One contract per package without exceptions: it would fail until the whole stack lands.

## Deferred

A check for private names read across modules (import-linter cannot express it); replacing
SQLAlchemy or FastAPI; `control/` keeping `IntegrityError` and `select`; use cases that receive
injected readers instead of the session factory, until the maintainer decides.

## Supersedes

None.

## Links

- [`openspec/changes/issue-1023-hex-boundaries/`](../../openspec/changes/issue-1023-hex-boundaries/)
- [`.importlinter`](../../.importlinter) and [CI controls](../ci-controls.md#architecture-and-typing-controls)
- [ADR-007](ADR-007-harness.md), which places the investigator loop
- Issue #1023 and its epic #1015
