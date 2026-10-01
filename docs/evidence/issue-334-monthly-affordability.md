# Issue #334 — monthly affordability

**Delivery route:** delegated direct, pure calculation extension on the separately frozen endpoint/incident affordability slice.

## Behavior and limits

An active monthly balance requires explicit prompt, completion, and request prices from the unique fresh endpoint. Missing price is unknown, not zero. The calculator subtracts conservative endpoint maximum-prompt cost and request fee, then floors the remaining exact `Decimal` USD capacity to a completion-token maximum, clamped by endpoint and incident limits. Equality is affordable. An unset monthly dimension (`None`) disables only the monthly cap; zero is active and permits a request only when all known costs are zero. No incident still leaves monthly enforcement active. Incident zero continues to deny positive output.

This unit computes affordability only. It does not wire runtime admission, reservations, atomicity, settlement, live catalog/inference, historical `#130/#333` accounting, or whole-issue acceptance. UTC admission-month selection and historical terminal-usage provenance belong to their respective policy/admission boundaries; this calculator does not rewrite history.

## Repeat locally

From a clean checkout, copy `.env.example` to ignored `.env` and run `scripts/bootstrap-worktree.py` to create a unique Compose project. Use a free isolated network if Docker's default allocator conflicts.

```sh
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_consumption_affordability.py'
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm python-checks python scripts/consumption_monthly_affordability_demo.py
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm harness npm --prefix schemas/tooling run conformance -- --consumer issue-10
```

The committed tests cover endpoint/incident bounds, exact Decimal cost, request fee, active zero/free requests, unset balances, malformed prices and invalid balances. The demo uses only synthetic endpoint values; no credential, paid request or live provider is needed. The exact candidate SHA, full-run output, image/lock provenance, commands and actual capture are recorded in `/tmp/issue334-monthly-affordability-evidence-20260930/REPORT.md`.

## Actual output

`issue-334-monthly-affordability.png` is a native Chromium screenshot of the actual offline Docker demo output, not generated art or product UI. With prompt cost $0.50, request fee $0.20, completion cost $0.10/token, and monthly remaining exactly $1.00, the output cap is 3; all costs then equal the budget. All-free pricing at monthly zero admits to the endpoint ceiling; an unknown prompt fee at zero denies; an unset monthly dimension with unpriced metadata leaves the endpoint cap unchanged. These are controlled calculator results, not live-provider or runtime-admission evidence.
