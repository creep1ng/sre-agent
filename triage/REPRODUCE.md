# Reproduce the triage/audit review

The reports distinguish exact-head tests, controlled persisted behavior, browser route mocks, and hosted CI. All fixture data are synthetic. No real provider call is claimed.

## Prepare safely

1. Use a disposable checkout of the exact full head SHA in the relevant `pr-N.md`. Keep the evidence files in a separate writable directory. Do not run these destructive test fixtures against an existing/shared database.
2. Place `compose.review.yaml`, the Python probe/server files, `audit_fixture.py`, `browser.config.cjs`, and `connected-browser.cjs` together in that evidence directory. The Compose file supplies its own isolated, tmpfs PostgreSQL service and no published ports; it never loads the project's `.env`.
3. Set `REVIEW_SOURCE_DIR` to the absolute candidate checkout, `CANDIDATE_SHA` to the verified full head, and a unique Compose project name (examples use `sre-review-isolated`). For browser work set `REVIEW_SURFACE=audit` or `triage`, `AUDIT_PR`, and `AUDIT_BROWSER_SPEC` as listed below. These are safe local configuration, not credentials.
4. Run the commands from the evidence directory. The default image builds use the candidate's locked Dockerfiles. The observed audit reused checks image `sha256:e9d909738233806dc27166113a1599ed0c6667e5b44fa83688eef38dc84a83a8` and browser image `sha256:abba619978eef39a9a21080cbcc1b4225d4e6d179f17df388e914f4b2c7e4967`, with candidate source mounted read-only at `/repo`. Rebuilding those images was not part of the observed audit. Cached-tooling reuse is not a claim that this review ran each PR's image build.

## Build the tools and run checks

```sh
docker compose -p sre-review-isolated -f compose.review.yaml build checks browser
docker compose -p sre-review-isolated -f compose.review.yaml run --rm checks pytest -q tests/test_triage_http.py
```

Replace the final pytest file list with the exact list in `pr-N.md`. Tests always use this harness's ephemeral database. Do not pass production URLs. For pytest-only slices no web service is needed.

## Observe behavior (not only test counts)

Run the applicable command at its candidate:

| PR | Container command arguments after `run --rm checks` |
|---|---|
| 371 | `python /evidence/probe-behavior.py restart` |
| 372 | `python /evidence/probe-behavior.py audit-query` |
| 373 | `python /evidence/probe-behavior.py store` |
| 374 | `python /evidence/probe-behavior.py commands` |
| 380 | `python /evidence/probe-behavior.py link` |
| 389 | `python /evidence/probe-triage.py declare` |
| 391 | `python /evidence/probe-triage.py http` |
| 378, 379 | `python /evidence/probe-audit.py` |

Example:

```sh
docker compose -p sre-review-isolated -f compose.review.yaml run --rm checks python /evidence/probe-triage.py declare
```

The audit read probe uses a copied reviewer fixture from PR #379's exact head, while all application imports resolve to the current candidate under `/repo/src`. This allows testing #378 before that fixture entered the repository. Fixture IDs/HMAC references are synthetic; no credential is printed.

## Real connected browser

For #385/#386 use `REVIEW_SURFACE=audit` and arguments `audit 385` / `audit 386`. For #392/#393 use `REVIEW_SURFACE=triage` and arguments `triage 392` / `triage 393`.

```sh
docker compose -p sre-review-isolated -f compose.review.yaml up -d --wait web
docker compose -p sre-review-isolated -f compose.review.yaml run --rm --no-deps browser node /out/connected-browser.cjs triage 393
```

The real candidate FastAPI application and PostgreSQL run in the web/db containers. The review wrapper only serves static candidate files and maps `/api` to the candidate API, not production nginx; this is controlled integration, not a full production-proxy/OTel demonstration. No browser route mocks are used by this driver. It creates a temporary local `local-credential.json` solely for the issued fixture key; NEVER publish this file. The API key input is cleared before screenshots. The generated `pr-N-connected.json` records responses without headers, keys, or provider content.

Expected #392/#393 behavior after repair: switching from successful link to declare sends only declaration fields and succeeds. Observed current candidates: a leftover `target_incident_id` is included and HTTP returns 422. Expected #385/#386 detail: allowed routing references are visible. Observed: status and latency appear; routing references supplied by the API do not.

## Existing browser suites

Set `AUDIT_PR=393`, `AUDIT_BROWSER_SPEC=triage.spec.js`, or `AUDIT_PR=386`, `AUDIT_BROWSER_SPEC=audit-events.spec.js`.

```sh
docker compose -p sre-review-isolated -f compose.review.yaml run --rm --no-deps browser /e2e/node_modules/.bin/playwright test --config=/out/browser.config.cjs
```

This runs the authored route-mocked cases over a container-local static server. The connected-only cases are skipped unless their documented production topology is supplied. Do not describe those skipped cases as locally passing. Separate connected probes above are additional evidence, not the same test suite.

## Cleanup

```sh
docker compose -p sre-review-isolated -f compose.review.yaml run --rm --no-deps checks python -c "from pathlib import Path; Path('/evidence/local-credential.json').unlink(missing_ok=True)"
docker compose -p sre-review-isolated -f compose.review.yaml stop web db
docker compose -p sre-review-isolated -f compose.review.yaml rm -f web db
```

Only this uniquely named project is touched. PostgreSQL data were tmpfs; no volume teardown is needed. Never run global prune or `down -v`.

## Capture provenance

- `pr-N-behavior.png`: Chromium screenshot of the actual sanitized saved behavior log, with wrapping enlarged for readability. These are **captured logs**, not application UI screenshots or hand-authored result panels.
- `pr-N-connected.png`: actual Playwright browser screenshots against the candidate API and isolated PostgreSQL, with no route mock.
- `pr-N-browser.png`: earlier host-Chromium/CDP capture of the same connected triage flow; supplementary, not the Docker browser reproduction.
- Existing suite screenshots contain mocked journey results and must not be represented as real backend evidence.

## Publication-copy safeguards

These publication copies preserve observed results. The reviewer drivers additionally fail closed unless the database URL names user `audit`, database `python_checks`, and this harness host `db` (or the historical isolated review container alias). Temporary fixture credentials are created with owner-only permissions. These guards protect the evidence harness; they do not modify candidate source. The declaration diagnostic intentionally demonstrates the current defect and is not a passing acceptance test for a repaired candidate. Historical image reuse is documented above; portable paths use the included Compose file and `/repo`, `/evidence`, `/out`, not a workstation directory.
