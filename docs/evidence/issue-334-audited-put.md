# Audited consumption-policy replacement — issue #334

This unit adds administrator-only `PUT /v1/consumption-limits` with expected-version
compare-and-set, bounded idempotency, exact decimal values, and metadata-only
`consumption_limits.replace` audit events. It does not enforce admission or settle
provider usage; existing policy read, published cost history, and #333 behavior remain.

The policy mutation, idempotency response, and audit append share one SQL transaction.
Audit failure returns retryable `503` and rolls back policy/idempotency state. Requests
use request-only synthetic authentication; credentials never appear in the URL, page,
response, screenshot, or committed files. No provider credential/call is configured.

Evidence kind: controlled local integration. Actual browser capture: [audited policy
replacement](issue-334-audited-put.png). It shows the response only; SQL and tests
verify the corresponding persisted state and audit behavior separately.

## Reproduce

Prepare synthetic local `.env`, bootstrap `.env.worktree`, and use the isolated
worktree Compose network/database. Run at repository root:

```sh
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml -f /tmp/issue334-audited-put-evidence-20260930/compose-network.override.yaml --profile checks run --build --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_control_acceptance.py -k consumption_policy'
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml -f /tmp/issue334-audited-put-evidence-20260930/compose-network.override.yaml --profile checks run --build --rm python-checks
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml -f /tmp/issue334-audited-put-evidence-20260930/compose-network.override.yaml --profile checks run --build --rm harness npm --prefix schemas/tooling run conformance -- --consumer issue-10
```
