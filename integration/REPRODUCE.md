# Reproduce the prospective integration checks

Use a **disposable clean clone**, never a working delivery branch. This verifies the seven heads in `integration-summary.json`, in its recorded order, starting at `4b0c8740a042a8654979dd43481c7ad4f9992ea1`. Stop if any head or expected tree differs. Synthetic commit IDs need not match because metadata differs; the **tree IDs must match**.

## Safe setup

The host supplies Git, Docker, and local path setup. Clone the public `https://github.com/creep1ng/sre-agent.git` repository, fetch the exact seven head SHAs from the summary (or the corresponding `refs/pull/N/head` refs), and detach at the starting main SHA. Set `SOURCE` to that absolute clone path and `EVIDENCE` to this downloaded evidence directory. Do not place evidence inside the source clone. No private credentials or existing database are required.

Build the repository's pinned locked check-tool image, then reconstruct the candidate inside Docker. `reconstruct.py` creates local synthetic commit objects and checks out their tree; it updates no branch and performs no remote mutation.

```sh
docker build --target checks -f "$SOURCE/docker/api.Dockerfile" -t sre-integration-python:local "$SOURCE"
docker run --rm --network none --user "$(id -u):$(id -g)" \
  -v "$SOURCE:/repo" -v "$EVIDENCE:/evidence:ro" -w /repo \
  sre-integration-python:local python /evidence/reconstruct.py
docker build -f "$SOURCE/docker/e2e.Dockerfile" -t sre-integration-browser:local "$SOURCE"
docker build -f "$SOURCE/docker/harness.Dockerfile" -t sre-integration-contracts:local "$SOURCE"
```

The original audit used an **existing** Python image (`sha256:e9d909738233806dc27166113a1599ed0c6667e5b44fa83688eef38dc84a83a8`) and an **existing** browser image (`sha256:abba619978eef39a9a21080cbcc1b4225d4e6d179f17df388e914f4b2c7e4967`), not fresh application builds. Its Python lock SHA256 exactly matched the final source. Python3.12.14, Ruff0.11.7, mypy2.3.1, uv0.8.14; browser Node24.20.0/Playwright1.63.0. Hosted static-web CI selects Node22.14 instead. The contract image was newly built from the candidate's pinned Dockerfile/lock. The public Dockerfiles above remove any dependency on private cached image tags.

## Python, migration and combined-service checks

Use a unique container name if this one exists. PostgreSQL is a new tmpfs cluster, no ports, no shared volume, no external network. The test container joins only that DB network namespace. `POSTGRES_HOST_AUTH_METHOD=trust` is limited to this disposable isolated namespace; do not copy it to a deployment.

```sh
docker run --pull missing --detach --name sre-integration-proof-db \
  --network none --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_DB=python_checks -e POSTGRES_USER=python_checks \
  -e POSTGRES_HOST_AUTH_METHOD=trust \
  postgres:17.4-alpine@sha256:7062a2109c4b51f3c792c7ea01e83ed12ef9a980886e3b3d380a7d2e5f6ce3f5
docker run --rm --network container:sre-integration-proof-db \
  --user "$(id -u):$(id -g)" -e PYTHONPATH=/repo/src \
  -e TEST_DATABASE_URL=postgresql://python_checks@127.0.0.1:5432/python_checks \
  -e DATABASE_URL=postgresql://python_checks@127.0.0.1:5432/python_checks \
  -e DEMO_DATABASE_URL=postgresql://demo@demo-db:5432/demo -e UV_CACHE_DIR=/tmp/uv \
  -v "$SOURCE:/repo:ro" -v "$EVIDENCE:/out" -w /repo \
  sre-integration-python:local python /out/inside-checks.py final
docker rm --force sre-integration-proof-db
```

Expected: all15 command exits zero; full Python1220passed/1skipped. The skipped live OpenRouter test is intentional: this independent check sends **no provider request** and receives no secrets. For the combined service probe, recreate the empty DB, rerun the same test container replacing `python /out/inside-checks.py final` with `python /out/combined-runtime-probe.py`, then remove only that DB. Expect one run, two events, both retries replayed, a persisted human comment without an approval record, cursor`seq:1`, and equality after reopening the database handle.

Per-boundary test names and exact source trees appear in the summary. Select that boundary's reconstructed tree in your disposable clone, use another **fresh DB**, and replace the command with `python /out/inside-checks.py focused <the listed test files>`. Do not treat the final full suite alone as boundary proof.

## Browsers and contracts

These UI tests render actual source in Chromium, but intercept API responses with synthetic fixtures; they are **not connected API/provider journeys**. Final UI screenshot options capture full pages. No screenshot is generated artwork.

```sh
docker run --rm --network none --ipc=host --user 0 -e NODE_PATH=/e2e/node_modules \
  -v "$SOURCE:/repo:ro" -v "$EVIDENCE:/out" -w /repo \
  sre-integration-browser:local /e2e/node_modules/.bin/playwright test \
  --config=/out/final-ui-browser.config.cjs
docker run --rm --network bridge --ipc=host --user 0 -e NODE_PATH=/e2e/node_modules \
  -v "$SOURCE:/repo:ro" -v "$EVIDENCE:/out" -w /repo \
  sre-integration-browser:local /e2e/node_modules/.bin/playwright test \
  --config=/out/final-online-browser.config.cjs
docker run --rm --network none -v "$SOURCE:/repo:ro" -w /repo \
  sre-integration-browser:local sh -c 'node --check scripts/showcase.js && node --check public/incident-ui/war-room.js && node --check public/incident-ui/review.js && node --check public/incident-ui/postmortem.js && test -f index.html && test -f styles/design-system.css'
docker run --rm --network none --tmpfs /workspace:mode=1777 -v "$SOURCE:/source:ro" \
  sre-integration-contracts:local sh -c 'npm --prefix schemas/tooling test && npm --prefix schemas/tooling run validate && npm --prefix schemas/tooling run validate:releases && npm --prefix schemas/tooling run lint:openapi'
```

The whole static catalog loads public Google/jsDelivr fonts; the `bridge` browser command permits those public asset requests, with no API/provider credentials supplied. A deliberately offline broad run fails two **unchanged showcase** console-error assertions; the same two fail on the starting main tree. See the report for the normal-network outcome and retained failed-run evidence. The58 connected-browser tests are skipped without a production API configuration, and `api-seam`/`production-proxy` are excluded by the repository's static config. This does not prove production nginx, OTel, connected browser authorization, hosted CI or independent human approval.
