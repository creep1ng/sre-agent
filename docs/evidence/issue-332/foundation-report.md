# Issue332 foundation: persisted corpus, not retrieval

**8 real owner/SQL/network observations passed.** The foundation delivers immutable versioned
owner data and ready-only activation. It deliberately does not expose searchable endpoints.
Primary evidence kind: **controlled integration**. Owner calls and SQL use actual PostgreSQL;
HTTP readiness and endpoint absence use a running FastAPI process over TCP.

## Actual versus expected

| Scenario | Expected | Actual |
| --- | --- | --- |
| First seed / identical replay | Create, then no new rows | true / false |
| Same version, changed bytes | Reject collision; retain original | Collision rejected; persisted original unchanged |
| Two demo collections | Active; one document and chunk each | Exact SQL rows verified for both |
| Empty chunk activation | Reject unready owner | bok_version_not_ready |
| Runtime readiness |200 on migrated schema |200 |
| Search endpoint | Absent from this unit |404 |

CA1 owner foundation is covered; the “both collections searchable” portion is deferred to
retrieval. CA2–CA6 are not claimed by this foundation. No fixture fallback or ingestion HTTP
endpoint is invented: ingestion proof calls the existing owner functions inside the image.
See the [retrieval CA1–CA6 source map](retrieval-report.md#acceptance-matrix) for the separate
required-retrieval candidate; its evidence does not expand this foundation’s scope.

## Source verification and delivery scope

Writer full lane:1223 passed,1 skipped; parent focused70 passed; independent full1223 passed,
1 skipped, 84.11s. Skip is the unconfigured live-provider smoke, not run. The parent verified source
preservation before freezing. Source diff versus main:530 additions+25 deletions=555,29 paths.
The maintainer explicitly approved scoped size exceptions for the two coherent required units
in the parent conversation on 2026-09-29, retaining complete tests/docs and deferring Jev. This is
not a GitHub review approval. Evidence additions are counted again at publication, not hidden. Published owner migration bytes are unchanged; additive merge20260929_15
reconciles BoK20260924_14 and usage20260926_14.

## Risks, rollback and next owner

Catalog availability is not owner search readiness. Empty or revoked owners must never be
marketed as searchable. Revert this coherent source unit before deployment only; persisted
BoK data intentionally prevents lossy downgrade. Parent owns publication and human-review request.
Chain: **📍 #382 foundation → #422 required retrieval → human integration**. Same bottom-up
stacked-to-main strategy; no feature tracker and no automatic merge.

## Identity and environment

- Tested source: `1b70672629d0c65b393fc6d31022f6a04207b615`; source base: `5b6109bd2c8100455136cf12ce91c52830833c7f`.
- Schema: `20260929_15`; Python3.12.14; Docker29.8.1; Compose5.5.1; runtime UID65532.
- Runtime image: `sha256:5a0c4893411bb6a31bd5efe73ed12c32552b36f5213e83076625ba4766462df0`.
- Checks image: `sha256:e114368c4667f4b87c91a974229849f0fb5aff299f429271cbd30c6e6273e21e`.
- PostgreSQL: `postgres:17.4-alpine@sha256:7062a2109c4b51f3c792c7ea01e83ed12ef9a980886e3b3d380a7d2e5f6ce3f5`; private project network, tmpfs database, no DB host port.
- Lock SHA-256: `783c78b44e4ab07091d0ee1d44a693b77f1ec0fdc94f9aa3c0e212cd34dc878b`. Source was read-only during evidence work.
- Synthetic built-in corpus only; generated ephemeral credentials stayed in process memory.
  No provider/OTel/SSH/cloud traffic, secret-bearing configuration or ambient identity was used.

## Reproduce and inspect

[Container commands](reproduction.md), [portable probe](producer-probe.py),
[full recorded results](foundation-results.json), [sanitized probe summary](foundation-probe.txt),
[local checks excerpt](foundation-checks.txt), [provenance](provenance.json),
[review-resolution ledger](review-ledger.md). Actual final build, guarded migration and network
probe commands exited0. Foreground API exited0 after an explicit scoped stop; owned tmpfs
project removed without `-v`. No runtime handle remains active.

## Capture

[Real browser PNG](foundation.png) shows recorded actual network/SQL data, not a live application UI.
The capture was visually inspected for readability and sensitive content. Credentials/headers,
personal paths, raw configuration and confidential corpus content are excluded.

## Hosted CI and acceptance boundary

The parent independently confirmed all eight mandatory jobs succeeded on this exact source:
[CI run36660022792](https://github.com/creep1ng/sre-agent/actions/runs/36660022792).
Jobs: configuration-lock, checks-image, static-web, unit, contracts, compose-smoke,
production-browser and Quality gate. This is hosted functional proof, not semantic acceptance.
Governance metadata/evidence publication and independent human review remain pending.
No approval label, merge, issue closure or release is authorized by these artifacts.

## Security and video

Sanitized: yes

Deferred: media storage unavailable; screenshot evidence is mandatory.
