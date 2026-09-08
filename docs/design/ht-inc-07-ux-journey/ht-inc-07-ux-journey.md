# HT-INC-07 — Operator incident journey

Issue [#150](https://github.com/creep1ng/sre-agent/issues/150) is a research and
UX-refinement delivery: it does **not** implement screens, runtime behavior, or
a new state machine. The checked-in incident workflow remains authoritative.
This canonical document integrates the original operational journey introduced
in [commit `c43f01c2`](https://github.com/creep1ng/sre-agent/commit/c43f01c2)
with complementary decision/recovery research; neither contribution replaces
the other.

## Review path

1. Review the 15 stages and P01–P07 surface inventory.
2. Review the Mermaid responsibility **flowchart** in
   [`user-journey.mmd`](user-journey.mmd), then the decision/recovery map in
   [`incident-operator-flow.mmd`](../../diagrams/incident-operator-flow.mmd).
3. Review the separate Mermaid `journey` expected-experience companion in
   [`incident-operator-journey.mmd`](../../diagrams/incident-operator-journey.mmd).
4. Check the mapped issues and contract guardrails before proposing UI work.

## Scope and contract authority

| Source | Role here |
| --- | --- |
| [Issue #150](https://github.com/creep1ng/sre-agent/issues/150) | Requires research, journey, Mermaid, rendered evidence, and issue mapping; excludes UI/runtime implementation. |
| [`incident-response.yaml`](../../../agent/workflows/incident-response.yaml) and [`incident-state.schema.yaml`](../../../agent/schemas/incident-state.schema.yaml) | Normative incident transitions, four decision points, and state shape. |
| [`incident-runs.openapi.yaml`](../../../agent/api/incident-runs.openapi.yaml) and [ADR-008](../../adrs/ADR-008-run-events-transport.md) | Run lifecycle, commands, snapshots, and cursor polling. |
| [Notion alternatives](https://www.notion.so/3b4e4205157e80818779cab2fdc1be39), [process](https://www.notion.so/3b4e4205157e80d985e9c3b76e023d3a), [historical flow](https://www.notion.so/3b4e4205157e8012b98dfc33ab72b2ca) | Research index/historical context only; checked-in contracts and live GitHub scope prevail. |

The canonical path is `detected → triage → active → investigating → mitigating
→ verifying → resolved → postmortem → closed`. `dismissed` and `linked` are
terminal alert paths. Declaration creates `incident_id`; closure requires a
postmortem. The domain validates and persists decisions; UI submits intent and
reads a safe projection.

## 15-stage operator journey

| # | Stage | Actor | Surface | Status / visible result |
| --- | --- | --- | --- | --- |
| 1 | Receive alert | System | — | #149 adapts signal to alert with service, severity, timestamp. |
| 2 | Identify signal | Human | P01 inbox #15 | `detected`; ordered list and count. |
| 3 | Review detail | Human | P02 detail #15 | `detected`; context and source metadata. |
| 4 | Start triage | Human | P02 #15 | `midnight:triage-requested`; no incident yet. |
| 5 | Decide disposition | Human | P03 triage #23 | `triage_outcome`: dismiss, link, or declare. |
| 6 | Enter incident | Human + system | P03 #23 | #26 validates; declaration creates `incident_id`, severity, event. |
| 7 | Prioritize active incidents | Human | P04 board | **Gap:** aggregated active-incident view. |
| 8 | Coordinate | Human | P05 war room #36 | Persisted shared state, owners, comments. |
| 9 | Reconstruct context | Human | P06 timeline #36 | Ordered actor/sequence/time/type events. |
| 10 | Investigate | Human + agent | P05/P07 | #145/#146 safe hypotheses and cited evidence. |
| 11 | Decide mitigation | Human + agent | P07 monitor | `evidence_sufficiency`; proposal, risk, verification. |
| 12 | Approve and apply | Human | P07 monitor | Blocking approval; human-operated or simulated mitigation. |
| 13 | Verify stability | Human + agent | P06/P07 | `stability_check`; unstable returns to investigation. |
| 14 | Review postmortem and close | Human + agent | P06 | Postmortem and terminal closure event. |
| 15 | Follow up after close | Human | Follow-up surface | **Gap:** action items, ownership, due dates. |

### Surface inventory, roles, and gaps

- **P01/P02:** [#15](https://github.com/creep1ng/sre-agent/issues/15) is
  fixture-driven and does not create incidents. **P03:** #23 captures
  dismiss/link/declare; #26 validates the decision and transition.
- **P04 board is not a war room:** #36 and [#189](https://github.com/creep1ng/sre-agent/issues/189)
  provide incident detail/war-room reads, not a board. The board gap remains.
- **P05/P06:** #36 reads persisted shared state and ordered events; it does not
  promise push. Role instructions, formal alert-acknowledgement ownership, and
  curator timeline pins remain separate refinement gaps.
- **P07:** #145/#146 define governed runs, commands, snapshots, and events.
  UI never executes infrastructure or transitions the workflow locally.
- **Reload/share is not follow-up management:** #146/#189 restore persisted
  IDs, version, and ordered events; they do not manage action items. [#51](https://github.com/creep1ng/sre-agent/issues/51)
  is a demo integration, not a follow-up UI story.
- The fixture severity vocabulary (`critical|warning|info`) and workflow
  vocabulary (`sev1..sev4`) have no cross-contract mapping.

The operator perceives, decides, approves, coordinates, and closes. UI displays
versioned state and captures intent; the domain/runtime validates transitions,
requires approvals, and writes timeline events; the harness runs governed steps
and reports safe progress, results, or failures.

## J01–J12 decision and recovery map

| J steps | Covers | Contribution | Evidence |
| --- | --- | --- | --- |
| J01–J03 | 2–6 | Scan/request triage/dismiss-link-declare; dismissal ends the alert path, link opens an eligible incident. | #15, #23, #26 |
| J04 | 7–9 | Read persisted war room and safe timeline; board remains distinct. | #36, #189 |
| J05–J07 | 10–11 | Start/resume only when domain permits; review governed evidence; optional authorized BoK may be restricted/insufficient. | #37, #145, #185, #40, #34; [#35](https://github.com/creep1ng/sre-agent/issues/35) is the future workflow-harness connector. |
| J08–J09 | 11–13 | Human approval blocks mitigation; rejected changes and unstable verification return to investigation. | #41, #26 |
| J10–J12 | 14–15 | Review postmortem, close, then reload/share persisted links; action-item follow-up remains separate. | #43, #146, #189 |

Run states (`running`, `awaiting_human`, `completed`, `terminated`) are
independent from incident states. `resume_from_run_id` requests the last
snapshot only when the domain permits; `awaiting_human` expects an authorized
command. Completed/terminated runs and closed incidents are never presumed
resumable. Reload is server-authoritative cursor polling, not browser state or
SSE.

Denied capability, invalid output, upstream unavailability, or exhausted
budget blocks/escalates without state advance. Rejected mitigation and failed
verification return to investigation; recovery is successful only after stable
verification. Loading, empty, unauthorized, not-found, conflict, and
disconnected reads remain distinct. UI exposes IDs, progress, cursors,
attribution, timestamps, and summarized events—not prompts, credentials,
provider data, raw arguments, or raw output. BoK is optional: [#34](https://github.com/creep1ng/sre-agent/issues/34)
authorizes retrieval, not a dedicated human knowledge-navigation surface.

## Consolidated research and treatment

Research is public documentation, public product material, and open-source code
review performed 2026-09-07—not authenticated-product testing or user
interviews. It informs interaction patterns; it does not import vendor state
machines.

| Source | Observed pattern | Treatment |
| --- | --- | --- |
| [incident.io triage](https://docs.incident.io/incidents/triaging), [roles](https://docs.incident.io/incidents/incident-roles), [timeline](https://docs.incident.io/post-incident/timeline) | Accept/decline/merge, role instructions, curated timeline inputs. | Adapt explicit disposition and attributable context; retain project states. |
| [incident.io Investigations](https://incident.io/investigations), [product overview](https://docs.incident.io/getting-started/what-is-incident-io) | Marketing depicts hypotheses, evidence, and confidence, while product docs describe AI SRE as coming soon. | Inspiration only; no availability, performance, or autonomous-remediation claim. |
| [PagerDuty board](https://support.pagerduty.com/main/docs/navigate-the-incidents-page), [workflow runs](https://support.pagerduty.com/main/docs/incident-workflows#view-workflow-executions-and-step-output) | Board filters; step list alongside detail/output. | Adapt board-to-detail and safe progress, never raw output or vendor run states. |
| [Rootly lifecycle](https://docs.rootly.com/incidents/incident-lifecycle), [timeline](https://docs.rootly.com/incidents/incident-timeline/incident-timeline) | Lifecycle labels; actor/source filtering; `detected_at` and `acknowledged_at` are timestamps. | Adapt attribution, not labels or timestamp-as-state semantics. |
| [IncidentFox UI docs](https://github.com/incidentfox/incidentfox/blob/main/web_ui/docs/README.md), [OpenSRE](https://github.com/Tracer-Cloud/opensre) | Open-source runs/knowledge/remediation routes; public-alpha sessions/status/resume. The Notion index supplies no OpenSRE URL, so this repository identity is inferred from its description. | Code/public-alpha context only; no board/war-room behavior asserted. |
| [Rootly alert fields](https://docs.rootly.com/alerts/alert-fields), [severities](https://docs.rootly.com/configuration/severities), [built-in fields](https://docs.rootly.com/configuration/built-in-fields) | Normalized alert fields, single-select severity, built-in versus custom fields. | Adapt explicit severity/metadata presentation; do not invent a mapping for the project’s two vocabularies. |
| [PagerDuty during](https://response.pagerduty.com/during/during_an_incident/), [after](https://response.pagerduty.com/after/after_an_incident/) | IC, deputy, scribe, liaison, and post-incident coordination patterns. | Adapt visible responsibility; do not claim a role-assignment runtime. |
| [incident.io declaring](https://docs.incident.io/incidents/declaring), [workflows](https://docs.incident.io/workflows/getting-started), [postmortems](https://docs.incident.io/post-incident/postmortems-overview) | Minimum declaration form, trigger/condition/step workflows, and reviewable postmortems. | Adopt declaration/postmortem review intent; adapt workflow history to governed run events. |
| [Opsgenie lifecycle](https://support.atlassian.com/opsgenie/docs/manage-alerts-through-their-lifecycle/), [Atlassian lifecycle notice](https://www.atlassian.com/licensing/opsgenie) | Acknowledgement, responders, escalation. | Legacy reference only: sales ended 2025-06-04 and support ends 2027-04-05. |

**Discarded patterns:** metrics that exclude declined triage need a metrics engine
outside #150; escalation on no-ack/no-close needs a notification/on-call runtime.
Neither is introduced by this journey, and the agent cannot autonomously remediate.

## Mermaid evidence and rendering

The three views have different purposes: [`user-journey.mmd`](user-journey.mmd)
shows responsibility boundaries; [`incident-operator-flow.mmd`](../../diagrams/incident-operator-flow.mmd)
shows decisions/errors/recovery loops; [`incident-operator-journey.mmd`](../../diagrams/incident-operator-journey.mmd)
uses Mermaid `journey` syntax for expected experience.

Journey scores are expected successful-path experience, not measured satisfaction
or runtime state: `1`–`2` uncertainty, `3` meaningful but unconfirmed work,
`4` confident learning/follow-up, `5` confirmed recovery/closure. J09 is `5`
only after successful verification; J11 is `5` after closure. Failure and
rejection use the decision-flow return paths, never a success score.

Rendered evidence: [responsibility SVG](user-journey.svg) · [responsibility PNG](user-journey.png)
· [decision SVG](../../diagrams/incident-operator-flow.svg) · [decision PNG](../../diagrams/incident-operator-flow.png)
· [experience SVG](../../diagrams/incident-operator-journey.svg) · [experience PNG](../../diagrams/incident-operator-journey.png).

[`scripts/render_incident_journey.sh`](../../../scripts/render_incident_journey.sh)
renders all three sources and three readable decision-flow phase PNGs without a
repository dependency. Install the pinned CLI outside the repository, then run:

```bash
PUPPETEER_SKIP_DOWNLOAD=true npm install --prefix /tmp/issue150-render \
  --cache /tmp/issue150-npm-cache --no-audit --no-fund @mermaid-js/mermaid-cli@11.12.0
export CHROME_PATH="$(command -v chromium || command -v chromium-browser || command -v google-chrome)"
[[ -x "$CHROME_PATH" ]]
export MMDC_PATH=/tmp/issue150-render/node_modules/.bin/mmdc
scripts/render_incident_journey.sh
```

`CHROME_PATH` must name an executable existing Chrome/Chromium binary; set it
explicitly when the local browser has another name. `MMDC_PATH` defaults to the
path shown above. This documentation-only work adds no runtime harness,
persistent state, migration, transport, or UI behavior.
