# SRE agent local foundation

The repository runs a minimal FastAPI composition root, PostgreSQL, and the existing framework-agnostic web catalog as one reproducible local stack. The control plane, incident-resolution plane, harness, and gateway remain explicit boundaries without introducing domain endpoints prematurely.

## Quick path

Create the ignored local environment file, then replace every angle-bracket placeholder with
your own value. Do not commit the file or print its API keys.

```bash
cp .env.example .env
docker compose run --rm migrate
docker compose run --rm seed
docker compose up --build --wait
```

The required seed inputs are `ADMIN_HUMAN_API_KEY`, `DEMO_HUMAN_API_KEY`,
`INCIDENT_HARNESS_API_KEY`, `RESTRICTED_HARNESS_API_KEY`, `TRIAGE_AGENT_MODEL`, and
`TRIAGE_AGENT_PROVIDER`. Each API key must be unique, begin with `sre_`, contain at least 32
characters, and have a unique first eight characters. The model uses `<lab>/<model>` syntax;
the provider uses the HT-01 provider vocabulary. `.env.example` intentionally contains only
nonfunctional placeholders.

Migrate and seed are explicit one-shot operations. The API process never creates tables, runs
Alembic, or seeds data at startup; readiness returns a sanitized `503` until its schema exists.
An identical seed rerun prints `seed converged` and preserves stable IDs, counts, assignments,
grants, and credential hashes. Partial or incompatible seed-owned state fails atomically with a
secret-free `seed_state_conflict` diagnostic.

Open the web catalog at <http://127.0.0.1:8080>. API liveness and readiness are available at <http://127.0.0.1:8000/health/live> and <http://127.0.0.1:8000/health/ready>.

Run the contract harness as a one-shot profile:

```bash
docker compose --profile harness run --rm harness
```

Remove every project-owned container, network, and volume with:

```bash
docker compose down -v --remove-orphans
```

Re-running `docker compose up --build --wait` requires no undocumented recovery step. PostgreSQL data persists in a project-scoped volume until the explicit `down -v` teardown. Harness dependencies are locked into its image and copied to an ephemeral filesystem for each run; rebuilding the image is sufficient after a tooling lockfile change.

## Database lifecycle and rollback

Run `docker compose run --rm migrate` before `docker compose run --rm seed`. Repeating either
command is safe when the migration history and seed-owned rows match. Before any durable data is
accepted, the schema can be removed with:

```bash
docker compose run --rm migrate alembic downgrade base
```

Rollback delivery slices in reverse order: CI/docs, seed/runtime wiring, repositories, schema,
then DTOs. Once durable data or audit events exist, do **not** downgrade destructively. Back up
the five tables and audit history, revert application/runtime code first, and preserve the
database until an operator-approved migration or restore plan exists.

## System structure

| Path | Responsibility |
| --- | --- |
| `src/sre_agent/application.py` | Single FastAPI composition root |
| `src/sre_agent/control/` | Control-plane boundary |
| `src/sre_agent/incident/` | Incident-resolution-plane boundary |
| `src/sre_agent/harness/` | Contract and fixture harness boundary |
| `src/sre_agent/gateway/` | HTTP gateway and health probes |
| `schemas/` | Versioned contract authority and conformance tooling |
| `index.html`, `styles/`, `scripts/`, `public/` | Existing static web catalog |

See [runtime boundaries](docs/architecture.md) and the [Codex worktree workflow](docs/codex-worktrees.md).

## Local verification

All verification runs inside Compose containers. In a linked worktree, replace
`docker compose` below with `scripts/worktree-compose` so the generated project name and ports
remain isolated.

Run the complete Python suite, lint, formatting, lock consistency, and Alembic drift check:

```bash
docker compose --profile checks run --build --rm python-checks
```

Run the complete contract and JavaScript verification set:

```bash
docker compose --profile checks run --build --rm harness npm --prefix schemas/tooling test
docker compose --profile checks run --rm harness npm --prefix schemas/tooling run validate
docker compose --profile checks run --rm harness npm --prefix schemas/tooling run validate:release -- --release 1.0.0
docker compose --profile checks run --rm harness npm --prefix schemas/tooling run validate:release -- --release 1.1.0
docker compose --profile checks run --rm harness npm --prefix schemas/tooling run lint:openapi
docker compose --profile checks run --rm harness npm --prefix schemas/tooling run conformance -- --consumer issue-10
docker compose --profile checks run --rm harness npm --prefix schemas/tooling run conformance -- --consumer issue-11
docker compose --profile checks run --rm harness npm --prefix schemas/tooling run conformance -- --consumer issue-13
docker compose --profile checks run --rm harness node --check scripts/showcase.js
```

To verify issue #13 only, run its HTTP behavior tests and pinned contract obligation:

```bash
scripts/worktree-compose --profile checks run --build --rm python-checks pytest tests/test_authentication.py
scripts/worktree-compose --profile checks run --build --rm harness npm --prefix schemas/tooling run conformance -- --consumer issue-13
```

Direct Python dependencies are pinned exactly in `pyproject.toml`, and `uv.lock` is the reviewed
transitive lock. The `python-checks` image pins its verification tools and `uv lock --check`
verifies that project metadata and the lock remain aligned without installing anything on the
host.

## Web design system

The static catalog is a framework-agnostic UI foundation for the midnight.agent gateway and incident-response surfaces. Import `styles/design-system.css` before product-specific styles.

```html
<link rel="stylesheet" href="/styles/design-system.css" />
```

### Structure

| Path                    | Responsibility                                               |
| ----------------------- | ------------------------------------------------------------ |
| `palette.css`           | Primitive brand and functional color values                  |
| `styles/fonts.css`      | Spline Sans, Offside, and Monaspace Neon font loading        |
| `styles/tokens.css`     | Light/dark semantic tokens and component aliases             |
| `styles/base.css`       | Reset, typography defaults, focus, and accessibility helpers |
| `styles/components.css` | Framework-agnostic component and domain-pattern classes      |
| `styles/showcase.css`   | Catalog layout only; do not ship with the product UI         |
| `scripts/showcase.js`   | Catalog theme, tabs, filters, and copy interactions          |
| `public/`               | Approved light/dark logos, mark, and favicon                 |

### Token rule

Components consume semantic or component tokens, never primitive values.

```css
/* Correct: intent survives theme changes. */
.product-panel {
  background: var(--ma-color-bg-surface);
  color: var(--ma-color-text-primary);
}

/* Avoid: the primitive has no usage contract. */
.product-panel {
  background: var(--ma-color-ghost-white);
}
```

The hierarchy is `primitive -> semantic -> component`. Theme switching changes semantic values while component APIs remain stable.

### Included patterns

- Buttons, icon buttons, badges, alerts, cards, panels, tabs, form controls, switches, tables, meters, and empty states
- Light, dark, and system-preference themes with persistent selection
- Incident summary, evidence timeline, governed-resource list, responder identity, and audit table
- Reduced-motion, forced-color, keyboard-focus, responsive, and screen-reader support

### Product principles

- Evidence stays attached to diagnoses, actions, and transitions.
- Permission state is visible before a governed action executes.
- Severity and policy outcomes never rely on color alone.
- Dense operational screens use hierarchy rather than decorative noise.
- Prefer spacing and alignment over nested cards when content already shares a clear parent.
- Prompt content is treated as sensitive; audit patterns foreground metadata.

### Scope

This release intentionally does not select a frontend framework. The solution design leaves that decision open, so future React, Vue, or mobile adapters should wrap these token and behavior contracts rather than fork them.
