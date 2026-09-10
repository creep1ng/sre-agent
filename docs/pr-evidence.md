# Pull-request acceptance evidence

Every PR submitted for acceptance, including documentation, infrastructure, contracts
and tests-only changes, needs a screenshot and reproducible commands. Video is optional while media storage is unavailable: use a real HTTPS recording link or write exactly `Deferred: media storage unavailable; screenshot evidence is mandatory.`. Do not invent a URL. Use the repository template's exact English headings; HTML guidance comments are ignored.
Drafts may be incomplete but cannot receive a passing `pr-governance` status.

## Author path

1. Reference the issue. Use `Refs #183` for a partial work unit; do not close an
   issue whose criteria remain pending. Declare `direct` or `sdd` as the delivery route.
2. Map each covered criterion to its scenario, actual result and HTTPS evidence.
   For SDD include the shared `openspec/changes/` or `openspec/specs/` path.
3. Record full tested and base commit SHAs, environment versions, data provenance,
   prerequisites and commands in a `sh`, `bash` or `shell` fenced block. The PR's
   reproduction commands must invoke `docker compose` or `docker run`; `uv`, `npm`,
   `pytest`, and similar tools may appear only as commands executed inside the selected
   container.
4. Link a real HTTPS screenshot. Optionally link a real HTTPS recording; while media storage is unavailable, use the exact documented deferral instead. Use an appropriate rendered artifact for documentation; do not invent a running server for a textual or contract change.
5. Explain expected/actual results, remaining scope, compatibility and rollback.
   Sanitize all evidence, then declare exactly `Sanitized: yes` in Security.
6. Obtain ordinary independent human review. CI does not prove semantic acceptance.

Inspect candidate identity and size without running PR-provided commands:

```sh
gh pr view 183 --json number,headRefOid,baseRefOid,additions,deletions,baseRefName
```

Here `183` is an illustrative **PR** number, not a claim that issue #183 is a PR.
Replace it with the actual PR number. Count all additions plus deletions against
its current base, including lockfiles, generated files and fixtures, never net lines.

## Containerized PR reproduction

The `Reproduction commands` section is a demo contract: every command in its fenced
block starts a container with `docker compose` or `docker run`. The host is limited to
Git checkout, Docker, and safe local configuration preparation declared in `Environment`.
Do not list host `uv`, `npm`, `pytest`, or equivalent package-tool commands as how-to-test
steps; pass them to the appropriate container instead.

Before reproducing a change, the author declares the required local configuration in
`Environment` (for example, an untracked `.env` based on `.env.example`, with local
non-production values). Compose interpolates the complete file before profile filtering, so even
a `checks`-profile demonstration needs every required configuration value present. Do not paste,
source, print, or attach that file. Docker provides a reproducible execution boundary, but it
does **not** by itself pin images or dependencies: record the tested SHA and relevant image
build/lockfile provenance alongside the command.

Use only services that already exist in `compose.yaml`. For example, the current isolated
checks and contract harness can be demonstrated without host package managers or a destructive
volume teardown:

```sh
docker compose --profile checks run --build --rm python-checks pytest -q tests/test_authentication.py
docker compose --profile checks run --build --rm harness npm --prefix schemas/tooling run conformance -- --consumer issue-10
```

These commands run Python and npm inside `python-checks` and `harness`, respectively. They
may create only the profile's ephemeral/one-shot resources; do not add `docker compose down -v`
or another global teardown to PR reproduction instructions. If a demonstration needs a running
service, use its existing scoped Compose service and document the safe, project-specific cleanup.

This policy governs contributor-facing PR reproduction and demo commands. It does not prescribe
or validate internal GitHub Actions runner steps. The current metadata validator checks only a
nonempty fenced command block; a human reviewer must verify that the PR follows this container
boundary.

## Evidence boundaries

Choose exactly one primary Evidence kind: `mock`, `controlled integration`,
`real external service`, or `rendered artifact`. Explain mixed surfaces in the
criterion mapping. A schema mock is valid contract evidence but cannot close a
real-provider integration criterion. A Swagger screenshot alone does not prove
an endpoint executes successfully. Passing tests complement observable behavior.

Acceptable: a documentation PR records its rendered page, the requested change,
an image, exact build/preview command, SHA and expected/observed result.
Unacceptable: only a test count, unrelated screenshot, example.com link,
placeholder, or a claimed live integration demonstrated with a fixture.

Screenshots, any recordings, commands and artifacts must exclude API keys,
Authorization headers, personal data, full prompts/outputs and sensitive request
payloads. Use controlled synthetic data. Never upload `.env` or unfiltered dumps.
Secret scanners are complementary and do not certify images or videos as safe.

## Human acceptance

CI validates the PR description and candidate metadata; it does not authorize a merge.
It does not require approval comments, labels, or per-commit confirmations. The maintainer
reviews evidence freshness, scope, size, governance changes, and risk once when deciding
whether to merge. Keep independent work in focused PRs when that improves reviewability,
but no fixed line-count exception is enforced.

If multiple open PRs share the exact same head SHA, `pr-governance` fails closed because
commit statuses cannot distinguish them. Use distinct candidates or close the redundant
proposal before asking for acceptance.

## What automation does and does not prove

`pr-governance` rejects missing/duplicate sections, empty command blocks,
placeholders, a missing screenshot HTTPS reference, a video that is neither an HTTPS reference nor the exact documented deferral, stale base SHA, unsupported delivery/evidence kinds, and incomplete size data. It never executes supplied
commands, downloads evidence, judges videos, or verifies that a named OpenSpec
path really satisfies the issue. A human checks those claims and the DoD checklist.

The workflow loads policy only from the resolved default-branch commit, never the
PR branch, and uses no repository secrets. `statuses: write` is limited to the
trusted metadata job so the result can be attached to the PR head rather than the
`pull_request_target` base. It never checks out or executes untrusted PR code.

Every run reconciles all open PRs from current API data, with a fresh snapshot before
publishing. Pull-request events handle PR edits and pushes.
A 15-minute scheduled reconciliation covers base advances;
GitHub scheduling can be delayed, so this is eventual revalidation, not an atomic
merge authorization service. Dispatch manually after a base advance before integrating.
All failures are candidate-bound and summaries omit raw descriptions/attachments.
Unchanged conclusions are not republished, avoiding redundant status history.

The workflow must first land on the default branch to bootstrap trusted loading.
Do not require this status before a successful live pilot. See
[rollout and administrative authorization](governance-rollout.md).
