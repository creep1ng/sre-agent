#!/usr/bin/env bash
# Usage: bash docs/evidence/335/prepare.sh <env-file>, from the checkout root.
# Brings up the scoped sre-pm335 stack, provisions run grants and seeds a verifying incident.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd); ENV_FILE=$1; API=http://127.0.0.1:$(grep "^API_PORT=" "$ENV_FILE" | cut -d= -f2-); P=(-p sre-pm335 --env-file "$ENV_FILE")
SRE_AGENT_BUILD_REVISION=$(git rev-parse HEAD) docker compose "${P[@]}" up -d --build --wait api >/dev/null 2>&1
export ADMIN_API_KEY=$(grep '^ADMIN_HUMAN_API_KEY=' "$ENV_FILE" | cut -d= -f2-) AUDIT_KEY_HEX=$(openssl rand -hex 32)
docker compose "${P[@]}" run --rm --no-deps -v "$PWD/scripts:/app/scripts:ro" -e ADMIN_API_KEY -e AUDIT_KEY_HEX seed python scripts/provision_incident_workflow.py 2>/dev/null
for g in "demo-human run.read_context" "incident-harness run.read"; do set -- $g
  curl -s -o /dev/null -w "grant $1 $2 -> %{http_code}\n" -X POST "$API/v1/grants" -H "Authorization: Bearer $ADMIN_API_KEY" -H "Idempotency-Key: pm335-$1-$2" -H 'Content-Type: application/json' \
    -d "{\"grant_id\":\"grant-pm335-$1-${2//./-}\",\"principal_id\":\"$1\",\"action\":\"$2\",\"resource\":{\"resource_type\":\"incident_workflow\",\"resource_id\":\"incident-response\"},\"effect\":\"allow\"}"
done
docker compose "${P[@]}" exec -T db sh -c 'psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$HERE/seed.sql" && echo "seeded inc-pm335-demo (verifying)"
