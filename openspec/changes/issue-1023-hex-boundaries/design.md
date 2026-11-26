# Design: The core depends on ports (#1023)

The boundary, the measured context and the home of every module are in
`docs/adrs/ADR-009-core-ports-and-adapters.md`.

## Decisions

Each decision is stated once, in ADR-009: the boundary, units of work (owning and bound) and
which errors an adapter translates, published names, `gateway/` by role, the executor, settings
and the home of every module. A moved name's importers change in the layer that moves it; there
are no shims. The import contracts and their exceptions are described with them, in
`.importlinter` and `docs/ci-controls.md`.

## Verification per layer

The checks command (`--profile checks run --build --rm python-checks`), the CI static checks,
`lint-imports` output, the indicators by the clone route of `docs/quality-indicators.md`, the
runtime `openapi.json` compared with `main`, the gate route evidence, requests compared with
`main` where SQL or a router moves, and Telegram transcripts compared with `main` where chat
changes. Console e2e and the close-loop journey run on the layers that move incident, chat,
executor or gateway code.
