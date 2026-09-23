# HU-OPS-03 — War room con estado y timeline compartido (issue #36)

Ruta: `public/incident-ui/war-room.html?incident_id=…` (deep-link; #23 enlazará
aquí cuando exista). Fuente única: API de consultas del dominio (#189).
Solo lectura: sin transiciones, sin harness, sin API de comentarios.

## Contratos consumidos (#189)

`incident-detail:1.0.0`, `run-event:1.0.0` (timeline), `incident-snapshot:1.0.0`,
`incident-queries.openapi.yaml:1.0.0`, `error-envelope:2.0.0`. Endpoints
`GET /v1/incidents/{id}`, `/timeline`, `/snapshot` vía seam `public/api/client.js`
(`getIncident`, `getIncidentTimeline`, `getIncidentSnapshot`) tras el proxy
mismo-origen `/api` (topología #148, CSP sin CORS).

## Refresh (decisión)

ADR-008 fija polling con cursor a cargo de la UI. La frecuencia automática
sigue abierta (Daniel+Camilo), por lo que esta vista implementa **refresh
manual** (CASO A): el botón Actualizar re-lee detalle+snapshot+timeline desde
el inicio y reemplaza el render (sin duplicados por construcción; `Cargar más`
anexa por `next_cursor`). Los casos de concurrencia (nuevo run entre
páginas, denegación al paginar, respuestas tardías) se cubren en la slice
siguiente. CA2 se cumple mediante este mecanismo documentado;
no se promete ni finge push/SSE. Frecuencia automática = bloqueo pendiente,
no implementado.

## Estructura

Resumen (incident_id, estado, severidad/impacto, versión, snapshot
`v{version} (seq {event_sequence})`, approvals como responsables — sin owner
contratado, documentado como brecha), timeline (actor, fecha, secuencia, tipo,
resumen; `seq` + cursor), comentarios = eventos del timeline (sin endpoint de
escritura: solo lectura). Errores diferenciados 401/403/404/503 + falta de
`incident_id` + timeline vacío; jamás fixtures como fallback ni contenido
parcial en 403. Credencial solo en memoria (`createMemoryCredentialStore`,
formulario propio, botón Olvidar); 401 reabre el formulario.

## Demo y evidencia

Sin bootstrap en producción (prohibido inventarlo): preparar con
`DATABASE_URL=... python scripts/seed_war_room_demo.py` (idempotente por
replay; crea `inc-war-room-demo` + run + 3 eventos de 3 actores + snapshot vía
UoW/runtime reales; **no** crea grants — las lecturas siguen 403 hasta el
sedeo de `run.read`, brecha B6 documentada). Evidencia UI: Playwright con API
mockeada (`tests/browser/war-room.spec.js`, 8 tests); lógica viva contra PG
verificada en desarrollo (detalle 200, timeline seq 0-2, snapshot v1/seq0).
curl live: `curl -H "Authorization: Bearer …" http://127.0.0.1:8000/v1/incidents/{id}{,/timeline,/snapshot}`.

## Relación y fuera de alcance

Consume #189; alimenta el journey #150 (etapas 8–9). #23 aportará la entrada
desde triage (hoy solo deep-link, sin puente falso). Fuera: lifecycle,
harness, comentarios-escritura, war-room push, detección/thresholds.
