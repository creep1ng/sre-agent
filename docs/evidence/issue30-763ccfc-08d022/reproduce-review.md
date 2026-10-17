# Portable reproduction after review

This supplement supersedes **instructions only**, not the original README, records,
SHAs or manifests. Runtime 763ccfc/contract 2.7.0 remains the recorded baseline;
current main/contract 2.8.0 is not credited with that run. New observer checks select
the actual API contract; supplemental fixture checks are not live audit evidence.

## Separate inputs and private configuration

Use host Git to keep two absolute checkouts: `RUNTIME_DIR` at
`763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9`, and `DELIVERY_DIR` at the delivered
observer/evidence candidate. Set `VERIFY_DIR=$DELIVERY_DIR/docs/evidence/issue30-763ccfc-08d022`.
The runtime checkout never needs to contain the new helpers. Work from `RUNTIME_DIR`.
Prepare a new unique `PROJECT`, private absolute `STATE_DIR`, writable new
`CAPTURE_DIR`, and `NETWORK_FILE` copied from this delivery's networks.yaml with
currently unused subnets. Preserve old captures, credentials and volumes.

Set `ENV_FILE` to a private copy of the runtime's .env.example. Fill four distinct
32-plus-character `sre_` API keys, random `POSTGRES_PASSWORD`/`AUDIT_HMAC_KEY`,
matching **fully expanded** `DATABASE_URL` (Docker run does not expand Compose
interpolation), both models `synthetic/control`, both providers `synthetic`, empty
provider keys, `SRE_AGENT_BUILD_REVISION=$RUNTIME_SHA` and contract version 2.7.0.
Set `RUNTIME_SHA` to the full runtime SHA above and `DEMO_STATE_DIR` to an absolute
private directory containing grafana-mcp.env with a fresh `MCP_GRAFANA_SERVER_TOKEN`.
Do not source, print or upload either file. All these values are synthetic/local.
The host prepares Git/Docker/configuration only; Python/npm run in containers.

## Build, readiness, replay and complete observers

```sh
docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f compose.yaml -f compose.mcp.yaml -f compose.issue29-counter.yaml -f compose.issue30.yaml -f "$NETWORK_FILE" config --quiet
docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f compose.yaml --profile checks build python-checks harness
docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f compose.yaml -f compose.mcp.yaml -f compose.issue29-counter.yaml -f compose.issue30.yaml -f "$NETWORK_FILE" up --build -d --wait --wait-timeout 150 mcp-seed api grafana-mcp issue30-fault-proxy mcp-upstream
docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f compose.yaml -f compose.mcp.yaml -f compose.issue29-counter.yaml -f compose.issue30.yaml -f "$NETWORK_FILE" ps -q api
docker run --rm --network "container:$API_CONTAINER" "$PROJECT-python-checks:latest" python -c 'import httpx,socket; c=httpx.Client(timeout=10,trust_env=False); urls=["http://api:8000/health/ready","http://grafana:3000/api/health","http://prometheus:9090/-/ready","http://grafana-mcp:8000/__count","http://issue30-fault-proxy:8000/__stats"]; assert all(c.get(u).status_code==200 for u in urls); socket.create_connection(("mcp-upstream",8000),timeout=5).close(); i=c.get("http://api:8000/openapi.json").json()["info"]; assert i["x-sre-agent-build-revision"]=="763ccfc3965cd21f2a9b8046f71b9112d9b7b2e9" and i["x-sre-agent-contract-version"]=="2.7.0"; print("Runtime readiness/revision/contract verified")'
docker run --rm --user "$(id -u):$(id -g)" --network "container:$API_CONTAINER" --env-file "$ENV_FILE" -e TESTED_SHA="$RUNTIME_SHA" -v "$RUNTIME_DIR/scripts:/app/scripts:ro" -v "$CAPTURE_DIR:/capture" "$PROJECT-python-checks:latest" python /app/scripts/issue30_capture.py
docker run --rm --user "$(id -u):$(id -g)" --network "container:$API_CONTAINER" --env-file "$ENV_FILE" -v "$VERIFY_DIR:/verification:ro" -v "$RUNTIME_DIR:/candidate:ro" -v "$CAPTURE_DIR:/capture" "$PROJECT-python-checks:latest" python /verification/issue30_sql_full.py
docker run --rm --network none --read-only --tmpfs /tmp --tmpfs /workspace:rw,uid=1000,gid=1000 -v "$RUNTIME_DIR:/source:ro" -v "$VERIFY_DIR:/verification:ro" -v "$CAPTURE_DIR:/capture" "$PROJECT-harness:latest" node /verification/validate_audit.mjs
docker run --rm --user "$(id -u):$(id -g)" --network "container:$API_CONTAINER" --env-file "$ENV_FILE" -e TESTED_SHA="$RUNTIME_SHA" -v "$VERIFY_DIR:/verification:ro" -v "$RUNTIME_DIR:/candidate:ro" -v "$CAPTURE_DIR:/capture" "$PROJECT-python-checks:latest" python /verification/reproduce_401.py
docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f compose.yaml -f compose.mcp.yaml -f compose.issue29-counter.yaml -f compose.issue30.yaml -f "$NETWORK_FILE" stop
```

Assign `API_CONTAINER` from the scoped `ps -q api` output before Docker run commands.
Record actual built/running image IDs with host Docker inspection and compare the
API image to `$PROJECT-api-runtime:local`; require equality before results. Tags
above are built locally from the declared checkout/lockfiles, not unpullable cache IDs.
The counter overlay already clears external=false; do not omit it or use global
networks. Mount the **whole** VERIFY_DIR because the observers share audit_contract.py.
Run commands independently: baseline replay exits 0, complete Python/Ajv validation
exits 1 for zero valid/nine invalid events, and the corrected 401 observer exits 1
for the missing terminal event. Those failures are not fixed or weakened here.

A successful mocked authentication fixture certifies observer behavior only. A live
valid authentication event remains unexecuted while the producer emits no event.
After a separately approved runtime correction, rebuild/recheck readiness and repeat
fresh integrated verification. This supplement neither accepts nor closes #30.
