# Issue 47 runbook follow-ups: provisioning verification (release e5c542d7)

Date: 2026-10-18. Branch tested: `docs/issue-47-runbook-followups`, runbook revision
`d1df3e4ef2db6e584d4c31fdcec734d4da1b396b` (commit under review). Release executed:
`e5c542d7ca5f097f5e19ebaf90c70e1aa0b62e80`, the runbook pin. Runner: repository
sandbox run performed by the author after the first independent execution.
Runbook under test: [issue-47-clean-install-runbook.md](../../issue-47-clean-install-runbook.md),
SHA-256 of the executed copy: `074de84777c835081fa99a00e80cf030976ddcbcbd7db3f13dff7cf5378981d9`.

## Environment and method

- Windows 11 host with Docker Desktop; Docker Engine 29.2.1; Docker Compose v5.0.2;
  12 CPUs; about 29 GB free.
- Fresh clone of the branch into an empty directory, then the runbook's own "Get the
  release" block (literal `git clone` of the repository plus `git checkout e5c542d7`;
  `git rev-parse HEAD` printed `e5c542d7ca5f097f5e19ebaf90c70e1aa0b62e80`).
- Compose project `sre-agent-47fu` (unique name; the published default
  `sre-agent-release` belongs to the earlier runs); ports 8688 (API), 8888 (web),
  5688 (PostgreSQL), verified free first.
- Commands ran through Git Bash on the host; everything Docker-side ran inside the
  documented images. Host adaptations, all noted inline below: the Linux `ss` port
  check was replaced by the equivalent read-only `netstat` filter; the unique project
  name above replaced the published default; and mounting the optional helper used the
  runbook's own heredoc (PowerShell has no heredoc, so the shell here is Git Bash).
- One host-shell pitfall found while executing the optional section: Git Bash (MSYS)
  rewrites container-looking absolute paths, so `python /setup/provision_demo.py` was
  passed to the container as `C:/Program Files/Git/setup/provision_demo.py` and failed
  with `python: can't open file`. The literal documented command then ran unmodified
  from PowerShell and succeeded. On the documented Linux target no shell rewrites the
  argument, and the repository's own setup path passes it through Python directly, so
  this is a host-shell artifact, not a runbook defect; it did not require a runbook
  change.

## Finding 2: project-name pre-check (new section)

Observed with the literal block from "Confirm the project name is free". Positive
control against an existing foreign project on this host (`sre-agent`, read-only
listing) proved the check detects ownership:

```text
== positive control: existing project sre-agent (read-only listing) ==
sre-agent_postgres_data
fce22fd1b6fa
2a7ca1706d83
75f5627798b7
== runbook pre-check, literal block ==
PROJECT=sre-agent-47fu
(no output after PROJECT= means the name is free)
```

The two filter commands printed nothing for `sre-agent-47fu`, exactly as the expected
result states, and the same filters return the owning volume and containers for a
project name already in use, which is the documented abort condition. The scoped reset
later removed only `sre-agent-47fu_postgres_data`; the shared `sre-agent_postgres_data`
and the foreign stacks were untouched.

## Findings 3 and 5: backup location and secret scoping

Backup (revised section, literal commands): the dump was copied to
`C:/Users/mario/sre-agent-backup.sql`, outside the checkout; `git status` inside the
release checkout stayed clean, so nothing sensitive appears in the work tree:

```text
== copy to the host, outside the checkout ==
sre-agent-47fu-db-1 Copied ... to C:/Users/mario/sre-agent-backup.sql
-rw-r--r-- 1 mario 197609 68833 ... /c/Users/mario/sre-agent-backup.sql
== dump size and header ==
68833
--
-- PostgreSQL database dump
--
== git sees nothing new inside the checkout from the backup ==
no backup file inside the checkout
```

The restore block then read the dump back from `$HOME` into the scratch database and
counted `4` principals, with the scratch database dropped afterwards; the optional
`rm "$HOME/sre-agent-backup.sql"` cleanup was exercised and the file disappeared.

Host limitation: NTFS through MSYS cannot express POSIX modes, so `chmod 600` still
prints `-rw-r--r--` here for every non-read-only file. On the documented Linux target
the expected `-rw-------` is the real behavior; this Windows run verifies location and
sensitivity handling, not the mode bit.

The `.env` secret block was written with the published demo values and the unique
project name. No secret value is reproduced in this file; the section now states the
replacement rule (four `sre_[A-Za-z0-9_-]{24,128}` keys plus a 64-hex
`AUDIT_HMAC_KEY`) for any shared or reachable environment.

## Finding 4: console title

The literal headless command returned the raw shell title, and the Spanish console
boot title stays as the independent execution observed it:

```text
== raw shell title (literal runbook command) ==
<title>midnight.agent</title>
== supplementary: principals page status ==
200
```

## Core install steps (rerun against the revised runbook)

1. `docker compose up --build --wait` exit `0`; documented order with `db`, `api`,
   `web` healthy and `migrate` / `seed` `Exited (0)`, build cached.
2. `alembic_version` printed `20261009_01`; `docker compose run --rm migrate` exit `0`.
3. `seed created`; counts row `4 | 4 | 2 | 16`; seed rerun printed `seed converged`.
4. Health: `{"status":"ok"}`, `{"status":"ok","dependency":"postgresql"}`, `ok`.
5. UI smoke: raw title `<title>midnight.agent</title>`;
   `/public/admin/principals.html` answered `200`.
6. Persistence: `seed converged` after `down` + `up --wait`; principals `4`.
7. Backup and restore: see above (68,833-byte dump, restore count `4`).
8. Scoped reset: `seed created` again and the baseline row `4 | 4 | 2 | 16`;
   afterwards this project's volume exists again by design and the shared volume is
   intact.

## Optional provisioning section (executed as documented)

Before-state, after the scoped reset (literal SQL from the section plus the 403 probe):

```text
== grants total / demo-human active before provisioning ==
16
0
== triage context with the demo key BEFORE provisioning ==
403
{"error":{"code":"not_authorized","message":"Missing the required action grant or human operator identity."}, ...}
HTTP 403
```

The two documented compose commands ran with the helper file exactly as written
(the second command verbatim from PowerShell, see the host-shell note above):

```text
== step 1: MCP seed ==
mcp seed created
== counts after the MCP seed ==
19
3
== step 2: demo provisioning ==
demo permissions converged; restricted identity unchanged
== counts after provisioning ==
31
12
== grants by principal ==
 admin-human      |     14
 demo-human       |     12
 incident-harness |      5
```

The MCP seed registered the demo server and tools in the catalog (fresh-volume
focused rerun):

```text
mcp seed created
     resource_type      | count
------------------------+-------
 administrative_control |     8
 llm_model              |     2
 mcp_server             |     1
 mcp_tool               |     2
demo-human active grants after the MCP seed: 3
```

Reruns converge instead of duplicating: `mcp seed converged` and
`demo permissions converged; restricted identity unchanged`; the counts stayed
`31` and `12`.

Triage verification (literal runbook command, then the supplementary declare):

```text
== literal runbook check: triage context after provisioning ==
200
== context body ==
{"alert_id":"alert-checkout-001","triage_state":null,"allowed_actions":["open_triage","triage_dismiss","triage_link","triage_declare"]}
== supplementary: declare from the demo key (isolated stack only) ==
{"alert_id":"alert-checkout-001","status":"declared","incident_id":"inc-f77a4b1fd2ef878472a83081318a6535", ...}
HTTP 201
```

The 403-to-200 transition reproduces the blocker reported by the first independent
execution and resolves it with the documented supported path.

## Ownership and teardown

`docker compose down --volumes --remove-orphans` removed only `sre-agent-47fu`
containers, network and volume. After cleanup, the shared stack
(`sre-agent-web-1` / `api-1` / `db-1`), the foreign projects and
`sre-agent_postgres_data` were still running and present, and no `sre-agent-47fu`
resource remained. The optional helper `compose.provision.yaml` is untracked and not
gitignored (`git status` showed `?? compose.provision.yaml`), matching the section's
instruction to keep it out of Git and delete it; it was removed at the end.

## Caveats

- Warm Docker cache: the build reused layers, so start time is not a cold-VM measure.
- POSIX file modes cannot be verified on this NTFS host (see above); a Linux run
  re-verifies `chmod 600` in seconds.
- The browser-side boot title `Alertas · midnight.agent` is a live-UI observation from
  the independent execution; this file records the raw-shell side by curl and the
  implementation (`public/console/console.js`, `public/console/routes.js`) at the
  executed release.
- The executed runbook revision is the commit above; one prose sentence scoping the
  J7 claim was clarified after the run. No command changed before or after execution.

## Artifacts

- `runbook-under-test.md`: exact runbook copy executed (SHA-256 above), kept in the
  runner sandbox.
- Per-step command scripts and raw outputs were kept locally by the runner and can be
  shared on request.
