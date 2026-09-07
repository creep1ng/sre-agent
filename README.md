# SRE agent local foundation

The repository runs a governed, non-streaming `POST /v1/responses`, PostgreSQL, and the existing
framework-agnostic web catalog as one reproducible local stack. Authorization precedes provider
routing, and every released response or denial is gated by metadata-only audit persistence.

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

`AUDIT_HMAC_KEY` protects audit references. `OPENROUTER_API_KEY` is optional for ordinary local
and deterministic checks; when set, Compose passes it only to `api`. Set
`OPENROUTER_TIMEOUT_SECONDS` between 0 and 120 seconds. The seed, contract harness, deterministic
issue-14 harness, and live-smoke client never receive the provider secret.

## Idempotency-Key for client mutations

`Idempotency-Key` is a client-owned request header for each mutating `POST`. It is **not** an
`.env` setting, API credential, or secret.

1. Generate a fresh key for each logical mutation, for example:

   ```bash
   python -c 'import uuid; print(uuid.uuid4())'
   ```

2. Send that value in the `Idempotency-Key` header. A UUID is a convenient valid value; keys
   must contain 16–128 printable ASCII characters.
3. Reuse the same key only when retrying the same request with the identical payload. The service
   replays the original result without repeating the mutation.
4. Never reuse the key with a different payload: the service returns `409 idempotency_conflict`.

The key is scoped to the authenticated principal and target operation, so generate and retain it
with the client request until that request has completed or no longer needs a retry.

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

Prove issue #14 deterministically against an isolated PostgreSQL container and recording provider:

```bash
docker compose --profile issue-14 run --build --rm issue-14-harness
```

The live smoke is deliberately separate from ordinary CI. It sends exactly one request through
the running API only when both explicit enablement and API-owned secrets are configured:

```bash
# Set OPENROUTER_API_KEY and a non-placeholder AUDIT_HMAC_KEY in the ignored .env first.
RUN_OPENROUTER_LIVE_SMOKE=1 docker compose --profile live-smoke run --build --rm live-smoke
```

The client receives only a provider-secret presence flag, its harness credential, and non-secret
routing expectations. A missing enable flag or provider/audit secret produces a pytest skip.

### Verify one authorized response

With `INCIDENT_HARNESS_API_KEY` already loaded by your local secret-management workflow, send one
bounded request directly to the API. Do not paste or commit the credential.

```bash
curl -i http://localhost:8000/v1/responses \
  -H "Authorization: Bearer ${INCIDENT_HARNESS_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"triage-agent","input":"Summarize the incident."}'
```

An authorized, correctly routed request returns `200` with a completed text item at
`output[0].content[0].text`. The gateway validates OpenRouter's completed Responses envelope and
does not expose its generation identifier; it emits its own `resp_...` identifier instead.

#### When a changed `.env` route does not take effect

`TRIAGE_AGENT_MODEL` and `TRIAGE_AGENT_PROVIDER` initialize the persisted `triage-agent` route;
the running gateway reads that route from PostgreSQL, not from a later `.env` edit. Re-running the
strict seed deliberately reports a conflict rather than silently changing an existing route. Do
not delete the database volume to force an update. Reconcile the expected old and new route with a
reviewed, guarded maintenance update, then rebuild/restart the API.

If OpenRouter resolves a requested model alias to a dated canonical model, the gateway performs one
additional endpoint-catalog lookup and accepts the result only when the catalog proves the exact
model/provider identity. A missing, ambiguous, or mismatched catalog entry fails closed rather than
returning an unverified response.

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

All verification runs inside Compose containers. The Python command starts a dedicated PostgreSQL
service backed by disposable `tmpfs`; it neither starts nor mounts the persistent demo database.
An isolation guard also refuses to run when the test and demo database identities match. In a
linked worktree, replace
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
docker compose --profile checks run --rm harness npm --prefix schemas/tooling run validate:releases
docker compose --profile checks run --rm harness npm --prefix schemas/tooling run lint:openapi
docker compose --profile checks run --rm harness node --check scripts/showcase.js
```

`validate:releases` discovers every published SemVer directory in `schemas/releases`, validates
them in deterministic order, and fails if any directory is omitted or its manifest is invalid.

To verify issue #13 only, run its HTTP behavior tests and pinned contract obligation:

```bash
scripts/worktree-compose --profile checks run --build --rm python-checks pytest tests/test_authentication.py
scripts/worktree-compose --profile checks run --build --rm harness npm --prefix schemas/tooling run conformance -- --consumer issue-13
```

The issue #14 deterministic harness is the release gate for allow, deny, zero-call, normalized
failure, protected readback, and audit-commit behavior. The live smoke is optional evidence, not a
replacement for those deterministic checks.

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
