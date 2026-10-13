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
- [ ] S618-2 Add canonical configuration/preflight and single-command orchestration;
  bounded failure/recovery, preserve data/secrets, independent OTel (CA1/2/3/5/6).
- [ ] S618-3 Verify real first/second setup and invalid/conflicting/down destination;
  preserve IDs/key hashes/incidents/audit, record sanitized evidence (CA1/2/5/6/8).
- [ ] S618-4 Publish operator guide and verify bounded API journey with deny,
  investigation state/events/audit, plus OTel fail/reset signals (CA7/8).
- [ ] S618-5 Publish <=400-line feature-branch PR slices with real screenshots,
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
