# War room runs — revalidation on the rebased base (#37, #652)

Recorded October 18, 2026, 19:25–19:36 COT, one sequential session. Every number
below is from this run; nothing is copied from earlier records.

## Tested and base SHAs
- Tested SHA: f8d723031a3a09eadf271c1212a1e7e248aa25ad (PR #652 head after the rebase)
- Base SHA: 317b17f8fe82f3c94beb70899de4093ecf949ec2 (PR #651 head rebased onto main)
- main: d9eb9fb0a937e2e8afee0fc1473098ad5f897e36 (#654 fix(web) + #656 docs(ops))

## Environment
- compose project sre-agent-37; inline overrides on every invocation:
  WEB_PORT=8091 API_PORT=8011 POSTGRES_PORT=5439.
- persisted demo volume sre-agent-37_postgres_data reused; no `-v` anywhere.
- stamps: base 2026-10-19 (idempotent reuse per the seed script design); fresh
  2026-10-19-spec-rb, 2026-10-19-probe-rb, 2026-10-19-cap-rb. The -mon set stays
  reserved for the demo operator run and was not consumed here.
- provision over the persisted volume: 409s with the printed summary confirming
  run_read_active, run_start_active, run_command_active, run_approve_active all
  true (the documented benign path).

## Real-backend spec and HTTP probes
- tests/browser/war-room-runs-real.spec.js: 4 passed (10.1 s) on stamp
  2026-10-19-spec-rb (start+reload, double-click, restricted 403, 404/401).
- Direct probes through the web proxy on stamp 2026-10-19-probe-rb:
  - POST /api/v1/incidents/inc-37-start-2026-10-19-probe-rb/runs → 201;
    run_id run_c4c2a75efc29cd82, current_state investigating.
  - The same POST replayed with the same Idempotency-Key → 200 with the
    identical run_id; no second run appeared.
  - GET the same incident detail → 200 with exactly one run.
  - GET with the restricted harness credential → 403 not_authorized with no
    run ids leaked in the body.
  - GET an unknown incident → 404 incident_not_found.
- Capture on stamp 2026-10-19-cap-rb: one real run started from the UI,
  run_700e2780f1e2cd15, strip "Run en curso · Investigando"; PNG recorded at
  docs/evidence/37-war-room-run-start-revalidated.png. The capture script
  writes the fixed historical path, so the historical PNG was restored
  bit-for-bit from the commit (sha256 of both sides:
  46298e733d72af13369e13e6d928746642ff131b15d11ef787af8aeee9f619f7).

## Regression suites at this tree
- Static Python guards (war-room + postmortem): 8 passed, 0.09 s.
- Full tests/browser/war-room.spec.js (mocked, static-host pattern):
  32 passed, 1.3 m — the 28 pre-existing scenarios, the #654 375px timeline
  test, and the four mocked journeys added by #652.
- Production lane on the compose network (CI-equivalent; the real spec skips
  without SRE_REAL_BACKEND): 145 passed, 4 skipped, 1.8 m.

## Infra incidents during this session (recovered; product evidence unaffected)
1. First compose calls failed because this worktree initially had no .env
   (interpolation errors). Fixed by copying the authorized .env locally; no
   key value was ever printed.
2. One compose up and one compose run were invoked without the inline port
   overrides and bounced against the main stack's busy 55433/8000/8080 ports.
   Recovered by re-running those steps with the overrides ON the command line,
   per the runbook. No data was created or deleted; volumes stayed intact.

## Still outside this record (unchanged claims)
- The resume action, a real stale-version 409 transport, and live denied/503
  scenarios remain mocked-only, exactly as the #652 body already states.
- Cleanup: compose down without -v at 19:36 COT; ports free afterwards;
  neighboring stacks untouched.
