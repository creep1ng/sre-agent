#!/usr/bin/env bash
# Prepare the pinned recording environment; --reset erases only its validated DB volume.
set -euo pipefail

reset=0
if [[ $# -gt 0 ]]; then
  if [[ $# -ne 1 || $1 != --reset ]]; then
    echo "Usage: $0 [--reset]" >&2
    exit 2
  fi
  reset=1
fi

ROOT=/home/creep/sre-recording-20261005/triage
PROJECT=sre-rec-triage-20261005
SHA=734fa82cb13ed09494414892c14af8483f59a3bd
umask 077
evidence=$(mktemp -d /tmp/sre-triage-recording.XXXXXX)
chmod 700 "$evidence"
step=preflight
trap 'code=$?; printf "final_step=%s\nexit_code=%s\n" "$step" "$code" >> "$evidence/checkpoint.txt"; echo "Evidence: $evidence"' EXIT
printf 'project=%s\nsource_sha=%s\nreset=%s\n' "$PROJECT" "$SHA" "$reset" > "$evidence/checkpoint.txt"
printf 'dc() { docker --context default compose --env-file %q -p %q --project-directory %q -f %q "$@"; }\n' \
  "$ROOT/.env" "$PROJECT" "$ROOT" "$ROOT/compose.yaml" > "$evidence/dc.sh"

fail() { echo "ERROR: $1" >&2; exit 1; }
d() { docker --context default "$@"; }
dc() {
  d compose --env-file "$ROOT/.env" -p "$PROJECT" \
    --project-directory "$ROOT" -f "$ROOT/compose.yaml" "$@"
}
run_step() {
  step=$1
  shift
  echo "$step"
  # Keep raw process output out of evidence: it can contain configuration values.
  if "$@" >/dev/null 2>&1; then
    printf '%s: ok\n' "$step" >> "$evidence/checkpoint.txt"
  else
    code=$?
    printf '%s: failed (exit %s)\n' "$step" "$code" >> "$evidence/checkpoint.txt"
    exit "$code"
  fi
}
check_container() {
  identity=$(d inspect --format '{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}|{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$1" 2>/dev/null)
  [[ $identity == "$PROJECT|$2|$ROOT" ]] || fail "Unexpected container ownership; nothing will be reset."
}
check_volume() {
  identity=$(d volume inspect --format '{{.Name}}|{{index .Labels "com.docker.compose.project"}}|{{index .Labels "com.docker.compose.volume"}}|{{.Driver}}|{{if .Options}}configured{{else}}none{{end}}' "$db_volume" 2>/dev/null)
  [[ $identity == "$db_volume|$PROJECT|postgres_data|local|none" ]] || fail "Unexpected DB volume ownership or storage; nothing will be reset."
}

# Compose must use the recording file, not ambient credentials, endpoints or profiles.
unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH
unset DATABASE_URL POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD
unset ADMIN_HUMAN_API_KEY DEMO_HUMAN_API_KEY INCIDENT_HARNESS_API_KEY RESTRICTED_HARNESS_API_KEY
unset TRIAGE_AGENT_MODEL TRIAGE_AGENT_PROVIDER REMEDIATION_AGENT_MODEL REMEDIATION_AGENT_PROVIDER
unset OPENROUTER_API_KEY OPENROUTER_MANAGEMENT_API_KEY OPENROUTER_TIMEOUT_SECONDS AUDIT_HMAC_KEY
unset COMPOSE_PROJECT_NAME COMPOSE_FILE COMPOSE_PROFILES RUN_OPENROUTER_LIVE_SMOKE
unset SRE_AGENT_APPLICATION_VERSION SRE_AGENT_CONTRACT_VERSION SRE_AGENT_BUILD_REVISION
export API_PORT=26200 WEB_PORT=26201 POSTGRES_PORT=26202

[[ -f $ROOT/.env && -f $ROOT/compose.yaml ]] || fail "The pinned recording checkout or its existing .env is missing."
[[ $(git -C "$ROOT" rev-parse --show-toplevel) == "$ROOT" ]] || fail "Unexpected recording repository root."
[[ $(git -C "$ROOT" rev-parse HEAD) == "$SHA" ]] || fail "Recording SHA changed; review it before proceeding."
if ! git -C "$ROOT" diff --quiet || ! git -C "$ROOT" diff --cached --quiet; then
  fail "Recording source has tracked changes."
fi
case $(d context inspect default --format '{{(index .Endpoints "docker").Host}}') in
  unix://*) ;;
  *) fail "Only the local Unix-socket Docker context is supported." ;;
esac
run_step "Validate Compose configuration" dc config --quiet
images=$(dc config --images db migrate seed api web 2>/dev/null)
[[ -n $images ]] || fail "No runtime images resolved."
while IFS= read -r image; do
  d image inspect "$image" --format '{{.Id}}' >/dev/null 2>&1 || fail "A required image is missing; build the pinned services manually using runbook section 3."
done <<< "$images"

db_id=
for service in api web db; do
  id=$(dc ps --all --quiet "$service")
  [[ $id != *$'\n'* ]] || fail "Multiple containers exist for a target service."
  if [[ -n $id ]]; then
    check_container "$id" "$service"
  fi
  if [[ $service == db ]]; then db_id=$id; fi
done
db_volume=${PROJECT}_postgres_data
if [[ -n $db_id ]]; then
  mount=$(d inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{if eq .Type "volume"}}{{.Name}}{{end}}{{end}}{{end}}' "$db_id")
  [[ $mount == "$db_volume" ]] || fail "PostgreSQL is not mounted on the expected named volume."
fi
if d volume inspect "$db_volume" >/dev/null 2>&1; then check_volume; fi
if [[ $reset == 1 ]]; then
  [[ -n $db_id ]] || fail "No existing DB container to validate. Run without --reset to finish an interrupted setup."
  check_volume
  consumers=$(d ps --all --quiet --no-trunc --filter "volume=$db_volume")
  [[ $consumers == "$db_id" ]] || fail "The DB volume has unexpected consumers; nothing will be reset."
  printf 'validated_db_volume=%s\n' "$db_volume" >> "$evidence/checkpoint.txt"
  echo "Resetting ONLY $PROJECT: recorded incidents, decisions and audit will be erased."
  run_step "Stop triage api/web/db" dc stop api web db
  run_step "Remove triage api/web/db containers" dc rm --force api web db
  check_volume
  run_step "Remove validated triage DB volume" d volume rm "$db_volume"
fi

run_step "Start triage database" dc up -d --no-build --pull never --wait --wait-timeout 60 db
run_step "Apply pinned migrations" dc run --rm -T --no-deps --pull never migrate
run_step "Seed governance identities" dc run --rm -T --no-deps --pull never seed
run_step "Start triage API" dc up -d --no-deps --no-build --pull never --wait --wait-timeout 60 api
run_step "Start triage web" dc up -d --no-deps --no-build --pull never --wait --wait-timeout 60 web

step="Provision and verify exact permissions and unopened alert"
if dc run --rm -T --no-deps --pull never -e RECORDING_RESET="$reset" -v "$ROOT/scripts:/app/scripts:ro" seed python - > "$evidence/verification.txt" 2>/dev/null <<'PY'
import asyncio
import json
import os
import urllib.error
import urllib.request

from sqlalchemy import text
from scripts.provision_incident_workflow import (
    CATALOG_BODY, CATALOG_IDEMPOTENCY_KEY, GRANT_BODY, GRANT_IDEMPOTENCY_KEY,
)
from sre_agent.governance.authorization import AuthorizationDecisionEngine
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import CredentialRepository, GrantRepository, ResourceRepository


class PreparationError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise PreparationError(message)


def request(url, key=None, body=None, idempotency=None):
    headers = {}
    if key:
        headers["Authorization"] = "Bearer " + key
    if body is not None:
        headers["Content-Type"] = "application/json"
        headers["Idempotency-Key"] = idempotency
    query = urllib.request.Request(
        url, data=None if body is None else json.dumps(body).encode(), headers=headers,
    )
    try:
        with urllib.request.urlopen(query, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


async def verify(bodies):
    database = Database(os.environ["DATABASE_URL"])
    try:
        async with database.sessions() as session:
            version = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
            require(version == "20260923_13", "Unexpected migration revision.")
            print("migration: 20260923_13")
            credentials = CredentialRepository(session)
            operator = await credentials.authenticate(os.environ["DEMO_HUMAN_API_KEY"])
            restricted = await credentials.authenticate(os.environ["RESTRICTED_HARNESS_API_KEY"])
            require(operator and operator.principal.principal_id == "demo-human", "Operator identity mismatch.")
            require(restricted and restricted.principal.principal_id == "restricted-harness", "Restricted identity mismatch.")
            grants = GrantRepository(session)
            engine = AuthorizationDecisionEngine(ResourceRepository(session), grants)
            for body in bodies:
                grant = await grants.get(body["grant_id"])
                require(grant and grant.status == "active" and grant.effect == "allow"
                        and grant.principal_id == "demo-human" and grant.action == body["action"]
                        and grant.resource.resource_type == "incident_workflow"
                        and grant.resource.resource_id == "incident-response", "Grant is missing, changed or revoked.")
                allowed = await engine.evaluate(operator.principal, body["action"], "incident_workflow", "incident-response")
                denied = await engine.evaluate(restricted.principal, body["action"], "incident_workflow", "incident-response")
                require(allowed.decision.decision == "allow" and denied.decision.decision == "deny", "Authorization verification failed.")
                print(body["action"] + ": persisted active; demo-human allow; restricted-harness deny")
            incidents = (await session.execute(text("SELECT count(*) FROM incident.incidents"))).scalar_one()
            decisions = (await session.execute(text("SELECT count(*) FROM alert_triage"))).scalar_one()
            if os.environ["RECORDING_RESET"] == "1":
                require(incidents == 0 and decisions == 0, "Reset did not leave an empty recording state.")
            print(f"recording state: {incidents} incidents; {decisions} triage decisions")
    finally:
        await database.dispose()


def main():
    status, payload = request("http://api:8000/health/ready")
    require(status == 200 and json.loads(payload) == {"status": "ok", "dependency": "postgresql"}, "Readiness failed.")
    print("readiness: HTTP 200; PostgreSQL ready")
    admin = os.environ["ADMIN_HUMAN_API_KEY"]
    status, _ = request("http://api:8000/v1/catalog/resources", admin, CATALOG_BODY, CATALOG_IDEMPOTENCY_KEY)
    require(status == 201, "Workflow catalog provisioning failed.")
    bodies = [GRANT_BODY]
    for action in ("alert.read", "alert.triage", "alert.dismiss", "alert.associate", "incident.declare"):
        bodies.append({
            "grant_id": "grant-demo-human-" + action.replace(".", "-") + "-incident-response",
            "principal_id": "demo-human", "action": action, "effect": "allow",
            "resource": {"resource_type": "incident_workflow", "resource_id": "incident-response"},
        })
    for body in bodies:
        key = GRANT_IDEMPOTENCY_KEY if body["action"] == "run.read" else "recording-demo-" + body["action"] + "-grant-v1"
        status, _ = request("http://api:8000/v1/grants", admin, body, key)
        require(status == 201, "Exact permission provisioning failed.")
    asyncio.run(verify(bodies))
    status, payload = request("http://web/api/v1/alerts/alert-payment-002/triage", os.environ["DEMO_HUMAN_API_KEY"])
    require(status == 404 and json.loads(payload).get("error", {}).get("code") == "triage_not_found",
            "alert-payment-002 already has a decision or could not be read. Use --reset for a new recording.")
    print("alert-payment-002: HTTP 404 triage_not_found; ready for manual open_triage version 1")
    status, _ = request("http://web/api/v1/alerts/alert-payment-002/triage", os.environ["RESTRICTED_HARNESS_API_KEY"])
    require(status == 403, "Restricted identity is not denied by the HTTP boundary.")
    print("restricted-harness: HTTP 403")
    status, _ = request("http://web/public/incident-ui/alerts.html")
    require(status == 200, "Alert inbox is unavailable.")
    status, _ = request("http://web/public/admin/triage.html")
    require(status == 200, "Triage UI is unavailable.")
    print("UI: inbox and triage HTTP 200")


try:
    main()
except PreparationError as error:
    print("ERROR: " + str(error))
    raise SystemExit(1) from None
except Exception as error:
    print("ERROR: preparation failed (" + type(error).__name__ + "); no secret-bearing details emitted.")
    raise SystemExit(1) from None
PY
then
  cat "$evidence/verification.txt"
  printf '%s: ok\n' "$step" >> "$evidence/checkpoint.txt"
else
  cat "$evidence/verification.txt"
  fail "Preparation verification failed; preserve this checkpoint and stop."
fi
step=ready
echo "Inbox: http://127.0.0.1:26201/public/incident-ui/alerts.html"
echo "Triage: http://127.0.0.1:26201/public/admin/triage.html?alert_id=alert-payment-002"
echo "Use the existing DEMO_HUMAN_API_KEY in the UI off camera; do not paste it into logs."
