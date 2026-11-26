# Design: The core depends on ports (#1023)

The boundary, the measured context and the home of every module are in
`docs/adrs/ADR-009-core-ports-and-adapters.md`.

## Decisions

Each decision is stated once, in ADR-009: the boundary, units of work (owning and bound) and
which errors an adapter translates, published names, `gateway/` by role, the executor, settings
and the home of every module. A moved name's importers change in the layer that moves it; there
are no shims. The import contracts and their exceptions are described with them, in
`.importlinter` and `docs/ci-controls.md`.

## Contracts

| Contract | Source | Forbidden | Lines on `main` |
| --- | --- | --- | --- |
| Incident core does not use concrete adapters | `incident` | the ADR's list | 0 |
| Governance does not use concrete adapters | `governance` | the ADR's list | 0 |
| Investigator reaches the gateway over HTTP only and cannot write state | `investigator` | the ADR's list and `incident` | 1 |
| The deploy-executor's decisions import no framework and no adapter of its process | `executor.catalog`, `operations`, `signature` | FastAPI, Starlette, httpx, `gate`, `cli`, `executor.app`, `docker`, `flags` | 1 |
| MCP ownership and the vocabulary import no framework and no adapter | `mcp`, `vocabulary` | the ADR's list | 0 |
| Triage, Chat, BoK reach state and frameworks only through ports | `triage`, `chat`, `bok` | the ADR's list | 5, 10, 11 |
| Only the entry point imports the composition root | every package but `main`, `cli` included | `application` | 0 |

The ADR's list: SQLAlchemy, FastAPI, Starlette, psycopg, httpx, `persistence`, `gateway`,
`control`, `gate`, `cli`, `application`. Contract names that tests assert stay as they are.
`triage/` and `cli/` gain an `__init__.py`: import-linter does not see a directory without one,
and a source module that does not exist is a configuration error. An `ignore_imports` line
covers what it names: any part of an external package, or one module of ours. A later layer
adds `settings` as the source of a contract once `settings.py` stops importing the investigator,
and `seed_settings` when it is created. `settings.py` imports no `governance` either: the executor
imports it, and the executor's contract forbids `governance`.

## Verification per layer

The checks command (`--profile checks run --build --rm python-checks`), the CI static checks,
`lint-imports` output, the indicators by the clone route of `docs/quality-indicators.md`, the
runtime `openapi.json` compared with `main`, the gate route evidence, requests compared with
`main` where SQL or a router moves, and Telegram transcripts compared with `main` where chat
changes. Console e2e and the close-loop journey run on the layers that move incident, chat,
executor or gateway code.
