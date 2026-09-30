# Issue #332 — Foundation F R11 acceptance report

**Candidate:** `e2b83d45f285c46a5a83c0234846dbfd122934df`
**Tree:** `ec2cd2164ebbe2acc07608a2426cd700a301574d`
**Base:** current main `2779b0b9af4476c1e1a0c0b99ab2379c8326a86e` (parents `b25763cd3e914da74af0ee6a9257a4f830cb379a` + `2779b0b9`)
**PR:** #382, base `main`, DRAFT
**Diff vs base:** 1,071 additions + 25 deletions = 1,096 lines / 29 paths
**Controlled result:** 18 observed scenarios, all assertions passed; schema `20260929_15`; captured `2026-09-30T13:59:36Z`.

## Acceptance map

| Criterion | Current evidence | Boundary |
| --- | --- | --- |
| CA1 — immutable, versioned owner ingestion and safe activation | [Current producer JSON](results/foundation-results.json), [capture](foundation.png). First seed created, exact replay false, altered same-version bundle raised collision and retained original bytes; two demo rows persisted active 1/1. Empty activation `bok_version_not_ready`; partial document stayed `indexing` and activation `bok_version_not_ready`. Changed and deleted persisted chunks each raised `collection_version_collision`, left `ready` with drift intact, restored in `finally`, then valid activation `active`. Arbitrary document/chunk order `active`. Success catalog case advanced inactive `ResourceRow.updated_at` from 2000-01-01 while preserving owner `created_at`; rejected drift case raised `BoKVersionCollision`, left catalog `inactive` with timestamp unchanged, preserved owner `created_at`, restored child in `finally`. Four exact-replay drifts retained parent manifest, raised collision, restored rows, allowed intact replay. | Real synthetic owner operations against disposable PostgreSQL. SQL owner evidence plus TCP readiness/404; not HTTP retrieval. |
| CA2–CA6 — governed retrieval | Not provided by Foundation. | Retrieval belongs to M (#422), not this PR. |

Source checks for exact merge bytes: focused 125 passed (23.74s); configured full/static 1,272 passed, 1 intentional live-provider skip (81.43s), exit 0; Ruff 170 files, lock 93, imports 5, mypy 12, Alembic no new operations. Hosted workflow: [exact-head CI run 36722870580](https://github.com/creep1ng/sre-agent/actions/runs/36722870580), all 8 required jobs SUCCESS (configuration-lock, checks-image, unit, contracts, static-web, compose-smoke, production-browser, Quality gate).

## Reproduction and safety

See [portable reproduction](reproduction.md). The run used frozen F SHA, existing Compose `api`/`python-checks` services, `python-checks-db` tmpfs with no host DB port, isolation guard before migration and probe, overlay subnet `10.254.239.0/28`, sequential project `issue332-foundation-r11`, synthetic in-memory API keys never serialized. API served real FastAPI over project network; probe exercised owner SQL directly as labeled observations. No external providers, paid APIs, Jev, cloud, OTel, SSH, production, concurrent stress, admin-write prevention or platform hardening claimed. Scoped `down` without `-v` removed DB/network; owned labels verified empty.

## Capture

`foundation.png` is a real local Chromium 153.0.8010.52 screenshot (1600×1500, 217,709 bytes) of the HTML renderer over saved JSON, with background networking off and DNS blocked. Visually inspected for 18 readable cards, correct SHA/binding, and disclosure footer. Privacy audited: synthetic corpus only, no credentials, headers, queries, or keys. No generated image or fixture fallback.
