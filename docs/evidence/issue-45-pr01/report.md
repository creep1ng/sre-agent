# Issue 45: prerequisite documentation evidence

**Rendered documentation only; no live MCP acceptance.** This report records the
first stacked-to-main stage. Read the [operator guide](../../issue-45-grafana-mcp-operator-runbook.md)
and view its [actual screenshot](prerequisites.png).

## Demonstrated artifacts

| Artifact | SHA-256 |
|---|---|
| Operator guide | `4e7b75726b9c155ebb9ec759a46188e9d1c76833590b4e6b82a997c7ee8be3fc` |
| PNG | `6eef308944ac5b3153b885be06d6ff5e3203e0857eca0ffc5b48a074d6399f80` |

Base: `5b6109bd2c8100455136cf12ce91c52830833c7f`. The PR body binds the
committed tested SHA separately; this report does not reference its own commit.
Guide and PNG bytes are unchanged from the demonstrated first-stage capture.

## Observed readback

From the checkout root, with the verified harness image already cached:

```sh
docker run --rm --pull never --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --entrypoint node \
  -v "$PWD/docs/issue-45-grafana-mcp-operator-runbook.md:/evidence/operator.md:ro" \
  sha256:060b50ea88cf38bb3c2b6b0bb5920f2460091056381db72d802424c5f1df697d \
  -e 'const fs=require("node:fs"); const text=fs.readFileSync("/evidence/operator.md","utf8"); if(!text.startsWith("# Issue 45:") || !text.includes("documentation, not new probe commands or live acceptance") || !text.includes("stacked-to-main")) process.exit(1); process.stderr.write(`Node ${process.version}\n`); process.stdout.write(text);'
```

Observed: exit 0, stderr `Node v22.14.0`, stdout byte-identical to the guide.
The run used an empty inherited environment except local executable lookup and
an anonymous Docker configuration. No credentials, pull, build or services were used.

## Portability: build recipe, not executed for this stage

The local image ID above is not a distributable registry reference. The public
Node digest pinned by the [harness Dockerfile](../../../docker/harness.Dockerfile)
is `node:22.14-alpine@sha256:9bef0ef1e268f60627da9ba7d7605e8831d5b56ad07487d24d1aa386336d1944`.
An exact local inspection returned “No such image”; the cached public Node image
listing was empty. No registry lookup, pull or new build was attempted.

For a separate authorized reproduction, prepare a private ignored `.env` from
`.env.example` with non-production settings and no provider credentials. Run the
existing `scripts/bootstrap-worktree.py` safe configuration setup to generate the
unique `.env.worktree`; never print, source, attach or commit either file.
The [wrapper](../../../scripts/worktree-compose) reads those files in that order.
The equivalent Docker commands below use that generated identity, not a shared
project name. Building may require public registry/npm network access and
containerized `npm ci`; obtain the applicable permission first.

```sh
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree \
  -f compose.yaml --profile checks build harness
docker compose --project-directory "$PWD" --env-file .env --env-file .env.worktree \
  -f compose.yaml --profile checks run --rm --no-deps --no-build \
  -v "$PWD/docs/issue-45-grafana-mcp-operator-runbook.md:/evidence/operator.md:ro" \
  harness node -e 'process.stderr.write(`Node ${process.version}\n`); process.stdout.write(require("node:fs").readFileSync("/evidence/operator.md","utf8"));'
```

Expected: the guide and Node version, without starting API, DB or demo services.
These source-validated Compose commands were **not executed for this stage**;
they are not a claim of current build success. No environment setup was needed
or performed for the observed cached-image readback above.

## Screenshot and checks

Chromium 153.0.8010.52 rendered local HTML made from the exact guide bytes, with
no external assets/fonts, blocked DNS and the browser sandbox enabled. The real
1600×3300 PNG (493445 bytes) was visually inspected; all rows and the source-hash
footer are visible. It is not a generated image or historical full-candidate reuse.

Fifteen relative links, three shell blocks and whitespace checks passed without
executing document text. Guide, tracker, report and visible screenshot were privacy-checked;
no environment files, secrets, private absolute paths or provider payloads are included.
All original recovery source hashes/status/HEAD remain preserved. A local tracker
mirror refresh is pending; it is not acceptance evidence.

## Limits and rollback

All real CA1–CA8 and original live acceptance tasks remain open. Historical
13/13 plus independent 3/3 belong to the full recovery, not this documentation
stage. Portable build execution, public evidence binding, hosted CI and human
review remain pending. Revert the guide, tracker, report and PNG together;
no executable, runtime, configuration, dependency or producer source changed.
