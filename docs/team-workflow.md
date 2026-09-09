# Shared agentic delivery workflow

Every contribution follows one reproducible path: **triage → verifiable criteria → route
selection → implementation → verification → evidence → human review → integration**. Gentle AI
helps contributors follow the path; repository documentation and GitHub controls make the result
visible to the whole team.

This guide is the common team baseline for issue #183. It does not contain credentials, private
model settings, or a harness-specific configuration.

## Quick path

1. Start from an issue with a bounded problem, owner, estimate, dependencies, and verifiable
   acceptance criteria.
2. Select the direct or SDD route before changing code; record that route in the pull request.
3. Run the relevant checks, collect evidence at the tested SHA, and complete every required PR
   evidence field.
4. Request independent human review; Codex or other bots may assist. Integrate only after required checks, evidence review, and
   repository protection rules succeed.

The issue remains the planning record. A partial PR must state what it covers and must not claim
to close the full issue.

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
the tested SHA and preview command, declare `Visual applicability: no` with the
text-only reason, link the concrete Markdown file and expected/actual result, then ask
a reviewer to confirm the issue criterion. A screenshot is not required.

### SDD route

Use SDD when behavior, a public contract, boundaries, or design choices still need a durable,
reviewable decision. Treat [OpenSpec](../openspec/) as the shared authority for those artifacts;
agent memory and chat history are not substitutes for repository-visible specifications. Write
`sdd` under `Delivery route` and link the change artifacts in the PR.

**Complete SDD example:** add an operator-visible incident action with a new authorization rule.
Create the proposal, requirements/scenarios, design, and tasks in OpenSpec; have the decision and
contract reviewed; implement the approved tasks; run applicable contract and integration checks;
link every criterion to the resulting evidence; complete verification; then archive the accepted
delta into the durable spec. The PR still requires commands, SHA, environment and an
explicit visual-applicability decision; a screenshot is required only for changed visual surfaces.

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

When a PR requests acceptance, it must provide all of the following. The canonical field syntax
and validator behavior are in [PR evidence requirements](pr-evidence.md).

| Requirement | What the reviewer must be able to verify |
| --- | --- |
| Traceability | Linked issue; scope; covered and pending criteria; selected route and any OpenSpec links |
| Reproduction | Tested commit SHA, base, environment, prerequisites, expected versus actual results, and containerized PR commands |
| Demonstration | Declare exactly one visual-applicability statement with a reason. A changed UI, wireframe or Swagger UI needs a screenshot of the actual surface; documentation, backend and tests-only changes use concrete file/scenario evidence instead. Mixed changes need both. Video is optional. |
| Criterion mapping | Each acceptance criterion maps to a test, request/response, capture, file, or demonstration; label mocks, controlled integration, and live external-service evidence accurately |
| Operational assessment | Risks, compatibility effects, and rollback procedure |
| Sanitization | No secret, sensitive header, personal data, confidential content, or unsafe raw log is attached or linked |

Evidence is tied to the tested SHA. If behavior changes, update it. If a later SHA reuses evidence,
the author explains why it remains valid and the reviewer confirms that explanation.

The review-size limit is **400 added plus deleted lines**. It has no silent exclusion. An oversized
PR needs the `size:exception` label, a specific reason, and a link to an identified maintainer's
approval. The exception never waives security, evidence, checks, or review.

Automated validation can check field presence, visual applicability and references. It requires a real screenshot only when applicability is `yes`; it cannot establish that the classification or evidence proves behavior. The human reviewer owns that judgement.

### Containerized PR reproduction

The PR's `Reproduction commands` are contributor-facing demo commands. Every command in that
fenced block must use `docker compose` or `docker run`; do not provide host `uv`, `npm`, `pytest`,
or equivalent package-tool commands. The host prerequisites are Git, Docker, and safe local
configuration preparation, recorded under `Environment`. Tools may execute as arguments within
the selected container.

Declare any untracked `.env` prerequisite under `Environment`, using `.env.example` as the
starting point and local non-production values. Compose interpolates the complete file before
profile filtering, so even a `checks`-profile demonstration needs every required configuration
value present. Do not paste, source, print, commit, or attach that file. Docker confines
execution, but does not automatically pin image tags or dependencies: record the tested SHA and
relevant image build/lockfile provenance with the command.

Use existing Compose services only. The present isolated checks and harness support these examples:

```sh
docker compose --profile checks run --build --rm python-checks pytest -q tests/test_authentication.py
docker compose --profile checks run --build --rm harness npm --prefix schemas/tooling run conformance -- --consumer issue-10
```

Both package tools run inside the containers. These one-shot commands avoid a global volume
teardown; do not add `docker compose down -v` to a PR demo. A change that needs a running service
must use the existing scoped Compose service and state its safe project-specific cleanup.

This rule applies to PR reproduction and demonstration, not GitHub Actions' internal runner
commands. The current metadata validator only confirms a nonempty fenced block, so the reviewer
must enforce the container boundary during evidence review.

## Peer reproduction exercise

During onboarding, every contributor completes this exercise:

1. Prepare a small issue-linked PR using only this guide and repository documentation.
2. A different contributor checks out the recorded SHA, follows the stated prerequisites and
   commands, and independently reproduces the expected result.
3. The reproducer reviews the criterion-to-evidence mapping, visual applicability,
   any required screenshot, any linked video, sanitization, and selected delivery route.
4. Record gaps in the issue or PR and improve the shared documentation before declaring the
   onboarding exercise complete.

This exercise tests the workflow, not an individual's memory or private setup.

## Integration responsibility

The author supplies accurate evidence and updates it when needed. The reviewer independently
checks scope, reproducibility, evidence sufficiency, and sanitization. Reviewers may use
Codex or other bots, but must validate findings and explain the scenario, impact and next
step in clear language before sharing them. Tool assistance does not replace the human
approval required by repository policy. See [review feedback guidance](pr-evidence.md#clear-actionable-review-feedback).
Maintainers decide a
size exception and administer branch/ruleset protection after a pilot proves the controls block
invalid PRs. GitHub Actions validates only untrusted PR metadata; it must not execute commands or
download arbitrary URLs supplied by a PR description.

For staged rollout, see [governance rollout](governance-rollout.md). For CI control ownership and
non-blocking diagnostic proposals, see [CI control inventory](ci-controls.md).
