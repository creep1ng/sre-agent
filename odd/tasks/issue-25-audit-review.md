# Issue 25 audit integrated closure

## Objective / problem / why
Deliver the corrected audit UI/API stack on an actual integrated candidate, with
truthful partial results, retained detail errors, behavioral safety/failure tests,
reproducible source-matched HTTP/SQL/browser evidence, governed terminal persistence,
and explicit independent human acceptance before ordinary integration.

## Scope / authorization / constraints
- Repository creep1ng/sre-agent, current gh session: Projects/GitHub reads/fetch,
  code pushes, bounded correction PRs, evidence/verdict comments, GitHub Codex reviews
  and conditional ordinary merges explicitly authorized by the user.
- Each correction PR <=400 additions+deletions. User-approved size exception ONLY
  final atomic integration PR518 (currently5476 lines). No automatic labels,
  force-push, review dismissal, admin bypass or issue closure.
- User accepted earlier exact5188c06/source5ac ONLY conditionally no unresolved
  Codex findings + ALL checks PASS. That receipt is qualified by subsequent findings
  and never transfers to a new head. Ask fresh acceptance after clean current review.
- Live Project8 midnight.agent: issue25 CLOSED/Done, humanclosed2026-10-07T03:24:35Z.
  This is not integration proof. Stable pagination explicitly deferred to470;
  live-provider/killed-DB/offline are not delivered or inferred.
- Preserve immutable contracts, metadata-only projection, authorization/runtime
  boundaries, additive legacy IDs and current main union. Academic freelancer scope.
- English technical artifacts, Spanish concise chat; real sanitized artifacts only.

## Route / testing / delivery gates
Delegated direct source/tests work, mechanical understood fixture/docs changes inline.
AGENTS.md failure-first is mandatory: missing behavior scenarios authored before
source and observed RED/GREEN. No verified strict-TDD toggle; do not invent one.
Runners: pytest/prechecks in Docker python-checks; Playwright in Docker e2e.
RDD off/global: disabled/unmanaged; GitHub Codex separately user-authorized.
Every current candidate needs actual functional proof, exact-head Codex without
remaining findings, ALL hosted checks PASS and fresh independent human acceptance.
Task checkboxes are outcome tracking, not review receipts or merge approval.

## Acceptance criteria
CA1 bounded valid filters/truthful truncation (pagination470 deferred).
CA2 safe actual decision/status/latency/correlation metadata.
CA3 no sensitive content before/after Apply; forbidden fields/parameters reject422.
CA4 no invented consumption. CA5 authorization/outage fail closed, UI clears stale
rows/details and shows error. CA6 actual per-request durable terminal audit; failed
append returns503 rather than claiming success.

## Checklist (stable IDs; historical outcomes retained)
- [x] T1 Read live issue/Project/PR evidence and explore code for P0/P1.
  Verified heads and scope. Read-only worker reviewed backend/auth/projection/UI.
  Potential defects must be reproduced before accepting severity or correction.

- [x] T2 Execute candidate checks, reproduce critical defects, fix confirmed P0/P1.
  Checks: audit HTTP/unit/seeds/UI pytest; browser audit journeys; missing behavioral
  coverage first. Avoid bug regression tests absent genuine behavior gap.

- [x] T3 Record criterion/evidence mapping, candidate identity, sanitization and gaps.
  Include actual HTTP/SQL/browser artifacts where available; do not fabricate
  captures or claim producer/real-provider evidence from mocked fixtures.

- [x] T4 Implement safe same-origin correlation link and request-ID deep link.
  Tests BEFORE source: valid real UUID navigation; authentication remains required;
  malformed/duplicate/untrusted URL values do not drive links or broad queries;
  no credentials/content/external destination in href. Runner: Playwright e2e.

- [x] T5 Verify connected persisted allow/deny navigation, capture sanitized proof.
  Preserve existing review artifacts. Observe current candidate browser/HTTP checks;
  pending full suite/provider/offline/killed-DB/human acceptance remain explicit.

- [x] T6 Publish two <=400-line units with current SHA/container/evidence metadata.
  Evidence-only unit first, navigation child second; preserve complete proof recipes.

- [ ] T7 Request and await GitHub Codex review on exact candidates; inspect findings.

- [ ] T8 Merge only if review/checks/dependencies and ordinary policy permit it.
  Parent PR378/379/385/386 currently OPEN/CHANGES_REQUESTED; no bypass.

- [ ] T9 Reconcile historical CHANGES_REQUESTED against current stack and correct
  still-applicable findings. User explicitly authorized this extension; verify
  contracts, coverage, real captures, Docker recipes and current integration conflicts.
  Do not rewrite an immutable release or bypass independent human acceptance.

- [x] T10 Publish narrowly-scoped AuditEventId contract in a free release namespace.
  2.6.0 plan invalidated: already immutable on live main (PR423). Proposed2.7.0
  and same contract-only size exception explicitly confirmed by user.
  New independent release branch derives freshmain published2.6, not oldstack.
  Authorized full snapshot exception for2.7.0; preserve byte-identical releases<=2.6.0.
  Write contract-behavior tests first: UUID/cor_ accepted, malformed rejected,
  generic Id still restricted; observe RED then generate snapshot/tooling GREEN.
  Runner: harness npm tooling tests, projection/evidence/validate-all/conformance.

- [x] T11 Resolve parent integration conflicts and reverify resulting stack.
  Fresh main677 leaf080:68targeted/4browser/1562full+1skip, prechecks pass.
  New review corrections receive separate exact-candidate checks below.

- [x] T12 Correct PR490 Codex evidence finding: helper must compare HTTP event ID,
  request correlation, status and latency to actual producer/SQL row. Reproduce
  mismatched projection acceptance before source; fix fail-closed and re-capture.

- [x] T13 Preserve additive legacy event-ID runtime lookup compatibility.
  ValidlegacyIDs:401unauth,403nonadmin,404authorizedabsent; invalidbothlanguages422.

- [x] T14 Durably audit all list/detail terminal outcomes and fail closed on append.
  Existing audit.project/read_metadata boundary; no recursive self-reading/content.
  All failure-first HTTP cases authored before implementation, split <=400-line units.

- [x] T15 Render safe request/incident/run/task/trace correlation refs in detail.
  Explicit schema fields/digests/textContent only; no raw identifiers or extra links.

- [x] T16 Pre-author stronger browser/HTTP checks: sensitive absence before/after
  Apply, forbidden parameters with valid filter, authenticated/authorized query
  failure and stale-data clearing, truncation, persistent detail404/503.

- [x] T17 Correct truncation announcement and detail error persistence; verify
  observed browser RED then GREEN on integrated source.

- [x] T18 Recover/reconcile T13/T14 terminal read audit + legacy compatibility;
  actual candidate checks must prove persistence/release gate and contracts2.7.

- [x] T19 Regenerate HTTP/SQL/browser evidence with exact candidate source hashes,
  helper-produced sql.correlation, no mixed parent/child candidate claims.

- [x] T20 Validate integrated candidate, map CA/gaps and publish explicit technical
  acceptance only if supported. Independent human acceptance remains pending.

- [x] T21 Replace terminal-reference tautologies with observed expected metadata;
  prove missing identity/resource cannot pass (PR498 comment4206776809).

- [x] T22 Clear retained detail error only after a later successful detail fetch;
  preauthor browser journey, observe RED/GREEN (PR499 comment4206790465).

- [x] T23 Exercise populated controlled correlation refs and restrict mutation
  probe catches to exact row-count failures; reject wrong status/malformed rows
  (PR500 comment4206804260; PR501 comment4206792111).

- [x] T24 Guarantee bounded query-fault restoration on capture failure/timeout;
  verify existing host UID command rather than blindly changing it (PR502).

- [ ] T25 Reverify actual corrected joint candidate, refresh sanitized artifacts,
  request exact-head Codex review, reconcile human review and integration gates.

- [x] T26 Require caller-specific list/detail envelopes before terminal mutation
  classification (PR516 comment4207605002, P1). Preauthor wrong detail/list and
  mutation-detail-envelope behavior cases, observe RED/GREEN in Docker pytest,
  regenerate actual terminal SQL artifacts, publish bounded correction.

- [x] T27 Align runtime audit-route OpenAPI metadata with published2.7 (PR518
  comment4207658104): filters/path/auth, response/error and governed metadata;
  preserve custom runtime validation/terminal recording, no automatic FastAPI
  validation bypassing the governed service. Failure-first OpenAPI behavior checks.

- [x] T28 Enforce released canonical UUID or additive legacy-ID language (PR518
  comment4207658116), with preauthored HTTP422/terminal persistence proof for
  digit-leading compact/braced/URN forms; preserve actual valid legacy forms.

- [x] T29 Adapt existing governed-operation expected inventory to the two audit
  routes' actual admin.read/administrative_control/audit scope, preserve assertions;
  no new unit scenarios after source. Separate <=400 fixture-only correction,
  then rerun exact joint full suite; no blanket fullGREEN claim yet.

- [x] T30 Preassert parameter uniqueness in existing parity scenario, observeRED,
  fix via native documentation-only Path schema (no servicevalidation bypass),
  verify same canonical schema plus HTTPterminal behavior, publish separatebounded
  unit because PR520already400. Localtechnicalacceptance791/6ed provisional again.

- [x] T31 Correct PR520 P1 comment4208495712: parity environment override masks
  defaultcontract2.6 vs emitted2.7metadata. Removeoverride and assertdefaultactive
  matchespublished2.7 beforefix; activatepublished2.7default, adaptexistingrelease
  expectations/example configuration, preserveimmutableversions/overridecompatibility.
  FailurefirstDockerpytest; boundedfollowup, freshcandidate verification.

- [x] T32 Correct PR522 P2 comment4208493370: evidencecarrier lacks mainunion.
  DeterministichostGitsetup must explicitly check out immutabletestedjointSHA
  beforeDockerbuild (isolatedworktree), sourcehashverified; do notclaimcarrier's
  ownhead executed. Refreshactualfinaljointproof then exactheadreview/CI/human.

- [x] T33 Investigate PR518 P2 comment4208468108: released2.7 metadata operation
  enum excludes existing persisted mounted operations. Preserveimmutable snapshots
  and all visible events; choose honest runtime-local representation or approved
  newrelease after scoped read-only exploration. No implementationacceptanceyet.

- [x] T34 Adapt only existing usage publication expectations to active published
  2.7; preserve selector/security/status/closedschema/inventorychecks. Mechanical
  onefilefixturecorrection after observedfullRED, no newpost-codeunit scenarios.
  Verifyexistingmodule then actualjointfullsuite. Runtime/helpers/UIbytesunchanged
  frome0 source; deployedcapturebuildrevisionmusttruthfullyremain e0 unlessrebuilt.

- [x] T35 Reject noncanonical request UUID filter spellings before UUID conversion
  (518comment4209292491): preauthor compact/braced/URN authorized422 +onevalidation
  terminal, preservecanonicalforms andauth/grantordering; observeREDthenGREEN.

- [x] T36 Expose audit UI in existing control-plane navigation (518comment4209292475):
  narrowread-onlynavexploration, browserjourneytestbeforeHTML/sourceedit, observed
  missinglinkREDthen actualnavigationGREEN; real repeatablescreenshot, safeURLs.

- [x] T37 Normalize accepted canonical UUID event IDs before case-sensitive
  VARCHAR lookup (4209709009). Preauthor realpersisted uppercaseUUID detail200
  +terminalmetadata; preserve legacyIDcase/authorizationorder; REDthenGREEN.

- [x] T38 Reject forbidden content-retrieval parameters on detail reads
  (4209709019). Preauthor known-ID+raw/redacted-content422 withonevalidation
  terminal, no sensitivepayload; retainauth/grantorder; REDthenGREEN beforefix.

- [x] T39 Investigate hosted static-web FAILURE job112911847073/run37656076374
  on8c; readactualfailurelogs, reproducebeforeboundedfix. No guess/retrybypass.

- [x] T40 Enforce published RFC3339 syntax for from/to before broad Python ISO
  parsing. Preauthor actual authorized HTTP422+exactonevalidationterminal for
  basic/week/date-only/missing-zone forms alongside validdecisionfilter; preserve
  validextendedUTC/offset/fraction forms and auth/grantordering. ObserveREDbefore
  boundedsourcefix; exactDockerGREEN, currentunion/provenance/reviewCIhumanagain.

- [x] T41 Reject nonempty GET bodies on governed audit list/detail, including
  validfilter+raw/redacted-content JSON orarbitrarynonemptybody. Preauthoractual
  HTTP422/exactonevalidationterminal/contentabsence beforeimplementation; preserve
  auth401/grant403ordering andvalidbodylessreads. Do notparse/logbodycontents,
  bypassgovernedterminalfinish, editimmutablecontracts orintroduceDTOexceptions.
  Smallboundedsource/testsunit, freshjointproof/reviewALLCIhumanacceptanceagain.

## Current candidate / verified proof / pending work
- Remote final518 remains669d1a3337e6055fa633e654c48dfe34bfc47f91/base
  9d6ed3da8f22132561635de9a429989d21773724, historical tested/deployed731.
  New current tested/deployed joint source a9841a2e7101bcc125874a6a3e167174b996230d;
  unpublished carrier88604b8 source/test/public/scripts/config identical (gitdiff0).
- Independent API/host/helper runtime-source SHA256
  75afe467ad1de907877ef705fe2cfd1a2d7d3eab7123928fecd201936ba0f59d;
  UIjs0ccffe45 unchanged. Actual native OpenAPI complete list/detail validate
  runtime-local34-operation schema and unique path; contract2.7 preserved.
- Current fullDocker1664passed/1opt-inliveproviderSkip448.74s exit0,
  prechecks/AlembicPASS; rebuilt auditbrowser14/17.6s, originalloopbackstatic
  76passed60skip2.1m. Freshterminal13/7.46s+11actualJSONL;
  sequential runningdetail5/time12/body14 each exactly1safe SQLterminal.
- Actual connectedallowdeny200403200/3populatedHMACrefs; fault200->503 clears
  previous1row/1detail to0/0 with visibleerror, boundedfinally restoredt|t.
  Navigation1/4.9s, mockrecovery1/5.1s. All9currentPNGs manuallyinspected;
  15textartifact privatevalue/syntheticmarker scansPASS without secretoutput.
- T41 scopedfailurefirst RED18failed62passed31.47s BEFOREcode ->80GREEN30.37s,
  Ruff/formatPASS. Body boolean stream drain neverbuffers/parses/logscontents;
  list/detail governed422validation afterauth/grants has no subjects/content.
  Bodyless200 andbodyanonymous401/restricted403 preserved. Bounded0716ef0
  over55498lines(95add3del), unpublished; proof branch edc93 awaiting artifacts.
- Latestremote669 exactCodex5446708398/18:36:51Z NEWP2comment4210579828
  GETbodyignored200 is nowlocallyfixed but no current publishedreview yet.
  Historical731technicalacceptance andhuman8c/source5ac receipt QUALIFIED.
- Old669hostedstaticFAILED10m15/QualitygateFAILED/compose+productionbrowserSKIP;
  actualjob112951192298 Chromium aptmirror dependencyinstall stalled beforetests.
  Unit/contracts/config/security/etcPASS; not ALLPASS. No CIweakening/retrybypass.
- Next: refresh currentreport/exactDockerbodyprobe, publish boundedsource/proof
  <=400 each and final-onlyexception aggregate, attachPRs; exactheadCodex without
  findings/ALLCI/freshhuman receipt before ordinary SHApinned conditionalmerge.

## Publication / significant historical rationale
- Original378→379→385→386→490→491 and497–502/514–517 preserved in final ancestry;
  originalparents stillopen/oldfindings do not authorize individual unsafe merges.
-493contract2.7 independentrelease was humanaccepted c76476c then ordinarymerged
  ef5ba500; occupied2.6proposal492 closed, immutable2.6 preserved. Receipt notruntime.
-519caller-envelope125→520runtimecontract400→521inventory10→542nativepath27→
  543defaultcontract12→544runtimeprojection251. Runtime-local schema instead of
  dishonestly reusing frozen2.7operation-enumURN; no eventhiding/newimmutable edits.
-522currentevidence344;547requestUUID41→548navigation52→549proof190;
  551detail82→552sidebar5 siblings,553proof302;554time86,555proof240. AllnewPR
  attachments confirmed; final-onlyexception, no sourceunit exceeds400.
- Exact8c review5445675670 found uppercaseUUIDdetail404 anddetailcontentqueryignored;
  correctedT37/T38. Hostedstaticoldsidebar expectationRED then5linefixturecorrected.
  Exact1be review5446408317 found RFC3339 lexicalgap; correctedT40. Historical
  1be hostedALLPASS does not erase its Codex finding or authorize later merge.
- Prior ee827/sourcea592 humanreceipt6039287589 and8c/source5ac receipt6042778973
  remain historical/qualified. Local technical reports do not replace human receipt.

## Evidence limitations / failure disclosures
- Independent hashes rejected temporary old8f helper image; regenerated actualproof,
  no manually repaired JSON. Earlier interruptedbuilds/fullchecks exit130 notpasses.
- Typed terminalmutationprobes require caller-specific HTTP envelopes before1→0/1→2
  SQL classification; wrong-route envelopes/malformedrows are not accepted mutations.
- Validationstage terminal has no subjects perreleasedDTO663+, even when authorization
  precedes query/bodyvalidation. No newDTOexception/relabeling toattachsubjects.
- Initial currentdetailSQLdelta overlappedconnectedbrowserreadwriters and failed
  exactoneassertion; temporarypartialcapture rejected, all5+12rerunsequentially.
- FullstaticNGINX71/60skip/3fail andnonloopbackHTTP73/60skip/1fail notCIequivalent:
  CSP/insecureorigin differences. Use originalplaywright.config.js loopback via
  sharedDocker namespace andreadonlyrootindex/palette/public/styles/showcase mounts;
  do not weakenCSP/crypto/tests. Scopedservercleanup observed.
- Earlier full1606/1609 failures were existinggoverned-inventory/usage2.6 pins; only
  expected inventories/version adapted after observedfailures, thenactualfullGREEN.
- Permission/cache/formatter/screenshot/scan failures disclosed; hostUID/cache/tmp
  corrections did not weaken permissions or turn failedruns into successfulproof.

## Recovery / relevant files
- odd/tasks/issue-25-audit-review.md and full Engrammirror9488/topic
  odd/issue-25-audit-review/tasks remain the ONE feature document. Read both onresume.
- Historical full ledger preserved immutably at669d1a3337e6055fa633e654c48dfe34bfc47f91:
  odd/tasks/issue-25-audit-review.md; condensed here for recoverable current intent,
  not to hide authoredlines or alter acceptance. Gitparentfinalexception unchanged.
- docs/evidence/issue-25-closure-verification.md: sourceidentity/criteria/results/
  Dockerreproducers/technicalverdict; actual issue-25-* JSON/JSONL/OpenAPI/PNGs.
- src/sre_agent/gateway/audit_reads.py: governedreadservice/routes/metadataOpenAPI.
- tests/test_audit_reads_http.py, tests/test_audit_reads_openapi.py,
  tests/test_audit_read_terminal_boundary.py: actualHTTP/SQL/schema/mutation proof.
- tests/browser/audit-events.spec.js: behavioralUI/nav/content/error journeys.
- scripts/verify_issue25_audit.py, capture_issue25_audit_terminal.py,
  capture_issue25_audit.mjs, capture_issue25_correlation.mjs,
  capture_issue25_query_failure.mjs, control_issue25_query_fault.py: actual helpers.
- .env.worktree ignoredmode600 synthetic/private; NEVERprint/source/commit/upload.
  Current declaredbuilda984; safeComposeprojectaudit25-closure/subnet10.253.139.0/28,
  nohostports. Separate disposablechecksDB; no activefault/fullchecks writer now.
