# Issue 47 clean-install verification (release e5c542d7)

Date: 2026-10-17. Release SHA verified: `e5c542d7ca5f097f5e19ebaf90c70e1aa0b62e80`
(origin/main). Runbook under test: [issue-47-clean-install-runbook.md](../issue-47-clean-install-runbook.md).
Runner: repository sandbox run performed by the author before the peer execution.

## Environment and method

- Windows 11 host with Docker Desktop; Docker Engine 29.2.1; Docker Compose v5.0.2.
- Fresh clone of the release into an empty directory, checked out at the tested SHA.
  Compose project `sre-agent-release`; ports 8688 (API), 8888 (web), 5688 (PostgreSQL).
- The runbook commands were executed in the documented order through Git Bash against
  the running stack. Without a POSIX shell, just one host adaptation was needed:
  `.env` was written with the exact documented content (PowerShell has no heredoc).
- The port check was verified with `netstat` instead of Linux `ss`. Everything else in
  the runbook ran verbatim.

## Step results (observed output, trimmed)

1. `docker compose up --build --wait` exit `0`. BuildKit had every layer cached; the
   stack reached the documented order: `db` healthy, `migrate` `Exited (0)`, `seed`
   `Exited (0)`, `api` healthy, `web` healthy (about 30 s total on this warm cache).
2. Migrations: `psql ... SELECT version_num FROM alembic_version` printed
   `20261009_01`; `docker compose run --rm migrate` exited `0`; migrate logs are
   intentionally empty, as the corrected runbook now states.
3. Seed: `docker compose logs seed | tail -n 1` ended with `seed created`; the count
   query returned exactly one row: `4 | 4 | 2 | 16` (principals, credentials,
   model_aliases, grants). `docker compose run --rm seed` printed `seed converged`.
4. Health checks: `/health/live` returned `{"status":"ok"}`; `/health/ready` returned
   `{"status":"ok","dependency":"postgresql"}`; web `/health` returned `ok`.
5. UI smoke: root page title `midnight.agent`;
   `/public/admin/principals.html` loaded with the admin key and rendered 4 principal
   rows (`admin-human`, `demo-human`, `incident-harness`, `restricted-harness`) with
   0 page errors. Screenshot below, captured with real Chromium.
6. Persistence: `docker compose down` + `up --wait` printed `seed converged` and the
   principal count remained `4`; the `postgres_data` volume survived the restart.
7. Backup: `pg_dump` produced a 70,134-byte plain-SQL dump starting with
   `-- PostgreSQL database dump`. Restoring it into a scratch `restore_check` database
   exited `0` with `ON_ERROR_STOP=1` and reported `4` principals; the scratch database
   was dropped afterwards.
8. Scoped reset: `down --volumes` removed only `sre-agent-release_postgres_data`
   (verified with `docker volume ls`); `up --wait` printed `seed created` and returned
   the exact baseline `4 | 4 | 2 | 16` with `alembic_version = 20261009_01`.

## Gaps found by the literal run and fixed in the runbook

- Migrate logs contain no application output (alembic is silent here); the runbook now
  verifies migrations through `Exited (0)` plus the `alembic_version` row instead of a
  log line.
- The release UI title is `midnight.agent` and the console path is
  `/public/admin/principals.html`; both were corrected after live observation.
- Warm-cache start time is under a minute; the "3–10 min" estimate only fits a cold
  VM and was reworded.

## Caveats

- Docker image layers were fully cached from earlier local builds, so observed build
  time was seconds, not a cold-VM build. A real Linux VM may differ in build times and
  file permissions only.
- No paid provider call occurs in this run, and the OpenTelemetry integration is out of
  scope for this runbook.

## Artifacts

- `console-principals.png`: real Chromium full-page capture of the running release
  console showing the 4 seeded principals; the API key is entered only in the masked
  password field. Captured through the pinned Playwright 1.63.0 e2e image
  (`sha256:014ea60897cedd48fdf8d3832295252453412501823624ce7acc253311243a6d`).
- Raw command logs were kept locally by the runner and can be shared on request.
