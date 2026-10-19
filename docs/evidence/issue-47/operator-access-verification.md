# Issue 47: operator access section verification (release e5c542d7)

Date: 2026-10-19 (UTC). Release `e5c542d7ca5f097f5e19ebaf90c70e1aa0b62e80`, Linux workstation,
Docker 29.9.1, Compose 5.6.0, project `sre-agent-release`, warm build cache. Fresh clone; every
`sh` block of the edited runbook executed in order, verbatim, with sanitized per-step logs kept
locally by the runner.

## Why the section exists

The first independent run of the published runbook (see the #47 Runner log) passed every step,
but on the resulting baseline `demo-human` had none of the 16 seeded grants: Triage answered
"Sin acceso" (HTTP 403) and the Grants page offers no incident resource, so the evaluator plan's
J2 step 4 and J3 to J5 could not start.

## Observed

- Pre-check: `ports free`, `project free`.
- Steps through scoped reset matched the runbook (`20261009_01`, `4 | 4 | 2 | 16`, `seed converged`,
  health ok, 68,833-byte dump written to `../`, mode `-rw-------`, restore `4`).
- Scoped reset: the first `up --wait` stopped with `service "migrate" didn't complete
  successfully: exit 1` while PostgreSQL restarted during first initialization (`the database
  system is shutting down` in the db log). Rerunning `docker compose up --wait` converged:
  `seed created`, `4 | 4 | 2 | 16`. The runbook now lists this bounded recovery.
- Operator access: `mcp seed created`; `demo permissions converged; restricted identity
  unchanged`; active grants `admin-human 14`, `demo-human 12`, `incident-harness 5`. A second run
  printed `mcp seed converged` and the same provisioning line.
- Browser (Chromium, incognito, console session with `DEMO_HUMAN_API_KEY`): Triage on
  `alert-checkout-001` loaded its context (`GET .../triage/context` 200), and `triage_declare` with
  the confirmed alert context returned `declared, incidente inc-060d2d91c8cee8cc84bf2198c13cf07a`,
  actor `demo-human`. Capture: `triage-declared-after-provisioning.png` (no credential visible).
- Cleanup removed only `sre-agent-release` resources.

No provider key, remote operation or paid call was involved.

## After #663 merged

#663 documented the same two commands in the runbook section "Optional: provision a
triage-capable operator". That section passes the audit key and the `scripts/` mount through a
local `compose.provision.yaml` override; this record used the equivalent `-e`/`-v` flags. Both
variants were executed on fresh isolated installs of `main` `7da3bfd`, and #663's again on
`ef8947f` with #664. Both produced the same results: grants `16`, then `19`, then `31`, with
`demo-human` at `12`. `GET /v1/alerts/alert-checkout-001/triage/context` went from 403 to 200
for `demo-human` and stayed 403 for `restricted-harness`. This PR keeps only two changes: the
evaluator-plan precondition and the troubleshooting row for the race observed above.
