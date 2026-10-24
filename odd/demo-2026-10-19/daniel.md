# Daniel: UI de incidentes para la demo del lunes 19

Demo: lunes 2026-10-19 a las 17:00 (Bogotá). Pruebas humanas E2E: desde el domingo 2026-10-18.
En `origin/main` no hay forma de iniciar una investigación desde la UI y no existen acciones de
verificación ni de cierre. Tres tareas en orden, cada una con su resultado verificable.

## T1, viernes 17 y sábado mañana: iniciar y reanudar investigación desde la war room (#37)

Rama sobre `feat/ht-web-shell-review-feedback` (head de #648), porque #646 reescribe
`public/incident-ui/war-room.js`. Rebasas cuando la consola entre a main el sábado.

Alcance:

- En `public/api/client.js` añade `startRun`, `getRun` y `listRunEvents` contra
  `POST /v1/incidents/{id}/runs`, `GET .../runs/{run_id}` y `GET .../runs/{run_id}/events`.
  Contrato: `agent/api/incident-runs.openapi.yaml`, esquemas `run-start-request`, `run-state`
  y `run-event`. Cuerpo de inicio: `{"workflow_version":"1.0.0","objective":"investigate"}`.
- Botón "Iniciar investigación" solo con incidente en `active`. "Reanudar" si existe un run en
  `awaiting_human`.
- `Idempotency-Key` estable por incidente y objetivo, guardada en memoria de sesión, para que
  doble clic y recarga no creen otro run.
- Mostrar `status`, `pending_command` y `terminated_reason`. `denied` se lee como
  "autorización denegada, requiere intervención"; nunca como completado.
- Distinguir 401, 403, 404, 409 y 503. Refresco manual, sin SSE. Ninguna clave en la URL.

Resultado verificable (Playwright contra API real con `demo-human`):

- Clic crea un run y la war room lo muestra.
- Recargar conserva el mismo `run_id`.
- Doble clic deja `detail.runs` con un solo elemento.
- `restricted-harness` recibe 403 y la UI no muestra éxito.

Entrega: captura PNG, PR menor de 400 líneas, `Refs #37`, campos de la política completos.
Camilo valida el domingo que su corrida real se ve en tu pantalla.

## T2, sábado tarde: verificación y cierre en Decisiones (#41 CA3 y CA4)

Camilo publica el sábado a las 14:00 el contrato con `verification_passed`,
`verification_failed` y `close_incident`. Puedes empezar con fixtures de ese enum.

Alcance:

- Botones "Verificación estable", "Verificación no estable" y "Cerrar incidente".
- "Cerrar incidente" con aprobación explícita y visible solo en estado `postmortem`.
- Un 409 por versión obsoleta conserva el motivo escrito por el usuario.

Resultado verificable:

- Recorrido real desde la UI: `mitigating`, `verifying`, `resolved`, `postmortem`, `closed`,
  con captura por estado.
- Intentar cerrar sin postmortem muestra el rechazo del backend y el estado no cambia.
- Recargar y una segunda sesión autorizada ven lo mismo.

## T3, domingo: postmortem contra backend real (#43)

Cuando entre el artefacto mínimo de Camilo, `public/incident-ui/postmortem.js` deja de usar el
fixture y lee el artefacto real. Editar y guardar con versión. Enlace desde el incidente.

Resultado verificable:

- Recargar muestra el mismo id y versión.
- 403 sin fragmentos de contenido.
- Guardar con versión obsoleta muestra un conflicto recuperable.

## Tus PRs abiertas

- #482: Ricardo decide hoy contra #648; no le dediques más tiempo.
- #588: se mergea el sábado.
- #418: deja un comentario diciendo si ya atiende los cambios pedidos.
- #582 y #623: siguen en draft, no son para la demo.
