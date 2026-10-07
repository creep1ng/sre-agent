# Issue #334 — endpoint and incident affordability

**Delivery route:** delegated direct, bounded pure calculator. This slice is local evidence for endpoint-token and shared incident-token ceilings only; monthly affordability is a separate successor.

## Behavior

`calculate_affordability` selects a fresh, unique provider endpoint from the controlled catalog snapshot. Its conservative input bound is the endpoint's `max_prompt_tokens`; output is limited by both the endpoint's effective completion ceiling and the active incident balance remaining after that input bound. Exact equality is allowed. An unset incident dimension (`None`) does not impose an incident cap; zero or input-only remaining capacity denies positive output. Invalid/missing/stale/ambiguous capacity fails closed with `consumption_bounds_unavailable`.

This module does not admit runtime requests, reserve tokens, settle usage, enforce a monthly budget, call inference, or prove whole-issue acceptance. Endpoint metadata can be synthetic; no live provider is needed.

## Repeat locally

From a clean checkout, copy `.env.example` to ignored `.env`, then run `scripts/bootstrap-worktree.py`. Use a fresh Docker project and an available isolated network. The writer verified and used `10.253.139.0/28` after checking Docker IPAM and routes; choose a different free `/28` if that subnet is occupied.

```sh
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_consumption_affordability.py'
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm python-checks python scripts/consumption_affordability_demo.py
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm harness npm --prefix schemas/tooling run conformance -- --consumer issue-10
```

The focused contract suite exercises exact endpoint/incident boundaries, unset and zero, invalid balances, stale/ambiguous/mismatched endpoints, and malformed bounds. The demo prints deterministic JSON from an offline synthetic snapshot. No credentials, host ports, paid requests or live provider access are needed. The exact tested commit, full-runner output, and local environment are recorded in `/tmp/issue334-affordability-evidence-20260930/REPORT.md`.

## Actual output

`issue-334-affordability.png` is a native Chromium 153.0.8010.12 screenshot of the actual JSON emitted by the Docker demo; it is not a generated image or product UI. For endpoint max output 100 and conservative input 10, incident balance 12 permits output 2 at equality; balance 10 and balance 0 deny; unset permits the endpoint ceiling 100. All outputs are controlled local behavior, not live-provider evidence or runtime-admission proof.
