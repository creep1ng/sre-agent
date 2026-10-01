# Issue #334 admission evidence

S8 wires atomic admission into `POST /v1/responses`: policy load, affordability
cap, advisory-lock reservation, 429/503 denial before provider contact, effective
`max_output_tokens` propagation, and exact settlement with uncertain retention.

Base: S8a service `af335eb`. Size: S8b wiring + HTTP proofs + this guide.

Reproduce with a fresh checkout (host provides Git, Docker, synthetic `.env`
from `.env.example`; no live provider keys):

```sh
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree \
  -f compose.yaml -f /tmp/issue334-admission-evidence-20260930/compose-network.override.yaml \
  --profile checks run --build --rm python-checks
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree \
  -f compose.yaml -f /tmp/issue334-admission-evidence-20260930/compose-network.override.yaml \
  --profile checks run --rm python-checks sh -c \
  'python scripts/assert_test_database_isolated.py && pytest -q tests/test_consumption_admission_http.py'
```

Expected: deny returns 429 with `monthly_limit_exceeded` and zero provider
requests; allow returns 200 with a positive bounded cap and a settled
reservation. Denial audits carry scope/policy metadata only.
