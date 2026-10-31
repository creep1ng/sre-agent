# Issue 870: the Midnight landing at `/`

`web/incident-console/e2e/landing.spec.ts` writes these screenshots while it drives the real web
proxy of `compose.yaml` (no `LEGACY_CONSOLE` override). The page is
`landing/index.html`, ported from `docs/design/brand-round-1/02-nocturno.html`.

| File | Viewport | Language |
| --- | --- | --- |
| [`desktop-es.png`](desktop-es.png) | 1440 × 960, full page | Spanish (browser `es-CO`) |
| [`desktop-en.png`](desktop-en.png) | 1440 × 960, full page | English, chosen with `ES · EN` and kept after a reload |
| [`phone-es.png`](phone-es.png) | 390 × 844, full page | Spanish (browser `es-CO`) |
| [`phone-en.png`](phone-en.png) | 390 × 844, full page | English (browser `en-GB`, nothing stored) |

The same run checks that `/` answers 200 with the landing, that every request stays on the proxy's
origin (fonts included) with no console error, that both «Abrir la consola» links are moonlight
and open `/app/`, that `/?view=decisions` and `/public/admin/principals.html` still reach the
previous console, that `/?view=alerts`, `/?view=triage` and `/?view=war-room` land on `/app/`,
and that `/llms.txt` answers as `text/markdown`.

## Repeat

With an untracked `.env` from `.env.example` (synthetic values):

```sh
docker compose up --build --wait db api web
docker compose --profile e2e run --build --rm -e HOST_UID=$(id -u) -e HOST_GID=$(id -g) incident-console-e2e \
  sh -c 'npx playwright test e2e/landing.spec.ts e2e/proxy.spec.ts; s=$?; chown -R "$HOST_UID:$HOST_GID" e2e/artifacts; exit $s'
```

The screenshots land in `web/incident-console/e2e/artifacts/landing/`. The sky is seeded, so a
repeat run draws the same week.
