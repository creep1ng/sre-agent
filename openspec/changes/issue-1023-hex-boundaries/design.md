# Design: The core depends on ports (#1023)

The boundary, the measured context and the home of every module are in
`docs/adrs/ADR-009-core-ports-and-adapters.md`.

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
and a source module that does not exist is a configuration error. An `ignore_imports` line names
one importing module and one imported package, so it covers every import of that package by
that module until a layer deletes it.

## Decisions

- **Transactions.** A port that shares its caller's transaction is a unit of work, as
  `IncidentUnitOfWork` is: the core opens it from a factory; the SQL adapter builds every
  repository over one session; a unit can be bound to a session an adapter already holds. Errors
  the core answers are translated by the adapter into errors of the port module.
- **Published names.** Models whose names collide keep their defining module
  (`gateway/responses.py`, `control/service.py`); endpoint functions keep their names; moved
  modules keep their logger names.
- **`gateway/`.** A service that runs on the gate is inbound and moves whole with its router to
  `gateway/http/`; use cases without HTTP go to `gateway/usecases/`; outbound clients to
  `gateway/adapters/`.
- **Executor.** The decision returns status, body and the change to record; `app.py` turns them
  into the response and keeps sending the record after it. One HTTP client per call stays.
- **Settings.** `settings.py` stops importing the investigator first, so every process can read
  its configuration there; the core receives values, never reads them.
- No shims: a moved name's importers change in the layer that moves it.

## Verification per layer

The checks command (`--profile checks run --build --rm python-checks`), the CI static checks,
`lint-imports` output, the indicators by the clone route of `docs/quality-indicators.md`, the
runtime `openapi.json` compared with `main`, the gate route evidence, requests compared with
`main` where SQL or a router moves, and Telegram transcripts compared with `main` where chat
changes. Console e2e and the close-loop journey run on the layers that move incident, chat,
executor or gateway code.
