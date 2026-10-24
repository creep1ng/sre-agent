# Prepare recording triage

## Objective and problem

Provide a reusable local script that prepares the pinned section-7 triage recording
environment. Existing seed/provision helpers converge governance data but do not reset
persisted alert decisions; `alert-payment-002` was already declared before the approved reset.

## Authorized scope

The user explicitly approved erasing and recreating ONLY the PostgreSQL database of
Compose project `sre-rec-triage-20261005`, including incidents, runs, decisions and audit.
The script must require `--reset` before this destructive operation. It may stop/remove
only that project's `api`, `web` and `db` containers and remove only the validated named
volume mounted at `/var/lib/postgresql/data`. No generic `down -v`, pruning, SQL reset,
remote operations, source reset, volume/socket mounts for Docker access, installations,
builds, provider/model calls, credential rotation, or permission relaxation.

Preserve `.env`, all worktrees/source/images, and every resource of base, review,
postmortem and other projects. The fixed target is
`/home/creep/sre-recording-20261005/triage`, SHA
`734fa82cb13ed09494414892c14af8483f59a3bd`, ports 26200/26201/26202.

## Route and files

- Route: delegated direct, one script reusing existing Compose services and provisioning
  constants; no SDD or native review lifecycle.
- Deliverable: `scripts/prepare_recording_triage.sh` in the current writable workspace.
- Tracking: this document and Engram topic `odd/prepare-recording-triage/tasks`.
- Existing helpers: `scripts/provision_incident_workflow.py` for catalog/grant constants;
  runtime `migrate`/`seed` services; runbook section 5 for governed HTTP provisioning.
- Do not invoke `seed_war_room_demo.py`: section 7 must start with an unopened alert.

## Verification mode

No current explicit TDD on/off source exists in the actual project configuration.
Do not infer it from installed pytest or historical task documents. The parent explicitly
directed ordinary containerized functional checks for this script, not an invented
strict-TDD mode or unit tests written after code. Existing checks: Bash syntax,
ShellCheck in an already-built image when available, and real Compose/API/database proof.

## Failure cases to check before implementation

- Invalid arguments must exit before touching Docker or data.
- Missing/dirty/wrong-SHA target, missing `.env`, non-local Docker endpoint, or missing
  runtime images must fail before deletion; never build/pull/reconfigure automatically.
- Missing/ambiguous DB container, wrong project/service/root labels, non-volume PostgreSQL
  mount, wrongly owned volume, or extra volume consumers must fail before deletion.
- A failed command must stop immediately and retain a private, secret-free checkpoint.
- Migration/seed/readiness/provision failures must never print credentials, headers or DSNs.
- Replayed grant creation is insufficient: verify all six current grants active, demo-human
  allow and restricted-harness deny; do not restore revoked grants automatically.
- A successful reset must show `20260923_13`, empty incident/decision state and GET
  `/v1/alerts/alert-payment-002/triage` = 404 `triage_not_found`.
- Check that unrelated project containers/volumes and local configuration remain unchanged.

## Acceptance criteria

1. Only the exact authorized DB volume is deleted with `--reset`, after label/mount checks.
2. Existing local images are reused; all runtime/package execution stays in containers.
3. Migrations, base governance seed and six incident-response grants are verified.
4. db/api/web are healthy and the original alert is absent, ready for manual `open_triage`.
5. Evidence/checkpoint is private and sanitized; script prints UI URLs, never credentials.
6. No commits and no other project/source/environment modification.

## Tasks and progress

- [x] T1: Search existing helpers and map the exact target/reset scope.
  Evidence: no wrapper exists; target db/api/web healthy; DB mount is named volume
  `sre-rec-triage-20261005_postgres_data`; migration `20260923_13`; six exact grants active.
- [x] T2: Implement guarded preparation/reset script and observe syntax/ShellCheck results.
  Evidence: executable script created; `bash -n` and whitespace check passed; invalid
  argument exits 2 before any Docker action. ShellCheck passed using the already-built
  `sre-rec-base-20261005-python-checks` image with no network and a read-only script mount.
  The node-checks image lacked ShellCheck (exit 127); the available lint image initially
  reported SC2015, corrected to an explicit source-cleanliness conditional before rerun.
- [x] T3: Re-read Docker identities, execute `--reset` once, verify real seeded readiness,
  unopened alert and preservation of other projects; retain evidence on failure.
  Evidence: one foreground `--reset` invocation exited 0. Exact volume ownership, mount,
  local driver/no options and sole DB consumer were revalidated before deletion.
  db/api/web are healthy on 26202/26200/26201; migration is `20260923_13`; six exact
  grants are active with demo-human allow/restricted-harness deny; 0 incidents and 0
  triage decisions; original alert returns 404 `triage_not_found`, restricted returns 403,
  inbox/triage pages return 200. All 4 unrelated containers, 62 unrelated volumes,
  image IDs, existing `.env` fingerprint and pinned source SHA remained unchanged.
  Private evidence: `/tmp/sre-triage-recording.UjIOba` (700 directory, 600 files), including
  commands, expected/observed results, services, candidate SHA and next manual UI step.
  Protected resource baseline: `/tmp/sre-triage-preservation.s2U0r8`.
- [x] T4: Inspect final diff, record read-only review state/risk when available, and hand off
  actual results for the parent's independent verification.
  Evidence: final script remains 243 lines, executable 755, SHA256
  `865f4b6f9a10ab489a56878906231fdbdda70645fc060d84cd636d6b935e1490`;
  Bash syntax passes and no whitespace errors were emitted. Only this script and this
  document are new/untracked. Native review mode is off, decided by clone-local;
  `gentle-ai review assess --cwd /home/creep/workshop/sre-agent --json` exited 1 because
  explicit untracked-file declaration is required. Risk is UNASSESSED, not a fabricated
  low/pass result. No STATUS/START/review actor was invoked. Independent read-only
  verification found no blocker: candidate hash matched, containerized Bash syntax passed,
  services were healthy and retained evidence contained no credentials. The parent also
  reran Bash syntax and read the actual reset results. Failure guards other than invalid
  arguments and the non-reset preparation path
  were inspected but not exhaustively exercised; no fault injection into other projects.

## Next step

Perform manual section 7 in the triage
UI using `alert-payment-002`, `open_triage` and expected version 1. Use the returned version
for `triage_declare`. No incident was pre-created. Do not reset again until another take
is desired; `--reset` irreversibly erases the triage recording database.

## Rollback boundary

The new script and tracking document can be removed independently. The approved database
reset is irreversible: no backup is created and erased recording data cannot be recovered
through this helper. `.env`, images, worktrees and unrelated project data are preserved.
