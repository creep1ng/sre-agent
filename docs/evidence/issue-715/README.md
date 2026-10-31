# Issue #715 shell journeys: local run

Stack: `docker compose up --build --wait db api web` (compose.yaml only, LEGACY_CONSOLE=redirect).
Runner: `docker compose --profile e2e run --build --rm incident-console-e2e` (Playwright 1.63, Chromium).
Screenshots in this folder come from `e2e/shell.spec.ts`. Playwright list output:

```
#48 14.19 ✓ 2518 modules transformed.
#48 14.75 ✓ built in 1.38s
  ✓   1 e2e/design.spec.ts:30:1 › el filtro de servicios es un menú junto al titular y filtra la bandeja (8.4s)
  ✓   2 e2e/design.spec.ts:50:1 › la historia va en una columna al lado, con hallazgos y decisiones dentro, y el agente en violeta (37.9s)
  ✓   3 e2e/design.spec.ts:84:1 › el cierre se resume como línea de tiempo, sin tarjetas ni listas (5.8s)
  ✓   4 e2e/governance.spec.ts:20:1 › el gobierno de IA se abre desde la barra lateral en otra pestaña (8.6s)
  ✓   5 e2e/journey.spec.ts:55:1 › una alerta crítica llega a incidente cerrado en 7 clics, sin salir de una sola vista (1.4m)
  ✓   6 e2e/journey.spec.ts:133:1 › descartar pide un motivo y se puede deshacer (6.6s)
  ✓   7 e2e/journey.spec.ts:146:1 › si el agente no puede investigar, dice por qué y se reintenta en el mismo incidente (18.7s)
  ✓   8 e2e/journey.spec.ts:168:1 › pedir cambios devuelve la propuesta al agente y la nueva explica qué ajustó (54.1s)
  ✓   9 e2e/journey.spec.ts:183:1 › si la mitigación no funciona, «Sigue fallando» vuelve a investigar sin abrir otro incidente (57.6s)
  ✓  10 e2e/journey.spec.ts:198:1 › la bandeja dice qué hace el agente y permite vincular una alerta al incidente abierto (28.8s)
  ✓  11 e2e/journey.spec.ts:231:1 › se ve bien en modo oscuro y en el celular (35.4s)
  ✓  12 e2e/proxy.spec.ts:8:1 › el proxy sirve la consola nueva en /app y la anterior solo donde aún no hay equivalente (5.1s)
  ✓  13 e2e/shell.spec.ts:23:1 › las direcciones de la consola anterior abren la consola nueva (12.2s)
  ✓  14 e2e/shell.spec.ts:72:1 › la barra lateral y la búsqueda se usan con el teclado y los ids quedan en detalles técnicos (10.1s)
  ✓  15 e2e/live-inbox.spec.ts:48:1 › sin credencial pide conectar y no llama a la API (1.0s)
  ✓  16 e2e/live-inbox.spec.ts:61:1 › una clave inválida se explica sin códigos y no deja la clave en el navegador (1.8s)
  ✓  17 e2e/live-inbox.spec.ts:79:1 › sin permiso de lectura se explica y la lista anterior desaparece (3.4s)
  ✓  18 e2e/live-inbox.spec.ts:98:1 › un fallo transitorio conserva la lista y se recupera en el siguiente sondeo (2.4s)
  ✓  19 e2e/live-inbox.spec.ts:123:1 › sondea cada 15 s y conserva el mismo alert_id (4.7s)
  ✓  20 e2e/live-inbox.spec.ts:140:1 › muestra servicio, severidad, hora local y estado de triage; solo new y triaging cuentan (2.8s)
  ✓  21 e2e/live-inbox.spec.ts:162:1 › el filtro aparece con un solo servicio y filtra de verdad (2.4s)
  ✓  22 e2e/live-inbox.spec.ts:184:1 › una respuesta vacía deja un estado claro (1.6s)
  -  23 e2e/live-real.spec.ts:18:3 › bandeja contra la pila real › una falla real de checkout llega, se refresca y se filtra
  1 skipped
  22 passed (6.8m)
```
