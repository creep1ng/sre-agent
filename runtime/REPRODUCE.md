# Reproduce runtime audit evidence

Use the individual report's exact head SHA; do not reuse one PR's source for another. Host prerequisites: Git, Docker/Compose, the repository checkout, and this audit's published `proof-*.py` files in a local evidence directory. Assign `EVIDENCE_DIR` to that absolute directory as safe shell configuration before the block. No provider secret is required for #396/#411/#410/#413/#412 or UI tests. Each project name below is dedicated to this audit and must be unused by other work.

## Atomic run-start and HTTP boundary

The repository's checked-in Dockerfile and `uv.lock` define a reproducible tool build. It pins Python base digest `sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`; PostgreSQL Compose service pins `sha256:7062a2109c4b51f3c792c7ea01e83ed12ef9a980886e3b3d380a7d2e5f6ce3f5`. The audit itself reused an existing checks image with exact source mounted read-only; these commands rebuild the candidate instead.

At #396 head:

```sh
docker compose --env-file .env.example -p audit-runtime396 --profile checks run --build --rm -v "$EVIDENCE_DIR:/evidence:ro" python-checks python /evidence/proof-396.py
```

At #411 head:

```sh
docker compose --env-file .env.example -p audit-runtime411 --profile checks run --build --rm -v "$EVIDENCE_DIR:/evidence:ro" python-checks python /evidence/proof-411.py
```

Both drivers reset only the dedicated checks database and load the candidate's synthetic initial-data helper. #396 then calls the real runtime directly and runs SQL, expecting one run/event/snapshot on success, zero for rollback, same-run retry, and reconstruction through a fresh database/runtime object. #411 intentionally demonstrates the reported boundary defects, not a passing suite.

For the provisioning failures, at the respective candidate:

```sh
docker compose --env-file .env.example -p audit-runtime410 --profile checks run --build --rm python-checks pytest -q -p no:cacheprovider tests/test_incident_workflow_provisioning.py::test_run_start_is_granted_and_revoked_apart_from_run_read
docker compose --env-file .env.example -p audit-runtime413 --profile checks run --build --rm python-checks pytest -q -p no:cacheprovider tests/test_incident_workflow_provisioning.py::test_the_harness_can_never_approve_what_it_proposed
```

Each is expected to fail with `resource_missing` on this candidate, showing test-order dependence. Running the whole module first is not an independent-case reproduction.

Cleanup: stop only the named dedicated Compose project's `python-checks-db` using `docker compose --env-file .env.example -p <that-project> --profile checks stop python-checks-db`. Never use `down -v` or shared data. Its data is tmpfs, and test runs recreate their own schemas.

## Browser UI

The audit used `issue331-e2e-evidence:local`, built from `docker/e2e.Dockerfile`: pinned Playwright 1.63.0 image digest `sha256:eff16c30e6f3f4af0a03fa4b706120d5e9b0891c344a27d64559aff5900a4a27`, plus the checked-in npm lock. Use `docker build -t audit-runtime-browser -f docker/e2e.Dockerfile .` as a Docker-only preparation if the cached name is unavailable. Each candidate is served read-only, with synthetic HTTP fixtures explicitly intercepted by Playwright. This verifies the actual browser code, not an integrated backend.

Use the published browser configs and `extra-ui.spec.js`, which are audit evidence, not repository tests. At each exact candidate, select its applicable checked-in file (`war-room.spec.js`, `review.spec.js`, or `postmortem.spec.js`):

```sh
docker run --rm --network none --ipc=host --user 0 -e NODE_PATH=/e2e/node_modules -v "$PWD:/repo:ro" -v "$EVIDENCE_DIR:/out" -w /repo audit-runtime-browser /e2e/node_modules/.bin/playwright test --config=/out/browser-audit.config.cjs /repo/tests/browser/war-room.spec.js
```

At #416 head, reproduce the extra failure with:

```sh
docker run --rm --network none --ipc=host --user 0 -e NODE_PATH=/e2e/node_modules -v "$PWD:/repo:ro" -v "$EVIDENCE_DIR:/out" -w /repo audit-runtime-browser /e2e/node_modules/.bin/playwright test --config=/out/extra-audit.config.cjs --grep 'review conflict'
```

At #418 head use the same command with `--grep 'postmortem stale'`. The two extra tests deliberately fail on #416 (reason lost when reopening after conflict) and #418 (out-of-order run response replaces current provenance). Screenshots show the actual browser behavior. No application source files are modified.

## Live gateway #390

Use an isolated fresh Compose project, with untracked local configuration containing gateway keys, audit HMAC, a valid provider key, and model/provider assignments. The audit used `z-ai/glm-5.3-flash` with `novita`, only as process-local configuration; it did not change a shared environment file. Never print or publish that file. The supplied `proof-390.py` calls the actual harness GatewayClient, not a replacement client. It makes at most three live provider calls with a short synthetic prompt, and exercises a restricted key plus an ephemeral key that it revokes. Its output excludes keys and model text. Run it in a separate harness-side container that receives only the gateway keys required for the scenarios, never OPENROUTER_API_KEY; the script asserts that variable is absent. Mount exact candidate code read-only and give `INVESTIGATOR_AUDIT_URL` the isolated API service URL. `pr-390-live-behavior.log` and `pr-390-audit-sql.log` are the sanitized observations.

Live provider availability/cost is external and may change. A skipped optional smoke is not positive live evidence. This audit is automated and does not represent independent human approval.


For a teammate's new #390 reproduction, prepare `LOCAL_CONFIG` as the path to an untracked disposable local configuration based on `.env.example`, with valid credentials and routing described above; never attach it. The published override removes host database/API ports and passes only gateway credentials to the smoke client. The unused project name below must not identify another stack.

```sh
docker compose --env-file "$LOCAL_CONFIG" -f compose.yaml -f "$EVIDENCE_DIR/live-audit.override.yaml" -p audit-runtime390 --profile live-smoke run --build --rm -v "$EVIDENCE_DIR:/evidence:ro" live-smoke python /evidence/proof-390.py
```

This rebuild-based teammate path is supplied for reproducibility, not claimed as the exact audit command: the audit used its cached image with a read-only source bind and independently created isolated database. The provider-call budget is three. Stop only the dedicated project afterward; no global volume teardown.

## Local pinned demo #370: setup and browser diagnostic

**This is a new, statically reviewed teammate recipe, not an additional executed result.** The recorded audit used an isolated cloud guest and a local tunnel; those resources are terminated. This recipe needs neither AWS access nor the private launcher. It exercises the same exact candidate and pinned demo on a fresh local Linux host. It does **not** promise reproduction of the environment-dependent Grafana 503.

### Prerequisites and boundary

- Use Git to prepare a **standalone clean checkout** at `aa29c08971f7a69575b2d544af1dd4195395ad20` and make it the working directory. Do not use a shared worktree or shared Docker daemon. The container mounts this checkout at the identical absolute host path because its Docker client creates host-side bind mounts. Only ignored `otel-demo/` and `.demo-state/` receive generated demo state; tracked candidate inputs are not edited.
- Read this candidate's [demo operations](https://github.com/creep1ng/sre-agent/blob/aa29c08971f7a69575b2d544af1dd4195395ad20/docs/demo-env.md), [manifest](https://github.com/creep1ng/sre-agent/blob/aa29c08971f7a69575b2d544af1dd4195395ad20/demo/manifest.yaml), and [image lock](https://github.com/creep1ng/sre-agent/blob/aa29c08971f7a69575b2d544af1dd4195395ad20/demo/digests.lock). Upstream is OpenTelemetry Demo `3.0.0`, commit `1755859a9de82c2e5e225be68abc401a5ebf2b4f`; do not substitute a current demo release.
- Dedicated host: Docker Engine and Compose **2.24.4+** (`!override` support), at least 4 CPUs, 4 GB free RAM and 15 GB free disk, loopback ports 8090/9090 free. Budget up to 30 minutes for first image pulls/startup; no provider calls. The operator refuses any existing containers other than its labelled runner, all existing volumes, and non-default networks. Fixed upstream container/network names make a fresh daemon important even with the unique `audit-runtime370-demo` Compose project.
- Set `EVIDENCE_DIR` to this published `runtime` directory and `DEMO_OUTPUT` to a new absolute output directory using safe local shell configuration. No real gateway/provider credentials are needed. The generated MCP token stays in ignored `.demo-state/grafana-mcp.env` with mode 0600; never publish it or expanded Compose configuration.
- Mounting the Docker socket grants daemon control: use **only the dedicated disposable local host**. Do not point these commands at a remote/shared daemon. The operator selects only its named project and requires its local ownership marker for cleanup.

### Build tools and start the pinned environment

All Python/Node/Git dependency work below happens inside containers. The operator inherits the candidate's pinned Python base and locked dependencies. Docker CLI/Compose tooling is version-tagged `docker:27.5.1-cli`, **not claimed as an immutable audit-image digest**; the browser image uses the checked-in pinned Playwright base/npm lock. The adapter pulls every demo image by the candidate lock's digest, tags that exact content locally, then invokes the unchanged candidate operation with only the project name adjusted in memory.

```sh
docker build --target checks -t audit-runtime370-checks -f docker/api.Dockerfile .
docker build --build-arg CHECKS_IMAGE=audit-runtime370-checks -t audit-runtime370-ops -f "$EVIDENCE_DIR/demo-ops.Dockerfile" "$EVIDENCE_DIR"
docker build -t audit-runtime370-browser -f docker/e2e.Dockerfile .
docker run --rm --user 0 --label audit.runtime370.runner=true -e AUDIT_DEDICATED_DAEMON=yes -v /var/run/docker.sock:/var/run/docker.sock -v "$PWD:$PWD" -v "$EVIDENCE_DIR:/evidence:ro" -w "$PWD" audit-runtime370-ops timeout 1800s python /evidence/demo-audit.py up
docker run --rm --user 0 --label audit.runtime370.runner=true -e AUDIT_DEDICATED_DAEMON=yes -v /var/run/docker.sock:/var/run/docker.sock -v "$PWD:$PWD" -v "$EVIDENCE_DIR:/evidence:ro" -w "$PWD" audit-runtime370-ops timeout 180s python /evidence/demo-audit.py verify
```

Expected: all services available, exact image digests accepted, MCP token required; only `127.0.0.1:8090` and `127.0.0.1:9090` published. Envoy 10000 may appear as an exposed container port but must have no host mapping. Digest mismatch or any other verification failure is a failed result: do not update the lock or relax the port policy to make it pass. Interrupted startup may leave this attempt's resources; use the scoped cleanup below.

### Capture the real browser and Grafana assets

Linux host networking lets Chromium reach the **host loopback** bindings without republishing ports. The probe loads storefront, Grafana and Jaeger; captures actual screenshots; logs failed HTTP/JS requests using paths only; then requests at most three Grafana JS assets sequentially for comparison. It submits no credentials and does not inject API mocks. Expected: all three applications visibly load without the Grafana boot-error screen. Inspect the screenshots; this small diagnostic is not a complete application acceptance suite.

```sh
docker run --rm --network host --ipc=host --user 0 -v "$EVIDENCE_DIR:/evidence:ro" -v "$DEMO_OUTPUT:/out" audit-runtime370-browser sh -c 'timeout 180s node /evidence/demo-browser.cjs > /out/reproduction-370-browser.log 2>&1; result=$?; cat /out/reproduction-370-browser.log; exit "$result"'
```

New output is `reproduction-370-browser.log` and `reproduction-370/{store,grafana,jaeger}.png` in `DEMO_OUTPUT`; archived audit screenshots are not overwritten. The original audit observed storefront/Jaeger loading, Grafana HTML 200 with concurrent JS 503, and sequential guest asset 200. The cause remains **UNATTRIBUTED**; a successful local rerun is new evidence, not proof that the original failure was fabricated or candidate-caused. Preserve actual outcomes even when they differ.

### Cleanup only this attempt

Run this even after failed verification or a failed browser diagnostic. The ownership marker prevents an unowned teardown; the candidate's `down` removes only `audit-runtime370-demo` containers/networks, **without removing volumes**. No global `down -v`, volume deletion or prune is used. Retained volumes/state belong only to this disposable host; retire that host through its owner's normal process rather than deleting arbitrary resources.

```sh
docker run --rm --user 0 --label audit.runtime370.runner=true -e AUDIT_DEDICATED_DAEMON=yes -v /var/run/docker.sock:/var/run/docker.sock -v "$PWD:$PWD" -v "$EVIDENCE_DIR:/evidence:ro" -w "$PWD" audit-runtime370-ops timeout 180s python /evidence/demo-audit.py down
```
