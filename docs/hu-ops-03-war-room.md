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
anexa por `next_cursor`). El run queda fijado desde `detail.runs` durante
toda la paginación y el snapshot (el cursor `seq:N` solo vale dentro de un
run); Actualizar re-deriva el último run y reinicia la paginación. Cada carga
lleva una generación de sesión: olvidar/cambiar credencial o refrescar
invalida respuestas anteriores, que se descartan sin tocar el DOM. CA2 se
cumple mediante este mecanismo documentado; no se promete ni finge push/SSE.
Frecuencia automática = bloqueo pendiente, no implementado.

## Estructura

Resumen (incident_id, estado, severidad/impacto, versión, snapshot
`v{version} (seq {event_sequence})`, approvals como responsables — sin owner
contratado, documentado como brecha), timeline operativo de eventos (actor,
fecha, secuencia, tipo, resumen; `seq` + cursor). Comentarios persistentes de
usuario NO visibles: no existe API de comentarios (dependencia pendiente de
#23); el timeline muestra eventos de la atención, no comentarios. Errores
diferenciados 401/403/404/503 + falta de `incident_id` + timeline vacío;
jamás fixtures como fallback ni contenido parcial en 403 (una denegación
durante `Cargar más` retira el contenido protegido). Credencial solo en
memoria (`createMemoryCredentialStore`, formulario propio, botón Olvidar);
401 reabre el formulario.

## Demo y evidencia

Sin bootstrap en producción (prohibido inventarlo): preparar con
`DATABASE_URL=... python scripts/seed_war_room_demo.py` (idempotente por
replay; crea `inc-war-room-demo` + run + 3 eventos de 3 actores + snapshot vía
UoW/runtime reales; **no** crea grants — las lecturas siguen 403 hasta el
sedeo de `run.read`, brecha B6 documentada). Evidencia UI: Playwright con API
mockeada (`tests/browser/war-room.spec.js`, 13 tests: resumen, run fijado
entre páginas, paginación sin duplicados, refresh con cambio de versión,
denegación 401/403 durante `Cargar más` sin parciales, recuperación 503,
respuestas obsoletas descartadas, vacío, missing-id, 401/403/404/503, sin
lifecycle controls, dos sesiones); estabilidad de lectura tras recrear pools y
servicio en el mismo proceso (relectura secuencial, no dos sesiones
concurrentes), en `tests/test_incident_query_timeline.py`
(#189). Renders reales de resumen y 403 capturados en verificación para
evidencia de revisión. Comando reproducible contra un stack vivo (requiere
grant `run.read`; hoy bloqueado según #184):
curl live: `curl -H "Authorization: Bearer …" http://127.0.0.1:8000/v1/incidents/{id}{,/timeline,/snapshot}`.

## Relación y fuera de alcance

Consume #189; alimenta el journey #150 (etapas 8–9). #23 aportará la entrada
desde triage (hoy solo deep-link, sin puente falso). Pendientes explícitos:
API de comentarios visibles (CA4 parcial: sin contrato #23 no se muestran),
sedeo de grants `run.read` (sin permisos globales), ownership formal.
Fuera: lifecycle, harness, comentarios-escritura, war-room push,
detección/thresholds.
