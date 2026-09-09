# Issue 183 local validation record

This records configuration verification and a narrow hosted-CI failure/recovery;
it is not peer acceptance or a live merge-blocking demonstration. The implementation baseline is integrated main
`a21d8914cafbf2a291d78b1ac641726b48f12501`. No public contract or migration was changed. The expanded CI slice adds only browser harness adjustments and new control configuration/tests; it does not alter application behavior. The pre-publication candidate was prepared in the
`codex/issue-183-governance` worktree.

## Executed locally

The expanded CI controls were validated as configuration and local boundary checks. These results are not hosted CI, peer acceptance, or a live merge-blocking demonstration. Do not infer an activated GitHub protection from local execution.

| Verification | Observed result |
| --- | --- |
| `node --check .github/governance/pr-evidence.cjs` | Pass |
| Temporary metadata/API simulation harness | 25 scenarios pass |
| Extracted Quality gate shell, all jobs successful | Pass |
| Each of seven jobs set to failure/cancelled/skipped/neutral/empty | All 35 combinations fail closed |
| Gate dependency inventory | Every mandatory CI job included |
| Compare original/current existing suite commands | Python, PostgreSQL, contracts, browser and Compose test invocations preserved |
| `actionlint` 1.7.7 on all three workflow files | Pass |
| `python scripts/validate_ci_hardening.py` | Pass |
| `pytest -q tests/test_ci_hardening.py` | 5 passed |
| `ruff check .` and `ruff format --check .` | Pass; 83 files already formatted |
| Import Linter copied-candidate regression | Direct and indirect temporary incident-runtime-to-persistence imports fail; the unchanged persistence incident adapter passes. Earlier false passes resolved installed `/app` code rather than the copied candidate, not a contract failure. |
| Mypy RED/GREEN probe | A temporary incompatible `int` assignment failed; scoped strict configuration passes |
| Lockfile RED/GREEN probe | Temporary manifest/lock mismatch failed; restored `uv lock --check` passes |
| Checks image + full Python suite through scoped Compose | `763 passed, 1 skipped`; the isolated `issue183-python-final` project was removed |
| Runtime and checks Docker builds | Pass using verified pinned image digests and `uv sync --locked` |
| Isolated production Compose startup | Pass: database, migration, synthetic seed, API and web reached their declared states without E2E host ports |
| Mutation diagnostic | Completed in an isolated copied workspace: corrected rerun has 83 total and 83 killed, with 0 survived/no-test/skipped/suspicious/timeout/interrupted/segfault mutations. The exporter writes JSON to `mutants/mutmut-cicd-stats.json`; the workflow now reads that file rather than exporter stdout. |
| Survivor disposition | Initial safe IDs `evaluate__mutmut_6`, `_7`, `_19`, `_20`, `_21`, `_22` replaced exact resource type/id or grant principal/action/resource lookup arguments with `None`. They exposed missing assertions of the existing reader-contract identity, not new behavior. The test double now records exact arguments; corrected rerun killed all six. |
| Final checks-image boundary subset | Lock check, Import Linter and scoped mypy pass; `37 passed` for runtime, copied-candidate import, mutation configuration and authorization tests after the correction |
| Static showcase browser smoke | Verifier: `2 passed` of 2; production-only API seam and proxy specs are excluded from this static server lane. |
| Production-image browser control | Hosted run `34274635594` initially found two host-only fixture assumptions (2 passed, 2 failed). The correction was rerun once with CI-equivalent ephemeral inputs: `4 passed`; API/web were candidate images, API/web had zero source mounts and host ports, and scoped cleanup removed its containers, network and volume. The production topology asserts the seeded unprivileged demo's concealed 404; revoked-credential and forwarded-header assertions stay in the host harness. |
| YAML parsing and `git diff --check` | Pass |

The temporary harness lives outside the repository at `/tmp/issue183-pilot.cjs`.
It covers 400/401 lines, approved size, label removal, wrong permission,
missing mandatory evidence, empty template, placeholder/duplicate sections,
changed base, evidence reuse, write-independent confirmation, admin/maintain self-attestation,
comment revocation, bot denial,
command injection remaining inert data, SDD path requirements, snapshot changes,
head-bound status publishing, unchanged-status deduplication and a metadata race. It does not create public PRs
or alter repository tests. Preserve its output with the final publication evidence;
temporary local paths are not a shared test suite or proof of hosted execution.

Reproduce the static checks using the project development environment and pinned
`actionlint` installed outside the project dependency files:

```sh
node --check .github/governance/pr-evidence.cjs
actionlint .github/workflows/ci.yml .github/workflows/pr-governance.yml .github/workflows/quality-diagnostics.yml
python scripts/validate_ci_hardening.py
pytest -q tests/test_ci_hardening.py
ruff check .
ruff format --check .
git diff --check
```

## Remote changes verified

GitHub API readback confirms native secret scanning and push protection enabled.
Both existing rulesets are unchanged. Issue #183 was amended to the approved scope,
preserving title, state, labels, assignees and milestone. Its approval label was
not granted by this implementation. The stale-context overlap with #144 is linked,
not automatically closed.

## Required before acceptance

- Publish reviewable work units through the approved-issue policy.
- Capture a screenshot of the actual delivered result at its published SHA. Video is optional while media storage is unavailable; include a real link or the documented deferral, never a fabricated URL.
- Complete the hosted negative/positive scenarios in the rollout guide.
- Have another contributor reproduce and judge the evidence independently. An admin/maintain evidence or governance self-attestation is not semantic independent review; GitHub-native required approvals remain `0` because authors cannot self-approve. `creep1ng` is the planned independent reproducer/reviewer; this is pending, not an approval.
- Run the same diagnostics in hosted GitHub Actions after publication; local pass evidence does not establish a hosted check or merge protection.
- Obtain an explicit `size:exception` approval before publishing any work unit containing the current `uv.lock` update, which alone exceeds the 400-line limit.
- Verify diagnostics in hosted Actions and dependency-audit network behavior.
- Obtain explicit maintainer activation confirmation, apply and read back required
  contexts/review settings, then prove the effective integration block.

Until those steps finish, report **enforcement partial** and **RDD disabled/unmanaged**.
