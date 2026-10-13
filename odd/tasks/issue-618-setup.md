# Issue 618 — Single-command SRE setup

## Objective / why
Prepare the delivered SRE workflows from one clean checkout without worktree recipes
or manual grants; distinguish installation/readiness from functional acceptance.

## Authority / constraints
- User authorized implementation, current gh reads, branches/pushes/draft PRs in
  creep1ng/sre-agent. No merge, closure, AWS operations or paid LLM calls.
- User requires feature branches and several PRs, each <=400 additions+deletions.
- Direct route: orchestrate existing Compose, seed and domain APIs; no SDD selected.
- GitHub Projects consulted live: midnight.agent #8, issue618 OPEN / Todo.
- Base main: c3cffb790e0015192908ad95d53ce1489b0403c6.
- Strict TDD ON from ~/.gentle-ai/state.json; author behavior checks before source,
  observe RED then GREEN/refactor. Runner: Docker Compose and real HTTP/PostgreSQL.
- RDD off; do not change configuration. Preserve existing runtime/test boundaries.
- Engram mirror pending: runtime supplies no registered session ID; writes forbidden.
- #494 OPEN; AWS producer PRs495–513 not integrated. Fail closed in AWS mode;
  no guessed interface, file copying, deployment or IAM/network modification.

## Tasks / acceptance checks
- [x] S618-1 Provision demo operator workflow/triage and investigator direct MCP
  grants with existing domain services; convergence and restricted denial (CA2/4/6).
- [x] S618-2 Add canonical configuration/preflight and single-command orchestration;
  bounded failure/recovery, preserve data/secrets, independent OTel (CA1/2/3/5/6).
- [x] S618-3 Verify real first/second setup and invalid/conflicting/down destination;
  preserve IDs/key hashes/incidents/audit, record sanitized evidence (CA1/2/5/6/8).
- [ ] S618-4 Publish operator guide and verify bounded API journey with deny,
  investigation state/events/audit, plus OTel fail/reset signals (CA7/8).
- [x] S618-5 Publish <=400-line feature-branch PR slices with real screenshots,
  tested/base SHA, reproduction, risks/rollback and CA matrix; request human review.

## Remaining acceptance gates
CA1 final main-integrated clean checkout, CA3 real AWS consuming #494, CA7 independent
human reproduction and explicitly enabled paid/live LLM proof cannot be inferred
from local controlled integration, tests, health, screenshots or hosted CI.

## Progress / evidence
2026-10-13: inspected current main, Compose, README, seed, investigator and domain
provisioner. No local OTel project running; unrelated issue30 containers must remain
untouched. Docker socket requires sandbox escalation. Initial sandbox gh failure
resolved by authorized escalation. No source edits yet.

## Next step
Author real HTTP provisioning acceptance checks before changing grants/bootstrap.

S618-1 verified: test-first module RED missing provisioner; second RED exposed the
existing domain grant admission gap; GREEN real HTTP/PostgreSQL 1 passed9.59s.
Operator triage200/declare201/run201/read200/events200; restricted403; audit200;
repeat preserved IDs/hash/grants/incidents; revoked grant failed without repair.
Evidence docs/evidence/issue-618/01-provision.txt. All calls controlled; no LLM.
Host live OTel prerequisite blocked: free disk3.9GB <15GB; no cleanup authorized.
Docker default pools exhausted; dedicated nonoverlapping10.253.161.0/28 checks.
Next: publish first <=400-line slice, then verify canonical setup/repeat/failure.

S618-2: canonical setup/config implemented, eight isolated black-box invalid inputs
rejected before Docker mutation with sanitized diagnostics. Prepared internal-network
check, real schema/services/governed MCP probes, explicit paid flag(default0), URLs
and scoped data-preserving stop. PR620 permissions347lines; PR621 startup395lines.
E2E exposed corrected discovery query contract and TIME_WAIT false occupancy.
Additional S618-1 lifecycle gap: inactive catalog replay RED1failed12.52s; readback
fix plus current compatibility GREEN73passed44.95s; supplement in slice3.
S618-3 first/repeat, occupied port, controlled MCP outage/restore observed; full
final-candidate repeat/stop completion still pending. No real OTel/AWS/paid calls.
Next: finish repeat artifact, publish verification slice and operator guide/matrix.

S618-3 GREEN: complete controlled CLI E2E passed from host and from pinned Python
Docker runner with local socket/CLI mounts. Current production source unchanged
between those runs; source155fc26. First/repeat preserved keys/IDs/grants/incidents,
audit retained, occupied port and stopped owned MCP fixture rejected, recovery and
scoped stop/restart passed. Log docs/evidence/issue-618/03-repeat.txt; screenshot3.
CA6 actual harness container absent provider/MCP secrets, upstream DNS denied.
S618-4 guide/README and controlled journey complete; live OTel fail/reset blocked
by disk requirement, human reproduction pending. CA matrix acceptance.md accounts
for all eight criteria and separates verified/partial/blocked surfaces.
Hosted CI initialunit930passed1failed exposed own public-schema cleanup removing
USAGE privileges. Existing tests preserved; new fixture now drops only tables and
audit trigger function. Full local suite1848passed1skip2warnings468.59s; no current hosted-green claim.
Next: finish full suite, propagate fixture fix across feature slices, publish3/4.

Final local verification: complete preserved suite1848passed1skip2deprecationwarnings
468.59s; source tree1b63d2129e2e6923f134e22fcf01a7e20c7bc176. Original CI failed
fixture isolation, corrected at first slice51315f6 and reapiled remaining own
branches (lease protected); final candidate contents identical after reapiling.
Exact first slice plus incident persistence13passed9.85s. All PR diffs remain
349/395/396/<400 lines, current bases confirmed. Actual Docker CLI E2E passed;
no production-source byte changed since tested155fc26 (git diff verified).
S618-5 drafts620/621/622/624 published; human review remains required. S618-4 partial:
local real OTel fail/reset blocked by disk, AWS by unintegrated494; no paid enable.
Next: independent human review and remaining live/main acceptance; do not merge/close618.

Post-refactor exact focused rerun13passed1live-skip6.61s. Skip reason: explicit
RUN_OPENROUTER_LIVE_SMOKE=1 required (not authorized/enabled). Removed historical
README curl-secret argv example; manual Compose diagnostics explicitly keep the
canonical project/layers, never an unrelated default project. Source unchanged.

## Session delivery summary
- Goal: implement618 setup and verify all eight CA without false live acceptance.
- Instructions: explicit gh scope; feature slices<=400; strictTDD; no merge/closure,
  AWS sessions/operations, paid calls, global cleanup or weakened existing tests.
- Discoveries: domain lacked triage grant admission; replay hid inactive catalog;
  TIME_WAIT caused false port conflict; own fixture must preserve public privileges.
- Accomplished: canonical startup/config/readiness/stop, domain grants, controlled
  CLI/API/store E2E and recovery, full1848pass1live-skip, guide/matrix/screenshots;
  PR620/621/622/624. Hosted620unitgreen; otherCI pending/governance red observed.
- Next Steps: human review, final integrated-main checkout, adequate realOTel
  host+fail/reset signals, approved494 AWS producer/interface. No618closure.
- Relevant Files: scripts/setup_sre.py,setup_config.py,provision_demo.py;
  tests/test_demo_provision_http.py; scripts/verify_setup_{preflight,repeat}.py;
  docs/setup-sre.md, docs/evidence/issue-618/, README.md, .env.example.
- Engram: all writes/session summary forbidden without registered runtime ID;
  this local recovery record remains authoritative pending the memory mirror.
