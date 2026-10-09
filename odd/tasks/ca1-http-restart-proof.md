# CA1 HTTP-created run restart proof

## Objective / problem / why
Close only #330 CA1's combined HTTP-start and real restart evidence gap on the
user-confirmed candidate c7d297cbb11059b1b958e2dece8d54d9db016e1c.

## Authorized scope and constraints
Add a reproducible controlled-integration harness and local evidence. No public
contract changes, external effects/CA6, issue closure, production,
volume deletion or other-project restart. Preserve existing local modifications.
Route: delegated direct; application behavior is already specified.
GitHub Projects live lookup attempted through public URLs but unavailable;
no ambient authenticated remote session is authorized. User's supplied CA1
scenario defines this local proof, not live project status or acceptance.
RDD: off, source global (`gentle-ai review mode status`); disabled/unmanaged.
TDD: no explicit switch found; repository tests-first policy applies. Harness
failure cases are specified before implementation; no production code planned.
Runner: Docker Compose python-checks, pytest; destructive fixtures only on
python-checks-db tmpfs, never demonstration db/postgres_data.

## Acceptance criteria / checks
HTTP-only fresh run creation (201), schema-valid state/events, SQL version and
cursor correlation, real API process restart on unchanged database/volume,
identical durable reads, replay/resume 200 same identity without duplication,
persisted auth refusals 401/403. Preserve unexpected differences as failures.
Record final SHA, diff/hashes, images/versions, commands and genuine capture.

## Tasks
- [x] T1 Implement integrated harness with precondition-only provisioning,
  schema validation, read-only SQL assertions and before/after phases.
- [x] T2 Execute packaged persistent-volume journey; prove API restart and
  unchanged db/volume; collect correlated HTTP/SQL execution records.
- [ ] T3 Run related tests and repository checks on isolated checks database;
  review diff, capture real HTTP output, record hashes and limitations.

## Progress / evidence / next step
Explored HEAD, worktrees, required boundary and current routes/Compose topology.
Docker daemon 29.8.2 accessible with approved sandbox escalation; Compose 5.6.0.
T1/T2 verified. T3 local Python checks, capture and diff review complete;
broad npm release-tooling diagnostic remains pending (do not claim all green).

T1 proof: new Python HTTP/SQL harness and Compose lifecycle runner implemented;
ruff, format and shellcheck passed in checks image; before/after phases observed.
No application or contract changes. Full integrated assertions need ~505 source
lines across two coherent units (HTTP/SQL phases and Compose lifecycle), retaining
readable checks rather than weakening evidence to fit the advisory ODD heuristic.

T2 proof: project ca1-01a118c1-verified, run_084284a4f8a41001,
HTTP201 -> actual api restart PID289577 to307918 -> identical HTTP/SQL reads,
replay200, resume200, auth401/403; one run/event/snapshot/commit, version1 seq:0.
DB identity/PID/StartedAt/mount exactly preserved on named postgres_data volume.
Docker lifecycle cache ancillary evidence skipped (empty); primary restart proof
passed via PID and StartedAt. Failed rehearsals preserved in outputs/ca1 root
and outputs/ca1/final; not application failures. Capture/checks still pending T3.

T3 observed: final-image four suites34 passed; full Python suite1774 passed /1
external smoke skipped (both initial and final Python-harness images). Guard,
shellcheck, ruff lint/format, lock, imports5/5, mypy12 files, alembic and five
Python validators passed. Native HTTP PNG captures inspected; JSON/SQL equality
and packaged/host source hashes independently checked. Preexisting diff hash
unchanged; no production/contract modifications. English report, reproduction
commands, patch and source manifest delivered under workspace outputs/ca1.
T3 remains unchecked solely for the broader npm schema-tooling test still running
in ca1-01a118c1-harness-run-a847b3381c59 (live schema-tooling.log, frozen progress
snapshot supplied); chained validate/validate:releases/lint:openapi not run yet.
Next: collect that result without touching demo DB, then independent local review.

## PR publication follow-up (2026-10-08)
User authorized publication of a new branch and draft PR in creep1ng/sre-agent
against main using the Codex GitHub connection. No merge or issue closure.
Current remote main is b9be06146e85b9e77ef1974263f555fcb1c9080f; application,
Compose, API Dockerfile, uv.lock and schemas have no diff from the tested SHA.
The proof sources remain unchanged. Preserve the original execution artifacts
and distinguish their tested tree from the documentation/publication commit.
Live issue #330 confirms the combined CA1 evidence gap. The GitHub connector
exposes no Projects read tool; live Projects status is not claimed.
The npm container is no longer present and its execution session is unavailable;
no final TAP summary was collected. Status: unresolved, not claimed running or
passed; chained validators remain unverified. The prior log is historical.
Draft remains incomplete: npm diagnostic, human review, and explicit maintainer
size approval (authored additions/deletions exceed 400) before acceptance.
Engram mirror pending: runtime identity unavailable; no memory writes attempted.
- [ ] T4 Publish scoped draft PR and verify branch, files, base/head and attachment.
