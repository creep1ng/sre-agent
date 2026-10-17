# Issue 30 — reproducible observer process checks

This is the separate small verification unit for #599; no runtime/schema changes.
**Mock-only**, not a live producer event, and not acceptance of #30. Real SQL/HTTP
still fails CA4: all nine literal stored events invalid and authentication absent.

The driver in `../issue30-763ccfc-08d022/check_401_observer.py` uses immutable
published positive fixtures for 2.7.0/2.8.0, mocks only HTTP/DB boundaries, then
executes the real observer and inspects exit/artifact presence. It never creates
an actual Principal or inserts events. Failure modes/cases were authored before
each corresponding observer correction; [phase results](process-results.jsonl)
retain original21 RED17 false positives, nested-null RED, partial/challenge RED,
and malformed29 RED3 lost artifacts (after fixing a setup-only non-JSON adapter).
Current29 GREEN for both releases preserves an artifact for every case.

## Reproduce in containers

Host Git supplies the tested delivery checkout and private `.env.example` copy
with required synthetic values for Compose interpolation; never source/print it.
Set PROJECT uniquely, DELIVERY_DIR to that checkout, VERIFY_DIR to its
`docs/evidence/issue30-763ccfc-08d022`, and SCRATCH_DIR to a new writable directory.
No private host path is embedded. Mock SQL metadata is intentionally not real DB
access; container network is none. Keep scratch separate from every real capture.

```sh
docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f "$DELIVERY_DIR/compose.yaml" --profile checks build python-checks harness
docker run --rm --user "$(id -u):$(id -g)" --network none --read-only --tmpfs /tmp -e TESTED_SHA="$TESTED_SHA" -e DATABASE_URL=postgresql://synthetic@db/synthetic -e CHECK_CONTRACT_VERSION=2.7.0 -v "$DELIVERY_DIR:/candidate:ro" -v "$VERIFY_DIR:/verification:ro" -v "$SCRATCH_DIR:/capture" "$PROJECT-python-checks:latest" python /verification/check_401_observer.py
docker run --rm --user "$(id -u):$(id -g)" --network none --read-only --tmpfs /tmp -e TESTED_SHA="$TESTED_SHA" -e DATABASE_URL=postgresql://synthetic@db/synthetic -e CHECK_CONTRACT_VERSION=2.8.0 -v "$DELIVERY_DIR:/candidate:ro" -v "$VERIFY_DIR:/verification:ro" -v "$SCRATCH_DIR:/capture" "$PROJECT-python-checks:latest" python /verification/check_401_observer.py
```

Expected/actual: process runner exit0 only when all29 expected observer exits match
and all29 artifacts exist. Negative observer cases themselves exit1; positive
fixtures exit0. These are not live authentication certificates. Known malformed
HTTP does not publish its body; missing correlation is unknown, never fake absence.

For the [controlled empty-input probe](empty-input-results.jsonl), prepare a new
scratch `audit-events-full.jsonl` as an empty file, never an actual run's file, then:

```sh
docker run --rm --network none --read-only --tmpfs /tmp --tmpfs /workspace:rw,uid=1000,gid=1000 -e SRE_AGENT_CONTRACT_VERSION=2.8.0 -v "$DELIVERY_DIR:/source:ro" -v "$VERIFY_DIR:/verification:ro" -v "$SCRATCH_DIR:/capture" "$PROJECT-harness:latest" node /verification/validate_audit.mjs
```

Expected/actual: exit1, result JSONL exists empty, stdout rows0/evidence_missing=true.
No events means no schema validation/acceptance, not zero failures implying GREEN.
Real ready Compose ten-case acceptance remains separate and failed. No old data,
expectation, schema, runtime or 422 interpretation is altered by this unit.
