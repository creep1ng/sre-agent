# SRE agent local foundation

The repository runs a minimal FastAPI composition root, PostgreSQL, and the existing framework-agnostic web catalog as one reproducible local stack. The control plane, incident-resolution plane, harness, and gateway remain explicit boundaries without introducing domain endpoints prematurely.

## Quick path

```bash
cp .env.example .env
docker compose up --build --wait
```

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

```bash
python -m pip install -e ".[dev]"
ruff check .
ruff format --check .
pytest

npm --prefix schemas/tooling ci
npm --prefix schemas/tooling test
npm --prefix schemas/tooling run validate
npm --prefix schemas/tooling run validate:release -- --release 1.0.0
npm --prefix schemas/tooling run validate:release -- --release 1.1.0
npm --prefix schemas/tooling run lint:openapi
npm --prefix schemas/tooling run conformance -- --consumer issue-10
node --check scripts/showcase.js
```

Direct Python dependencies are pinned exactly in `pyproject.toml`. The repository does not yet carry a verified transitive Python lock, so package indexes may resolve different compatible transitive versions over time. Create and review a standard lock in a network-enabled dependency update rather than fabricating one without resolver evidence.

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
