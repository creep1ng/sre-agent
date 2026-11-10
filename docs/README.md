# Documentation index

What each live document covers. Start with the [vision](vision.md), then the
[team workflow](team-workflow.md); the vocabulary is in the glossary of
[AGENTS.md](../AGENTS.md#glossary).

## Product and decisions

- [Vision and values](vision.md): what Midnight is for and the seven values a change is weighed against.
- [Product direction](product-direction-2026-10-28.md): the maintainer's decisions, round by round. Dated by design and kept live.
- [Backlog to 2026-12-04](backlog-2026-12-04.md): milestones and the stories in each. Dated by design and kept live.

## Architecture and contracts

- [Runtime and persistence boundaries](architecture.md), with the [change checklist](architecture.md#change-checklist).
- [Incident command runtime](incident-runtime.md) and the [incident run contract for consumers](incident-run-contract-consumers.md).
- [Investigator](investigator.md): the bounded investigation loop and its E2E journeys.
- [Interrupt policy](interrupt-policy.md): when Midnight wakes a person.
- [Incident postmortem](incident-postmortem.md).
- [Alert intake from Grafana](alert-intake.md) and [change events](change-events.md).
- [BoK retrieval](bok-retrieval.md) and the [governed Skill demo](skill-demo.md).
- [Deploy executor](deploy-executor.md): the catalog's remediation operations over docker-socket-proxy.
- [Telegram channel](telegram-channel.md).
- [Same-origin browser–API seam](browser-api-seam.md).
- [Contract 2.0.0 migration](contracts/2.0.0-migration.md); the contracts themselves are in
  [`schemas/`](../schemas/), with the release in force pinned in
  [`releases.lock.json`](../schemas/releases.lock.json).
- Decision records: [ADR-007](adrs/ADR-007-harness.md) (investigator loop),
  [ADR-008](adrs/ADR-008-run-events-transport.md) (run events), and the contract ADRs in
  [`schemas/adrs/`](../schemas/adrs/).
- Security: [threat model](security/threat-model.md) and
  [responses credential matrix](security/responses-credential-matrix.md).

## Running the stack and the demo

- [Isolated worktree environments](codex-worktrees.md), including troubleshooting a shared host.
- [Prepare SRE with one command](setup-sre.md).
- [Local full flow](local-flow/README.md): from a Grafana alert to the decision on one machine.
- [OTel Demo on EC2](otel-demo-ec2.md), [demo environment operations](demo-env.md) and
  [demo signals](demo-signals.md).
- [Governed Grafana MCP demo](governed-grafana-mcp-demo.md).

## Delivering a change

- [Team workflow](team-workflow.md): triage to integration, and the direct and SDD routes.
- [PR evidence](pr-evidence.md): the required evidence and the containerized reproduction.
- [Code-quality indicators](quality-indicators.md) of EP-14.
- [CI control inventory](ci-controls.md) and [governance rollout](governance-rollout.md).
- SDD artifacts live in [`openspec/`](../openspec/).

## Design and research

- [Brand round 1](design/brand-round-1/README.md), the [integrated console shell](design/ht-web-shell/ht-web-shell.md),
  the [operator incident journey](design/ht-inc-07-ux-journey/ht-inc-07-ux-journey.md) and the
  [control-plane wireframes](design/ht-ctrl-02/ht-ctrl-02-control-plane-wireframes.md).
- Designs of one story: [historical request attribution](design/issue-454-historical-attribution.md)
  and [controlled external effects](design/issue-567-controlled-effects.md).
- Spikes: [harness evaluation](spikes/ht-06-harness-evaluation.md) and
  [Jev as a mitigation scorer](spikes/jev-decision-model.md).

## Historical material

Versioned, but no longer describing how the system works today, and hidden from an unfiltered
`rg` by [`.rgignore`](../.rgignore) (`rg --no-ignore-dot` searches it too):

- [`docs/archive/`](archive/): runbooks, plans and acceptance records of one issue, sprint or date,
  such as the [governance pilot record](archive/governance-pilot.md) of #183.
- [`scripts/archive/`](../scripts/archive/) and [`compose/archive/`](../compose/archive/): scripts and
  Compose overlays of one issue or proof of concept that neither CI, `compose.yaml`, `docker/`,
  `tests/`, the README, AGENTS.md nor a live document uses. Run them from the repository root, as
  before (`python scripts/archive/...`, `docker compose -f compose.yaml -f compose/archive/...`).
- [`openspec/changes/archive/`](../openspec/changes/archive/), [`odd/`](../odd/), and the contract
  releases before the one in force under [`schemas/releases/`](../schemas/releases/).
- Evidence committed before #1018 opens at
  [`0cb2ad44`](https://github.com/creep1ng/sre-agent/tree/0cb2ad441e4f9923f3ff6d804dc59a6cfc51aa63/docs/evidence).
