# CI control inventory

Issue #183 makes candidate verification reproducible without claiming that a
local workflow is an active GitHub merge rule. `Quality gate` becomes enforceable
only after the hosted pilot and administrative activation in
[governance-rollout.md](governance-rollout.md).

## Required candidate path

Each required job has a timeout, Actions permissions are `contents: read`, and
all actions use reviewed full SHAs. Pull requests stop before expensive stages
when the runtime or checks image fails. After the checks image, the unit, contract,
static-web and composed-stack paths run in parallel, so a unit failure no longer
holds back the browser jobs; scheduled diagnostics retain `always()` paths for
investigation. The final gate accepts only `success` from every
required job; failed, cancelled, skipped, neutral, or missing work fails closed.

The one exception is a documentation-only pull request. The `changes` job runs first and
classifies the pull request as documentation-only when every changed path is under `docs/` or
is a root-level `*.md` file, and no file outside `docs/` and `*.md` names that path. For
example, `tests/test_mcp_overlay.py` reads `docs/governed-grafana-mcp-demo.md`, so a change to
that runbook runs the full path. A documentation-only pull request skips every build and test
job, and the gate then requires each of them to be `skipped` and `changes` to be `success`.
Pushes to `main` and scheduled runs never skip, so they still run the full path after a
documentation-only merge.

`contracts` also runs only when a pull request changes a contract input: `schemas/`, the
harness image (`docker/harness*`), `compose.yaml` or this workflow. The harness container
mounts only `schemas/` and `scripts/`, and none of its CI commands reads `scripts/`. Otherwise
the gate requires `contracts` to be `skipped`, and `compose-smoke` accepts that skip.

When `contracts` runs on a pull request or a push to `main`, it validates only the newest
published release in full and checks every older one against `schemas/releases.lock.json`
(`validate:releases:locked`). The lock pins the digest of each release's `manifest.yaml`, and
the manifest pins the digest of every other file of that release and of the ADRs, so changing
any published file fails: either the recomputed manifest differs from the committed one or the
manifest no longer matches its pinned digest. A step before the harness also fails when the
change edits or removes a digest the base commit already pinned, so a release cannot be
rewritten together with its lock entry. The nightly schedule still revalidates every release in
full (`validate:releases`). Publishing a release adds its digest with
`npm --prefix schemas/tooling run lock:releases`, which validates the unpinned releases in full
first.

| Stage | Control | Boundary protected |
| --- | --- | --- |
| Changes | Classify the pull request's changed paths | Only documentation no code reads skips the path; only a contract input runs contracts |
| Configuration lock | Build the runtime image with `uv sync --locked --no-dev` | Manifest/lock drift and runtime dependency resolution |
| Checks image | Ruff, `lint-imports`, scoped strict mypy, shell and declarative validators | Style, architecture imports, typed interfaces and contract metadata |
| Unit and contracts | Locked Compose Python checks and Node harness | Application behavior and published schemas |
| Compose smoke | Candidate API, web, database, migration, seed and harness | Startup and composed-service behavior |
| Production browser | Containerized Playwright against the candidate API/web images and isolated PostgreSQL | Delivered image, proxy, network and browser behavior |
| Real journeys | The seeded real-stack incident journeys on their own candidate stack | War room, mitigation review and postmortem against the real API |
| Triage review | The 55 T23 triage journeys on the isolated `compose.triage23.yaml` stack | Triage inbox, origin, recovery and session isolation |
| Deploy executor | The deploy-executor journey over docker-socket-proxy, then with the proxy stopped | Signed operations, rollback/restart idempotency and the proxy deny list |
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
It is not represented as full UI coverage; the seeded real-stack journeys below
add the incident flows.
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

### Real-stack journeys

The journeys below self-skip without their seeds, so a plain Playwright run never
proves them. `scripts/run_real_journeys.sh` seeds and runs them the same way in CI
and locally, with only `docker compose` on the host:

- `incidents` (real-journeys job): demo grants (`--seed-mcp`,
  `provision_demo.py`), then one stamped incident per journey for
  `war-room-runs-real`, `war-room-reasoning-real`, `review-mitigation-real`,
  `war-room-follow-real` and `postmortem-journey`. Stamps are fresh per run and
  separate per journey, because two of them approve their incident. The follow
  journey's live incident is finished by a second seed once its test has begun;
  the postmortem incident is resolved over the HTTP API as `demo-human`.
- `executor` (deploy-executor job): the `executor-e2e` profile, then the
  socket-down case after stopping `docker-socket-proxy`.
- T23 (triage-review job) keeps its own `scripts/run_triage23_review.sh`, which
  requires exactly 55 passed and no skipped tests.

Only the one-off seed container mounts `scripts/` read-only and receives the
audit key; the runner and the served images are unchanged. The script forces the
OpenRouter keys empty, so no investigation reaches a model provider. A journey
passes only if Playwright exits 0 and reports passed tests and none skipped.
Logs, Playwright artifacts and `summary.txt` land in `JOURNEY_ARTIFACTS`
(default: a new temporary directory). Local reproduction, with a synthetic `.env`
that has a random `AUDIT_HMAC_KEY` and, for the executor,
`DEPLOY_EXECUTOR_SIGNING_KEY`:

```sh
COMPOSE_PROJECT_NAME=journeys-demo scripts/run_real_journeys.sh incidents
COMPOSE_PROJECT_NAME=journeys-demo scripts/run_real_journeys.sh executor
docker compose -f compose.yaml -f compose.e2e.yaml --project-name journeys-demo --profile e2e --profile executor-e2e down -v --remove-orphans
scripts/run_triage23_review.sh
```

The executor journey builds the host-wide `demo/probe:1.0.0` and `1.1.0` tags.

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
