# Change events: what changed, and when

Issue #770. Midnight records every deploy, rollback and CI result of a service as a change event,
so an investigation can ask "what changed" before it guesses. One event carries the service, the
version or image, the commit, the author, the ref, a link to the run and the time.

## API

| Route | Grant over `incident_workflow/incident-response` | Answer |
| --- | --- | --- |
| `POST /v1/changes` | `change.write` | `201` with the new event; `200` with the stored one when `(source, external_id, service)` was already recorded with the same payload (`created: false`); `409 change_conflict` when that key was recorded with another payload |
| `GET /v1/changes?service=&since=&limit=` | `change.read` | Newest first, at most `limit` (1-100, default 20); `since` is an ISO 8601 time with its offset, written `Z` or URL-encoded as `%2B00:00` (a bare `+` in a query string reads as a space) |

Body of the `POST`: `source` (for example `github-actions`), `external_id` (the source's run id),
`service`, `kind` (`deploy`, `rollback` or `ci`), `status` (`succeeded` or `failed`), and the
optional `version`, `commit_sha`, `ref`, `author`, `url` and `occurred_at` (default: now; more
than 5 minutes in the future is rejected with `422`). Unknown fields are rejected with `422`. A
resend without `occurred_at` keeps the stored time; every other field must match or it is a `409`. Recording an event never opens an incident nor notifies anyone: a
red CI run on `main` is a change with `kind: ci` and `status: failed` that readers such as the
interruption budget (#771) can weigh.

The endpoint is generic. Only the GitHub Actions integration is built (decision of 2026-10-29).

## GitHub Actions

Create an agent principal for the repository, give it only `change.write`, issue it a credential
and store it as a repository secret. Then add the step after the deploy:

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./deploy.sh sre-checkout 1.5.0
      - uses: creep1ng/sre-agent/.github/actions/record-change@main
        if: always()
        with:
          midnight-url: ${{ vars.MIDNIGHT_URL }}
          api-key: ${{ secrets.MIDNIGHT_CHANGES_KEY }}
          service: sre-checkout
          version: demo/checkout:1.5.0
          status: ${{ job.status == 'success' && 'succeeded' || 'failed' }}
```

For a CI workflow on `main`, use `kind: ci` in the same way. The step derives the run link,
commit, ref, author and the idempotency key
(`<repository>/actions/runs/<run id>/attempts/<attempt>/jobs/<job id>/<kind>`) from the run
itself, so a resent step never duplicates the event, a re-run attempt records a new one, and a
`ci` job and a `deploy` job of the same run are two events. Using the step twice in one job with
the same kind and service but another payload answers `409`, which the step reports. When
Midnight does not record the event (unreachable, refused, an unexpected answer) the step warns
and the deploy stays green; set `fail-on-error: "true"` to fail it instead. Its messages never
include the API key.

## The investigator

An investigation whose identity holds `change.read` (`scripts/provision_demo.py` grants it to
`incident-harness`) is offered the tool `midnight_recent_changes` with a `service` argument. It
returns the service's last ten changes as evidence the hypothesis can cite, with the `request_id`
of the `GET /v1/changes` that served them, so the citation leads back to the read. The investigator
client answers this tool itself and never forwards it to Grafana MCP; the gateway only exposes its
closed list of MCP tools (`query_prometheus`, `query_elasticsearch`), and the `midnight_` prefix
keeps a future MCP tool from taking the name.

## Rollbacks

The deploy-executor records each rollback it completes as `source: deploy-executor`,
`kind: rollback`, `version` = the image it rolled back to, keyed by its execution id. It uses
`DEPLOY_EXECUTOR_CHANGES_API_KEY`, a credential of the agent principal `deploy-executor` that
holds `change.write` only; `scripts/provision_demo.py` creates that principal, its credential and
the grant from the key in `.env`, so the demo setup needs no console step. Without the key it
records nothing. The record is sent after the rollback has answered and never changes that
answer: a failed record is logged without the key. The executor reaches the API over the
internal `executor-call` network it already shares with it. What this adds to the executor's
attack surface is in [deploy-executor.md](deploy-executor.md#known-limitations-of-the-academic-demo).
