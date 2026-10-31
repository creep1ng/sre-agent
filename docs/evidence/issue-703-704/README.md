# Live triage from the new console (#703) and the server-started investigation (#704)

Browser journeys of the new console at `/app/` against the real API, PostgreSQL, the web proxy
and the console image, recorded on 2026-10-31 on one fresh stack, in the order below. Only the
model and the Grafana MCP upstream are stand-ins (`compose.live-triage-e2e.yaml`,
`scripts/live_triage_upstreams.py`): the model concludes at once (or after
`$LIVE_TRIAGE_FAULTS/model-delay` seconds) and each alert rule fires unless
`$LIVE_TRIAGE_FAULTS/{rule id}` reads `ok`. Live alerts still go through `GET /v1/alerts`, the
governed MCP path and the caller's grants. No real LLM call was made.

`stack/` holds one folder per scenario with its screenshots and the compact `verification.json`
the spec wrote. The console's incident page does not read live incidents yet (#708), so the
auto-investigate and dispatch-recovery folders record FastAPI's own events and timeline pages.

| Folder | Scenario |
| --- | --- |
| `auto-investigate-granted/` | declare from the card; the run is not pending within 5 s; a replay adds no run |
| `auto-investigate-no-grant/` | a declarant without `run.start`: a `run_start_blocked` event, no run |
| `declare/` | prefilled dialog, one stale-version retry, a lost answer retried with the same key |
| `triage-dismiss/`, `triage-conflict/`, `triage-link/` | dismiss with a stale retry, a Spanish refusal, link listing the incident by its alert |
| `dispatch-recovery/` | API killed mid-dispatch, then restarted; a hand-off that fails before its claim |

## Reproduce

Every spec opens its own alert episode (`web/incident-console/e2e/live-faults.ts`), so they run
one after another. From a checkout with `.env` (local `sre_` keys, `AUDIT_HMAC_KEY`):

```sh
export LIVE_TRIAGE_FAULTS=/tmp/live-triage-faults; mkdir -p "$LIVE_TRIAGE_FAULTS"
DC="docker compose --project-name live-triage-704 -f compose.yaml -f compose.e2e.yaml -f compose.live-triage-e2e.yaml"
$DC up --build --wait db api web incident-console
$DC run --rm --no-deps -T seed python -m sre_agent.persistence.seeds --seed-mcp
$DC run --rm --no-deps -T seed python /e2e/provision_demo.py
E2E="$DC --profile e2e run --build --rm --no-deps incident-console-e2e npx playwright test"
AUTO_INVESTIGATE=granted $E2E e2e/auto-investigate-live.spec.ts
AUTO_INVESTIGATE=no-grant $E2E e2e/auto-investigate-live.spec.ts
LIVE_DECLARE=1 $E2E e2e/declare-live.spec.ts
LIVE_TRIAGE=dismiss $E2E e2e/triage-live.spec.ts
LIVE_TRIAGE=conflict $E2E e2e/triage-live.spec.ts
LIVE_TRIAGE=link $E2E e2e/triage-live.spec.ts
# An API restart in the middle of a dispatch (the spec holds the model, then stops):
DISPATCH_RECOVERY=interrupt $E2E e2e/dispatch-recovery-live.spec.ts
$DC kill api && $DC up -d --wait api
DISPATCH_RECOVERY=interrupted $E2E e2e/dispatch-recovery-live.spec.ts
# A hand-off that fails before its claim: the investigator's identity cannot be read.
PSQL='psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
echo "UPDATE principals SET display_name='' WHERE principal_id='incident-harness';" | $DC exec -T db sh -c "$PSQL"
DISPATCH_RECOVERY=handoff-failure $E2E e2e/dispatch-recovery-live.spec.ts
echo "UPDATE principals SET display_name='Incident harness' WHERE principal_id='incident-harness';" | $DC exec -T db sh -c "$PSQL"
$DC down -v --remove-orphans
```

Artifacts land in `web/incident-console/e2e/artifacts/`, written by the runner's root user.
