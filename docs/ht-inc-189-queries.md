# HT-INC-RUNTIME-B — Consultas autoritativas de incidentes (issue #189)

Capa de lectura sobre el almacenamiento persistido (#146) y el runtime (#26).
Nada aquí muta estado: las consultas proyectan agregados y nunca crean
ejecuciones, snapshots ni decisiones.

## Fuente autoritativa

`PostgresIncidentUnitOfWork` (tablas `incident.*`, migración
`20260907_06`). Lecturas: `incidents.get`, `runs.get` + `runs.list_ids`,
`events.list_after`, `snapshots.latest`, `decisions.get` (puertos de lectura
añadidos por esta issue; sin cambios de escritura). Servicio:
`src/sre_agent/incident/queries.py` (`IncidentQueryService` + `incident_router`,
montado en `application.py`).

## Endpoints y contrato

Contrato versionado: `agent/api/incident-queries.openapi.yaml` (1.0.0),
validado por `scripts/validate_incident_queries.py` (schemas, paths, `$ref`,
ejemplos positivos y de error, registro en la policy).

| Método | Respuesta |
| --- | --- |
| `GET /v1/incidents/{incident_id}` | `incident-detail:1.0.0`: identidad, workflow, estado, severidad/impacto, alerta canónica, approvals acotados, versión, `runs[]` (vacío = ausencia explícita) |
| `GET /v1/incidents/{incident_id}/timeline?run_id=&after=&limit=` | `run-event:1.0.0` reutilizado: eventos ordenados + `next_cursor` + `has_more` |
| `GET /v1/incidents/{incident_id}/snapshot?run_id=` | `incident-snapshot:1.0.0`: snapshot + versión y `event_sequence` cubiertos |

## Timeline, paginación y versionado

Orden = `sequence` de **un** run (ADR-008); fusión cross-run explícitamente
fuera de alcance (sin orden contractual que la respalde). Sin `run_id` se lee
el último run (orden `created_at`); con `run_id` ajeno → 404. Cursor opaco
`seq:N` (`after` ausente = desde el inicio); cursor inválido → 422 sin reset
silencioso. `limit` 1..200 (defecto 50); `has_more` con fetch de `limit+1`.
Versión = agregado persistido, verbatim; detalle y snapshot la reportan igual.

## Snapshot

Último snapshot del run (`event_sequence`/`version` DESC). Sin run →
404 `run_absent`; sin snapshot → 404 `snapshot_absent`. Nunca se crea nada por
GET. `version`/`event_sequence` permiten a #36 detectar staleness.

## Autorización y errores

Bearer (`#13`) → 401 con `WWW-Authenticate: Bearer`. Autorización con el engine
compartido: `run.read` sobre `incident_workflow`/`incident-response`
(extensión aprobada en `authorization.v1.yaml`; recurso = workflow pinnado,
sin joins al gateway). Denegado → **403 sin contenido parcial** (se autoriza
antes de leer existencia). Inexistente → 404 (`incident_not_found`,
`run_not_found`, `snapshot_absent`). IDs/cursor/limit malformados y datos con
workflow desconocido → 422. Fallo de storage → 503 `storage_unavailable` con
`Retry-After`, sin internos. Sin escrituras de auditoría en lecturas (#189 lo
prohíbe para auditoría gateway).

## Seguridad de datos

Proyección allow-list (`projection-policy.v1.yaml` extendida; el validador la
hace cumplir fail-closed): solo identificadores opacos, textos acotados y
versiones. `turn_id` se mapea a `task_id` (C05); contexto textual y prompts
jamás se leen (endpoint `/context` excluido a propósito: exige
`run.read_context`). Decisiones ausentes o actores desconocidos → 503 en vez
de atribución inventada.

## Relación con #36

Suficiente para: estado+versión (CA1/CA2), responsables vía approvals/actores
de timeline, severidad/impacto, timeline paginado, snapshot, refresco por
cursor y distinción 401/403/404/422/503 (CA5/CA6). Brecha explícita: el estado
no tiene campo owner/responsable — `approvals` y referencias de actor son lo
único atribuible; ownership formal no existe en el contrato.

## Probar

```bash
python scripts/validate_incident_queries.py
pytest tests/test_incident_queries.py -q
```

PG local: crear DB, `DATABASE_URL=... alembic upgrade head`; el test usa
`postgresql://davasgo2702@localhost/sre_189_test?host=/tmp` y se omite con
`pytest.skip` si no hay servidor (omisión explícita, no un pass falso).
Demo HTTP contra stack: `docker compose up`, credencial con grant `run.read`
(vía grants directos en DB hasta que se sedeen), `curl -H "Authorization:
Bearer ..."` a los tres endpoints.

## Limitaciones conocidas

- Grants `run.read` no sedeados (decisión de seeds/catalog pendiente; deny por
  defecto hasta entonces).
- Sin timeline cross-run, sin endpoint `/context`, sin queries de triage (#23)
  ni comandos (#145 implementa routers, fuera de alcance aquí).
