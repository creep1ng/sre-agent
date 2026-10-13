# Issue 454: feature-branch split and current integration evidence

Main is unchanged. Start at feature `codex/feature-454`; subsequent PRs are
stacked on the previous cut. Review/merge from the bottom upward only after
applicable checks and human review. Partial prefixes are not deployments.

Only the contract-specific PR has maintainer authorization for
`size:exception-update-contract`. Every other cut is at most 400 additions
plus deletions against its declared base; binary artifacts are disclosed too.
The [cut manifest](cuts.csv) accounts for every original source file. Complete
src/tests/schemas/migrations/scripts trees match verified source
`0bfadf958f941ec61889daef4e207c2284801aa4`; no file hiding or minification.
A future feature-to-main PR is NOT exempt from the size policy and is not authorized.

[Current receipt](current-checks.txt), [actual HTTP/SQL](current-http-sql.json),
[canonical success](current-canonical.json), [empty-output error](current-canonical-empty-output.json),
[invalid-model error](current-canonical-invalid-model.json), and
[actual screenshot](current-integration.png) are controlled observations, not live-provider proof.
The 82-test run passed; its following demo returned401 after unrelated fixture
credentials. Repeating the 13 attribution scenarios immediately before the demo
passed and emitted this real HTTP/SQL proof. No source change or test was added.
Older issue-454 images/receipts remain original historical evidence, not fresh CI.
Full Python verification and hosted CI are separate; consult the current PR receipt.

## Repeat the complete candidate

Host requirements: Git and Docker. Check out verified source
`0bfadf958f941ec61889daef4e207c2284801aa4` before behavior checks.
No env file, real credentials, exposed port, or paid call is needed. Build uses
locked uv dependencies and docker/api.Dockerfile; the recorded run used cached
checks image sha256:714b91b0c89be30fb88ae8ccf68c364988cc482c1cd06fd96960bc564abf5b27
with actual candidate source mounted read-only. The DB is disposable tmpfs with
no external network. The checks container shares only its owned DB namespace.

```sh
docker build --target checks --tag issue454-feature-checks -f docker/api.Dockerfile .
docker run -d --rm --name issue454-feature-proof-db --network none --tmpfs /var/lib/postgresql/data:rw -e POSTGRES_DB=python_checks -e POSTGRES_USER=python_checks -e POSTGRES_HOST_AUTH_METHOD=trust postgres:17.4-alpine@sha256:7062a2109c4b51f3c792c7ea01e83ed12ef9a980886e3b3d380a7d2e5f6ce3f5
docker exec issue454-feature-proof-db pg_isready -U python_checks -d python_checks
docker run --rm --network container:issue454-feature-proof-db --mount type=bind,src="$PWD",dst=/candidate,readonly --workdir /candidate -e PYTHONPATH=/candidate/src:/candidate/tests -e TEST_DATABASE_URL=postgresql://python_checks@127.0.0.1:5432/python_checks -e DEMO_DATABASE_URL=postgresql://demo@never-demo.invalid:5432/demo -e DATABASE_URL=postgresql://python_checks@127.0.0.1:5432/python_checks -e TESTED_SHA=0bfadf958f941ec61889daef4e207c2284801aa4 -e PYTEST_ADDOPTS='-p no:cacheprovider' issue454-feature-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_issue_454_attribution_acceptance.py tests/test_issue_454_attribution_evidence.py tests/test_issue_454_attribution_guards.py && python scripts/issue454_demo.py && for artifact in /tmp/issue454*.json; do cat "$artifact"; done && alembic check' > /tmp/issue454-feature-repeat.log
docker stop issue454-feature-proof-db
```

Wait until pg_isready succeeds before the checks command. Retain stdout before
--rm; do not upload env files, headers, prompts, outputs or raw provider bodies.
Expected: unchanged historical assignment after reassignment; closed 401/403/422;
verified canonical credits on output rejection but none for invalid identities;
no new Alembic operations. Human acceptance and final main integration remain pending.
