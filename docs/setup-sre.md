# Prepare SRE with one command

This is the operator entrypoint for issue #618, not a worktree/test recipe.
Setup prepares the delivered SRE workflows; readiness is **not** acceptance of
signal recovery, a successful investigation, remediation, or an OKR.

## Before setup (once)

Use one checkout of the integrated release. Requirements: Linux/Unix host,
Python 3.10+ (stdlib for setup), local Docker Engine with Compose >=2.24.4,
Git and enough capacity for [OTel prerequisites](demo-env.md). Setup installs
nothing on the host. It uses only the local Unix Docker socket, never a remote
Docker context. Running it in a container grants that container local Docker
control; use only the reviewed candidate and mounts.

Prepare an ignored, owner-only `.env` from `.env.example`. Use literal unquoted
`KEY=value` lines, no shell expansion, duplicate keys or Compose/Docker overrides.
Provide four distinct `sre_` demo keys (32+ characters, unique first eight),
non-placeholder model/provider assignments, matching `POSTGRES_*`/`DATABASE_URL`
for `db:5432`, and a random `AUDIT_HMAC_KEY` of 32+ characters. Keep the file
mode0600; do not print, source, commit or attach it. No provider key is required
for readiness. Keys/routes are initial seeds, not automatic rotation/reassignment.

OTel has its **own lifecycle**, separate from SRE. Prepare the local environment
with `python scripts/demo_env.py up`; it creates the pinned checkout and MCP
caller token. `demo_env.py` requires PyYAML as documented in its own guide.
Secure `.demo-state/grafana-mcp.env` to mode0600, owned by the setup caller.
After the files exist, use `chmod 600 .env .demo-state/grafana-mcp.env`
(adjust the token path if `DEMO_STATE_DIR` is elsewhere). Both files must belong
to the setup caller. This is initial secret provisioning, not a recurring
SRE grant/setup step.
Run `python scripts/demo_env.py verify` to verify the actual OTel composition.
Setup consumes that prepared internal network/token; it never starts, resets,
stops or destroys OTel and never imports files from another branch/worktree.

## Configuration contract

| Setting | Default / meaning |
| --- | --- |
| `SRE_OTEL_MODE` | `local`; `aws` fails explicitly until #494 is integrated |
| `DEMO_STATE_DIR` | Absolute private state directory; defaults to this checkout's `.demo-state` |
| `SRE_MCP_NETWORK` | `sre-mcp-boundary`; must already exist and be internal |
| `SRE_SETUP_PROJECT` | `sre-demo`; use a unique `sre-…` name; never another checkout's project |
| `API_PORT`, `WEB_PORT`, `POSTGRES_PORT` | 8000/8080/5432, distinct loopback ports1024–65535 |
| `SRE_RUNTIME_SUBNET`, `SRE_CONSUMER_SUBNET` | Optional private, nonoverlapping IPv4 CIDRs, selected after checking local networks when Docker pools are exhausted |
| `SRE_ENABLE_PAID_LLM` | `0`; only explicit `1` plus API-owned `OPENROUTER_API_KEY` enables paid investigation calls |
| `TRIAGE_AGENT_*`, `REMEDIATION_AGENT_*` | Existing seed assignments; aliases stay `triage-agent`/`remediation-agent` |

AWS is **blocked/not integrated**, not ready or locally emulated. #494 owns its
bootstrap, launcher, connection interface, TTL and budget. This command does not
use AWS credentials, create IAM/resources/network rules, forward remote ports,
or guess an AWS endpoint/export format. Once that producer lands, its approved
connection interface needs integration and separate real acceptance here.
Changing mode does not require editing YAML/code; unsupported AWS exits before
any Docker mutation and leaves the local deployment untouched.

## Start and repeat

```sh
python scripts/setup_sre.py
```

For a private configuration elsewhere, add `--env-file /absolute/private/file.env`.
The command validates inputs/Docker/ports/isolation, runs existing migrations,
ordinary seed and MCP seed, prepares explicit demo permissions through the
existing domain service, starts API/web and probes governed MCP metric/log calls.
It prints the operational API/web URLs and whether paid LLM is enabled. Readiness
allows empty signal results: connection success is not recovery evidence.

Repeat the same command. It retains credentials, principal/grant IDs, incidents,
audit and the database volume. Conflicting/revoked grants fail; setup does not
silently reactivate authority, rotate secrets or reconcile changed routes.
The demo human receives workflow/triage permissions; `incident-harness` has its
own LLM seed grant and direct discovery plus two read-only MCP invocation grants.
It receives no run approval. `restricted-harness` receives no setup grants.
Audit is read using the existing admin human, not broad audit authority for the
investigator. Provider/MCP secrets stay API-owned; the standalone harness is
confined to its internal API-consumer network.

## Diagnose and recover

All failures exit nonzero. No raw Compose/provider exception output is forwarded:
Compose can expand secrets into errors. Diagnose locally and never attach raw
configuration, inspect dumps, headers or logs.

| Diagnostic | Bounded recovery |
| --- | --- |
| Missing/invalid/private input | Correct only the named private input/permissions; rerun |
| Docker/Compose unavailable | Start local Docker/update prerequisites; rerun |
| Port occupied | Choose a free port in the private config; do not stop foreign containers |
| MCP network missing/not internal | Prepare/verify the local OTel environment with its owner script |
| Network pool exhausted or overlap | Select unused optional CIDRs; never prune other projects |
| Seed/permissions/migration stage fails | Inspect this project's status and domain state; preserve DB; resolve conflict through existing administrative APIs/runbooks then rerun |
| OTel/MCP destination unavailable | Run OTel `verify`, correct its own environment, rerun SRE; no automatic reset |
| Setup overlay or foreign-checkout conflict | Retain evidence/state; review configuration or choose a distinct project; no overwrite |
| AWS blocked | Wait for #494 integration; local remains independent |

Partial setup may leave this project's services/data in place. Correct the cause
and rerun the **same command**; it converges. No global cleanup is a recovery step.
When inspecting Compose manually, use the same `SRE_SETUP_PROJECT`, private
`--env-file`, `compose.yaml`, `compose.mcp.yaml` and the generated
`DEMO_STATE_DIR/sre-setup/SRE_SETUP_PROJECT.json` layer. Set `DEMO_STATE_DIR`
explicitly for those manual commands; do not fall back to an unrelated default
project from historical examples. Never print `docker compose config`.
For seed route drift use the existing [routing reconciliation](../README.md#when-a-changed-env-route-does-not-take-effect), not volume deletion.

## Bounded reviewer journey

Use the current API, synthetic incident context and unique Idempotency-Key headers.
Keep credentials in a private client/secret workflow, never command arguments or
captures. The reproducible [controlled HTTP journey](../tests/test_demo_provision_http.py)
shows exact bodies and endpoints; [CLI E2E](../scripts/verify_setup_repeat.py) runs
against a prepared controlled fixture. These are evidence, not setup prerequisites.

1. As `restricted-harness`, POST `/v1/alerts/al-review/triage/commands` with
   `{"operation":"open_triage","expected_version":1}`: expect403.
2. As `demo-human`, the same operation with a fresh key: expect200. POST the
   `triage_declare` operation with version1, reason, severity, impact and actual
   `alert_context` (service, summary, observed_at, source, severity): expect201;
   retain `incident_id`. A complete synthetic declaration body is:

   ```json
   {"operation":"triage_declare","expected_version":1,"severity":"sev2",
    "reason":"Reviewer observed checkout failures","impact":"Synthetic checkout errors",
    "alert_context":{"service":"checkout","summary":"Synthetic reviewer alert",
     "observed_at":"2026-10-13T10:00:00-05:00","source":"reviewer-monitoring","severity":"sev2"}}
   ```

   Use the real observed context/time for live evidence, not this synthetic example.
3. POST `/v1/incidents/{incident_id}/runs` with
   `{"workflow_version":"1.0.0","objective":"investigate"}`: expect201. Without
   explicit paid enablement the dispatcher cannot make a paid model request;
   this does **not** prove a successful inference. Retain `run_id`.
4. Read `/v1/incidents/{incident_id}/runs/{run_id}` and its `/events` as the human:
   expect200; the restricted identity remains403. Inspect actual dispatch receipts
   and report completed/failure/unknown honestly, not just the HTTP start status.
5. As `admin-human`, GET `/v1/audit-events?principal_id=demo-human`: expect200;
   inspect metadata only. Never capture prompt/output or private tokens.
6. For real OTel signals use `python scripts/demo_env.py fail`, verify the change
   using [demo-signals](demo-signals.md), then `python scripts/demo_env.py reset`
   and verify recovery. Setup never injects the failure. This step cannot be
   replaced by the controlled MCP fixture or healthy containers.

Independent human reproduction from this guide, on the final integrated main SHA,
is required. Record any extra undocumented step as a gap before accepting #618.
Live LLM proof needs separately authorized paid enablement; never run it implicitly.

## Stop safely

```sh
python scripts/setup_sre.py --down
```

Stops only the selected SRE project, retaining its volumes/incidents/audit.
OTel stays running; stop it separately through `demo_env.py down` when intended.
Do not use `down -v`, global pruning, or AWS teardown as normal SRE recovery.
