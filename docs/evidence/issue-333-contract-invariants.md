# Issue #333: consistent cost and coverage boundaries

U333-7 repairs the mutable proposal, runtime validators/generated OpenAPI and semantic fixture conformance. U333-8 publication/activation and U333-10 hosted/human acceptance remain pending; immutable 2.4.0 is untouched. Route: delegated direct. Review the shared 26-case matrix, then the three validators and schema conditions.

## Candidate and scope

Base/HEAD: `c57732f4407e9a0d4e9ee89fde7286e79b4f1876` (PR #421), plus this uncommitted slice. Bind the tested commit before publication. Chain: `main ← #421 ← 📍 invariant preparation ← additive publication`; stacked-to-main, temporarily targeting the parent branch. This slice does not use the publication-only size exception.
SHA-256 identities of tested inputs:

| File | SHA-256 |
| --- | --- |
| `src/sre_agent/gateway/usage.py` | `d5299a5290fbff74e05cce6d6dc6804070d876c668b0c504570f8a6cfbcb980d` |
| `schemas/proposals/issue-333/usage-read.openapi.yaml` | `da93d4fdfebef3a45b6dce3a65b6b3d53089e5cb524144ec764a43206bc487f1` |
| `schemas/tooling/lib/schema-validation.mjs` | `22e74def3d00c81bce084eee33160a32282c9d0465f0e199d03ce9d960a24ae2` |
| `tests/test_usage_read_contract.py` | `c157e5e731b02305f961cf8557f4b31272013a7cf78c6601a8d4ef424ec23f86` |
| `schemas/tooling/test/usage-read-invariants.test.mjs` | `2d8945df9fe4f6fb74c9405468bcd959f735cf20e995c5c97053fb9990e20307` |
| `schemas/tooling/test/fixtures/usage-read-invariants.yaml` | `403574c6ecf1bc8a9d9de449b148dcbc7c269199eb9305671cb93b14f7188de2` |

## Observed proof

All scenarios preceded production edits. Runtime RED: **16 failed / 10 passed**. Initial schema RED exposed composed-filter closure; fixing only closure yielded **16 failed / 11 passed**, including arithmetic under/overcounts. Schema GREEN initially exposed strict-AJV missing integer types; explicit types fixed it. The first runtime GREEN attempt yielded **3 failed / 71 passed**: actual HTTP OpenAPI stripped `const: null` into `{}`. Replacing it with `type: null` fixed the three null-metadata cases without weakening tests.
After final Ruff normalization, **74 Python tests passed (17.67s)**, including all 48 previous usage/audit scenarios and the 26 new boundaries; lint passed and both files were already formatted. Full tooling: **123 passed, none failed/skipped (435.7s)**. Focused schema/conformance: **27 passed**. Refactor review retained the narrow solution. Immutable 2.4.0 hash comparison: **194 files unchanged**. Explicit validation of all ten immutable releases (1.0.0–2.4.0) passed.
The [actual conformance output](issue-333-invariants-output.txt) and [real Chromium screenshot](issue-333-invariants-output.png) show the executed positive/negative boundary cases, not an invented response or old capture. Expected/observed: ten valid payloads accepted, sixteen contradictions rejected; count-sum mismatches remain structurally valid JSON Schema but are rejected by runtime and semantic conformance. Empty complete scopes, incomplete-only partial scopes and complete coverage with incompatible-price null cost remain valid.
Primary evidence: **rendered artifact**, depicting actual controlled schema/conformance checks. Runtime evidence includes an actual `/openapi.json` HTTP response and PostgreSQL-backed usage regressions; no external provider was used. Sanitized: yes. Output and screenshot were inspected; no credentials, headers, personal data, prompts or provider outputs. Deferred: media storage unavailable; screenshot evidence is mandatory.

## Reproduction

Use the existing ignored local-only `.env`/`.env.worktree` prerequisites from [the preceding report](issue-333-residual-review.md). Execute sequentially in an isolated Compose project; only `python-checks-db` is destructive. Tested project: `candidate-wt-9bb3531fa9f1` with its owned `10.253.33.0/24` bridge. Python 3.12.14, Ruff 0.11.7, Node 22.14.0, PostgreSQL 17.4, Chromium 153; image digests and dependency locks remain repository-pinned. Runtime checks image: `sha256:a54c3ee278efe39f72d026a00ff9550cfb14f45570495c9540ab9bb298e38193`.

```sh
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_usage_read_acceptance.py tests/test_audit_events_contract.py tests/test_usage_read_contract.py && ruff check --no-cache src/sre_agent/gateway/usage.py tests/test_usage_read_contract.py && ruff format --check --no-cache src/sre_agent/gateway/usage.py tests/test_usage_read_contract.py'
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --build --rm harness npm --prefix schemas/tooling test
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --rm harness npm --prefix schemas/tooling run validate:releases
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree -f compose.yaml --profile checks run --rm harness node --test --test-reporter=spec schemas/tooling/test/usage-read-invariants.test.mjs
```

The final command emits the capture directly; redirect stdout to a local `.txt` and open that output in a browser to repeat its native rendered view. Raw build/test logs remain private; the committed capture contains only scenario names, observed successes and durations.

## Review dispositions and remaining work

| Historical thread | Reviewed SHA | CA / current disposition |
| --- | --- | --- |
| [383/4111980005](https://github.com/creep1ng/sre-agent/pull/383#discussion_r4111980005) | `4f090b9e93cb0ea9a24908ace6091806c5c5674c` | CA4: reproduced, fixed and locally verified; string amount requires USD/exact, null amount requires null metadata. |
| [383/4111980011](https://github.com/creep1ng/sre-agent/pull/383#discussion_r4111980011) | `4f090b9e93cb0ea9a24908ace6091806c5c5674c` | CA3: reproduced, fixed and locally verified; status reflects distinct-request coverage and semantic counts sum to request_count. |

The earlier eight-thread ledger remains historical evidence; neither thread was remotely resolved. Parent owns independent verification, current commit binding, publication and human review. U333-8 must coordinate the next version, publish a self-contained additive snapshot/usage.read audit operation, then activate it; do not rewrite 2.4.0. No current remote version availability was established in this slice. Rollback only these invariant validators, draft/semantic changes, shared boundary cases and evidence; preserve PR #421's attribution repair. Engram mirror is pending because runtime session identity is unavailable; no memory writes were attempted after the parent suspended them.
