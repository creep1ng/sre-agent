# Issue #715 shell journeys: local run

Stack: `docker compose up --build --wait db api web` (compose.yaml only, LEGACY_CONSOLE=redirect).
Runner: `docker compose --profile e2e run --build --rm incident-console-e2e` (Playwright 1.63, Chromium).
Screenshots in this folder come from `e2e/shell.spec.ts`.

Plain `/` and `/index.html` do not redirect: `/` is the address of the Midnight landing (#870,
decision of 2026-10-31) and, until that lands, keeps serving the previous console
(`01-raiz-no-redirige-a-la-consola.png`).

Proxy answers (`docker run --rm --network host curlimages/curl:8.10.1 -s -o /dev/null -w '%{http_code} %{redirect_url}'`);
the `keep:` lines come from the same `web` image started with `LEGACY_CONSOLE=keep`:

```
200   <- /
200   <- /index.html
302 http://127.0.0.1:48732/app/  <- /?view=alerts
302 http://127.0.0.1:48732/app/  <- /?view=triage&alert_id=x
302 http://127.0.0.1:48732/app/incidentes/INC-11  <- /?view=war-room&incident_id=INC-11
302 http://127.0.0.1:48732/app/incidentes/inc-abc_1  <- /?view=war-room&incident_id=inc-abc_1
302 http://127.0.0.1:48732/app/incidentes  <- /?view=war-room
200   <- /?view=decisions&incident_id=INC-11
keep: 200  <- /?view=war-room&incident_id=INC-11
keep: 200  <- /?view=triage
keep: 200  <- /
```

Playwright list output:

```
  ✓   1 e2e/design.spec.ts:30:1 › el filtro de servicios es un menú junto al titular y filtra la bandeja (2.6s)
  ✓   2 e2e/design.spec.ts:50:1 › la historia va en una columna al lado, con hallazgos y decisiones dentro, y el agente en violeta (31.0s)
  ✓   3 e2e/design.spec.ts:84:1 › el cierre se resume como línea de tiempo, sin tarjetas ni listas (1.7s)
  ✓   4 e2e/governance.spec.ts:20:1 › el gobierno de IA se abre desde la barra lateral en otra pestaña (2.0s)
  ✓   5 e2e/journey.spec.ts:55:1 › una alerta crítica llega a incidente cerrado en 7 clics, sin salir de una sola vista (1.0m)
  ✓   6 e2e/journey.spec.ts:133:1 › descartar pide un motivo y se puede deshacer (1.4s)
  ✓   7 e2e/journey.spec.ts:146:1 › si el agente no puede investigar, dice por qué y se reintenta en el mismo incidente (5.8s)
  ✓   8 e2e/journey.spec.ts:168:1 › pedir cambios devuelve la propuesta al agente y la nueva explica qué ajustó (35.3s)
  ✓   9 e2e/journey.spec.ts:183:1 › si la mitigación no funciona, «Sigue fallando» vuelve a investigar sin abrir otro incidente (36.8s)
  ✓  10 e2e/journey.spec.ts:198:1 › la bandeja dice qué hace el agente y permite vincular una alerta al incidente abierto (4.5s)
  ✓  11 e2e/journey.spec.ts:231:1 › se ve bien en modo oscuro y en el celular (27.7s)
  ✓  12 e2e/proxy.spec.ts:8:1 › el proxy sirve la consola nueva en /app y la anterior solo donde aún no hay equivalente (1.2s)
  ✓  13 e2e/shell.spec.ts:23:1 › las direcciones de la consola anterior abren la consola nueva (3.7s)
  ✓  14 e2e/shell.spec.ts:76:1 › la barra lateral y la búsqueda se usan con el teclado y los ids quedan en detalles técnicos (4.3s)
  ✓  15 e2e/live-inbox.spec.ts:48:1 › sin credencial pide conectar y no llama a la API (273ms)
  ✓  16 e2e/live-inbox.spec.ts:61:1 › una clave inválida se explica sin códigos y no deja la clave en el navegador (779ms)
  ✓  17 e2e/live-inbox.spec.ts:79:1 › sin permiso de lectura se explica y la lista anterior desaparece (836ms)
  ✓  18 e2e/live-inbox.spec.ts:98:1 › un fallo transitorio conserva la lista y se recupera en el siguiente sondeo (850ms)
  ✓  19 e2e/live-inbox.spec.ts:123:1 › sondea cada 15 s y conserva el mismo alert_id (791ms)
  ✓  20 e2e/live-inbox.spec.ts:140:1 › muestra servicio, severidad, hora local y estado de triage; solo new y triaging cuentan (831ms)
  ✓  21 e2e/live-inbox.spec.ts:162:1 › el filtro aparece con un solo servicio y filtra de verdad (1.4s)
  ✓  22 e2e/live-inbox.spec.ts:184:1 › una respuesta vacía deja un estado claro (797ms)
  -  23 e2e/live-real.spec.ts:18:3 › bandeja contra la pila real › una falla real de checkout llega, se refresca y se filtra
  1 skipped
  22 passed (3.8m)
```
