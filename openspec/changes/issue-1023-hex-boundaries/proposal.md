# Proposal: The core depends on ports (#1023)

## Intent

The core (`incident`, `investigator`, `triage`, `chat`, `bok`, `mcp`, `governance`, the
executor's decisions) still imports SQLAlchemy, FastAPI and the adapter packages in 9, 2 and 8
files (I07-I09 at `dce0dc31`). Draw the boundary once, bind it with import contracts, and move
one package per layer behind its ports without changing what any client observes. Value served:
5, the engine is the product and the interfaces are clients.

## Scope

### In Scope

- ADR-009 (`docs/adrs/ADR-009-core-ports-and-adapters.md`): core, ports, adapters, how a port
  takes part in a transaction its caller owns, what keeps published names, and where every
  module of `src/sre_agent/` ends.
- `.importlinter`: every core unit forbids the ADR's whole list, with today's violations listed
  as `ignore_imports`; `cli` is forbidden to the core and may not compose; later layers remove
  the listed lines.
- Later layers of the same stack, one package each, as `tasks.md` lists them.

### Out of Scope

- Changing behaviour, routes, contracts, schema names, status codes, audit events, log record
  names or environment variable names; replacing SQLAlchemy or FastAPI; the control plane's
  internal SQL; a check for private names read across modules.

## Capabilities

### New Capabilities

- `core-boundaries`: what may import what, how a port joins its caller's transaction, and how a
  later change shows that clients saw nothing.

### Modified Capabilities

- None.

## Approach

The first two layers add only the decision and the contracts (no production module moves). Each
later layer moves one package behind its ports, removes the `ignore_imports` lines it fixes and
adds none, and shows the runtime `openapi.json` and the gate route evidence identical to `main`;
layers that touch chat compare the Telegram transcripts with `main`.

## Rollback

Each layer is one pull request; reverting it restores the previous layer's tree and contracts.
