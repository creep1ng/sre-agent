# Issue 454 — historical request attribution evidence

Status: **implemented and locally verified; ready for independent human review**.
Refs #454. Refs #143. Route: direct, within the approved backend producer scope.
No consumer UI, merge, issue closure or independent human acceptance is claimed.

## Candidate, provenance and environment

- Tested source: `2a8a3599095bf363ee9c3fa8be4bf89756381813`; base: `23e1a42dd1f3c0ad98b76ee6f5f25906570d50c2`.
- Original design-first `3adefc2`, preauthored tests/contract `b7a3bc5`, then source
  `15325da`: [published provenance](https://github.com/creep1ng/sre-agent/commits/codex/issue-454-historical-attribution).
  Later bounded publication ordering does not change original TDD authorship.
- Real FastAPI/Uvicorn loopback HTTP and PostgreSQL17.4 tmpfs; Python3.12.14,
  uv0.8.14, Ruff0.11.7, mypy2.3.1; Node22.14.0/npm10.9.2 locked harness.
- Checks dependency image config `sha256:0cffb2ab74d459e763fff436a908c68488f0feb22fb18bd9c8a45e54d4b47ee9`.
  Final source/tests/migrations/schemas/scripts/docs mounted read-only; dependency
  lock `uv.lock` checked. Reproduction rebuilds that target at the tested SHA.
- Host Git/Docker and safe local configuration: ignored `.env` from `.env.example`,
  complete non-production values: run `scripts/bootstrap-worktree.py` with host
  Python3 to prepare `.env`/`.env.worktree` from public defaults. Do not print, attach or commit these files.
- Isolated project `sre-agent-wt-33a1a0365c22`, checks DB only. Safety script refuses
  a shared demo/production database before mutations. Never prune unrelated work.
- **Controlled integration, not live/paid provider:** the HTTP walkthrough uses
  `CreditedControlledProvider`. The canonical adapter scenario uses the actual
  OpenRouter adapter with `httpx.MockTransport`; no external provider request.

## Reproduction commands

Check out the tested source SHA and prepare safe configuration first. The first
command starts only the isolated checks DB. The acceptance fixture migrates and
seeds synthetic principals/aliases. JSON is emitted before disposable containers
are removed; the real HTTP report persists on the host via stdout redirection.

```sh
docker compose --env-file .env --env-file .env.worktree --profile checks up -d python-checks-db
docker compose --env-file .env --env-file .env.worktree --profile checks run --build --no-deps --rm python-checks
docker compose --env-file .env --env-file .env.worktree --profile checks run --build --no-deps --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_issue_454_attribution_acceptance.py && cat /tmp/issue454-attribution-artifact.json'
docker compose --env-file .env --env-file .env.worktree --profile checks run --no-deps --rm -e TESTED_SHA=2a8a3599095bf363ee9c3fa8be4bf89756381813 python-checks python scripts/issue454_demo.py > /tmp/issue454-http-sql.json
docker compose --env-file .env --env-file .env.worktree --profile checks run --no-deps --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_issue_454_attribution_evidence.py::test_canonical_openrouter_evidence_survives_http_persistence_and_read && cat /tmp/issue454-canonical-adapter-artifact.json' > /tmp/issue454-canonical-proof.log
docker compose --env-file .env --env-file .env.worktree --profile checks run --no-deps --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_issue_454_attribution_evidence.py tests/test_issue_454_attribution_guards.py && for artifact in /tmp/issue454-e2e-*.json; do cat "$artifact"; done' > /tmp/issue454-scenario-proof.log
docker compose --env-file .env --env-file .env.worktree --profile checks run --build --no-deps --rm harness sh -c 'npm --prefix schemas/tooling test && npm --prefix schemas/tooling run validate:releases && node schemas/tooling/release.mjs conformance --consumer issue-454 --release 2.8.0'
```

On the tested host only, Docker's default pools were exhausted. The optional local
`/tmp/sre-agent-issue454-network.yaml` had the exact public contents below; select
an actually unused subnet before use. Add `-f compose.yaml -f /tmp/sre-agent-issue454-network.yaml`
to the Docker commands if this workaround applies. It is not a required missing
checkout file. `/tmp` tmpfs avoided the earlier build/storage failure.

```yaml
networks:
  runtime:
    ipam:
      config:
        - subnet: 10.253.144.0/28
services:
  python-checks:
    tmpfs:
      - /tmp:size=128m
```

## CA1–CA11 matrix

Artifacts: [real HTTP/SQL](issue-454/http-sql.json), [canonical adapter](issue-454/canonical-adapter.json),
[roundtrip](issue-454/roundtrip.json); these contain actual safe output, not examples.

| CA | Implementation / scenario | Expected → observed |
| --- | --- | --- |
| 1 | `usage_requests.py`; authorized real request GET | One closed historical item → HTTP200 agrees with persisted snapshot |
| 2 | Closed `navigation` DTO/contract | No admitted incident/run URL → `status: unsupported`, no invented link |
| 3 | Separate immutable exact-assignment snapshot | Preserve logical alias → `triage-agent` before/after and SQL |
| 4 | Adapter-verified credit distinct from requested model | Preserve effective model → canonical `openai/gpt-4o-mini-20260915`, requested `openai/gpt-4o-mini` |
| 5 | Explicit credited-provider evidence | Preserve verified provider or honest absence → `openai`; timeout/no-credit cases unavailable |
| 6 | HTTP PUT assignment then GET same UUID; in-flight gated E2E | Historical record unchanged → identical JSON although current model is `anthropic/claude-3.5-haiku`; next request uses replacement |
| 7 | Shared authoritative selection/reconciliation, server snapshot query | No client-side HMAC resolution/join → only closed server projection; no current-alias reconstruction |
| 8 | Identifier-only snapshot; success/error sentinel checks | No sensitive content → no prompts, outputs, provider bodies, credentials, headers or raw HMAC in reports |
| 9 | Governed authorization before projection | Minimal denied envelope → actual401/403 only `error`, safe `request_id`, `retryable`; no items/counts/attribution |
| 10 | Dedicated bounded `/v1/usage/requests`, one selector | Match approved projection → real route200; missing/multiple selectors422; shared existing accounting |
| 11 | Design-first provenance above | Decision precedes implementation → design commit before preauthored tests and first source commit |

Behavior entry points at the tested SHA: `scripts/issue454_demo.py` (real HTTP/SQL,
CA1–3,6–10); `tests/test_issue_454_attribution_acceptance.py` (persisted roundtrip,
live consumer schema); `tests/test_issue_454_attribution_evidence.py` (canonical
credit, in-flight race, timeout, legacy, month/dedup, unsupported atomic store);
`tests/test_issue_454_attribution_guards.py` (authorization, selectors, immutable
writes, rollback after real audit insert, storage outage). Controlled failures
are injected intentionally; none are presented as external-provider evidence.

## Verification, failures and limits

- Original TDD RED:11 behavioral failures/39passes15.60s after invalid-fixture
  corrections. GREEN50passes/Alembic24.46s; response/usage regression90passes84.31s.
- Current-main predecessor exact source `5f3734277f918231f7fd4bbff38ed8021239a579`:
  Ruff/format258files, locked93packages, five import contracts, configured mypy12files;
  **1784passed,1skipped531.25s**, Alembic no upgrade operations. HTTP/SQL and canonical
  artifact runs passed. This predates the subsequent contract-P1 correction.
- Live OpenRouter smoke skipped: requires `RUN_OPENROUTER_LIVE_SMOKE=1`; no paid call
  or new credentials authorized. Broad unconfigured `mypy src` had an internal
  error; only the repository-configured mypy scope is claimed successful.
- Earlier full-suite failures exposed fixture teardown dependencies, old schema
  heads/version expectations and obsolete audit-failure injection; corrected
  existing tests without removing assertions or weakening runtime boundaries.
- Tooling130/130 and validate-all1.0.0–2.8.0 passed before Codex P1; five contradictory
  partial/unavailable cases then observed RED before tightening only new2.8.
- Existing rollback E2E strengthened at a genuine gap: controlled failure AFTER
  actual audit insert/flush; HTTP503 and neither audit nor snapshot survives.
  Targeted1PASS9.71s, RuffPASS. No new post-code unit test or production workaround.
- Corrected contract: latest focused2/2PASS107.79s and new2.8PASS222artifacts18checks;
  17 request fixtures pass declared validity. All14releases1.0–2.8 passed before
  the final identifier fixture correction; earlier13trees remain byte-identical.
  Full130 tooling run is predecessor-only, not claimed fresh after corrections.
- Consumer/capture E2E gaps preauthored `ef0c43f` before source fix `a23567e`:
  live OpenAPI rejected contradictory states and non-atomic injected stores failed
  closed. Verified RED2fail17.20s, GREEN41pass56.96s with Ruff/Alembic.
- Requested provider/router projection constraints now preserve ModelAlias min1/
  max100; credited-provider rules stay strict. Boundary consumer fixture observed
  RED1fail14.42s before public DTO fix. Actual routing still requires openrouter;
  rejected router100 PUT was a corrected invalid fixture, not accepted invocation.
- Actual denied-audit body now resolves using advertised2.8 error schema; prior
  served2.7 reference was unresolved RED. Affected74checksPASS75.18s/Alembic.
- Closed GET/schema consumer gaps: preauthored `5ae7e37` before fix `2b79302`,
  RED2fail9.48s then GREEN63pass65.91s/Alembic. Nonempty read bodies now audited422;
  live usage errors reference the published2.8 envelope. Proposal rejects five
  contradictory states. Existing E2Es persist safe observations for every scenario.
- UUID P1 from prefix review is inapplicable: integrated route uses JSON-mode
  model validation, JSON-mode dump and JSONResponse; actual request/month reads200.
  Strict DTO boundaries were not relaxed to address a nonexistent Python-mode path.
- Corrected final-SHA receipt and review readback follow. Local evidence is not
  hosted CI or independent human acceptance.

## Security, rollback and review

Sanitized: yes. Synthetic fixtures only; no `.env`, secrets, sensitive headers,
prompts, outputs, confidential data, personal data or raw audit references attached.
Snapshot writes and response-audit writes share one transaction; ADR-005 HMAC fields
are unchanged. UPDATE/DELETE denied; nonempty downgrade refused. Preserve historical
evidence instead of deleting it to force rollback. Earlier releases unchanged.

Screenshots: [actual HTTP/SQL](https://raw.githubusercontent.com/creep1ng/sre-agent/bb323a2d1ab00718ce961e3f702948aae04d9e89/docs/evidence/issue-454/http-sql.png), [canonical adapter](https://raw.githubusercontent.com/creep1ng/sre-agent/bb323a2d1ab00718ce961e3f702948aae04d9e89/docs/evidence/issue-454/canonical-adapter.png), [design](https://raw.githubusercontent.com/creep1ng/sre-agent/bb323a2d1ab00718ce961e3f702948aae04d9e89/docs/evidence/issue-454/design.png), [contract validation](https://raw.githubusercontent.com/creep1ng/sre-agent/bb323a2d1ab00718ce961e3f702948aae04d9e89/docs/evidence/issue-454/contract.png).
Video: Deferred: media storage unavailable; screenshot evidence is mandatory.
Independent human review: **pending**. No merge, closure or acceptance inferred.

## Final receipt and delivery

[Actual check receipt](issue-454/checks.txt): **1785passed,1live-smoke skipped543.46s**,
ShellCheck/Ruff/locked dependencies/import boundaries/configured mypy/AlembicPASS.
Standalone roundtrip1PASS9.43s; canonical adapter1PASS7.46s; actual HTTP/SQL and
published2.8 validationPASS222artifacts18checks. Actual responses conform to2.8.
[Ten scenario observations](https://github.com/creep1ng/sre-agent/tree/ab7ee47918d1b82ce7688c38588bb165fb08863b/docs/evidence/issue-454/scenarios)
and [actual capture](https://raw.githubusercontent.com/creep1ng/sre-agent/ab7ee47918d1b82ce7688c38588bb165fb08863b/docs/evidence/issue-454/scenarios.png)
cover races, timeout, legacy, dedup/month, denied/closed reads, outages and atomic
rollback. Full-suite observations and standalone canonical rerun have independent
request UUIDs; the tested source is identical, not a claimed single invocation.
Source drafts [#569](https://github.com/creep1ng/sre-agent/pull/569)–[#577](https://github.com/creep1ng/sre-agent/pull/577);
all receive Codex review. Contract P1 fixed after RED; UUID P1 refuted by JSON-mode
route and real200 reads; artifact P1 fixed by per-scenario persistence in#577.
Only#570 has the explicitly authorized `size:exception-contract-update`; all other
slices <=400 additions plus deletions. No ready-for-merge label, merge or closure.
Hosted CI is separate: unit/static/configuration/checks-image successes observed;
contracts may still run. A duplicate cancelled workflow produced a failed Quality
gate, and draft pr-governance is expected to fail. These are not local test failures
or human acceptance; see each PR's current checks before integration.
