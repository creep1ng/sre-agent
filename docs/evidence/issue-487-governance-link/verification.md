# Issue #487: governance link from the new console

## Change under test

The new incident console (`/app`, `web/incident-console`) adds one link, «Gobierno de IA», in a
separated group of the sidebar. It opens the administration console at
`/public/admin/principals.html` in a new tab so the incident view stays in place. This is the
rehearsal feedback of #487 implemented in the new console under the operation scope that #715
defines. The SharedWorker multi-tab session (#486) remains postponed, so the link opens the
legacy admin page directly and that page still asks for the operator key.

## Tested tree

- Parent: `96297ebb9eac32c58979b8896d9c91fbcac1a6b7` (`origin/main` when the run started).
- The suite ran on the working tree that the implementation commit contains. No file changed
  between the run and the commit; the PR records the commit SHA as its Tested SHA.

## Environment

- Windows host with Docker Engine 29.2.1 and Docker Compose v5.0.2. The host only used Git and
  Docker; every build and browser run happened inside containers.
- Isolated Compose project `issue487-link` built from `compose.yaml` plus `compose.e2e.yaml`, so
  no host port was published and the shared `sre-agent-*` containers were never touched.
- `.env` copied from the repository root, used only for Compose interpolation. It is gitignored,
  was not printed, and is not part of this directory.
- Images from `web/incident-console/Dockerfile`: `node:22.14-alpine` (digest pinned) for the
  console build, `nginx:1.27-alpine` (digest pinned) to serve it, and
  `mcr.microsoft.com/playwright:v1.63.0-noble` (digest pinned) for the E2E runner. The build step
  runs `tsc -b && vite build`, so the TypeScript build passed before the browser run.

## Commands

```sh
docker compose -p issue487-link --env-file .env -f compose.yaml -f compose.e2e.yaml up --build --wait db api web
HOST_UID=0 HOST_GID=0 docker compose -p issue487-link --env-file .env -f compose.yaml -f compose.e2e.yaml --profile e2e run --build --rm incident-console-e2e
docker compose -p issue487-link --env-file .env -f compose.yaml -f compose.e2e.yaml --profile e2e down -v --remove-orphans
```

The second command ran the whole `web/incident-console/e2e` suite, not only the new spec.

## Actual result

- `12 passed (3.9m)`. The new spec was
  `e2e/governance.spec.ts:20:1 › el gobierno de IA se abre desde la barra lateral en otra pestaña`
  (`2.6s`). The other 11 specs (design, journey, proxy) also passed against the same stack.
- Link in the rendered sidebar, read from the DOM inside the running stack:
  `{"href":"/public/admin/principals.html","target":"_blank","rel":"noopener noreferrer","text":"Gobierno de IA"}`.
- After the click, the popup loaded `http://web/public/admin/principals.html` and its level-1
  heading was `Principals`.
- Screenshots were produced by Playwright (Chromium 1.63) inside the E2E container, not by a
  fixture or a generated capture.

## Screenshots

| File | What it shows |
|---|---|
| `barra-lateral-gobierno.png` | The sidebar group «Gobierno de IA» below the rule, with the external-link affordance |
| `administracion-principals.png` | The new tab: `Principals` administration page with its API key session form |
