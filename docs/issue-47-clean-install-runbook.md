# Issue 47: clean-install runbook for the packaged release

**A fresh VM installs this release with Git and Docker alone: no host Python, no
worktrees, no manual database work.** The runbook pins a release SHA, configures private
local secrets, and verifies migrations, demo seed, health checks, backup and a scoped
reset. It uses the plain packaged stack (`compose.yaml`); the richer operator setup for
OpenTelemetry targets lives in [the setup guide](setup-sre.md) and is out of scope.

Follow every step in order and fill the [Runner log](#runner-log) while you execute.
No step requires the author's help; if one does, record it as a gap.

## Prerequisites

| Item | Requirement |
|---|---|
| Host | Linux VM recommended; Docker Engine running locally |
| Docker Compose | v2.24.4 or newer (`docker compose version`) |
| Git | to clone the release |
| Disk | about 10 GB free for images, PostgreSQL and the backup file |
| Ports | 8688 (API), 8888 (web), 5688 (PostgreSQL); all loopback-only |
| Secrets | four non-production demo API keys plus one audit key, provided below |

The ports above are chosen so this stack coexists with another local stack already
using 8000/8080/5432. Check they are free before starting:

```sh
ss -ltn | grep -E ':8688|:8888|:5688' && echo "PORT BUSY" || echo "ports free"
```

## Get the release

```sh
git clone https://github.com/creep1ng/sre-agent.git
cd sre-agent
git checkout e5c542d7
git rev-parse HEAD
```

The last command must print the full 40-character SHA starting with `e5c542d7`; every
step below was verified against that commit.

## Configure secrets and ports

The stack reads one untracked `.env` from the checkout root; it is gitignored and must
never be committed, printed, attached or sourced by other scripts. The values below
are non-production demo values; generate unique keys before any shared use.

```sh
cat > .env <<'EOF'
POSTGRES_DB=sre_agent
POSTGRES_USER=sre_agent
POSTGRES_PASSWORD=local-development-only
DATABASE_URL=postgresql://sre_agent:local-development-only@db:5432/sre_agent
API_PORT=8688
WEB_PORT=8888
POSTGRES_PORT=5688
COMPOSE_PROJECT_NAME=sre-agent-release
ADMIN_HUMAN_API_KEY=sre_admn_f0a3e3615a0d5f8f64d22ec52a23cf49
DEMO_HUMAN_API_KEY=sre_demo_0d4c56f6bc86bc1f178fcb8ecad591ae
INCIDENT_HARNESS_API_KEY=sre_inci_0b0232c6a252441a70e2786386df12d8
RESTRICTED_HARNESS_API_KEY=sre_rest_205458b988769da39607a6a772277d73
TRIAGE_AGENT_MODEL=openai/gpt-4o-mini
TRIAGE_AGENT_PROVIDER=openai
REMEDIATION_AGENT_MODEL=anthropic/claude-sonnet-4
REMEDIATION_AGENT_PROVIDER=anthropic
AUDIT_HMAC_KEY=fdbb97aa2412f7ed6909c15ef683704b2f22329070cde04610eb175a2beeb0e5
EOF
chmod 600 .env
```

- `POSTGRES_*` / `DATABASE_URL`: local database identity; host `db`; keep both sides consistent.
- `API_PORT` / `WEB_PORT` / `POSTGRES_PORT`: loopback port overrides; change a busy one, nothing else moves.
- `COMPOSE_PROJECT_NAME`: isolates containers, network and volume under `sre-agent-release_*`; keep it unique per checkout.
- The four `sre_` keys: credentials for `admin-human`, `demo-human`, `incident-harness`, `restricted-harness`; unique, with unique first eight characters.
- `TRIAGE_AGENT_*` / `REMEDIATION_AGENT_*`: initial demo routing for `triage-agent` and `remediation-agent`; seed inputs, not live providers.
- `AUDIT_HMAC_KEY`: protects audit references. No provider key is required; no paid model call happens.

## Start the stack

```sh
docker compose up --build --wait
docker compose ps -a
```

Expected: exit `0` after `db`, `api` and `web` report healthy. `ps -a` shows those
three `running (healthy)` and `migrate` / `seed` as `Exited (0)`, run in that order.
A warm local cache starts the stack in under a minute; a cold VM builds several
minutes first. No service runs migrations or seeds at API startup.

## Migrations

The `migrate` one-shot already ran `alembic upgrade head` before `api` started. Verify
it, then prove a rerun is a no-op:

```sh
docker compose ps -a
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT version_num FROM alembic_version"'
docker compose run --rm migrate
```

Expected: the SQL prints `20261009_01` (the release head), and the rerun exits `0`
without applying anything. The migrate container intentionally prints no application
output; its `Exited (0)` status and the `alembic_version` row are the evidence.
Readiness requires exactly that version.

## Demo seed data

The `seed` one-shot already ran. Verify its output and the seeded rows:

```sh
docker compose logs seed | tail -n 1
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT (SELECT count(*) FROM principals) AS principals, (SELECT count(*) FROM credentials) AS credentials, (SELECT count(*) FROM resources WHERE resource_type = '\''llm_model'\'') AS model_aliases, (SELECT count(*) FROM grants) AS grants"'
```

Expected: the last log line ends with `seed created` on a fresh volume, and one row
`4 | 4 | 2 | 16`: four principals (`admin-human`, `demo-human`, `incident-harness`,
`restricted-harness`), four credential records, the `triage-agent` and
`remediation-agent` aliases, and 16 grants (2 route invokes for the incident harness
plus 14 administrative grants for `admin-human`). Re-running the seed is safe and
prints `seed converged`:

```sh
docker compose run --rm seed
```

## Health checks

```sh
curl -fsS http://127.0.0.1:8688/health/live
curl -fsS http://127.0.0.1:8688/health/ready
curl -fsS http://127.0.0.1:8888/health
```

Expected: `{"status":"ok"}`, then `{"status":"ok","dependency":"postgresql"}` (it also
checks the migration head above), then plain `ok` from the web container.

## UI and API smoke

Open <http://127.0.0.1:8888> (title `midnight.agent`, linking the control plane), then
<http://127.0.0.1:8888/public/admin/principals.html>: paste `ADMIN_HUMAN_API_KEY` and
press "Connect and load". Expect 4 principals with their kinds. The key stays in the
masked field and in memory only, so it cannot leak into screenshots or shell history.
Headless equivalent:

```sh
curl -fsS http://127.0.0.1:8888/ | grep -o '<title>[^<]*</title>'
```

Expected: `<title>midnight.agent</title>`.

## Persistence check

Restart without touching the volume, then read the data again:

```sh
docker compose down
docker compose up --wait
docker compose logs seed | tail -n 1
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "SELECT count(*) FROM principals"'
```

Expected: `seed converged` (existing rows are validated, not recreated) and the count still prints `4`. Seeds, incidents and audit survive in the project-scoped `postgres_data` volume.

## Backup and restore notes

Back up from inside the container, then copy the dump to the host:

```sh
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists -f /tmp/sre-agent-backup.sql'
docker compose cp db:/tmp/sre-agent-backup.sql ./sre-agent-backup.sql
ls -l sre-agent-backup.sql
```

Expected: a non-empty plain-SQL dump whose first lines contain
`-- PostgreSQL database dump`. Keep the file outside Git. Prove it is restorable
without touching the live database:

```sh
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "CREATE DATABASE restore_check"'
docker compose cp ./sre-agent-backup.sql db:/tmp/restore.sql
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d restore_check -v ON_ERROR_STOP=1 -f /tmp/restore.sql'
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d restore_check -tAc "SELECT count(*) FROM principals"'
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "DROP DATABASE restore_check"'
```

Expected: the scratch database prints `4` and is dropped afterwards. A real recovery
restores the dump into a fresh project/volume (new `COMPOSE_PROJECT_NAME`); never
restore over a live database in place.

## Scoped reset

Return to the exact seeded baseline by removing only this project's volume and
starting again; the backup file on the host is kept.

```sh
docker compose down --volumes --remove-orphans
docker compose up --wait
docker compose logs seed | tail -n 1
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT (SELECT count(*) FROM principals) AS principals, (SELECT count(*) FROM credentials) AS credentials, (SELECT count(*) FROM resources WHERE resource_type = '\''llm_model'\'') AS model_aliases, (SELECT count(*) FROM grants) AS grants"'
```

Expected: `seed created` again and the same baseline row `4 | 4 | 2 | 16`.
`down --volumes` deletes only `sre-agent-release_*` resources. Never use `docker
system prune` or `docker volume prune` as recovery: they can destroy other projects'
data, including a shared stack's.

## Troubleshooting

| Symptom | Bounded recovery |
|---|---|
| `ss` shows a busy port / `port is already allocated` | Pick another free `API_PORT`, `WEB_PORT` or `POSTGRES_PORT` in `.env` and rerun `docker compose up --wait`; never stop foreign containers |
| `error while interpolating ... required variable ... is missing a value` | `.env` is incomplete or not in the checkout root; copy the block above verbatim and rerun |
| `migrate` exits non-zero | Inspect `docker compose logs migrate`; fix configuration; rerun `docker compose run --rm migrate`. The volume is preserved; do not delete it |
| Data from an older experiment appears | Two checkouts share one `COMPOSE_PROJECT_NAME`; compare `docker volume ls` with your project name and use a unique one |
| `seed_state_conflict` | Seed rows do not match the configured inputs; see the routing reconciliation notes in the [README](../README.md#when-a-changed-env-route-does-not-take-effect). Do not delete the volume to force it |
| Web pages fail to load data | Check `docker compose ps` and the API readiness URL first; web only proxies `/api/` to `api:8000` |

## Cleanup

```sh
docker compose down --volumes --remove-orphans
```

This removes only this project's containers, network and volume; the backup file and
`.env` stay on the host (keep `.env` out of Git). Confirm other stacks run with `docker ps`.

## Runner log

Copy this block into the issue or PR when your run finishes:

```text
Runner log - issue 47 clean install
- Release SHA executed: ______________ (git rev-parse HEAD) | date/runner: ______________
- Environment: VM/OS __________ | CPU/RAM/disk free __________ | docker ______ | compose ______ | project/ports __________ / __________
- Steps (command -> observed result): 1 build+up -> ; 2 migrations -> ; 3 seed counts -> ; 4 health -> ; 5 UI -> ; 6 persistence -> ; 7 backup -> ; 8 reset ->
- Deviations and reproducible failures (step, exact message, action):
- Author help required: yes/no (details):
- Total wall-clock time to first healthy stack: __________
```
