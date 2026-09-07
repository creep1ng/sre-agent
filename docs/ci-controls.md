# CI control inventory

This inventory separates repository-owned gates from external checks and from proposed controls.
It reflects `.github/workflows/ci.yml` and the pull-request checks observed on 2026-09-05.

## Implemented controls

| Control | Ownership | Reproducible evidence | Cost profile |
| --- | --- | --- | --- |
| Python lint, format, and tests | Versioned workflow | `python` job: Ruff and database-independent Pytest | Python install plus test runtime |
| Contract validation | Versioned workflow | `contracts` job: locked npm install, schema, OpenAPI, release, and conformance checks | Node install plus contract suite |
| PostgreSQL behavior | Versioned workflow | `issue-11-postgresql` job: migrations, seeds, persistence tests, Alembic drift, conformance | Ephemeral database service and Python/Node installs |
| Static web syntax/assets | Versioned workflow | `static-web` job | Node startup and file checks |
| Integrated Compose smoke | Versioned workflow | `compose-smoke` job with teardown under `always()` | Image builds and service startup |
| Secret scanning | External GitHub check | `GitGuardian Security Checks` appears separately on pull requests | External service; configuration is not versioned here |
| Workflow hardening | Versioned workflow | `python scripts/validate_ci_hardening.py` | Negligible text inspection |

Repository-owned jobs have explicit timeouts. Actions are pinned to full commit SHAs with semantic
version comments. The workflow retains only `contents: read`, does not reference repository secrets,
and groups runs by workflow plus PR number (or ref outside PRs). Thus a newer run replaces an older
run for the same PR while different PR numbers remain distinct groups.

## Action provenance

The following commits were verified against tags in the official `actions/*` GitHub repositories
using the Git references API on 2026-09-05:

| Action | Pinned commit | Version tag |
| --- | --- | --- |
| `actions/checkout` | `11d5960a326750d5838078e36cf38b85af677262` | `v4.4.0` |
| `actions/setup-python` | `a26af69be951a213d495a4c3e4e4022e16d87065` | `v5.6.0` |
| `actions/setup-node` | `49933ea5288caeca8642d1e84afbd3f7d6820020` | `v4.4.0` |

## Proposed gates (not implemented)

These are proposals, not current guarantees or required checks.

| Gap | Baseline required before policy | Expected cost | Next step |
| --- | --- | --- | --- |
| Python and Node dependency audit | Record findings from pinned `pip-audit` and `npm audit` runs, including accepted advisories and lockfile scope | Registry/advisory network access and an additional install; likely tens of seconds | Run a non-blocking baseline, define update/exception ownership, then approve a separate blocking gate |
| Python type checking | Select and pin a checker, then record errors over agreed production-module scope separately from tests | Checker install plus analysis; configuration and incremental cleanup | Produce a baseline report and ownership plan before deciding strictness or exclusions |
| Python coverage | Measure combined database-independent and PostgreSQL suites with a pinned coverage tool | Instrumentation overhead, report combination, and artifact handling | Capture a stable branch baseline, agree measurement scope, then propose—not invent—a threshold |

GitGuardian is not duplicated by these proposals. No coverage threshold, type policy, or dependency
vulnerability threshold is introduced by this change.
