# Issue #332 — Foundation evidence (current source)

**Candidate:** `ea74a6e8970ff6b3cbf7ebef885fc97c5816da89`  
**Base:** `5b6109bd2c8100455136cf12ce91c52830833c7f` (main)  
**Controlled result:** 16 observed scenarios, all assertions passed; schema `20260929_15`.

## Acceptance map

| Criterion | Current evidence | Boundary |
| --- | --- | --- |
| CA1 — immutable, versioned owner ingestion and safe activation | [Current producer JSON](results/foundation-results.json), [capture](foundation.png). First seed created, exact replay returned false, altered same-version bundle raised collision and retained original bytes; two demo rows persisted. A partial document remained `indexing` and activation returned `bok_version_not_ready`. Changed and deleted persisted chunk activations each raised `collection_version_collision`, left status `ready` and drift intact, restored in `finally`, then allowed valid activation. Arbitrary document/chunk order activated successfully. Four independent exact-replay drift cases likewise retained the parent manifest and corrupted children, raised collision, restored rows, and allowed intact replay. | Real synthetic owner operations against disposable PostgreSQL. SQL-level owner evidence; not HTTP. |
| CA2–CA6 — governed retrieval | Not provided by Foundation. | Retrieval belongs to M (#422), not this PR. |

The source tests and end-to-end focused/full suites are linked in the Retrieval report. Foundation's hosted workflow is separate: [exact-head CI run 36711627164](https://github.com/creep1ng/sre-agent/actions/runs/36711627164), all 8 required jobs succeeded.

## Reproduction and safety

See [portable reproduction](reproduction.md). The actual run used the exact frozen source SHA, existing Compose `api` and `python-checks` services, the `python-checks-db` PostgreSQL service on tmpfs with no host DB port, and the isolation guard before migration and probe. The API served the actual FastAPI app over the project network; the probe used only synthetic corpus/API keys held in memory. It exercised owner persistence directly as a separately labeled SQL observation. No external providers, paid APIs, Jev, cloud, OTel, SSH, production system, concurrent writer, admin-write protection or platform-hardening claim is made.

One first probe attempt hit a harness-only `None`-row handling error in the private evidence script while checking the expected absence after DELETE. Its `finally` restored the synthetic chunk, and the project was scoped down without `-v`; the corrected script was rerun against a fresh tmpfs database and passed. This setup failure is retained in the private execution ledger and is not counted as a source defect or successful observation.

## Capture

`foundation.png` is an actual local Chromium screenshot of the HTML renderer over the saved JSON, not a product UI. It was visually inspected for readable cards and disclosure. No generated image or fabricated capture is used.
