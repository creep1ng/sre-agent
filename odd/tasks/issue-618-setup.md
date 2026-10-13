# Issue 618 — Single-command SRE setup

## Objective / why
Prepare the delivered SRE workflows from one clean checkout without worktree recipes
or manual grants; distinguish installation/readiness from functional acceptance.

## Authority / constraints
- User authorized implementation, current gh reads, branches/pushes/draft PRs in
  creep1ng/sre-agent. Latest goal authorizes merge only after all CA verified;
  no premature issue closure or paid LLM calls. Explicit AWS operations and
  necessary pre-verification integration merges are now authorized.
- User requires feature branches and several PRs, each <=400 additions+deletions.
- Direct route: orchestrate existing Compose, seed and domain APIs; no SDD selected.
- GitHub Projects consulted live: midnight.agent #8, issue618 OPEN / Todo.
- Base main: c3cffb790e0015192908ad95d53ce1489b0403c6.
- Strict TDD ON from ~/.gentle-ai/state.json; author behavior checks before source,
  observe RED then GREEN/refactor. Runner: Docker Compose and real HTTP/PostgreSQL.
- RDD off; do not change configuration. Preserve existing runtime/test boundaries.
- Engram mirror pending: runtime supplies no registered session ID; writes forbidden.
- #494 OPEN; producer PRs495–513 unmerged. User explicitly authorized extending
  producer MCP/fail/reset and SSM token transfer to local0600 API-only storage.
  Keep zero public ingress, no IAM creation, no token argv/stdout/evidence.

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

- [ ] S618-6 Extend producer MCP/SSM private connection and owned fail/reset;
  test-first real E2E, then consume its contract from SRE (CA3/6/7).

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

## Goal resume — 2026-10-13
User clarified runtime goal reference628 means618; pursue all CA, then merge.
Historical no-merge notes are superseded only by this conditional authorization.
Metadata Security corrected620/621/622/624; trusted base parser readback0errors
all four. Drafts preserved; no review/acceptance claimed or protections bypassed.
DockerDataRoot/var/lib/docker shares60GB root filesystem,3.0GB free; /tmp tmpfs
not a replacement. No global/foreign cleanup. PyYAML host absent, available in
existing checks image; avoid silent host install.
494 latest513fa30491 guest.py deploys upstream compose+observability only, no
owned MCP overlay/token/connection export; guide509 documents SSM8090 only.
Asked for producer-extension scope, suitable local/authorized target, and ordered
main integration required byCA1. No AWS credentials/session inspected or reused.
Next: continue producer/real verification on scoped answers; keep goal active.
Engram mirror/session summary remains blocked by missing authoritative runtimeID.

User now authorizes necessary OTel Demo AWS operations and integration merges
before final main verification. No paid call, IAM bootstrap or foreign cleanup.
User supplied rapid-meadow scripts/otel_ec2.py; explicit operator guard verified.
Status absent; user approved up: running,2h TTL,scheduled expiry00:21:22UTC.
Live Projects rechecked618 Todo/494 In progress. CI38465270699 all technical
jobs SUCCESS at62439b8a2c; draft governance/human acceptance still pending.
SSM18091->8090 open; ingress empty; cloud-init done, storefront HTTP200.
Real scoped listing lacks grafana-mcp; sanitized report05 records remaining gap.
Real Compose25services/no MCP (including stopped); Grafana200, MCP initialize404.
Owner CLI lacks fail/reset; SRE aws rejected. CA3/7 remain incomplete, not accepted.
Next: resolve producer MCP/lifecycle contract, then validate SRE and integrate main.

User approved producer extension and private SSM token handoff. Test-first E2E
will cover actual transport, API-only secret access, fail/reset signal recovery.
No new IAM/public port; preserve TTL and producer lifecycle. Evidence slice05
separated from prior4, screenshot captured/inspected (UID correction after EACCES).

S618-6 transport failure modes before implementation: absent MCP route; anonymous
caller admitted; private token missing/unsafe; invalid authenticated initialize;
session/header leakage; missing read-only metric/log tools; provider/network errors.
First live E2E must reject anonymous initialize and then verify authenticated MCP
initialize+discovery using private token input. It is transport-only, not signal
recovery or SRE acceptance. Remaining governed query/fail/reset checks follow.
Auto-review rejected a checks-container token read (API-only scope). No command
executed. Removed all token access from external E2E: anonymous denial only;
authenticated probes must use governed API, not a runner-held MCP credential.
Observed real E2E RED: anonymous initialize HTTP404, exit1; token-free runner,
only test-code mount, target existing SSM18091. Report06 records actual output.
Ruff lint/format pass after correcting cache/config-file runner invocation.
Production AWS contract not implemented yet; do not turn this RED into acceptance.
Producer slice14 adds owned remote MCP/flags and loopback-only private token
handoff. Reuses locked MCP image and original app Compose; never edits upstream.
Lint/format pass; live GREEN requires installer/CLI slice next. Consumer E2E RED
remains83-line slice06; source module has no token argv/stdout/log output.
Producer prepare-mcp failed on legacy missing image. Read-only scoped inspection
confirmed cause; ListCommands denied by IAM (not expanded), malformed JSON local
probe corrected. Explicit prepare now pulls locked image, preserves token; live
GREEN anonymous MCP401 via SSM18092, no token access in E2E. Report07 is partial.
User authorized exactly1h extension; owner CLI updates persisted expiry records.
One-hour extension observed: expiry2026-10-14T01:21:22UTC (20:21 Bogotá).
Transport slice16 uses native SSM and private Unix socket; container joins only
prepared internal MCP network, mounts only pipe code/socket, no token/provider/AWS
credentials, no host port. Pinned existing Python image, never implicit pull.
Lint/format pass; full API transport E2E still pending private handoff/client slice.
Live connect-mcp succeeded; local connection.json/token each0600. Relay mounts
only pipe.py and transport socket, joins only internal sre-aws-mcp-boundary,
no host ports, no MCP/provider/AWS env. Token handoff service stopped via owner
SSM; retained token is not read by producer on reconnect. Contract state explicit.
Next: consume contract in SRE; observe valid AWS config RED before source change.
