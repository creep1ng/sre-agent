# Issue 30 — current integrated acceptance verification

**Outcome: not accepted.** The unchanged ten-scenario runner passes, but complete-event
validation fails five of nine persisted events, and the 401 has no terminal event.
This is fresh controlled integration evidence, not reuse of the 2026-10-03 results.

## Candidate, environment and provenance

- Tested/base runtime SHA: `763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9`.
- Branch: `codex/issue-30-ca4-documentation`; no runtime/schema/test changes or commit.
- Build context: frozen Git archive at that SHA, with only the existing documentary
  file added unchanged (SHA256 `e52b150006c2228c72ea7ff934ceaa64195d082512787a9a18d615fee926939b`).
- Project: `issue30-verify-763ccfc-08d022`; new PostgreSQL volume and synthetic keys,
  audit key, MCP token and database password. Empty provider keys; no paid calls.
- Two internal project networks: `10.253.147.0/28`, `10.253.147.16/28`; no host ports.
- Docker 29.9.0, Compose 5.6.0, Python 3.12.14, FastAPI 0.115.12, httpx 0.28.1.
- Running API image equals built image:
  `sha256:8027d8110b091553221f444dc06d43fec21d0e9220732e8b00c411969aaa0217`.
- Executed checks image:
  `sha256:1f78df99aaf6edb8e2442cc639952c77adb2a17d36680c3d577dcf0c96ec5cbb`.
- Grafana MCP 1.3.0, Grafana 13.1.0, Prometheus 3.13.1 and PostgreSQL 17.4 use
  repository-pinned digests. [Receipts](verification-receipts.jsonl) record every
  actual container/image, running-source hashes, OpenAPI revision/contract 2.7.0,
  readiness, SQL selection and checks. [Effective configuration](compose-config.sanitized.json)
  retains public configuration while replacing credentials; it is not a secret env file.

HTTP readiness/control probes were all 200 and MCP TCP was ready at
`2026-10-13T03:38:16.819628Z`, before the replay. `/version` returned 404 (not a
published endpoint); `/openapi.json` verified the actual revision instead.
The original documentary diff is preserved byte-for-byte in the checkout and in
the ignored run preservation directory. Historical JSONL/PNG hashes are recorded
in the receipt and rechecked unchanged. Nothing is relabeled as current evidence.

## Fresh matrix

Replay window: `2026-10-13T03:38:42.525131Z`–`2026-10-13T03:39:14.714085Z`
(2026-10-12, America/Bogota). Each case resets its own relay/proxy counters.

| Criterion | Observed result / evidence | Verification status |
| --- | --- | --- |
| CA1 | [Replay line 11](replay.jsonl#L11): 200, normalized vector(1), one `tools/call` attempt and one real forward; correlated schema-valid success event. | Passed in this run; human acceptance pending. |
| CA2 | [Lines 4–6](replay.jsonl#L4-L6): nonvisible/no grant/invalid credential = 403/403/401, safe errors, zero attempts/forwards. | Public access/counter checks passed; audit defects belong to CA4. |
| CA3 | [Lines 7–10](replay.jsonl#L7-L10): invalid input/timeout/unavailable/malformed = 422/504/503/502. Attempts 0/1/1/1; real forwards all zero. Closed safe errors; upstream faults are controlled injection, not actual external outages. | Public error checks passed; 503/504 audit retryability fails CA4. |
| CA4 | [Full SQL rows](sql-storage-full.jsonl), [full envelopes](audit-events-full.jsonl), [Python](audit-schema-results.jsonl) and [repository Ajv](audit-ajv-schema-results.jsonl): nine correlated events, four valid/five invalid; 401 absent across operations. | **Failed.** Approved 422 interpretation remains satisfied and unchanged. |
| CA5 | [Lines 2–3](replay.jsonl#L2-L3): allowed/denied known ID before discovery, 200/403; attempt/forward 1/1 and 0/0. | Authorization behavior passed; denied-event schema defect belongs to CA4. |

Cold `initialize` and `notifications/initialized` each occur once in the first
known-ID case, separately from `tools/call`; no discovery or `tools/list` is used.
Only the two successful controls forward real tool calls through MCP → Grafana →
Prometheus. Fault cases count one relay attempt but zero real tool forwards.

## Complete SQL and schema validation

The query uses `to_jsonb(a)` (all 26 storage columns), the actual public request
IDs and a half-open UTC window, with **no operation filter**. Raw SQL NULLs remain
in the separate storage artifact. For the JSON contract envelope, optional SQL-NULL
fields are omitted; required root fields (including `reason_code=null`) and every
non-null field/value remain. This only changes storage absence representation;
it never invents a denial cause, repairs retryability, drops non-null content or
selects a few favorable columns. Both validators use unmodified schema 2.7.0 and
format checking. Results: 200/200/422/502 pass; 403/403/403/504/503 fail. All nine
events have non-negative integer latency and metadata-only content/HMAC references.

- Three denied events lack `authorization_denial_cause`; the [schema requires][denial-schema] a
  non-null closed cause for authorization-stage 403/404 denial.
- The timeout/unavailable events persist `retryable=false`; [upstream 504/503][upstream-schema]
  require `true`. The original reduced-column helper cannot detect either defect.
- Local existing checks passed: **1823 passed, 1 skipped, 2 warnings**, exit 0;
  isolation, shellcheck, Ruff/format, lock, import/typing and Alembic chain passed.
  One paid live-provider check was skipped. Fixture conformance also passed;
  neither result proves that the actual producer emits contract-valid events.

## 401 reproduction, contradictory requirement and minimal proposals

The original 401 request ID is `c53f05eb-4f96-4f3d-be01-61895fa1085d` at
`2026-10-13T03:38:44.040552Z`–`03:38:44.042813Z`. SQL finds zero rows across all
operations, zero matches outside the window for that ID, and no authentication-stage,
`credentials.authenticate` or authentication-failed 401 event anywhere in the
replay window. A **separate repeat** also returned real 401 with zero tool calls
and zero all-operation rows (receipt `401-reproduction`, request ID
`24a9a2a7-ced3-4329-829b-b1eb6424fb31`). Its actual public body is in the receipt;
the credential/header is never saved. Its presence check exits 1, not green.

[OpenSpec terminal-attempt requirement][terminal-spec] explicitly includes governed
authentication outcomes. [ADR-005][audit-adr] requires stage-aware evidence without
fabricating pre-authentication authority. The [authentication-stage schema][authentication-schema]
permits absent unknown identity and forbids resource/decision there; that does not
permit omitting the terminal event itself. The generic OpenSpec attribution list
is constrained by these stage rules, not a reason to invent a Principal or resource.
[Current invocation][invoke-source] returns 401 before `_audited`; the authentication
dependency and global handler do not provide an alternative audit path.

Proposed **separate runtime correction**, requiring user approval; not implemented:

1. Route the MCP invalid-credential 401 through durable `_audited` with the same
   request ID, measured latency, authentication stage, operation/action, safe reason
   and retryability. Omit unknown identity and all resource/policy/routing evidence.
   Preserve the safe public body/WWW-Authenticate; if the store rejects the event,
   return `503 audit_unavailable` rather than release an unaudited 401. Apply the
   same boundary to MCP discovery only within an explicitly approved correction scope.
2. Forward the engine's existing `evaluation.denial_cause` through the MCP projector;
   do not guess a cause. [The engine already carries it][engine-source], while
   [the current producer][producer-source] drops it. Preserve the non-enumerable
   public 403 and keep this audit-only field out of the public error.
3. Forward the existing contracted normalized-error retryability into the projector
   for 503/504; its default `false` currently survives because the producer does
   not pass it. No schema relaxation, blanket 422 exception or evidence repair.

An existing discovery test explicitly expects no 401 audit, and the old capture
helper expects zero `mcp.invoke` rows. They were **not changed**. Passing those checks
is not acceptance of the contradictory absence. An approved correction must first
exercise the genuine full-event/presence failures, then rebuild and repeat integrated
verification; never weaken expectations or rewrite these failed artifacts.

## Reproduction and remaining scope

Use the recorded frozen checkout, or a fresh Git checkout of the full tested SHA.
Prepare a unique local `PROJECT`, private `ENV_FILE` from `.env.example`, private
`DEMO_STATE_DIR/grafana-mcp.env`, writable absolute `CAPTURE_DIR`, and this directory
as `VERIFY_DIR`. Use fresh synthetic credentials/password/audit key, models
`synthetic/control`, providers `synthetic`, empty provider keys, contract 2.7.0 and
`SRE_AGENT_BUILD_REVISION=$TESTED_SHA`. `NETWORK_FILE` is [networks.yaml](networks.yaml):
for a new project choose currently unused subnets, not another project's networks.
Run from the candidate checkout. `API_CONTAINER` comes from the scoped Compose
`ps -q api`; require ready health, actual OpenAPI SHA and built/running image equality
before replay. The executed private setup/outputs remain under
`/home/creep/.codex/worktrees/2458/sre-agent/.demo-state/issue30-verify-763ccfc-08d022`.

```sh
docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f compose.yaml -f compose.mcp.yaml -f compose.issue29-counter.yaml -f compose.issue30.yaml -f "$NETWORK_FILE" config --quiet
docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f compose.yaml -f compose.mcp.yaml -f compose.issue29-counter.yaml -f compose.issue30.yaml -f "$NETWORK_FILE" build api python-checks
docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f compose.yaml -f compose.mcp.yaml -f compose.issue29-counter.yaml -f compose.issue30.yaml -f "$NETWORK_FILE" up --build --force-recreate -d --wait --wait-timeout 150 mcp-seed api grafana-mcp issue30-fault-proxy mcp-upstream
docker run --rm --user "$(id -u):$(id -g)" --network "container:$API_CONTAINER" --env-file "$ENV_FILE" -e TESTED_SHA="$TESTED_SHA" -v "$PWD/scripts:/app/scripts:ro" -v "$CAPTURE_DIR:/capture" "$PROJECT-python-checks:latest" python /app/scripts/issue30_capture.py
docker run --rm --user "$(id -u):$(id -g)" --network "container:$API_CONTAINER" --env-file "$ENV_FILE" -v "$VERIFY_DIR/issue30_sql_full.py:/verification/issue30_sql_full.py:ro" -v "$PWD:/candidate:ro" -v "$CAPTURE_DIR:/capture" "$PROJECT-python-checks:latest" python /verification/issue30_sql_full.py
docker run --rm --network none --read-only --tmpfs /tmp --tmpfs /workspace:rw,uid=1000,gid=1000 -v "$PWD:/source:ro" -v "$VERIFY_DIR/validate_audit.mjs:/verification/validate_audit.mjs:ro" -v "$CAPTURE_DIR:/capture" sha256:52dcd551ecc52f60e405282c8fbed037b255e1144f351e77d04c118bc2bfb6bb node /verification/validate_audit.mjs
docker run --rm --user "$(id -u):$(id -g)" --network "container:$API_CONTAINER" --env-file "$ENV_FILE" -e TESTED_SHA="$TESTED_SHA" -v "$VERIFY_DIR/reproduce_401.py:/verification/reproduce_401.py:ro" -v "$CAPTURE_DIR:/capture" "$PROJECT-python-checks:latest" python /verification/reproduce_401.py
docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f compose.yaml -f compose.mcp.yaml -f compose.issue29-counter.yaml -f compose.issue30.yaml -f "$NETWORK_FILE" --profile checks run --rm python-checks
docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f compose.yaml -f compose.mcp.yaml -f compose.issue29-counter.yaml -f compose.issue30.yaml -f "$NETWORK_FILE" --profile checks stop
```

Expected/observed: legacy replay exits 0; both complete-event validators and the
401 terminal-event presence check exit 1; existing checks exit 0. Run the commands
independently after expected failures so later checks/cleanup are not skipped.
The cached harness image is a tooling prerequisite (current schemas are mounted,
not image-baked); rebuild `docker/harness.Dockerfile` if it is unavailable and
record its new image identity. Initial Ajv setup used a nonexistent export and
did not validate events; corrected to the repository's `createSchemaRegistry`,
then confirmed the same five failures as Python. No failed run is presented as a pass.

Not executed: hosted CI, human acceptance, new browser screenshot/video, paid
provider calls, integrated audit-store outage/release suppression. Existing mocks
are supplemental checks, not substitutes for the real stack/SQL evidence above.
Only this new project was stopped; its synthetic volume, snapshots and private
configuration remain. No prune, `down -v`, remote publication, merge or issue closure.
Fresh correction and human acceptance remain required; #30 remains OPEN/Todo.
The relay and fault proxy exited 137 during scoped stop (OOM-killed=false);
they had completed the scenario probes before shutdown, not crashed during replay.

Review packaging: preserve the existing documentation/recovery change as one unit
and this new evidence directory as another. Each unit stays at most 400 added plus
deleted lines; do not combine them into one acceptance PR without an approved exception.

[terminal-spec]: https://github.com/creep1ng/sre-agent/blob/763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9/openspec/specs/runtime-audit-evidence/spec.md#L9-L11
[audit-adr]: https://github.com/creep1ng/sre-agent/blob/763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9/schemas/adrs/ADR-005-audit-redaction.md
[authentication-schema]: https://github.com/creep1ng/sre-agent/blob/763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9/schemas/releases/2.7.0/json-schema/domain/audit-event.schema.json#L873-L890
[invoke-source]: https://github.com/creep1ng/sre-agent/blob/763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9/src/sre_agent/gateway/mcp.py#L446-L462
[engine-source]: https://github.com/creep1ng/sre-agent/blob/763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9/src/sre_agent/governance/authorization.py#L44-L55
[producer-source]: https://github.com/creep1ng/sre-agent/blob/763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9/src/sre_agent/gateway/mcp.py#L754-L764
[denial-schema]: https://github.com/creep1ng/sre-agent/blob/763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9/schemas/releases/2.7.0/json-schema/domain/audit-event.schema.json#L1424-L1460
[upstream-schema]: https://github.com/creep1ng/sre-agent/blob/763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9/schemas/releases/2.7.0/json-schema/domain/audit-event.schema.json#L590-L647
