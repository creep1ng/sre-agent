# Portable Worktree Setup

## Objective

Provide portable Unix and Windows entrypoints that create a linked Git worktree and same-named branch, copy the main worktree's `.env`, and reuse compatible dependency environments from the invoking or main worktree.

## Problem and Why

Creating a worktree currently requires several manual steps and duplicates expensive dependency environments. The workflow must preserve the main worktree's secrets source while keeping generated Compose identity local to the new worktree.

## Scope

- Add `.sh` and `.bat` entrypoints with shared, testable behavior.
- Generate a collision-free `word-word` name from built-in word lists.
- Create `.worktrees/<name>` and branch `<name>` from the invoking worktree's `HEAD`.
- Copy `.env` only from the main worktree.
- Reuse compatible `.venv` and detected `node_modules` directories, preferring the invoking worktree and falling back to main.
- Run the existing worktree bootstrap so `.env.worktree` remains isolated.
- Add focused automated tests and concise usage documentation.

## Constraints

- Technical artifacts are English.
- Never print `.env` contents.
- Never copy or link `.env.worktree`.
- Never install or mutate dependencies through shared environment links.
- Dependency reuse requires matching manifests/lockfiles.
- Rollback may remove only resources created by the failed invocation.
- Worktree folder and branch names must be identical.
- No merge is authorized by this feature task; delivery is through the stacked PRs
  created after implementation and remains human-owned.

## Authorized Scope

- `scripts/create-worktree.sh`
- `scripts/create-worktree.bat`
- A shared implementation under `scripts/` when needed to avoid duplicated cross-platform logic
- Focused tests under `tests/`
- Related usage documentation and ignore rules
- `docker/api.Dockerfile` checks-stage tooling needed by Git-backed tests
- This task document

## TDD

- Mode: strict
- Source: repository AGENTS.md (`Strict TDD Mode: enabled`)
- Runner: focused pytest command determined from the repository's existing test workflow

## Tasks

- [x] **WT-1 — Specify behavior with failing tests**
  - Cover naming, branch/path identity, caller `HEAD`, main `.env`, dependency-source preference, compatibility checks, collision handling, and rollback.
  - Acceptance: focused tests fail for the missing implementation (RED).
- [x] **WT-2 — Implement portable creation workflow**
  - Add `.sh` and `.bat` entrypoints and shared implementation where appropriate.
  - Acceptance: focused tests pass (GREEN); no secrets are logged; existing bootstrap behavior remains intact.
- [x] **WT-3 — Document and harden the workflow**
  - Document usage, shared-environment caveats, and Windows requirements; add syntax/static checks available in this environment.
  - Acceptance: focused regression checks and structural readback pass after refactor.

## Applicable Checks

- Focused pytest tests for creation and existing bootstrap behavior
- `bash -n scripts/create-worktree.sh`
- `shellcheck scripts/create-worktree.sh` when available
- Windows batch smoke test requires a Windows runner; record unavailable status honestly when not present

## Progress

- WT-1 complete. Focused coverage specifies random collision-free naming,
  caller-HEAD creation, main `.env` copying, compatible dependency selection,
  collision detection, and bounded rollback.
- RED observed with the repository checks container: collection failed because
  `scripts/create-worktree.py` did not exist.
- WT-2 complete. A shared Python implementation now owns Git discovery,
  creation, environment copying, compatibility checks, dependency linking,
  bootstrap execution, and rollback; shell and batch files are thin launchers.
- WT-3 complete. The worktree guide documents both launchers, source/fallback
  behavior, shared-environment mutation risks, editable-install caveats, and
  Windows junction requirements. `.worktrees/` is ignored.
- Independent-audit corrections complete: POSIX `.env` permissions are
  preserved, rollback deletes the branch only after confirmed worktree
  creation, and the Windows junction command keeps untrusted paths out of the
  command string by passing them through fixed environment-variable slots.
- Medium audit follow-up complete: name generation shuffles and exhaustively
  visits the full adjective/noun product without replacement; integration
  coverage proves main `.env` wins over a distinct caller `.env`; rollback
  coverage proves shared caller/main dependency sentinels survive failure.

## Verification Evidence

- RED: `docker compose --env-file .env.example --profile checks run --build --rm python-checks pytest -q tests/test_create_worktree.py tests/test_bootstrap_worktree.py`
  exited 2 with `FileNotFoundError: /app/scripts/create-worktree.py`.
- GREEN: the focused creator and bootstrap suite passed `12 passed` after Git
  was added to the otherwise repository-standard temporary checks container.
- REFACTOR regression: focused creator/bootstrap tests passed `12 passed`;
  Ruff reported `All checks passed!`; container ShellCheck passed without
  findings; `bash -n scripts/create-worktree.sh`, `python3 -m py_compile
  scripts/create-worktree.py`, and `git diff --check` passed.
- Temporary-repository smoke coverage is included in focused pytest: it creates
  real Git primary/caller/target worktrees and verifies branch, HEAD, env,
  dependency links, bootstrap, and rollback.
- Windows batch execution: unavailable (no Windows/cmd or Wine runner present).
- Audit RED: the exact combined check command reported `3 failed, 12 passed`:
  copied `.env` was `0644` instead of `0600`, unconfirmed rollback invoked
  `git branch -D`, and junction construction did not isolate a path containing
  `&` from the `cmd` command string.
- Audit GREEN: the same exact combined command reported `15 passed`; Ruff and
  ShellCheck also passed. Follow-up `bash -n`, `python3 -m py_compile`, and
  `git diff --check` all exited 0.
- Medium follow-up RED: the exact combined command reported `1 failed, 15
  passed`; repeated random selection exhausted 100 attempts despite one free
  adjective/noun combination.
- Medium follow-up GREEN: the same exact command reported `16 passed`; Ruff and
  ShellCheck passed. `bash -n`, `python3 -m py_compile`, and `git diff --check`
  again exited 0. Windows execution remains unavailable locally; the batch and
  junction boundaries have only structural/unit coverage in this environment.
- CI follow-up: the checks image initially lacked Git, causing the real-worktree
  tests to fail with `FileNotFoundError: git`. The checks stage now installs Git
  alongside ShellCheck; complete CI checks then passed Ruff and format checks,
  lock/import/mypy/declarative checks, and `805 passed, 1 skipped` in pytest.

## Next Step

Parent orchestration can mirror this completed document to Engram and perform
the deliverable-boundary review decision. The implementation is split into
stacked PRs #278 and #279; no merge was performed.
