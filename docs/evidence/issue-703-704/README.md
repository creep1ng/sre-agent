# Live triage from the new console (#703) and the server-started investigation (#704)

Browser journeys of the new console at `/app/` against the real API, PostgreSQL, the web proxy
and the console image, recorded on 2026-10-31. Only the model and the Grafana MCP upstream are
stand-ins (`compose.live-triage-e2e.yaml`, `scripts/live_triage_upstreams.py`): the model
concludes at once and each alert rule fires unless `$LIVE_TRIAGE_FAULTS/{rule id}` reads `ok`.
Live alerts still go through `GET /v1/alerts`, the governed MCP path and the caller's grants.
No real LLM call was made.

| Folder | Candidate | Scenarios |
| --- | --- | --- |
| `pr2-declare/` | head of the declare PR | declare, with one stale-version retry |
| `pr3-triage/` | head of the dismiss and link PR | dismiss, conflict, link |
| `stack/` | head of the E2E PR, one fresh stack | all of the above, plus auto-investigate `granted` and `no-grant` |

Each folder holds the screenshots and a compact `verification.json` the spec wrote. The incident
route renders «No encontramos ese incidente» for live incidents: reading them there is #708, so
`stack/auto-investigate-*/` also records FastAPI's own events and timeline pages.

## Reproduce

From a worktree with `.env` (non-placeholder local keys) and `.env.worktree`
(`scripts/bootstrap-worktree.py`):

```sh
export LIVE_TRIAGE_FAULTS=/tmp/live-triage-faults; mkdir -p "$LIVE_TRIAGE_FAULTS"
F="-f compose.e2e.yaml -f compose.live-triage-e2e.yaml"
scripts/worktree-compose $F up --build --wait db api web incident-console
scripts/worktree-compose $F run --rm --no-deps -T seed python -m sre_agent.persistence.seeds --seed-mcp
scripts/worktree-compose $F run --rm --no-deps -T seed python /e2e/provision_demo.py
run() { scripts/worktree-compose $F --profile e2e run --build --rm --no-deps incident-console-e2e \
  sh -c "npx playwright test $1; s=\$?; chown -R $(id -u):$(id -g) e2e/artifacts /fault; exit \$s"; }
AUTO_INVESTIGATE=granted run e2e/auto-investigate-live.spec.ts
```

Each scenario consumes one `Nueva` alert. Before the next one, end and reopen both episodes:
write `ok` to `$LIVE_TRIAGE_FAULTS/checkout-payment-error-rate` and
`$LIVE_TRIAGE_FAULTS/checkout-orders-error-rate`, let the console (or any `GET /v1/alerts`) poll
once, then delete both files. Then:

```sh
AUTO_INVESTIGATE=no-grant run e2e/auto-investigate-live.spec.ts
LIVE_DECLARE=1 run e2e/declare-live.spec.ts
LIVE_TRIAGE=dismiss run e2e/triage-live.spec.ts
LIVE_TRIAGE=conflict run e2e/triage-live.spec.ts
# link flips checkout-payment-error-rate itself; keep the other rule quiet so only one episode is new
echo ok > "$LIVE_TRIAGE_FAULTS/checkout-orders-error-rate"
LIVE_TRIAGE=link run e2e/triage-live.spec.ts
scripts/worktree-compose $F down -v --remove-orphans
```

Artifacts land in `web/incident-console/e2e/artifacts/`.
