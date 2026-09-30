# Issue #332 — foundation and immutable replay integrity

## Identity and scope

- Source F: `9fb91f725e5c292346b930e3dae787cc05fe1a71` (tree `5560166ed8e0f3ba0b3d90693f3077e54b9d7485`), based on main `5b6109bd2c8100455136cf12ce91c52830833c7f`.
- Source diff: 738 additions + 25 deletions = 763 lines across 29 paths. Schema head: `20260929_15`.
- F supplies the owner corpus, ready-only activation, migration merge and synthetic demo producer; it intentionally has no retrieval endpoint.
- The R5 replay correction compares persisted document metadata and chunk keys/content before an equal-manifest replay can return `False`. A child mismatch raises existing `BoKVersionCollision`; it does not rewrite corrupted children. Both F and M share owner SHA-256 `56d60886b1dfd7ee5957b67e727b993b700708fd8dae7e757b36c47d478b6b00` and persistence-test SHA-256 `6ba8380901bf750c461187c4cf5fcaea7fb336a750d2f94f89b06d9d46653e6f`.

## Verified current-source evidence

- Independent local full configured source suite: **1227 passed, 1 intentional live-provider skip**, exit 0. The skip is the unconfigured live OpenRouter smoke.
- Current-source producer probe: **12 observed scenarios**, exit 0, against FastAPI over TCP and the existing Compose `python-checks-db` disposable tmpfs PostgreSQL service; the database isolation guard and migration exited 0.
- Four separately labeled committed synthetic owner/SQL mutations all passed their assertions: chunk-content UPDATE, chunk DELETE, document-title UPDATE, and document `content_sha256` UPDATE. Each left the parent manifest unchanged, caused exact replay to raise `BoKVersionCollision`, left drift unrepaired until explicit restoration, restored successfully in `finally`, and then allowed intact replay to return `False`.
- Other recorded outcomes include first insert/replay, same-version collision, empty-version activation rejection, persisted demo rows, schema head `20260929_15`, readiness 200 and search endpoint 404.
- Local image IDs: API `sha256:29e3ebaa79496c3ba35e8dfc3cc3951e6e522c99ff8460d394f28ce80ed5add8`; checks `sha256:07a801296c34c978d14caa5dbfd1488bfd27bcc181b7213cd91a6b23c30c4105`.
- Hosted CI on this exact source succeeded: [run 36673827658](https://github.com/creep1ng/sre-agent/actions/runs/36673827658), all 8 required jobs SUCCESS, watch exit 0. CI success is not semantic or human acceptance.

The real JSON is [`foundation-results.json`](foundation-results.json); the visually inspected Chromium capture is [`foundation.png`](foundation.png), 1600 × 2400, SHA-256 `f198c0552e19d52afc9271f854fd52d89159dcd1c92c778a9d5cf4e4e9ca5c6f`. It renders the recorded output, not a live product UI.

## Criterion boundary

| Criterion | F evidence |
| --- | --- |
| CA1 — owner foundation | Source-suite checks, owner replay behavior, four persisted-child drift cases, readiness and search absence observed as above. |
| CA2–CA6 — governed retrieval | Not in F scope; provided by M and reported separately. |

## Historical evidence, not current proof

[The immutable prior foundation JSON](https://github.com/creep1ng/sre-agent/blob/7adfcaad8d2af313bd58983dd4bdd6df390e4426/docs/evidence/issue-332/foundation-results.json), [PNG](https://github.com/creep1ng/sre-agent/blob/7adfcaad8d2af313bd58983dd4bdd6df390e4426/docs/evidence/issue-332/foundation.png) and [report](https://github.com/creep1ng/sre-agent/blob/7adfcaad8d2af313bd58983dd4bdd6df390e4426/docs/evidence/issue-332/foundation-report.md) describe source `1b70672629d0c65b393fc6d31022f6a04207b615` (8 observations), not F. They remain immutable at the old published evidence commit and are excluded from the current manifest.

## Reproduction, safety and limitations

See [`reproduction.md`](reproduction.md) for the portable, bundle-relative commands. The local current run used the exact frozen SHA and a private overlay byte-identical to the included `compose-proof-network.yml` (`10.254.239.0/28`). API was stopped with intentional Ctrl-C (process exit 130); scoped Compose `down` exited 0, and the project's containers/network were absent afterward. A Compose-created project-named `postgres_data` volume metadata entry was left untouched because cleanup deliberately omitted `-v`; it was not the tmpfs test database.

Synthetic built-in corpus only; API keys were generated in memory, checked absent from serialized output, and not published. Provider keys stayed empty. No paid provider, Jev, cloud, OTel, SSH, persistent test DB, production load, privileged-write defense or concurrency guarantee is claimed. The SQL replay cases are distinct from HTTP outcomes and audit rows, and are not API SQL-read instrumentation.

## Delivery state

Evidence files and current CI proof are ready for parent publication; the evidence-only commit and public HTTPS binding remain parent-owned and pending. PR #382/#422 are DRAFT. `papiarcacamilo` was requested as reviewer; no human approval is recorded. The #382 finding remains unresolved until parent publishes/readbacks evidence and responds. No merge, issue closure, approval or label is claimed; optional Jev remains deferred.
