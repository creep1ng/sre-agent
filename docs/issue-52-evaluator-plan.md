# Evaluator plan for the Sunday human tests (#52)

Prepared by Mario. Slot assignment and the final candidate SHA stay with @creep1ng, coordinator of #52.
This plan does not freeze the candidate, does not close any issue and does not replace human acceptance.

## Purpose and schedule

- Sunday 18 October 2026: human tests over the frozen release candidate; demo Monday 19 October 2026,
  17:00 America/Bogota. The tests finish before the demo.
- Operationalizes #49 (at least three participants; success rate and critical problems documented) and
  feeds the acceptance decision in #52.
- Acceptance is decided in #52 against its freeze criteria: global DoD, measured KRs, demo from a clean
  reset, zero critical defects, declared limitations. A pass here is input to that decision, not the
  decision.

## Getting the candidate

1. Take the frozen candidate SHA from #52, recorded there by @creep1ng; do not use a branch tip or a
   remembered SHA.
2. Install it with the clean-install runbook of #47 (PR #656, open):
   - Runbook: https://raw.githubusercontent.com/creep1ng/sre-agent/6a0481c3c5f3c846e52f291d24df5ed403f065d0/docs/issue-47-clean-install-runbook.md
   - Verified execution: https://github.com/creep1ng/sre-agent/blob/6a0481c3c5f3c846e52f291d24df5ed403f065d0/docs/evidence/issue-47/clean-install-verification.md
   - Both are verified against release `e5c542d7` (the tip of main and the base of PR #656). If #52
     freezes another SHA, run the runbook against it and record divergences before the journeys.
3. Evaluate on an isolated install (fresh VM or empty directory) as the runbook describes, not on the
   shared long-running stack.

## Evaluator slots

Three evaluator slots plus one recorder; @creep1ng assigns people.

| Slot | Suggested coverage |
| --- | --- |
| Evaluator A | Operations: inbox, triage, war room, decisions, postmortem (J2 to J5) |
| Evaluator B | Administration: grants and consumption (J6) and governance surfaces |
| Evaluator C | Environment and integration: clean install (J1) and real MCP/OTel incident (J7) |
| Recorder | Keeps the registration sheet, evidence links and the results comment on #52 |

Owned areas per #52: Daniel, UI for investigation, decisions and postmortem; Camilo, agential
investigation and command producer; Mario, review, Grants and runbook. Keep that split; a journey should
not be verified only by its fixing owner.

## J1. Clean install of the frozen candidate (#47)

- Objective: the candidate installs on a fresh environment with documented health checks, persistence
  and scoped reset.
- Preconditions: fresh VM or empty directory; Git and Docker only; untracked `.env` exactly as the
  runbook documents (never printed, pasted or committed).
- Steps: follow the runbook verbatim, including its Runner log template.
- Expected: documented container order with build exit 0; `alembic_version` `20261009_01` with
  idempotent rerun; seed baseline `4 | 4 | 2 | 16` and `seed converged` on rerun; three health checks
  ok; console with the 4 seeded principals and no page errors; persistence across `down`/`up`; scoped
  reset back to the same baseline.
- Evidence: filled Runner log (SHA, environment, Docker commands, outputs), console capture, runbook
  section used.
- Triage owner: Mario (runbook); peer execution coordinated with @creep1ng.

## J2. Console shell, navigation, per-tab session and triage handoff (#487 units 1/5 to 3/5)

- Objective: from the stable entry, reach delivered surfaces with visible navigation and return without
  losing context or identity.
- Preconditions: J1 done; demo keys from the seed.
- Steps:
  1. Open `/` and enter the console (catalog at `/design-system.html`).
  2. Enter Operations with the demo key once and confirm the session is per tab.
  3. Open a second tab and confirm it stays anonymous (no key in URL or storage).
  4. From the inbox open Triage and declare an incident with a single key entry; confirm the incident
     band keeps incident and run across war room, Decisions and postmortem.
- Expected: visible entry and navigation, per-tab session, one key entry from the inbox, incident/run
  context kept in the band.
- Evidence: one capture per step, noting the candidate SHA.
- Triage owner: Daniel (#487 surfaces).
- Known limitations: shared multi-tab session (#486) and units 4/5 and 5/5 are pending; two isolated
  tabs are expected current behavior, not a defect.

## J3. Alert inbox to war room, start/resume and intervention (#37, #39)

- Objective: operate the whole incident from the UI without harness URLs or credentials: open the alert,
  declare from triage, start or resume the investigation run and read its durable result.
- Preconditions: J1 and J2 done; a controlled alert loaded (the exploratory walkthrough used a synthetic
  alert; real signals belong to J7).
- Steps:
  1. Open the alert from the inbox and declare from triage (single key entry).
  2. From the war room start the investigation, then reload and resume without duplicating effects.
  3. Read run state and events, contrasting the UI with the authoritative API.
  4. End a run in `unknown/needs_human` (for example with the LLM disabled) and look for a safe
     intervention or resume action.
- Expected: the run starts and resumes from the UI; receipt and state are durable; an
  `unknown/needs_human` outcome shows an explicit, safe intervention and stops looking `running`.
  Requests stay inside the governed gateway (#38 context); the UI exposes no provider keys.
- Known blocked as of the plan date: on the explored main (`aa789d9c`, #42 findings) the war room had no
  start/resume control; the API created the run but the UI step was missing, and a run ending
  `unknown/needs_human` kept `status=running` without intervention. In-flight: #651/#652 (#37),
  #649/#650 (#39). Re-verify on the frozen candidate before starting; if unchanged, record the blocker
  with SHA and move on.
- Evidence: captures of start, resume and the intervention (or of the missing action), plus the API
  contrast when used.
- Triage owner: Daniel (#37 UI); Camilo (#39 harness and gateway).

## J4. Human decisions and command producer 2.1.0 (#41)

- Objective: execute the human actions allowed by the pinned workflow version (approve/reject
  mitigation, failed verification, close with postmortem) from the UI, with actor derived from the
  credential and idempotent commands.
- Preconditions: an incident with a run in a state that allows decisions.
- Steps: approve and reject a mitigation proposal; force a failed verification; attempt
  `verification_passed` and `close_incident`; retry a command with the same idempotency key and confirm
  no duplicate effect.
- Expected: only workflow-valid transitions; commands use the pinned workflow version; no free status
  PATCH; actor and version recorded.
- Known blocked as of the plan date: explored main kept `run-command:2.0.0`; `verification_passed` and
  `close_incident` returned 422; 2.1.0 is already agreed (decision on #41). In-flight: #653 (review,
  verify, close), #582 (decision durability). Re-verify before starting; if unchanged, record and move
  on.
- Evidence: capture per action, exact request/response or UI messages, command and workflow versions.
- Triage owner: Camilo (producer contract); Daniel (UI).

## J5. Postmortem: generate, review, keep (#43, #335)

- Objective: request a traceable draft, review it and keep the validated version before close.
- Preconditions: an incident advanced to the postmortem stage.
- Steps: request the draft; review and edit it; save the validated version; check the artifact identity
  (incident link, version, review state); attempt to close only with a reviewed version.
- Expected: artifact persisted and versioned, linked to `incident_id`, review distinguished from
  incident status, content authorization respected.
- Known blocked as of the plan date: the view showed only `pm_demo0001`, clearly labeled as a
  non-persistent fixture. In-flight: #418, #588 (#43 view slices). Re-verify before starting; if
  unchanged, record and move on.
- Evidence: capture of draft, review and saved version (or of the fixture state), plus the artifact
  identifiers.
- Triage owner: Camilo (artifact producer, #335); Daniel (UI).

## J6. Administration: grants and LLM consumption (#21, #143)

- Objective: verify the admin surfaces: grant lifecycle with default deny and consumption reads with
  honest states.
- Preconditions: admin key from the seed; an active principal and resource.
- Steps: create a grant with an active Principal, action and resource; revoke it and confirm
  traceability is kept; probe an absent grant and confirm deny, not an error; open consumption and check
  the aggregate view, the bounded request drilldown, alias/model/provider snapshots, legacy and
  unavailable rows, and null staying unavailable.
- Expected: default deny presented as deny; revocation keeps traceability; consumption shows immutable
  attribution and explicit unavailable states with no invented zero.
- Evidence: captures of grant create/revoke/deny and of consumption rows in each state.
- Triage owner: Mario (Grants, per #52). #21 is delivered; #143 has the bounded request drilldown merged
  (#617), full walkthrough still pending.

## J7. Real MCP/OTel incident (#51), if surfaceable via the UI

- Objective: run the pinned OpenTelemetry Demo failure and prove a real incident: Grafana MCP read-only
  through the gateway, a real metric or log, evidence correlated to `incident_id`, plus verify/reset
  scripts.
- Preconditions: coordinate availability with Camilo and @creep1ng before the session. The exploratory
  walkthrough used controlled alerts and MCP, explicitly not real OTel signals.
- Steps: trigger the documented failure; investigate from the UI; confirm MCP reads only via the
  gateway; capture the real signal and its correlation; run verify/reset.
- Expected: real metric or log, correlated evidence, read-only MCP boundary respected, reset documented.
- If the candidate cannot surface this in the session environment, record "not evaluable here" with the
  reason and stop this journey; do not burn the schedule, and never substitute a controlled alert as
  real evidence.
- Evidence: real metric/log capture, correlation identifiers, verify/reset output.
- Triage owner: Camilo (#51).

## Cross-cutting rules

- Log per journey: candidate SHA, environment (host, Docker and Compose versions, ports, project name),
  exact commands, expected versus observed, real captures only. No invented evidence; no screenshots
  reused from another SHA without an explanation the reviewer can confirm.
- One evidence folder or link set per journey. Sanitize: no keys, tokens, headers, personal data or
  unsafe raw logs in captures or attachments.
- Verdicts: pass, fail or blocked. A fail is unexpected behavior that is not a declared limitation; it
  goes to the triage owner with the SHA and the exact step. A blocked journey still needs the SHA, the
  exact step, expected versus observed and a log or capture.
- Stop rules: a journey blocked by a known, unchanged behavior gets recorded and the next journey
  proceeds. Retry once at most unless new code landed. Keep the schedule: the demo is Monday.
- If the candidate changes during the session, restart journeys against the new SHA or record which
  journeys ran against which SHA.

## Known limitations to record as such (not failures)

- Shared multi-tab session is still pending (#486); per-tab isolation is the current expected behavior.
- Console units 4/5 (governance) and 5/5 (integration) of #487 are not delivered as of this plan.
- Three P2 review findings reproduced at `e5c542d7`: stale incident band without a run, alert deep-link
  residue when going back, 375 px timeline column. PR #654 tracks the fixes; re-check only if the
  candidate includes it, otherwise record as limitations.
- J3, J4 and J5 carry entries blocked as of the `aa789d9c` exploration; the frozen candidate may include
  the in-flight fixes. Re-verify first.
- The exploratory walkthrough used controlled alerts and MCP, not real OTel signals; J7 is where that
  gets real evidence.

## Registration sheet

The recorder keeps the authoritative copy and links it from #52.

| Evaluator | Journey | Verdict | Evidence link | Blocker or next owner |
| --- | --- | --- | --- | --- |
| | J1 | | | |
| | J2 | | | |
| | J3 | | | |
| | J4 | | | |
| | J5 | | | |
| | J6 | | | |
| | J7 | | | |

## After the session

- The recorder posts the results on #52: per-journey verdicts, blockers with owners and SHA, confirmed
  limitations.
- #52 decides candidate acceptance against its freeze criteria. Nothing here closes an issue, merges a
  PR or assigns labels.

## References

- Freeze and coordination: https://github.com/creep1ng/sre-agent/issues/52
- Exploration of record (`aa789d9c`): https://github.com/creep1ng/sre-agent/issues/42#issuecomment-6227247809
- #487 merged-part review: https://github.com/creep1ng/sre-agent/issues/487#issuecomment-6236594441
- Policies: `docs/pr-evidence.md`, `docs/team-workflow.md`.
