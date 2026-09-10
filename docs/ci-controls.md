# CI control inventory

Issue #183 makes candidate verification reproducible without claiming that a
local workflow is an active GitHub merge rule. `Quality gate` becomes enforceable
only after the hosted pilot and administrative activation in
[governance-rollout.md](governance-rollout.md).

## Required candidate path

Each required job has a timeout, Actions permissions are `contents: read`, and
all actions use reviewed full SHAs. Pull requests stop before expensive stages
when an earlier required stage fails; scheduled diagnostics retain `always()`
paths for investigation. The final gate accepts only `success` from every
required job; failed, cancelled, skipped, neutral, or missing work fails closed.

| Stage | Control | Boundary protected |
| --- | --- | --- |
| Configuration lock | Build the runtime image with `uv sync --locked --no-dev` | Manifest/lock drift and runtime dependency resolution |
| Checks image | Ruff, `lint-imports`, scoped strict mypy, shell and declarative validators | Style, architecture imports, typed interfaces and contract metadata |
| Unit and contracts | Locked Compose Python checks and Node harness | Application behavior and published schemas |
| Compose smoke | Candidate API, web, database, migration, seed and harness | Startup and composed-service behavior |
| Production browser | Containerized Playwright against the candidate API/web images and isolated PostgreSQL | Delivered image, proxy, network and browser behavior |
| Quality gate | Candidate/head/base summary retained 30 days | No skipped or failed required stage becomes an approval |

The check image is separate from runtime. It owns Ruff, Import Linter, mypy,
pip-audit and mutation tooling; the runtime image copies only the production
virtual environment. Both images install Python dependencies from `uv.lock`.
Python, Node, Nginx and PostgreSQL bases are version-tagged and digest-pinned;
the Playwright runner is likewise pinned to the lockfile's `1.63.0` package.

### Architecture and typing controls

`.importlinter` rejects direct and indirect dependencies from `incident` or
`governance` to concrete persistence, gateway, control or composition modules.
It rejects persistence dependencies on delivery/composition, while allowing the
persistence incident adapter to consume incident ports. Incident runtime and
ports cannot bring FastAPI, SQLAlchemy or HTTP client dependencies across their
boundary. YAML and Pydantic are deliberately not forbidden.

Mypy is strict only for `incident.persistence`, `incident.runtime`,
`governance.dto`, and `governance.authorization`, with the Pydantic plugin.
This is a deliberate incremental baseline: changing scope or adding a narrow
exception requires governance review, rather than a broad ignore.

### Production-image browser control

`compose.e2e.yaml` removes database, API and web host ports. A project-scoped
Compose network starts migration and synthetic seed before API and web become
healthy. The Playwright runner has no application source mount and does not
start Uvicorn: it receives only the browser test inputs and calls `http://web`.
Its production-image scope is deliberately limited to the same-origin API-client
seam and production proxy behavior; it is not represented as full UI coverage.
The existing static-web job retains the showcase interaction and accessibility
coverage separately. A second runner reaches a deliberately bad Nginx upstream
and is required to fail its API assertion; a pass is treated as a broken
negative test. CSP remains production-safe: this control does not permit inline
scripts, inline styles, `unsafe-inline`, or `unsafe-eval`.

The safe local reproduction shape is:

```sh
docker compose -f compose.yaml -f compose.e2e.yaml --project-name issue183-demo up --build --wait db api web
docker compose -f compose.yaml -f compose.e2e.yaml --project-name issue183-demo --profile e2e run --build --rm e2e
docker compose -f compose.yaml -f compose.e2e.yaml --project-name issue183-demo down -v --remove-orphans
```

Use a unique project name and only remove that project. The local `.env` remains
untracked and synthetic; do not print, commit, attach or reuse credentials.

## Informational diagnostics

`Quality diagnostics` runs weekly and by manual dispatch. It is not a required
PR check and never changes dependencies. It builds the locked checks image and:

- audits Python dependencies with pinned `pip-audit`, reporting unavailable or
  malformed results rather than a false clean state;
- audits both locked Node installations (the root and `schemas/tooling`) in a
  digest-pinned Node container; each matrix result is informative and visible;
- measures branch coverage over `src/sre_agent` in the existing locked Compose
  checks container, with no threshold or exclusions;
- copies the complete `src` package into an isolated temporary workspace, then
  mutates only `governance.authorization` while selecting its governing tests,
  with a 14-minute tool timeout inside a 20-minute job so image build, summary
  and cleanup retain budget;
- reports process errors separately from per-mutant no-test, skipped, suspicious, timeout, interruption and segfault counters; a shell timeout is explicitly incomplete.

Mutation testing has no PR threshold. It is evidence about test sensitivity;
survivors require a human decision and only motivate a test when they expose a
missing assertion for an already specified behavior.

## Administrative controls outside the repository

After a hosted pilot, require the exact observed `Quality gate` check run and
`pr-governance` status, stale-review dismissal, latest-push approval, and resolved
conversations. Set GitHub's native required-approval count to `0`; the maintainer's
merge decision is the human acceptance step, without separate custom confirmations.
Restrict governance, CI, lockfile, image, import-boundary and production-browser changes
to designated human reviewers. Preserve separate merger authorization while removing only
the quality ruleset bypass. Native GitHub secret scanning and push protection were already
enabled and read back; neither is created by these workflow files.
