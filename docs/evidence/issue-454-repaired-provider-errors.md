# Issue 454: repaired provider-error evidence

These are fresh controlled HTTP/OpenRouter-adapter/PostgreSQL observations.
They do not certify a live provider call or independent human acceptance.

## Candidate and behavior

Source tree: `af54167b2905510c5f6e8d2263e2852f0fb36619`. The recorded E2E source/tests match this tree;
subsequent tracker, screenshot and evidence-only commits do not alter runtime.
The [check receipt](issue-454/repair/checks.txt) identifies every tested cut separately.

- Valid canonical credit, HTTP200: [canonical](issue-454/repair/canonical.json).
- Valid canonical credit, empty output, HTTP502: [empty output](issue-454/repair/canonical-empty-output.json).
- Malformed canonical identity, governed HTTP502: [invalid model](issue-454/repair/canonical-invalid-model.json).
- Credits verified before output rejection remain available in historical reads.
- Invalid model identities are rejected before credit propagation; no invented credit.
- Other safe scenario observations in `issue-454/repair/` were copied before container removal.
- Earlier `checks.txt`, canonical receipt and screenshots remain predecessor evidence.

## Repeat

Use public `.env.example` for local interpolation; no live credentials required.
Run at the recorded source or a source/test-tree-identical evidence-only descendant.
The stdout file is retained on the host before the disposable container is removed.

```sh
docker compose --env-file .env.example -p issue454repair --profile checks run --build --rm -e RUFF_CACHE_DIR=/tmp/ruff-cache python-checks sh -c 'ruff check . && ruff format --check . && python scripts/assert_test_database_isolated.py && pytest -q tests/test_issue_454_attribution_acceptance.py tests/test_issue_454_attribution_evidence.py tests/test_issue_454_attribution_guards.py && for artifact in /tmp/issue454*.json; do cat "$artifact"; done' > /tmp/issue454-repair-proof.log
docker compose --env-file .env.example -p issue454repair --profile checks stop python-checks-db
docker compose --env-file .env.example -p issue454repair --profile checks rm -f python-checks-db
```

The real rendered [proof screenshot](issue-454/repair/proof.png) shows the receipt and actual
success/error observations. Only synthetic identifiers, projections and status are
included; no prompts, outputs, headers, API keys, provider bodies or environment files.
Independent human review, current hosted CI and app attachment readback remain separate.
