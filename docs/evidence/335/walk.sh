#!/usr/bin/env bash
# Usage: bash docs/evidence/335/walk.sh <env-file> after prepare.sh. Needs curl and jq.
# Credentials are read from the env file and never printed.
set -u
ENV_FILE=$1; INC=inc-pm335-demo; BODY=$(mktemp)
API=http://127.0.0.1:$(grep "^API_PORT=" "$ENV_FILE" | cut -d= -f2-)
key() { grep "^$1=" "$ENV_FILE" | cut -d= -f2-; }
DEMO=$(key DEMO_HUMAN_API_KEY); HARNESS=$(key INCIDENT_HARNESS_API_KEY)
call() { # call <bearer> <method> <path> [body] [idem]
  local args=(-s -o $BODY -w '%{http_code}' -X "$2" "$API$3" -H "Authorization: Bearer $1" -H 'Content-Type: application/json')
  [ -n "${5:-}" ] && args+=(-H "Idempotency-Key: $5")
  [ -n "${4:-}" ] && args+=(-d "$4")
  local code; code=$(curl "${args[@]}")
  echo "$2 $3${5:+  Idempotency-Key: $5}"; [ -n "${4:-}" ] && echo "body: $(jq -c . <<<"$4")"
  echo "HTTP $code  $(jq -c . $BODY 2>/dev/null || cat $BODY)"
}
ref='{"reference_version":"1.0.0","principal_id":"demo-human"}'
ver() { call "$DEMO" GET "/v1/incidents/$INC" >/dev/null; jq -r '.version // .incident_version' $BODY; }
state() { call "$DEMO" GET "/v1/incidents/$INC" >/dev/null; echo "incident: $(jq -c '{state, version, runs: [.runs[] | {run_id, current_state, status}]}' $BODY)"; }
content() { # content <timeline_event> <action_event> <summary>
  jq -cn --arg t "$1" --arg a "$2" --arg s "$3" '{summary:$s, impact:"About 3% of checkouts failed for 14 minutes; revenue impact unknown.", timeline:[{event_id:$t, description:"Stability check passed after the rollback."}], cause:{statement:"A config push removed the payment client timeout.", certainty:"probable"}, strategy:"Roll back the config and add a timeout guard.", actions_taken:[{event_id:$a, description:"Postmortem opened after resolution."}], verification:"Error rate stayed below 1% for 15 minutes.", pending:["Add a config lint for client timeouts."], unknowns:["Exact revenue impact."]}'; }

echo "### 0. Starting point"; state
echo; echo "### 1. verification_passed (run-command:2.1.0, #658): verifying -> resolved"
call "$DEMO" POST "/v1/incidents/$INC/runs/run_pm335verify/commands" "{\"command\":\"verification_passed\",\"actor\":\"human\",\"actor_reference\":$ref,\"expected_incident_version\":$(ver)}" pm335-verify-1
state
echo; echo "### 2. start_postmortem via POST /runs objective=postmortem: resolved -> postmortem, pm_ id reserved"
call "$DEMO" POST "/v1/incidents/$INC/runs" '{"workflow_version":"1.0.0","objective":"postmortem"}' pm335-start-pm-1
PMRUN=$(jq -r .run_id $BODY); state
call "$DEMO" GET "/v1/incidents/$INC/runs/$PMRUN/events" >/dev/null
echo "events of $PMRUN: $(jq -c '[.events[] | {event_id, kind}]' $BODY)"
STARTED=$(jq -r '.events[0].event_id' $BODY)
call "$DEMO" GET "/v1/incidents/$INC/runs/run_pm335verify/events" >/dev/null
VERIFIED=$(jq -r '.events[0].event_id' $BODY)
close() { call "$DEMO" POST "/v1/incidents/$INC/runs/$PMRUN/commands" "{\"command\":\"close_incident\",\"actor\":\"human\",\"actor_reference\":$ref,\"expected_incident_version\":$(ver),\"authorization\":{\"action\":\"run.approve\",\"resource\":{\"type\":\"incident_workflow\",\"id\":\"incident-response\"}},\"comment\":\"Postmortem reviewed.\"}" "$1"; }
put() { call "$DEMO" PUT "/v1/incidents/$INC/postmortem" "{\"expected_version\":$1,\"content\":$2}"; }

echo; echo "### 3. close_incident with only the reserved pm_ id: refused, incident unchanged"
close pm335-close-early; state
echo; echo "### 4. citation of an event that does not exist: 422"
put 0 "$(content evt_doesnotexist "$STARTED" 'Checkout payments failed for 14 minutes.')"
echo; echo "### 5. create the artifact (expected_version 0): 201; repeated create: 409, no duplicate"
put 0 "$(content "$VERIFIED" "$STARTED" 'Checkout payments failed for 14 minutes.')"
put 0 "$(content "$VERIFIED" "$STARTED" 'Checkout payments failed for 14 minutes.')"
echo; echo "### 6. edit version 1 -> 2: 200; stale edit still naming version 1: 409"
put 1 "$(content "$VERIFIED" "$STARTED" 'Checkout payments failed for 14 minutes after a config push.')"
put 1 "$(content "$VERIFIED" "$STARTED" 'Stale writer text.')"
echo; echo "### 7. restart the API, then reread: same id and version"
docker compose -p sre-pm335 --env-file "$ENV_FILE" restart api >/dev/null 2>&1
until curl -sf "$API/health/ready" >/dev/null; do sleep 1; done; echo "api restarted and ready"
call "$DEMO" GET "/v1/incidents/$INC/postmortem"
echo; echo "### 8. reader holding run.read without run.read_context (incident-harness): projection without text"
call "$HARNESS" GET "/v1/incidents/$INC/postmortem"
echo; echo "### 9. review of an older version: 409; approve the current version 2: 201, attributed to the caller"
call "$DEMO" POST "/v1/incidents/$INC/postmortem/reviews" '{"version":1,"outcome":"approved"}'
call "$DEMO" POST "/v1/incidents/$INC/postmortem/reviews" '{"version":2,"outcome":"approved","comment":"Matches the timeline."}'
echo; echo "### 10. edit after the review (version 3) voids it: close refused"
put 2 "$(content "$VERIFIED" "$STARTED" 'Checkout payments failed for 14 minutes after a config push removed a timeout.')"
close pm335-close-stale; state
echo; echo "### 11. approve version 3, then close: postmortem -> closed"
call "$DEMO" POST "/v1/incidents/$INC/postmortem/reviews" '{"version":3,"outcome":"approved"}'
close pm335-close-final; state
echo; echo "### 12. editing a closed incident's postmortem: 409"
put 3 "$(content "$VERIFIED" "$STARTED" 'Late edit.')"
