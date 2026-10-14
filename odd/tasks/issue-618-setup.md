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
SRE consumer RED with valid AWS contract exit1 (after correcting --env-file flag);
GREEN same canonical command: API/web/schema/grants plus real governed MCP200,
restricted403, paid disabled. Eight original preflight negatives remain GREEN.
Raw MCP access not used for authenticated checks. Metrics vector(1)1series and
logs *1document observed, but checkout signals absent. Public legacy demo.env
lacks declared FRONTEND_PROXY_ADDR/K6_TARGET_URL; current producer/main have them.
Next: owner-only legacy env convergence, observe fail/reset through governed API.
Legacy owner's tracked demo.env had only3 values (no frontend/K6 target override).
Current declared6-value file now installed as additional owned env layer; prepare
converges only flagd/checkout/MCP/load-generator/collector, untouched upstream/token.
Owner prepare exit0; wait for real traffic ingestion before accepting signals.
Real AWS journey GREEN: baseline226calls/0errors/16orders/proxy200x16; failure
52calls/12errors/0orders/proxy500x11; recovery26calls/0errors/4orders/proxy200x4.
Owner fail/reset, triage200/declare201/run201/read/events/audit200, restricted403;
repeat preserved domain state/credential digest/audit. No inference paid or claimed.
Full current preserved suite1908passed1live-skip2warnings400.63s; tested integrated
61a031c plus new public E2E script, no production change since live run/suite start.
Real harness verification GREEN: no MCP/provider/AWS env, direct MCP and external
transport unreachable. Current global Ruff GREEN. README/owner/setup guides now
cover private AWS contract, scoped lifetime/stop, no default AWS/paid action;
matrix separates feature verification, local controlled and main/human gates.
Published/attached new drafts626–635: evidence72,RED83,producer324/144/225/163/23,
consumer121,real journey296,guide148 lines. No size exception or main merge.
Main advanced to a6577404 (only public/frontend/browser/evidence relative to c3);
local current-main-candidate merged it, no Python runtime/test/source diff versus
8aabe38; canonical AWS setup rerun GREEN. Docs/journey captures inspected, no keys.
Hosted current-head CI, containerized owner-operation reproduction, independent
human guide reproduction and final clean-main proof remain required before merge.
Live own handles: MCP owner54840, storefront69336; expiry01:21:22UTC/20:21Bogotá.
Goal remains active618 (user correction of628); no paid inference or issue closure.
Engram writes/summary forbidden (no registered runtime identity); local recovery retained.
User accepted guide/evidence634/635; recorded explicitly on both GitHub PRs.
This is not final main/reviewer execution or approval of other producer slices.
Canonical setup observed GREEN inside production API imageec803 on candidate
9d6de74, explicit local bind mounts and no AWS credentials. Earlier same-path
-v mount failed exit2/empty code; --mount succeeded, report11 retains limitation.
Owner fail/reset container reproduction, remaining hosted gates, ordered scoped
integration and final main/human execution still pending. No full CA acceptance.
Scoped question pending: authorize temporary0600 credential material for the
explicit otel-demo session into ONLY owner CLI container, never API/harness/checks,
with deletion after owner reproduction. No export/mount performed while awaiting.
Current634 unit/static/checks/lock GREEN; contracts still IN_PROGRESS at01:06UTC.
Latest635fbe1485 published217 changedlines; refreshed true reproduction metadata.
Report11 Chromium screenshot captured/inspected with public-only mounts.
Earliest current AWS evidence CI38492296238: contracts/Compose GREEN, browser
IN_PROGRESS observed; other current gates remain pending, no merge attempted.
At01:12:59UTC, exact634head3ada494 run38492357802 completedSUCCESS:
contracts, Compose, productionbrowser and Qualitygate allGREEN. 626–633 current
technical Qualitygate alsoGREEN; draft governance stillFAILURE, no bypass.
635currenthead7e6a5d3 is225 changedlines; CI38494023547 PENDING confirmed live.
Previousheadfbe1485 CI38493766006 IN_PROGRESS, not evidence for currenthead.
User credential-owner-container authorization still pending; no export performed.
Expiry01:21:22UTC unchanged. No additional extension or final main acceptance.
Authorized expiry passed; real production-container setup rejects expired
contract exit1 before Docker/AWS actions, report12. Historical imageec803 absent
(exit125, not a setup check); rebuilt owned review API via pinnedDockerfile/lock
exit0, observedimage5fdd8f59. No credential export/new launch/extra extension.
User now explicitly approved new2h scheduled OTel demo inotel-demo/us-east-1
and temporary0600 credential handoff toONLY ownerCLI container; deletion afterward.
No newIAM/publicport/paidLLM. This supersedes waiting, not earlier expired evidence.
Owner-container failure modes before implementation: missing/incompatible AWS
binary/Python; wrong profile/account; absent/private credential; stdout leakage;
unscheduled/budget-refused launch; foreign state reuse; insufficient Docker disk.
Use pinned publicPython/AWSCLI stages, no credentials during build, source-only
mounts for owner, no SRE/API/harness/checks access to temporary AWS credentials.
Owner-only pinnedDocker tool offlineAWSversion2.36.49 verified; credentials0600
exported ONLYnamedotel-demo profile toprivate/tmp holder and mounted ONLYowner.
Owner container status absent, then up exit0/pending, scheduledexpiry03:28:03UTC
(twohours, no extension). Public-onlyscripts/demo mounts; no SRE config/token.
Old owned SSMhandles54840/69336 ended; contractdisconnected retained, no deletion.
Current635head90f8b5a CI38495525684 running: lock/checks/staticGREEN, unit/contracts
inprogress. Superseded headruns nowCANCELLED by workflow; none manually restarted.
Containerized E2E owner-hook failure modes before change: absent/wrong private
owner holder; absent/incompatible public owner image; wrong account/profile;
owner Docker CLI unreachable; accidental AWS credential mount into API runner;
owner operation failure/reset not attempted; signal window/traffic absent.
Observed gap: existing E2E owner hook executes host CLI and cannot use the
approved owner-only credential mount while all demo commands stay containerized.
Add explicit optional owner-container hook; preserve legacy runner behavior and
API-only token metadata. Runner references host holder path but never mounts or
reads its contents; only child owner mounts publicsource + privateAWS holder.
New bootstrap boot-finished probe returnedremote failure (not complete), not a
launch failure. Cloud-init diagnostic observedInProgress/unknown, not reported
ready. Native new storefront connection42305 started; HTTP readiness stillpending.
Public-file Ruff passed; corrected configfilenameconfig.toml toproperpyproject.toml
before applying repo settings. Ownerimagepullnever prevents implicit registrypull.
New storefront18091 HTTP200 observed. Owner-container prepare-mcp exit0, token
private/unexported, signals not accepted. New nativeMCP connection42839 started
with separate stateaws-container/networkvalidation2/CIDR128/28. New SRE project
sre-618-aws-container ports18638/18639/18640, CIDRs144/28 and160/28; old retained.
No AWS credential holder is inside checkout or mounted into productionAPI runner.
First fullycontainerized AWS journey90014 terminalexit1: governed readiness200,
but baselinecalls0/errors0/orders0/proxy0. Realtraffic-window assertion correctly
failed; noownerfail/reset executed or credited. Actualsource5e48ef4. PreserveRED
/tmp/sre618-container-aws-journey.txt; diagnose onlynew owned demo, no fake signals.
Healthdiagnostic initiallylocalimportfailed/noAWScall; correctedpublic/work import.
Newhealthsession51715 saves exactSSMhandle/private diagdir before polling.
Second fullycontainerized journey46097 exit0: baseline108calls/0errors/6orders,
failure68calls/16errors/0orders/proxy500x9, recovery234calls/0errors/15orders/proxy200x14.
Triage/run/read/events/audit +restricted403; repeatstable/auditretained. Ownerfail
andreset actuallyraninseparateownercontainers. Parentinspection: noAWScredmount/env.
Ownerguard13304 exit0 verifiedingress0/scheduledexpiry03:28:03UTC. Temporaryowner
credential/configfiles+holderdeletedverifiedabsent, no contentsread duringcleanup.
Real report13/capture inspected; explicitnativeconnectprereq, no fakeCLIall-container
claim. Guide correctedcold150s baseline andavoidlegacydirect-tokenrecipe; production
source unchangedsince5e48ef4. Current63590f8b5a fulltechnicalCI38495525684 SUCCESS.
Published/attached PR636 head23a69535, base90f8b5a,235changedlines; truecommands
andnativeproducerconnection prerequisite explicit. Asked once forhumanreviewof
remaining618/494stack plus636 before ordered integration; no mainreproduction
inferred. TemporaryAWScredential holder alreadyremoved; nativeSSM42305/42839live.
Resolved baseOID discrepancy: GraphQL495baseRefOidef5 differs baseRef.targeta657;
actualmainref/fetcha657 unchanged. Do not infer mainadvance fromPR snapshotOID.
636governancejob38498396813 failedglobalreconcile on unrelated540metadata; own
636draftstatusFAILURE isexpected. Do not modify540 or weaken workflow/checks.
Maintainer accepted remaining618/494stack and636 explicitly. Orderedintegration
began withnormalmerge/exactheadguards/noadminbypass; 4950fbddb5f,4963c9cc4a0,
503ebcb689f,504966a27d2,50594f3bd8e,50645122283,507b9d7dd60,508ae2ec009,
5097929361b,510d8011c48 verifiedMERGED. Live guardedpipeline68157; checkpoints
/tmp/sre618-merged-stack.jsonl, stops onheadchange/size>400/conflict/unavailablegates.
AllsourcepreparationPRes accepted/greeentechnical markedready, humanreviewrecorded.
New63623a69535 fulltechnicalCI38498396668 SUCCESS; stillnotfinalmainexecution.
CA8audit discovery to verify before sourcechange: --down currentlycalls normal
AWSconnectionvalidation, so expired/disconnected owner may block SRE-only stop.
Failure modes before implementation: expired/disconnected MCP; missing token or
network; foreigncheckoutproject; invalid private config; unintendedvolume removal;
new active SRE/owner altered by stopping oldselectedproject. E2Efirst againstreal
oldexpiredsre-618-aws, protectnewactiveproject/volumes. No AWSoperation/tokenread.
Guardedpipeline68157 stoppedterminal at620CONFLICTING; producer495–513/628–632
alreadymergednormally/headguards/cap, mainc07db658. Noforce/unreviewedheadmerge.
Expired-stopE2E authored BEFOREproductionchange: REDselectedexit1 expiredproducer,
thenGREEN15708 exit0/selectedcontainersabsent/volumes+newprotectedprojectretained.
Start stillrequiresproducer; downusesbaseComposeonly/removeorphansscopedchecked
project, localownership validated, noMCPtoken/network/expiryrequirement orAWScall.
