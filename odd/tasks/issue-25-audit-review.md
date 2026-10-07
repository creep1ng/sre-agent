# Issue 25 audit stack review

## Objective / problem / why
Review PR378 -> PR379 -> PR385 -> PR386 against live issue25, correct only verified
P0/P1 defects, and provide repeatable evidence. The user corrected the original
issue330 target to25. User additionally authorized safe correlation navigation with E2E proof.
Publication and conditional merge now authorized using current gh session; no
issue closure, protection bypass or pagination redesign. User authorized restoring
the unexpectedly reverted UI and repeating checks before publication.

## Scope / constraints
Candidate: 0af22e97d815a1c511b1a24eec14f70d3611be75; parent gateway
74feaa20f39f53447fcb25b7bf6d3b5d58a2af8c. Live Project midnight.agent: Todo.
CA1 filtered/bounded results; stable pagination explicitly deferred to470.
CA2 permitted metadata decision/status/latency/routing; CA3 required filters and
no content; CA4 no invented consumption; CA5 authorization/outage fail closed;
CA6 no invented persisted events. Real producer/browser evidence and human review
are distinct from test counts. Delivery units <=400 additions+deletions each: review evidence and correlation
navigation are separate cohesive units; never submit the combined diff as one PR.

Route: delegated direct exploration, bounded corrections after observed failures.
Testing: failure-first required by AGENTS.md; no verified explicit strict-TDD toggle
for this candidate, so no retroactive strict-TDD claim. Runners: pytest inside
python-checks; Playwright inside e2e. Preserve existing tests. Write missing
behavior scenarios before source edits; observe failure then pass.
RDD: off, deciding source global; ordinary repository policy, disabled/unmanaged.

## Tasks / acceptance / checks
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

- [x] T13 Preserve additive legacy event-ID runtime lookup compatibility.
  ValidlegacyIDs:401unauth,403nonadmin,404authorizedabsent; invalidbothlanguages422.
- [x] T14 Durably audit all list/detail terminal outcomes and fail closed on append.
  Existing audit.project/read_metadata boundary; no recursive self-reading/content.
  All failure-first HTTP cases authored before implementation, split <=400-line units.
- [x] T15 Render safe request/incident/run/task/trace correlation refs in detail.
  Explicit schema fields/digests/textContent only; no raw identifiers or extra links.

- [x] T12 Correct PR490 Codex evidence finding: helper must compare HTTP event ID,
  request correlation, status and latency to actual producer/SQL row. Reproduce
  mismatched projection acceptance before source; fix fail-closed and re-capture.

## Progress / next step
Baseline T1-T3: 24 pytest passed (15.04s), 4 browser journeys passed (4.8s;
three mocks, one connected). No P0/P1 confirmed or baseline production edits. Capture helpers verify
six producer cases with actual HTTP/SQL, including audit-store503/no persisted row;
connected Chromium detail PNG inspected, two P2 gaps reproduced with declared mocks.
Ruff passes. Full suite/live provider/offline/killed-DB/human acceptance NOT run.
Report: docs/evidence/issue-25-audit-review.md; #25 acceptance remains partial.
T4 observed RED3failed4passed, then final GREEN8passed8.6s. UUID boundary
gap found and corrected before final GREEN; source blob619ced26be1d901ba74cf3847a69905c887243df.
T5 real allow/deny navigation proof inspected; both sequences200/403/200,
nonadmin0rows, matchingproducer/SQLIDs. Final24pytestpassed16.45s; nodechecks
and identity/secret scans pass. Report: docs/evidence/issue-25-correlation-link.md.
Next: fresh restored-candidate verification, historical-review reconciliation, publication and conditional integration.
Full suite/provider/offline/killed-DB not run. Scoped containers stopped; volume retained.
Mirror: task file and full Engram recovery copy read back after each update.

T4/T5 reverified after authorized restore: blob619ced26 unchanged, browser8passed
10.3s, Python24passed20.20s; actual connected allow/deny recaptured at
2026-10-07T00:49:09.170Z, both200/403/200; screenshot inspected.
T9: historical UUID/status/latency/routing assertions and Docker recipe findings
are fixed. Current GitHub PR378 DIRTY/CONFLICTING against main4a4515b;
PR386 CLEAN/MERGEABLE against current385. Remaining OpenAPI event-ID mismatch
is in immutable2.3.0; user confirmed new2.6.0, preserving prior releases.
New release needs self-contained snapshot:199files/~7460addedlines. No overlay
supported; splitting incomplete snapshots breaks validate-all. Requires explicit
maintainer size exception: user explicitly approved for2.6.0 only.
Verified label size:exception-contract-update; apply only on contract-release PR.
PR490 published365additions at6cb4c7f after Codex crosscheckP2; four mismatch
probes accepted before source, rejected after; fresh6caseHTTP/SQL+connectedcapture
and Ruff pass. Initial exactarchive4browserpassed6.7s/24Pythonpassed13.75s.
PR491 published245additions, originald4c4a14 Codex no major issues; now0295805
incorporates parent fix and new exact review requested. Original exactarchive
8browserpassed10.1s plus connectedallow/deny200/403/200; current proof replay passed;5dc63d8 refreshed artifacts match parent SQL/requestIDs,
latest Codex no major issues.
T10 delegated contract2.6writer; T11 isolated parentmerge candidate delegated.
Currentmainfe6fca0 conflicts exactly migrations/env.py and tests/test_demo_seeds.py;
retain main union migration guard and version20260928_14, featureseedcount+1.
Codex exactlatestreviews, finalCI, contractpublication/integration/merge pending.

T10 collision: PR49280daa94 published then converted draft, MUST NOT MERGE.
Live mainfe6 contains immutable2.6 treea7148a introduceded99ca5(PR423),
including grants.create404; oldstack lacked2.6. Root proposed occupied namespace
without live version check. Future2.7 must derive live main2.6 and preserve404.
CodexP1: format-only UUID branch is annotation underdefaultJSONSchema; add
canonicalUUIDpattern and format-assertion-disabled behavioral case BEFORE fix.
Targeted10 and independent3 pass on incorrectnamespace80; not releaseacceptance.
Original fullsuite interrupted52passed; telemetry-off interrupted51passed.
T11 local378integratione4a2c68 passed56targeted/1548full1skip pluslint/typing/
Alembic,395diffvsfe6. Descendantrestackverification worker ongoing; no remote
parentpush, no reviewdismissal or merge.

User confirmed2.7.0 and transferdedicatedsizeexception. Live main advanced
todcda493; refresh integration descendants against currentmain beforepublication.
Old-fe6restackleafbf518db passed68targeted/4browser/1560full1skip; freshbase
validation pending. PR492 remainsdraft occupiednamespace; replacement2.7 independent
of audit runtime chain avoids acceptance dependency cycle.

T10 publication: user explicitly confirmed2.7 and transferred release-only exception.
PR493 efb153c629a09172f4e0c9052dfa3b1496663d0a, independent main base677fb76,
7657add/8delete208files, size:exception-contract-update applied. Invalid492 closed
as superseded; label removed there. Published2.6/grant404 and prior releases untouched.
Old proposed format-only UUID oneOf RED with formats disabled; canonical structural
UUID pattern produces disjoint alternatives. Preauthored focused2 tests pass formats
ON/OFF; third full-release test retained/pending. One wrong generic-Id cor_ rejection
assertion repaired to preserve actual existing acceptance, no new behavior coverage.
Generation3projectionfixtures/204artifacts17checks passes; actual focusedTAPlog
rendered into ChromiumPNG, manually inspected. Full tooling and validate-all running,
no complete pass claimed. Exact-head GitHub Codex requested, hostedCI pending.
T11 fresh677 leaf080bef8 targeted68passed44.84s/browser4passed7.7s; fullsuitepending.
Fresh realHTTP/SQL and connectedPNG captured and inspected at /tmp/audit25-leaf-evidence.
Next: await493review/checks; publish refreshedoriginalstack and490/491 evidence as set.

Current exact-head Codex blockers observed (not just Completed summaries):
493efb P1 narrows legacy2.6genericIds despiteadditive manifest, plus P2 compares
undefinedgrant404.description.493returnedDRAFT; fullrunsstoppedpartial34passed,
validate-allnoresult. Newfailurefirstcases authorizepreservingoldIdlanguage in
UUID/legacy disjointunion, legacybranchmustexcludeUUID(letterUUIDmatchesoldId).
Separate smallruntimeunit authorized: genericcontractIds followgovernedlookup404,
401unauth/403nonadmin, genuinelyinvalidsyntax422; existingauthorderunchanged.
386080P1 change-detector source scanning -> behaviorDOM/storage/requests writerfix.
379P2 missingvalidfilter/truequeryfault proof;386P2 hidden404 andforbiddenkeys remain
disclosed, no blanketallgoodclaim. Originalstackfastforwardpublished3ec/c654/61c/080.
T13 [pending]: additivelegacyruntimecompatibility smallchildunit, source+HTTP tests
failure-first, exactDockerchecks andartifact. Nevergrow395line378over400.
Next: schema/runtime/browsercorrections, freshcandidateproof, Codexagain/humanreview.

Current493 c76476c91bb98a9ad2556d100dc81f277d256745 publishesdisjointUUID/legacy
union, preservesall2.6validinstances, grant404deepequality, generation204/17.
Focused2GREEN formatsON/OFF, realTAPPNGrefreshedandinspected; finalreleasevalidator
333.5spasses inpartialfullsuite52+passes, wholetooling/validate-allpending.
Codexexactc764comment6030072145 no majorissues, oldinlineP1/P2notnewfindings.
386browserP1source-scan replacedbehaviorDOM/storage/requests andforbiddenquerykeys,
878c6cfpublished,4Playwrightpassed5.2s; reviewedagain.
378newP1confirmed: readsreturnwithoutterminal audit; independentlegacy/runtimewriter
authorizedsharedPostgresAuditStore+projectorfinish across200/401/403/404/422/503,
appendfault503, requestmetadataonly. All5failure-firstHTTPtestsRED14.05s, source
implementationongoing. Original378395lineunitnotinflated; newruntime/testPRsplit.
385correlationP1fixedin491child byschemaactualHMACincident_ref/run_ref/task_ref/trace_ref
rendering, notrawIDs; source/behaviorproofwriterongoing. Humanacceptancepending.

T10 completed: user accepted PR493 evidence for exact c76476c only, conditional
on checks. All hosted gates passed, tooling128/128 and all13 releases validated;
Codex found no new major issues. SHA-pinned ordinary merge produced
ef5ba500e673160aa73d92fffc61ee452c284bc6. Release2.6 byte-identical.
This human acceptance does NOT cover runtime or the remaining stack.

Current root343402 runtime candidate: boundary tests copied before source changes;
Docker60passed4failed131.67s. Existing HTTP expectations need adaptation to actual
new audit-read rows, valid generic legacy IDs, and shared audit-store constructor.
No root GREEN claimed. Actual Python is3.12.14. Writer failure-first5RED, isolated57
GREEN; exact root rerun pending. Genuine SQL evidence probe now269 lines, asserts
per-request row deltas and rejects zero/double append. Three cohesive <=400-line
units planned: runtime + existing fixture adaptation; preauthored boundary tests;
repeatable SQL capture helper. No contract-only exception on these units.

Restack worker final refs3868f177/26dba5a6/4b1e4f3b (not published yet) repair
existing browser auth mock setup only. ObservedRED7/1, GREENfocused1/1 and rebuilt
Playwright8/8; Python68/68 over source candidate074ed862. Full1562+1 remains
on080bef8, not attributed to current source. Human acceptance for these pending.

## Authorized closure-gap continuation (2026-10-07)
This section overrides earlier remote/merge permissions for this continuation.
User authorizes the five specified closure gaps, current gh session reads/fetch,
and publishing technical verdict/evidence on creep1ng/sre-agent. NO merge or issue
closure authorized. Technical acceptance is not independent human acceptance.
Live Projects #8 midnight.agent reports Done; issue25 is open with unchecked CA.
Live leaf491:343402e83b8147de335fba4b5890f1cbf54a8f16 on main ef5ba500.
Local working branch codex/issue-25-closure-verification. Other dirty worktrees
are read-only recovery sources, not verified candidates. Pagination remains470.
Route: delegated direct. Failure-first policy source AGENTS.md; no explicit strict
TDD toggle verified. Runners: Docker python-checks pytest and e2e Playwright.
RDD off/global: disabled/unmanaged; ordinary human evidence gate remains.

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

Checks/progress: live issue/Project/stack/comment read; initial sandbox GitHub
connection failed, authorized network rerun succeeded. No source edit yet.
Next: integrated final-candidate verification. Initial task mirror read back (observation9488).

User additionally authorizes push and followup PRs <=400 additions+deletions per
unit, using current gh session; no merge or closure. UI failure-first RED3/11,
first GREEN10/11 exposed bad503fixture (now contractual envelope); finalrerun
pending. Runtime first targeted29/29 passes; finalcandidate rerun pending.
Helper source probe confirmed missing sql.correlation; host execution blocked by
missingpsycopg, NOT a claimed runtimeRED. Docker integrated evidence pending.

T16/T17/T18 observed on sourcee1847a6: parent independent Playwright11/11
31.3s; terminal fixture5/5 +actualSQL11records (read200/401/403/404/422/503
each1row, appendfault503zero, no-op/doubleappend probe rejected). Helper actual
producerstatuses200/403/401/422/503 all1row, appendfault503zero; SQLcorrelation
now emitted and checked, sourcehash13a2b1fb matches host/Dockerexactsource.
Full parent Python/prechecks progressing; query-fault connectedcapturepending.

T19 complete: regenerated HTTP/SQL +allow/denyconnected+mock404/503/truncation
+realqueryfault200→503 screenshots/JSON; UIhash12497e0a matches actualsource.
Queryfaultremoved/tableverifiedrestored; scopedDockerdownexit0, volume retained.
ParentfullPython1567passed1liveproviderskipped691.34s andprechecks pass.
T20 localtechnicalacceptance recorded, publicationpending; nohumanacceptance.

T20 published: sixopenPRs497→498→499→500→501→502 (sizes225/310/134/228/269/376).
Explicittechnicalacceptance: issue25comment6037782058, PR378comment6037782499.
Initialpr-governancefailed: strictDeliveryroute/Security values includedexplanation;
body-onlyrepair preserved explanation elsewhere,497governanceSUCCESSobserved.
Hostedcontracts/otherchecksstillpending; independenthumanacceptance/integration
remainnextsteps. Nooriginalstackrewrites, merge, thread dismissal orissueclosure.

## Fresh review continuation
Live #25 was already closed by creep1ng at 2026-10-07T03:24:35Z; Project Done
is not proof of integrated delivery. Earlier open-state statements were inaccurate.
The active goal authorizes Projects, GitHub Codex reviews and conditional merges;
ordinary human evidence/review and size gates still apply. No bypass authorized.
Prior source e1847 acceptance is provisional pending the new exact-head findings.
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
T19/T20 evidence remains historical, not acceptance of the forthcoming candidate.
Next: failure-first bounded corrections; separate <=400-line follow-up PR units.

T22 observed focusedPlaywright RED stale visiblebanner, GREEN1passed2.7s and
retention/successpair2passed8.7s. UI34addedlines; fulljointbrowsercheck pending.

T22 parent independent fullPlaywright12passed15.1s on correctedservedUI.
T24 Docker-only orchestration EXIT/signal cleanup verified after injected failure
(exit1) and boundedtimeout(exit124): both restoredtable/faultremoved SQL t/t.
Existing marker-writing commands already had hostUID; no speculative UID fix.

User explicitly approved an exception ONLY for final atomic integration to main,
not correctionPRunits (>400 still forbidden there). Fresh review/evidence required
before merge; no protection bypass or independenthumanacceptance inferred.

T24 reopened: host-shell cleanup proof passed, but contributor recipe must start
containers on every command. Replace orchestration with a bounded controller inside
existing python-checks image (no Docker socket); preserve the tested cleanup intent.

T21/T23 parent9pytestpassed8.80s + actualterminal11JSONrecords; typedprobes
acceptonly1→0/1→2 countfault afterHTTP/rowvalidation. Expectedseededidentity/
resourceHMAC verified on403/404/503. Worker nonnullcorrelation RED/GREEN verified
three independentlyexpectedrefs inSQL/HTTP; freshversionedcapture stillpending.
Parentfirstformatcheckfailedhelper; formattedinDocker, lint/format andrerunpass.
Success200doesnotexposereadrequestID: validatevalidenvelope andcorrelateactualSQL.

T25 live integration base advanced to a3541a96d83364a126ceff418ed3cbf7dbdc2d82
(human incident commands API). After bounded sourceunits, merge currentmain only
on finalintegration branch; preserve both API and audit router/tests. Rebuild and
revalidate exactunion; previous sourcehash/testcounts are historical, not unionproof.

T24 finalcontainercontroller observed oldunprotectedRED (tablemissing/faultpresent),
readonly-markerfailure +done-timeout +browser-failedmarker allnonzeroandrestored;
realconnectedbrowser success503/0stalerows/0details andverifiedrestoration.
ControllerarmscleanupbeforeDDL, validatesrestricteddb, noDockersocket/newservice.
Docker-only recipe updated; finalRuffpassed. Parentfreshunioncapture stillpending.

T25 exactsourcea59256c73413e249f763c29f87404abdc1c0f07d includes maina354.
Unpublishedlintrepair restack heads:5e84484/c22edda/5f38d1b/93df181; no remoterewrite.
Parentfreshbrowser12passed39.7s; HTTPhelpermanifest/API/hostmatcha8c0d106,
servedUI0ccffe45 matches fourbrowserJSONs. Actualallow has3nonnullHMACrefs.
Freshconnectedfault200→503/1priorrow+detail→0/0/error, rawpreconditionarchived,
SQLrestorationt|t. Sanitizedtextscanspassed; full1591collectedsuite stillrunning.

T25 parentexactsourcea592 fullDocker1590passed1liveOpenRouterSkipped461.53s;
Ruff/format/lock/importboundaries/mypy/Alembiccheck allpassed. Fresh terminal
SQL capture nowregenerating afterfullsuite; no otherchecksDB writers.

T25 freshterminal9passed8.34s +11actualJSONLrecords; appendfault0rows; typed
probes0/2 rejected; all7normalreadterminals1row. Parentinspectedall7PNGs and
textsecret/private-marker scanspassed. Exacta592 localtechnicalacceptance renewed;
GitHubexactheadreview, hostedCI andindependenthumanfreshness acceptance pending.

## Caller-envelope review continuation
Published correction units PR514-517 and atomic integration PR518 head
 ee82793e834f28f95cf9b8a2cec79b6bc95665da over maina354. User accepted this
exact candidate/sourcea592 conditionally: no unresolved Codex findings and all
checks pass (PR518 comment6039287589). No merge performed.
- [x] T26 Require caller-specific list/detail envelopes before terminal mutation
  classification (PR516 comment4207605002, P1). Preauthor wrong detail/list and
  mutation-detail-envelope behavior cases, observe RED/GREEN in Docker pytest,
  regenerate actual terminal SQL artifacts, publish bounded correction.
T23 row-count proof is provisional again: a valid wrong-route envelope can pass
current helper. Existing populated HMAC/UI/restoration proof remains historical.
T25 local technical acceptance ofa592 is qualified pending T26 and fresh exact-head
review, CI and human freshness acceptance. Next: delegated helper/tests correction.
- [x] T27 Align runtime audit-route OpenAPI metadata with published2.7 (PR518
  comment4207658104): filters/path/auth, response/error and governed metadata;
  preserve custom runtime validation/terminal recording, no automatic FastAPI
  validation bypassing the governed service. Failure-first OpenAPI behavior checks.
- [x] T28 Enforce released canonical UUID or additive legacy-ID language (PR518
  comment4207658116), with preauthored HTTP422/terminal persistence proof for
  digit-leading compact/braced/URN forms; preserve actual valid legacy forms.
T27/T28 are exact-candidate unresolved findings; no merge while any remain.

T26 implementation verified: preauthored4RED plus old-source actual Docker wrong-
route mutation falsepositive; focused4GREEN/full13GREEN8.62s and actual11JSONL
records. Parentformatcheck failed then corrected; sourcecommitc0496a7, bounded
unit1f6449f125lines over517, unpublished. Fresh joint evidence still pending.
T27/T28 implemented after observed missing-error-envelope and malformed-UUID RED;
canonical compact/braced/URN forms now422+onevalidationrow, valid legacy compact
still404authorization. Rebuilt scoped28GREEN16.61s/Ruff; parentformatcheck failed
then formatted2files and staticchecks passed. Combined cohesive contract unit is
exact400 authored lines (385add/15delete), standalone0c9e56e over1f6449f, unpublished.
Final integrated source8f51c040923b932857cc3d12293117bd139289c8; fullDocker checks
session36717, runtime rebuild/browser session35620 running. No full GREEN claimed
for this source yet. ee827 CI later all ordinary jobs passed; security pending;
its Codex findings remain qualification gates, not erased by green CI.
Next: independent full verification and fresh HTTP/SQL/UI source-matched captures;
publish bounded units/update518, exact-headreview/checks and humanfreshness gate.

Live main advanced again to c2074fd8cb90840bc1a747dfe5ad1ad332d9ee03 (#488
current authenticated identity). Final-only automatic union preserves identity and
audit APIs; source25b48de45d0b25afb619a29e817ea51cfb5e9076. Obsolete8f fullchecks/
browser jobs interrupted intentionally exit130 (no fullPASS), no run containers
remain. New exactunion fullchecks session98667 and runtime/browser64482 running;
.env.worktree declaredrevision updated safely/mode600, neverprinted. Unitbranches
unchanged1f6449f125lines/0c9e56e400lines. All oldee827 hostedchecksSUCCESS now,
but oldacceptance remains qualified; no merge pending freshproof/review/human.

Fresh union full run observed RED:1606passed/1skipped/1failed323.43s. Existing
`test_current_governed_operations_have_one_declared_contract` correctly detects
newly described audit routes absent from its old EXPECTED_SCOPES inventory.
- [x] T29 Adapt existing governed-operation expected inventory to the two audit
  routes' actual admin.read/administrative_control/audit scope, preserve assertions;
  no new unit scenarios after source. Separate <=400 fixture-only correction,
  then rerun exact joint full suite; no blanket fullGREEN claim yet.

T29 existingfixture6GREEN12.32s/Ruff/format; finalsourcefixturecommit791ce48,
standaloneunit2c22464 adds10lines over0c9e56e. Runtime/helper/UI/Compose files
byteidenticalto25b48. Parent fullchecks verified25b48image+only791fixture readonly
mount:1607passed/1liveOpenRouterSkipped310.49s, prechecks/Alembicpassed, exit0.
Freshbrowser12passed18.3s; detail-recovery1passed4.9s actualPNG regenerated.
Freshterminal13passed7.93s +11actualJSONLrecords afterfullDBrelease. All8PNGs
manuallyinspected; privateconfig/private-marker textscanspassed. HTTPbadtemporary
capture detectedold8fhelperhash; regenerated aftersuccessfulbuild. Exacthost/API/
helperhash33640bab matches25b runtime source; capturesdeclaredrevision25b truthful.
Localtechnicalacceptance791recorded in updatedreport; unitpublication/newexacthead
Codex/CI/humanfreshness/conditionalmerge stillpending. No remoteheadupdate yet.

Published/attached boundedPR519helper125→520contract400→521inventory10→522evidence263.
No own-headexecutionfabricated: bodiespointtestedjoint791/carrier304/currentmainc207.
Afterpublicationlive mainadvanced31b4d2f8ba3dc292ea9bce59c069ffa21ebfc02f
(incidentmitigationUI plusadditivesharedAPIclientmethod); finalonlymerge6edab48
preservesall, backend/helpers/auditEvents script unchanged25b. Parentcurrentunion
fullchecks37467 usesverified25b backendimage pluscurrenttests/public readonlymount;
actualbrowser12passed15.2s afterweb/e2erebuild, fullGREENstillpending.
Next: freshtargetedcaptures/report/newfinalheadmetadata/review, humanfreshnessgate.

Parent actualGET `/openapi.json` found duplicate detail id/path parameters:
nativeFastAPIstr plus manuallyappendedoneOf. Existingparitytest silentlycollapsed
them into a dictionary, so scoped/fullGREEN is insufficient for validOpenAPI.
- [x] T30 Preassert parameter uniqueness in existing parity scenario, observeRED,
  fix via native documentation-only Path schema (no servicevalidation bypass),
  verify same canonical schema plus HTTPterminal behavior, publish separatebounded
  unit because PR520already400. Localtechnicalacceptance791/6ed provisional again.

T30 sourcecdf536f observed uniquenessRED1fail4.63s, focusedGREEN1pass4.15s;
actualAPI independently has onecanonical id/path and exacthost/API/helpermanifest
f80c78f9. Full1608passed1skip379.38s +prechecks/Alembic; browser12passed28.3s;
terminal13passed9.25s +11actualSQLrecords. All8freshPNG manually inspected;
connectedfault200→503 clearsprior1/1to0/0, boundedcontrollerrestored SQLt|t.
Standalone27line5a30533 unpublished; currentCDFtechnicalacceptance stillqualified.
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

T31 scopedRED2failed2passed8.86s beforedefaultactivation; GREEN4passed8.64s,
Ruff/formatpass, existingexplicitoverridecompatibilitypreserved. Fourfile8line
boundedsourcecommitted; fullnewjoint/capturesstillpending; release2.7immutable.
T33 scopedread-onlyexploration verified exactlysixruntimeDTOoperations absent
from2.7metadataenum, actualmigrationspersistthem andprojectionpreservesoperation.
Selectedboundedruntime-local namedOpenAPIcomponent derivedfromAuditEvent schema,
constrainedactualmetadata projection, visiblymarkedimplementationextension.
No frozenURNreuse/snapshotedit, no eventhiding/relabeling/newrelease. Testsfirst:
realpersisted sixfamilies/list/detailvalidateadvertisedschema, forbiddencontent
mustfail, legacycanonicalIDprojection remainsadditive, thenRED/GREEN sourcefix.

T33 realDBRED3failed10passed10.62s beforefix; sourcee0fa793c2fcb1c4dc3e75f4f0f444cff3f8badf3
inline runtime-local named$id/title/scope +internal$defs covers34operations and
actualIDlanguage, excludesprojectedcontent, no frozenURNreuse. Worker13GREEN10.81s;
parent16GREEN12.75s incldefaultrelease +Ruff/format. Parentfirstformatcachepermission
failedbeforepytest; onlycachelocation/tmpcorrected, no sourcechangeforcache.
Bounded251line3files unitprepared over8lineT31child over27lineT30child, unpublished.
Fullnewjoint4016/browser45729running; no currentfullGREEN orlocaltechnicalacceptance
claimed. Nextfreshcaptures/defaultschemaactualAPI, reportdeterministicworktree
setup, boundedpublication/evidence522restack, exactfinal518review/CI/human.

Fresh e0 fullsuite RED:1609passed1skipped1failed399.66s. Existing usage-publication
scenario pins activeCONTRACT_VERSION2.6 evenafter deliberate2.7activation;
its later canonicalusageURN expectation also pins2.6 despite selectedsnapshot2.7.
- [x] T34 Adapt only existing usage publication expectations to active published
  2.7; preserve selector/security/status/closedschema/inventorychecks. Mechanical
  onefilefixturecorrection after observedfullRED, no newpost-codeunit scenarios.
  Verifyexistingmodule then actualjointfullsuite. Runtime/helpers/UIbytesunchanged
  frome0 source; deployedcapturebuildrevisionmusttruthfullyremain e0 unlessrebuilt.

T34 existingmodule2GREEN5.77s/Ruffformat; fixtureonlysource13fc4ba1854ee75923a02da94311995e5d569c0e.
Runtime/helpers/UI bytesunchangede0, manifestb06fe806; actualnativeAPI OpenAPIcaptured
unmodified andadhoccompleteAPIlistenvelope/detailvalidate local34operationschema.
Actualbrowser12passed22.0s; refreshedrealallowdeny/DBfault/mocks beforefullDBrelease.
Fullrerun21510 startedon13fc, then sourcebranchesrecordedvia cleanfinalmergec126258
withoutanysrc/test/public/script/configtreechange (explicitgitdiffexit0).
Unpublishedcohesiveunits: nativepath27lines5a30533→defaultrelease12lines5f48f791
→runtimeprojection251lines7bcf29fd. Allparentunitheads nowancestors of finalcarrier.
Sourcebranchmergedoesnot itselfconferreview/humanacceptance. Freshfullstillpending.

PublishednewsourcePR542nativepath27→543defaultactivation12→544runtimeprojection251;
PR522append-onlyrestackedto544/evidence344, final518head7fc7921889862d6c4db01f3f99dca7c233b45f8a,
actualGitHubbase31b. Allreadbackheads/sizescorrect. Finalsource/test/public/script/config
identical13fc (gitdiffexit0). Parenttaskmergekeptnewverifiedcheckboxes/progressover
staleuncheckedcarrierhistory; no source/evidenceconflicts. Currentfull1610/1skip286.94s,
browser12/22s, terminal13/9.42s+11actualSQLrecords. ActualAPI/HTTPhelper/hostmanifestb06
andrawnativeOpenAPIdeclares e0 truthful; completeAPIlist/detailvalidate34-operationlocal
schema. All8freshPNGinspected andcurrentprivatevalue/markertextscanspass.
Nativeappattachcalls542/543/544 timedout (allattempted, no confirmedreceipt); GitHub
creation/readbackverified. Nativeartifactavailabilitydoesnot authorizeorblockmerge.
FreshCodexonexact7fc publishedtwoactualP2findings; localtechnicalacceptancequalifiedagain:
- [x] T35 Reject noncanonical request UUID filter spellings before UUID conversion
  (518comment4209292491): preauthor compact/braced/URN authorized422 +onevalidation
  terminal, preservecanonicalforms andauth/grantordering; observeREDthenGREEN.
- [x] T36 Expose audit UI in existing control-plane navigation (518comment4209292475):
  narrowread-onlynavexploration, browserjourneytestbeforeHTML/sourceedit, observed
  missinglinkREDthen actualnavigationGREEN; real repeatablescreenshot, safeURLs.
T25/T7/T8 remainpending; no mergeorhumanreceipttransfer. T30/T31/T32/T33/T34 source,
reproductionandboundedpublication outcomes nowobserved, finalacceptancestillgated.

T35 worker failure-first RED3malformed forms200/26passed; focused GREEN29passed17.78s,
Ruff/formatpass. Parent reviewed twofile41addition fix and committedf85157112fdd9c50204d72f6f615d90a0336f3e5.
No freshintegratedproof/publication claimed. T36 upstreammodel-aliases nav also
disabled; extend existing Model aliases→Consumption→Audit journey failurefirst
before upstreamHTMLedit. PR518qualification6042346787 published, actualremote
body staticvalidatorGREEN[] exit0 afteroptionalheredoc removal (reportkeepsrecipe).

T35/T36 actualjoint5ac4eaeb08aa3c3a17a3ad8db03e9cc3e771f288 includescurrentmain4e3:
full1613passed1opt-inliveOpenRouterskip315.38s/prechecks/Alembicexit0. Fullrunstarted
assembledtree; startmanifest src/tests/publicbytesmatchedcommittedtree; ancestry32ab
changesnosource/tests/public/scripts/config. Runtime/API rebuiltexact5ac; independent
host/API/helpermanifestf8014b2e9529563a2e824528c96bd61eb0d511d34a757af298b12265a47f2bbb.
Freshbrowser14passed18.3s; firstparent13pass1fail19.5s EACCESscreenshotmount
disclosed, sourceunchangedrerunuseswritabletemporarycapturefolder. Terminal13passed
10.29s+11actualSQLJSONL; wholelist/detailnativeAPIvalidationPASS. Actualallowdeny
200403200,3nonnullHMACrefs; connectedfault200503clears1row/detailto0/0 and
controllerrestorationverifiedt|t. Mockdetailrecovery1passed3.1s. All9currentPNGs
manuallyinspected; privateconfig/credentialmarkerscanspass. Preparedboundedsource
511fc41→e23ece52, newevidence936fc190over522 (includesrequiredsourceancestry,
no unrelatedmainfiles); unpublished. Reportlocaltechnicalacceptance5ac renewed,
NOT freshhumanreceipt/GitHubCodex/CIapproval; T25/T7/T8 stillpending.

Publication verified: PR547head511fc41lines/base544,548heade23ece52/base547,
549head936fc190/base522; allnativeattachments547/548/549succeeded. Earlier542/543/544
nativeattachmentretryalso nowconfirmed. Atomicfinal518head8c06bffacb6e78d5410e94aa598fee54c8e97d16
base4e3 size4976(alladditions+deletions), final-onlyuserexception. Allbounded
headsancestorsfinal, finalsrc/tests/public/scripts/configidenticaltested5ac.
ActualremotebodytrustedstaticvalidatorDocker/networknoneGREEN[] exit0.
Exact8cCodexrequested6042753256. UserfreshhumanacceptedEXACT8c/source5ac
(1613Python/14browser,UUID/navfixes,pagination470deferred), CONDITIONALLY
no unresolvedCodexfindings +ALLchecksPASS; receipt6042778973. No transfer
tofuturehead; no remotemergeyet. This localtaskappendisnotpushed, soacceptedhead
remains8c unchanged. T25/T7/T8 remainpendingactualreview/CI/conditionalmerge.

Fresh exact8cCodexreview5445675670 (17:07:52Z) has two NEW P2findings:
- [x] T37 Normalize accepted canonical UUID event IDs before case-sensitive
  VARCHAR lookup (4209709009). Preauthor realpersisted uppercaseUUID detail200
  +terminalmetadata; preserve legacyIDcase/authorizationorder; REDthenGREEN.
- [x] T38 Reject forbidden content-retrieval parameters on detail reads
  (4209709019). Preauthor known-ID+raw/redacted-content422 withonevalidation
  terminal, no sensitivepayload; retainauth/grantorder; REDthenGREEN beforefix.
- [x] T39 Investigate hosted static-web FAILURE job112911847073/run37656076374
  on8c; readactualfailurelogs, reproducebeforeboundedfix. No guess/retrybypass.
Human8cconditionalreceipt remains recorded butconditionsNOTmet; no merge.
Anynewsourceheadrequiresfreshactualproof/review/CI/humanfreshness, notreceipttransfer.

T39 rootcauseactualhostedoldexistingexpectationdisabledAudit&consumption;
DockerfocusedRED1fail thenunchangedscenarioexpectationadapted4add1del, GREEN1/2.5s.
Committedea15c9c918b2707545a8b04702960688c778cd84; bounded7447c4591a150b52485e5345f3f8c8a7852bfc0a
5lines over548, unpublished. Fullstaticselection againstNGINX71pass60skip3fail1.3m
notCIequivalent(CSP); staticHTTPnonloopback73pass60skip1fail1.6m usesinsecureorigin
no crypto.randomUUID→fallbackkeyviolatesoldUUIDexpectation; no producttestweakening.
ActualCI-equivalentstaticHTTPloopbackDocker74passed60skipped1.5m exit0; server
existingpythonimage/read-onlypublicassets/no.envGit/nohostports, runnerexistinge2e
sharesnetworknamespace for127.0.0.1:4173, traceoff, automaticservercleanupobserved.
T37/T38workerRED4fail28pass51.58s; initialpreauthoredsuccesshelperincorrectly
expectedresponse terminalrequestID unavailableon200. Parentapprovedcorrection
ONLYalreadyauthoredscenario viaSQLbefore/afterrowIDs andexpectedmetadata, no new
scenarioaftercode. PreservevalidationstagewithoutsubjectperDTO663+, no newexception
orrelabelauthorization; parentretractedunverifiedauthcontextforwardingassumption.
FinalworkersourceGREEN pending; no newjointfull/runtimecaptures/remotepush/acceptance.

T37/T38 sourceverified andcommittedf24befc4bb0d029fa1248888e7ab154c32a9e67a
79add3del82lines2files; standalonee64a9fb9d0a5b292bb616e59ba2ab2f3e7bb4535 over547.
Worker32GREEN16.66s thenformatterpermissionfailed; parentinterruptedslowwriter
afterstatushandoff(no activechecksDBcontainer), hostUIDformatterleftfileunchanged,
Ruffcheck/formatPASS andindependent32GREEN18.34s. No sourcechangeafterobservedGREEN.
CanonicalUUIDONLYnormalizebeforelookup; legacyIDsunchanged. Forbiddencontentkeys
reject422validationafterauth/grant, no subjects perreleasedDTO; no newexception.
Mainadvanced9d6ed3da8f22132561635de9a429989d21773724 (#550 credential-resetlock);
cleanlocalunion1cacab56 preservesall. Bounded82detail/5sidebarheadancestrymerged
intofinald0f5a35f80d9a0c8e0fc1b027a0baa60ffb28ecb, byteidenticalruntime/tests/public
/scripts/configtof24(gitdiffexit0). Ignoredsyntheticbuildrevisionf24/mode600safe.
NewactualjointfullPython13535, runtimebuild+auditbrowser53946, wholecurrentstatic
loopbackbrowser20805 running; no newfullGREEN/capturefreshness/localtechnical
acceptance claimed. Currentremote518still8c qualified; allnewunitsunpublished.

Current exactf24 verification completed: defaultfullDocker1616passed/1opt-inlive
OpenRouterSkipped392.02s, prechecks/AlembicPASSexit0; independent32scoped18.34s,
rebuiltAPI/web/e2e auditbrowser14passed19.5s. Main9d fullstaticCI-equivalentloopback
136scenarios76passed60skipped1.8m/exit0, automaticservercleanupobserved. Fresh
HTTP/API/hosthash946c1fdf477ce5255e69e9efee6d5acece79c19b73d670ed047b99d56f953106
matches. NativeAPIcompleteenvelope/detail34operationschema validationPASS.
Actualrunningdetail5JSONL: uppercasepersistedUUID200/exact1authorizationterminal,
4contentkeys422/exact1validationterminal/no subjects orcontent. FirstadhocSQLreader
KeyError usedwrongrootrequestID; correctednestedcorrelationreader, reranall5 actual
HTTP/SQL, no API change ormanualartifactrepair. Freshterminal13passed8.99s/11actual
JSONL; connectedallowdeny200403200/3nonnullHMACrefs; realqueryfault200503clears
1row/detailto0/0, restoredt|t. Nav1passed3.2s/mockrecovery1passed3.1s capturesfresh.
Parentmanuallyinspectedall9PNGs; privatevalue13textartifacts/syntheticmarkerscansPASS.
InitialDockerdefaultUIDprivateenvscanpermissionfailure correctedhostUID/mode600
unchanged. Sourcefinald0treeidenticalf24. Reportrefresh/boundedpublication/newexact
Codex/ALLCI/freshhumanreceipt/ordinaryconditionalmerge remainpending; NO merge.

Published fresh boundedunits551detail82/e64over547,552sidebar5/7447over548,
553freshproof302/b644over549; allnativeattachmentsconfirmed. Currentfinal518
head1be80efeee25563da9f54db97c1f0058f5f28105/base9d6ed3 size5278 final-onlyexception;
source/test/public/script/configbytesidenticalactuallytested/deployedf24.
Reportcurrenttechnicalacceptancef24renewed, historical5ac labelednotcurrent;
parentcorrectedworkerunexecutedstaticrecipe to actualoriginalconfig/rootassets
loopbacktopologybeforepublication. Actualremotebody trustedDocker/networknone
validatorGREEN[]exit0. ExactheadCodexrequested6043851594. LiveProjects25CLOSED/Done
is humanstate, not proofintegration. NewallCI/Codex/humanfreshreceipt pending.
No merge oroldreceipttransfer. This taskappendnotpushed: finalhead stays1be80.

Fresh exact1beCodexreview5446408317 at18:10:09Z newP2comment4210324797:
- [x] T40 Enforce published RFC3339 syntax for from/to before broad Python ISO
  parsing. Preauthor actual authorized HTTP422+exactonevalidationterminal for
  basic/week/date-only/missing-zone forms alongside validdecisionfilter; preserve
  validextendedUTC/offset/fraction forms and auth/grantordering. ObserveREDbefore
  boundedsourcefix; exactDockerGREEN, currentunion/provenance/reviewCIhumanagain.
Currentlocaltechnicalacceptancef24qualified; NO merge/freshhumanreceipttransfer.
Hosted1beunitSUCCESS; contracts/staticpending atlastsnapshot, notallchecksPASS.

T40 failurefirstfinalRED9failed51passed24.02s before86linefix. Initialpre-source
helpergeneralizednosubjectvalidation toauthorization404 (10fails) correctedbefore
source, finalREDgenuine. Worker60GREEN27.35s/Ruffformat/diffcheckPASS,28preauthored
cases include24malformed from/to+4legal UTC/offset/fraction/lowercaset/zforms.
Parentreviewed/committed731ec67304e05a9f981e945599696a34921a1d2e (84add2del);
boundedchild2a5c8a5over551,86lines, unpublished. OnlyASCIIextendedsyntax before
calendarparse, RFC3339§5.6lowercaset/z normalized, offsetrangesexplicit; unchanged
leap-seconddatetime limitation, no snapshot/DTOexception/dependencychange.
Finalancestry5541290 sourceidentical731; fullDocker42474/runtimebrowser65246/
static79778 running, actualHTTP/native/detail/timecaptures starting. No newfull
GREEN/currenttechnicalacceptance/remoteheadupdate claimed yet; NO merge.

Current731 fullDocker1644passed1opt-inliveOpenRouterSkip448.88s/prechecksAlembicPASS
exit0; rebuiltAPIaudit14passed37.7s; fullstatic76pass60skip2.1m/exit0cleanup.
Freshhost/API/helperhash9ec98adb3e3b245591727fbefb55f64de81a01a2652cee957946868c55cbce0a
matches; nativecomplete34oplist/detailschemaPASS; realdetail5+time12JSONL exactly
1terminal/status/stage/safemetadataeach. Initialdetaildelta overlappedbrowserread
writers, exactoneassertionfailed, partialcapture rejected thenall5+12rerunsequentially;
no manualfieldrepair. Freshterminal13passed9.10s+11actualJSONL; connectedallowdeny
200403200/3nonnullHMACrefs; realfault200503clear1/1→0/0visibleerror restoredt|t.
Freshnav1/5s/mockrecovery1/5.6s; all9PNGsparentinspected;14textprivatevalue/markerscans
PASS. Updatedreportexact731 localtechnicalacceptance; immutableleap-seconddatetime
limitationunchanged; RFC3339primarysourcecited. Newboundedproofover553 prepared
240lines incl86source/12timeJSONL, publication/newreviewALLCIhuman gatespending.
NO merge; old1behostedallchecksSUCCESSdoesnoteraseRFC3339Codexfinding.
