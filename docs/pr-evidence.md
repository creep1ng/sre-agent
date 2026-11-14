# Pull-request acceptance evidence

Every PR submitted for acceptance, including documentation, infrastructure, contracts
and tests-only changes, needs a screenshot and reproducible commands. Video is optional: attach a real recording, or write exactly `Not recorded; screenshot evidence is mandatory.`. Do not invent a URL. Use the repository template's English headings.
No automated check reads the description (#1081 retired the `pr-governance` status), so the
template is a guide for the author and the reviewer.

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
4. Attach a real screenshot to the PR (see [Where evidence lives](#where-evidence-lives)). Optionally attach a real recording; without one, write the exact no-video sentence instead. Use an appropriate rendered artifact for documentation; do not invent a running server for a textual or contract change.
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

Container pitfalls that silently invalidate evidence:

- Piping a script into `docker run` without `-i` exits 0 without executing it, because stdin is
  not attached. Prefer mounting the script read-only and require the artifact it writes; when
  comparing hashes between host and container, compare the digest only, not whole `sha256sum`
  lines, whose paths differ.
- Playwright deletes its `outputDir` at startup, so pointing it at a bind-mount root fails with
  `EACCES`. Use a child of the mount (for example
  `PLAYWRIGHT_OUTPUT_DIR: /artifacts/test-results`) or a path under `/tmp`.
- The static browser suites (`playwright.config.js`, `playwright.api.config.js`) expect the
  loopback origin `http://127.0.0.1:4173`: run Playwright in the server container's network
  namespace. A non-loopback HTTP origin such as `http://web` is not a secure context and lacks
  `crypto.randomUUID`; never stub it or weaken assertions to pass. See
  [issue 25 closure verification](https://github.com/creep1ng/sre-agent/blob/0cb2ad441e4f9923f3ff6d804dc59a6cfc51aa63/docs/evidence/issue-25-closure-verification.md).

This policy governs contributor-facing PR reproduction and demo commands. It does not prescribe
or validate internal GitHub Actions runner steps. No check validates it; the reviewer verifies
that the PR follows this container boundary.

For Compose failures on a shared host (exhausted Docker address pools, a lingering checks
database, migration suites that need their own PostgreSQL cluster), see
[troubleshooting local stacks](codex-worktrees.md#troubleshooting-local-stacks).

## Evidence boundaries

Choose exactly one primary Evidence kind: `mock`, `controlled integration`,
`real external service`, or `rendered artifact`. Explain mixed surfaces in the
criterion mapping. A schema mock is valid contract evidence but cannot close a
real-provider integration criterion. A Swagger screenshot alone does not prove
an endpoint executes successfully. Passing tests complement observable behavior.

Acceptable: a documentation PR records its rendered page, the requested change,
an image, exact build/preview command, SHA and expected/observed result.
Real behavior proof must be FastAPI output, SQL query output, UI, or exact
instructions to repeat the expected behavior.
Unacceptable: only a test count, unrelated screenshot, example.com link,
placeholder, invented SVG, generated capture, or a claimed live integration
demonstrated with a fixture.

## Where evidence lives

Maintainer decision (2026-11-09): evidence for new PRs, screenshots and videos, is attached to
the PR body or to a PR comment, not committed. Dragging a file into the editor makes GitHub
insert an `<img src="https://github.com/user-attachments/assets/…">` tag for an image and a bare
`https://github.com/user-attachments/…` URL for a video; leave either as GitHub wrote it. GitHub
accepts images, and `.mp4`, `.mov` and `.webm` videos up to 10 MB on the free plan and 100 MB on
paid plans ([attaching files](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/attaching-files)).
Evidence that is neither image nor video (JSON, TXT, SQL, logs) goes as an attached file in a PR
comment (`.json`, `.txt`, `.log`, `.sql`, `.md`, `.csv`, `.zip`, `.gz`, up to 25 MB), or as text
inside a `<details>` block of the PR body, in a code fence.

The repository is public, and so are its attachments: anyone can open them without signing in.
The sanitization rule below applies to them in full.

An agent cannot upload attachments through `gh` or the REST API. When an agent prepares a PR, it
leaves each file at a path it reports, fills every other section, and the maintainer attaches
the files by hand.

E2E runs and capture scripts write to directories git ignores (`artifacts/` at the root,
`web/incident-console/e2e/artifacts/`); attach what a PR needs from there. `docs/evidence/` left
git in #1018 and `.gitignore` keeps it out. Evidence committed before then opens on GitHub at
[`0cb2ad44`](https://github.com/creep1ng/sre-agent/tree/0cb2ad441e4f9923f3ff6d804dc59a6cfc51aa63/docs/evidence),
and the maintainer keeps a local copy of that tree with its `SHA256SUMS`.

Screenshots, any recordings, commands and artifacts must exclude API keys,
Authorization headers, personal data, full prompts/outputs and sensitive request
payloads. Use controlled synthetic data. Never upload `.env` or unfiltered dumps.
Secret scanners are complementary and do not certify images or videos as safe.

## Human acceptance

CI runs the candidate's checks. It does not read the PR description and does not authorize a
merge, and it requires no approval comments, labels, or per-commit confirmations. The maintainer
reviews evidence freshness, scope, size, governance changes, and risk once when deciding
whether to merge. Keep independent work in focused PRs when that improves reviewability,
but no fixed line-count exception is enforced.

Reviewers may use Codex or other bots to assist a review. The human reviewer validates every
finding, restates it plainly and actionably, and remains the accountable acceptance step; a bot
finding is never an acceptance by itself.

## What automation does and does not prove

`Quality gate` runs the candidate's code: the checks image, the unit and contract suites and the
composed-stack journeys listed in [CI controls](ci-controls.md). No workflow reads the PR
description, so nothing automated checks that its sections are complete or that the evidence
satisfies the issue. The reviewer checks those claims and the DoD checklist.

A `pr-governance` commit status used to validate the shape of the description. #1081 retired it
because it checked the form of the description, not the delivery. How a PR should prove that it
delivers its issue's criteria is open in #1083.
