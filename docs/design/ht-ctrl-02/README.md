# HT-CTRL-02 — Control Plane Wireframes

Este paquete contiene wireframes de baja/media fidelidad listos para importar en Figma como SVG editable.

## Archivos

- `00-overview.svg`
- `01-principals-list.svg`
- `02-principal-detail.svg`
- `03-credentials.svg`
- `04-resources-catalog.svg`
- `05-alias-detail.svg`
- `06-grants.svg`
- `07-audit-consumption.svg`
- `08-limits-budget-future.svg`

## Navegación propuesta

Overview → Principals → Resources & Aliases → Grants → Audit & Consumption → Limits & Budget.

Navegación contextual:
- Principal Detail → Credentials
- Principal Detail → Grants con `principal_id` preseleccionado
- Principal Detail → Audit con `principal_id` preseleccionado
- Resource Detail → Grants con `resource_id` preseleccionado
- Alias Detail → Audit con alias preseleccionado

## Reglas de dominio visibles en los wireframes

- `Principal` = identidad `human | agent`.
- `triage-agent` = alias lógico de modelo, no identidad.
- Grant = `Principal + action + resource`.
- Ausencia de grant activo = deny.
- No se introducen roles, organizaciones o SSO.
- El harness solicita `triage-agent`; el gateway resuelve modelo/provider efectivo.
- Credenciales: el secreto se visualiza una sola vez en emisión/rotación.
- Auditoría: experiencia `filter-first` y detalle metadata-only.
- Limits & Budget se representa como superficie futura, no implementación de Sprint 1.

## Estados obligatorios incluidos

- Estado vacío: Credentials sin API keys.
- Estado de error/denegación: Grant inexistente/inactivo → Access unavailable / deny.

## Anotaciones API por pantalla

### Principals
- `GET /v1/principals`
- `POST /v1/principals`
- `GET /v1/principals/{id}`
- `PUT /v1/principals/{id}/status`

### Credentials
- `GET /v1/principals/{id}/credentials`
- `POST /v1/principals/{id}/credentials`
- `POST /v1/credentials/{id}/rotation`
- `DELETE /v1/credentials/{id}`

### Model aliases
- `GET /v1/model-aliases`
- `GET /v1/model-aliases/{id}`
- `PUT /v1/model-aliases/{id}/assignment`
- `PUT /v1/model-aliases/{id}/status`

### Grants
- `GET /v1/grants?principal_id=...` o `resource_id=...`
- `POST /v1/grants`
- `DELETE /v1/grants/{id}`

### Audit
- `GET /v1/audit-events` con al menos un filtro
- `GET /v1/audit-events/{id}`

## Decisiones UX/API que deben permanecer explícitas

1. `provider` opcional en backlog vs requerido en contrato actual.
2. CRUD genérico de `Resource` todavía debe formalizarse o diferirse.
3. Grants requiere contexto/filtro inicial.
4. Audit requiere filtro inicial.
5. Audit es metadata-only.
6. Consumo todavía necesita contrato/fuente formal.
7. Desactivar Principal no debe asumir cascadas sobre credenciales/grants.
8. Las listas del contrato MVP están acotadas; no dibujar paginación clásica sin cambio contractual.

## Mapeo con #57

- Principals list/detail: incluido.
- Credentials: incluido.
- Resource catalog: incluido.
- Alias → model + provider: incluido.
- Grants create/revoke/deny: incluido.
- Audit/consumption: incluido.
- Limits/budget future surface: incluido.
- Empty state: incluido.
- Error/denial state: incluido.
- API/data annotations: incluidas.
- No organizations/roles/SSO: explícitamente excluidos.
