# Change events: what changed, and when

Issue #770. Midnight records every deploy, rollback and CI result of a service as a change event,
so an investigation can ask "what changed" before it guesses. One event carries the service, the
version or image, the commit, the author, the ref, a link to the run and the time.

## API

| Route | Grant over `incident_workflow/incident-response` | Answer |
| --- | --- | --- |
| `POST /v1/changes` | `change.write` | `201` with the new event, or `200` with the stored one when `(source, external_id, service)` was already recorded (`created: false`); the first write wins |
| `GET /v1/changes?service=&since=&limit=` | `change.read` | Newest first, at most `limit` (1-100, default 20) |

Body of the `POST`: `source` (for example `github-actions`), `external_id` (the source's run id),
`service`, `kind` (`deploy`, `rollback` or `ci`), `status` (`succeeded` or `failed`), and the
optional `version`, `commit_sha`, `ref`, `author`, `url` and `occurred_at` (default: now). Unknown
fields are rejected with `422`. Recording an event never opens an incident nor notifies anyone: a
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
commit, ref, author and the idempotency key (`<repository>/actions/runs/<run id>/attempts/<attempt>`)
from the run itself, so a resent step never duplicates the event while a re-run attempt records
a new one. When Midnight does not record the event the step warns and the deploy stays green;
set `fail-on-error: "true"` to fail it instead.
