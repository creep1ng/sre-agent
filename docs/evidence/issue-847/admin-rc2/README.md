# Administration plane in the RC-2 console: test runs (#847)

Tested SHA: de8d519d248ea90279ec8577f48c0e69ee987dfa (top of 9/10). Local Docker Compose worktree stack, real API and PostgreSQL, synthetic keys, no model provider.

## RC-2 console suite (incident-console-e2e, ADMIN_REAL=1)

```
[10/47] e2e/admin.spec.ts:41:1 › the administration plane lives in the console's own navigation
[11/47] e2e/admin.spec.ts:65:3 › against the real control plane › an operator creates an identity, issues its key, grants it a model and reads the audit
[12/47] e2e/admin.spec.ts:143:3 › against the real control plane › the same plane reads in English on the light theme
[13/47] e2e/design.spec.ts:30:1 › el filtro de servicios es un menú junto al titular y filtra la bandeja
[14/47] e2e/design.spec.ts:50:1 › la historia va en una columna al lado, con hallazgos y decisiones dentro, y el agente en violeta
[15/47] e2e/design.spec.ts:84:1 › el cierre se resume como línea de tiempo, sin tarjetas ni listas
[16/47] e2e/journey.spec.ts:55:1 › una alerta crítica llega a incidente cerrado en 7 clics, sin salir de una sola vista
[17/47] e2e/journey.spec.ts:133:1 › descartar pide un motivo y se puede deshacer
[18/47] e2e/journey.spec.ts:146:1 › si el agente no puede investigar, dice por qué y se reintenta en el mismo incidente
[19/47] e2e/journey.spec.ts:168:1 › pedir cambios devuelve la propuesta al agente y la nueva explica qué ajustó
[20/47] e2e/journey.spec.ts:183:1 › si la mitigación no funciona, «Sigue fallando» vuelve a investigar sin abrir otro incidente
[21/47] e2e/journey.spec.ts:198:1 › la bandeja dice qué hace el agente y permite vincular una alerta al incidente abierto
[22/47] e2e/journey.spec.ts:231:1 › se ve bien en modo oscuro y en el celular
[23/47] e2e/landing.spec.ts:30:1 › / sirve la landing en español, con fuentes propias y sin peticiones a terceros
[24/47] e2e/landing.spec.ts:62:1 › el selector ES · EN cambia el idioma y lo recuerda al recargar
[25/47] e2e/landing.spec.ts:85:1 › sin elección guardada, un navegador en inglés ve la landing en inglés
[26/47] e2e/landing.spec.ts:95:3 › en un móvil el cielo enmarca solo la noche del viernes (es)
[27/47] e2e/landing.spec.ts:95:3 › en un móvil el cielo enmarca solo la noche del viernes (en)
[28/47] e2e/landing.spec.ts:115:1 › la consola anterior sigue donde /app aún no llega, y lo que /app reemplaza redirige
[29/47] e2e/landing.spec.ts:134:1 › /llms.txt existe y describe Midnight para agentes
[30/47] e2e/language.spec.ts:41:1 › a Spanish browser starts in Spanish and switches to English and back
[31/47] e2e/language.spec.ts:66:3 › an English browser › starts in English, and a stored Spanish choice wins over it
[32/47] e2e/language.spec.ts:75:3 › an English browser › shows the shell in English in both themes
[33/47] e2e/proxy.spec.ts:8:1 › el proxy sirve la consola nueva en /app y la anterior sigue en sus vistas pendientes
[34/47] e2e/shell.spec.ts:22:1 › each section is a word in the text face with its own icon
[35/47] e2e/shell.spec.ts:33:1 › live mode lists only sections backed by the API
[36/47] e2e/shell.spec.ts:42:1 › the sidebar folds from the keyboard and a reload remembers it
[37/47] e2e/shell.spec.ts:83:1 › muted text keeps 4.5:1 on the sidebar and the page in both themes
[38/47] e2e/theme.spec.ts:48:1 › the console follows the system theme and repaints when it changes
[39/47] e2e/theme.spec.ts:58:1 › a forced theme wins over the system and survives a reload
[40/47] e2e/theme.spec.ts:83:1 › the shell paints no amber in either theme
[41/47] e2e/inbox-real.spec.ts:87:5 › es-night › es-night: the decision leads in amber, then the digest and last night
[42/47] e2e/inbox-real.spec.ts:87:5 › es-day › es-day: the decision leads in amber, then the digest and last night
[43/47] e2e/inbox-real.spec.ts:87:5 › en-night › en-night: the decision leads in amber, then the digest and last night
[44/47] e2e/inbox-real.spec.ts:87:5 › en-day › en-day: the decision leads in amber, then the digest and last night
[45/47] e2e/inbox-real.spec.ts:102:1 › three days later the digest and last night are gone, the decision still waits
[46/47] e2e/inbox-real.spec.ts:110:1 › each item opens its incident
[47/47] e2e/inbox-real.spec.ts:119:1 › once the decision is taken, nothing waits and nothing is amber
  14 skipped
  33 passed (6.2m)
```

## #722 grant journey through /app/admin/permisos (service-operation-e2e)

```
[1/3] tests/browser/service-operation-grant-real.spec.js:89:5 › setup lets the agent roll sre-checkout back, and nothing else
[2/3] tests/browser/service-operation-grant-real.spec.js:110:5 › the console offers only mitigation.execute, and a revoked grant is granted again anew
[3/3] tests/browser/service-operation-grant-real.spec.js:144:5 › an operation outside the catalog, or another action on one, is refused
  3 passed (8.0s)
```

## Previous console, static suites (playwright.config.js)

Whole suite before the last spec update: 104 passed, 33 skipped, 1 failed (the old in-console Triage hand-off, replaced in 9/10). After it, console-shell and console-incidents: 19 passed, 2 skipped.

## Screenshots

01–07: Spanish, dark. 11–13: English, light. The one-time key and the issued credential's prefix are masked.

## Skills (#31, layer 11)

`e2e/admin.spec.ts` and `e2e/shell.spec.ts` on the Skills layer, real API: 8 passed. The journey publishes
a version from the console, is refused a dependency that is not `id@version` before sending, reads the
manifest (published, not active), activates it, and is refused the same version with other content (409).
Screenshots: `08-skill.png` (es, dark) and `14-skills-light.png` (en, light).

## Knowledge (#33, layers 12–14)

`e2e/admin.spec.ts` and `e2e/shell.spec.ts` on the Knowledge layer, real API with the BoK publish route: 9 passed,
twice in a row. The journey publishes a collection from the console (a document without text is refused before
sending; three headings make three chunks), reads its content, is refused a search without a grant, grants
`bok.search` on the exact version in Permissions, and the search finds the published text.
Screenshots: `09-conocimiento.png` (es, dark) and `15-knowledge-light.png` (en, light).

## After the rebase onto main and the maintainer's feedback (2026-11-03)

Stack rebased onto `main` `7413c94d`. On the top (layer 16), local Docker Compose worktree stack:
- RC-2 console suite (`incident-console-e2e`, `ADMIN_REAL=1`): 36 passed, 21 skipped (opt-in journeys), 0 failed.
- `admin.spec.ts` + `shell.spec.ts` with the follow-ups: 10 passed. They cover aligned form fields, the Skill owner as the connected identity, a `.zip` of runbooks published as a collection, and a Skill `.zip` filling its form.
- #722 grant journey through `/app/admin/permisos`: 3 passed, three runs in a row after scoping its "nothing else" check to `sre-checkout`. Since #724 `provision_demo.py` also grants `flag.set` on `payment` and `checkout`, so the unscoped check failed on `main` too. One earlier run failed once in the second case and did not repeat.
- Previous console, static suites: 104 passed, 33 skipped, 1 failed. The failure was `console-shell` Back/Forward navigation under load; it passed 3 of 3 when repeated alone and does not touch administration.
- Python checks on the BoK layers over the new `main`: ruff, format and import contracts clean; 121 passed.

New screenshots: `08a-skill-formulario.png` and `10a-conocimiento-formulario.png` (forms after an upload) and `10-conocimiento-zip.png`.

## API keys: rotate and revoke (layer 18)

`e2e/admin.spec.ts` and `e2e/shell.spec.ts` on layer 18, real API: 11 passed in two runs (the second with the final screenshot masks). The journey marks
the key the console is connected with ("Esta consola") on `admin-human`, issues a key for a new identity, rotates
it, and checks with `GET /v1/whoami` that the old key now gets 401 and the new one 200. It then revokes the new
key (401 afterwards), and the list keeps both keys as revoked with their dates and no actions left.
Screenshots: `16-esta-consola.png`, `17-rotar-clave.png` and `18-claves-revocadas.png`. A key's prefix is
masked wherever it appears: in the list, the dialog title and the confirmation toast.
