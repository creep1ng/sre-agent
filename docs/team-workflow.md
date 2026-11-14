# Shared agentic delivery workflow

Every contribution follows one reproducible path: **triage → verifiable criteria → route
selection → implementation → verification → evidence → human review → integration**. Gentle AI
helps contributors follow the path; repository documentation and GitHub controls make the result
visible to the whole team.

This guide is the common team baseline for issue #183. It does not contain credentials, private
model settings, or a harness-specific configuration.

## User and scope

Users are independent freelancers maintaining several services. Out of scope: an SRE on-call
team, production hardening, and complex edge-case validation. This is an academic project;
optimize for clear, repeatable behavior over operational coverage.

## Quick path

1. Start from an issue with a bounded problem, owner, estimate, dependencies, and verifiable
   acceptance criteria.
2. Select the direct or SDD route before changing code; record that route in the pull request.
3. Run the relevant checks, collect evidence at the tested SHA, and complete every required PR
   evidence field.
4. Request human review. CI does not read the PR description and requires no separate approval
   comments, labels, or commit confirmations. Integrate only after required checks,
   evidence review, and repository protection rules succeed.

The issue remains the planning record. A partial PR must state what it covers and must not claim
to close the full issue.

Issue status lives in GitHub Project #8, which holds several hundred items.
`gh project item-list` returns only 30 items unless you pass a large `--limit`; to read one
issue's status, prefer `gh issue view N --json projectItems`.

## Team baseline

The evaluated baseline is **Gentle AI 2.5.0**, on the stable release channel. Its documentation
manifest is [gentle-ai-profile.yaml](gentle-ai-profile.yaml); that YAML is deliberately **not** a
native Gentle AI configuration schema.

Use these commands to inspect, not blindly modify, a local installation:

```bash
gentle-ai version
gentle-ai --help
gentle-ai install --scope workspace --dry-run
gentle-ai doctor
```

Install or synchronize only after reviewing the preview and the agent/harness-specific impact.
`gentle-ai install` and `gentle-ai sync` manage local configuration; they do not replace this
repository's documented workflow. Recheck the commands and skill inventory before upgrading the
evaluated version because command flags and skill contents can change between releases.

### Shared versus personal configuration

| Shared in this repository | Personal or harness-specific |
| --- | --- |
| OpenSpec artifacts, this guide, the evaluated version, PR evidence, and route-selection rules | API tokens, `.env`, model choices, editor/browser/terminal adapters, and personal preferences |
| The skill inventory in the documentation manifest | A harness's native config file and its provider-specific format |
| The policy that RDD activation is explicit and user-owned | Whether a user has locally enabled or disabled RDD |

Never commit credentials, local environment files, provider headers, private prompts, raw
production data, or generated traces containing sensitive values.

## Choose the route before implementation

### Direct route

Use a direct route only when the change is small, mechanically understood, and has no unresolved
behavior, contract, or design decision. Write `direct` under `Delivery route` and explain the reason in the PR summary.

**Complete direct example:** correct a wording typo in an existing operator guide. The issue states
the exact replacement; no public behavior changes. Edit the guide, render or preview it, record
the tested SHA and preview command, attach a screenshot showing the rendered result and either a real video or the documented no-video sentence,
then ask a reviewer to confirm the issue criterion.

### SDD route

Use SDD when behavior, a public contract, boundaries, or design choices still need a durable,
reviewable decision. Treat [OpenSpec](../openspec/) as the shared authority for those artifacts;
agent memory and chat history are not substitutes for repository-visible specifications. Write
`sdd` under `Delivery route` and link the change artifacts in the PR.

**Complete SDD example:** add an operator-visible incident action with a new authorization rule.
Create the proposal, requirements/scenarios, design, and tasks in OpenSpec; have the decision and
contract reviewed; implement the approved tasks; run applicable contract and integration checks;
link every criterion to the resulting evidence; complete verification; then archive the accepted
delta into the durable spec. The PR still requires the same screenshot, commands, SHA, and
environment evidence as a direct change; video is optional; without one, write the documented no-video sentence.

SDD is a route-selection tool, not paperwork for trivial edits. Direct work never skips evidence,
security, or human review.

### RDD is opt-in

Receipt-driven development (RDD) is an additional review workflow, not a prerequisite for normal
delivery. Its activation is owned by each user; it is not enabled by this guide, a hook, or the
shared manifest. Inspect the local state without changing it:

```bash
gentle-ai review mode status --cwd .
```

Follow the repository's ordinary review policy whenever RDD is off. Never enable, disable, or
work around RDD on another contributor's behalf.

## Required PR evidence

When a PR requests acceptance, it must provide all of the following. The fields are described
in [PR evidence requirements](pr-evidence.md).

| Requirement | What the reviewer must be able to verify |
| --- | --- |
| Traceability | Linked issue; scope; covered and pending criteria; selected route and any OpenSpec links |
| Reproduction | Tested commit SHA, base, environment, prerequisites, expected versus actual results, and containerized PR commands |
| Demonstration | **One screenshot for every PR**, including documentation-only work; show the actual artifact, not an invented running service. Screenshots and videos are attached to the PR, not committed ([where evidence lives](pr-evidence.md#where-evidence-lives)). A video is optional and must be either a real attachment or link, or the documented no-video sentence. |
| Criterion mapping | Each acceptance criterion maps to a test, request/response, capture, file, or demonstration; label mocks, controlled integration, and live external-service evidence accurately |
| Operational assessment | Risks, compatibility effects, and rollback procedure |
| Sanitization | No secret, sensitive header, personal data, confidential content, or unsafe raw log is attached or linked |

Evidence is tied to the tested SHA. If behavior changes, update it. If a later SHA reuses evidence,
the author explains why it remains valid and the reviewer confirms that explanation.

Keep PRs focused enough to review safely. CI does not enforce a
fixed line limit or require a size-exception label; the maintainer evaluates scope when merging.
When a change grows beyond one reviewable PR (see the 400-line guidance in `AGENTS.md`), prefer a
feature branch delivered as a stack of PRs managed with `gh stack` over a size exception.

No automated check reads these fields (#1081). The reviewer judges whether the screenshot and any video prove the behavior.

### Containerized PR reproduction

The PR's `Reproduction commands` run only through `docker compose` or `docker run`; the host
supplies Git, Docker and safe local configuration. The rule, its examples and the container
pitfalls are in [containerized PR reproduction](pr-evidence.md#containerized-pr-reproduction).

## Peer reproduction exercise

During onboarding, every contributor completes this exercise:

1. Prepare a small issue-linked PR using only this guide and repository documentation.
2. A different contributor checks out the recorded SHA, follows the stated prerequisites and
   commands, and independently reproduces the expected result.
3. The reproducer reviews the criterion-to-evidence mapping, required screenshot, any attached video or the no-video sentence, sanitization, and selected delivery route.
4. Record gaps in the issue or PR and improve the shared documentation before declaring the
   onboarding exercise complete.

This exercise tests the workflow, not an individual's memory or private setup.

## Integration responsibility

The author supplies accurate evidence and updates it when needed. The reviewer independently
checks scope, reproducibility, evidence sufficiency, and sanitization. Maintainers decide a
size exception and administer branch/ruleset protection after a pilot proves the controls block
invalid PRs. No workflow may execute commands or
download arbitrary URLs supplied by a PR description.

The repository accepts only merge commits; squash and rebase merges are disabled, so integrate
with `gh pr merge --merge`. Head branches are deleted automatically on merge; check that any
stacked PR now targets the intended base before integrating it.

For staged rollout, see [governance rollout](governance-rollout.md). For CI control ownership and
non-blocking diagnostic proposals, see [CI control inventory](ci-controls.md).
