# HT-CTRL-02 — Wireframes del plano de control (v2)

- Issue: #57
- Versión del artefacto: 2.0
- Estado: revisión corregida posterior al feedback de la primera propuesta
- Alcance: MVP single-workspace
- Derivado de: #56
- Contrato rector: #9 y `schemas/releases/1.0.0/openapi/control-plane.yaml`

## Objetivo

Definir wireframes de baja/media fidelidad para el plano de control administrativo sin introducir organizaciones, roles, SSO ni multi-tenancy como requisitos del MVP.

La revisión v2 corrige la fragmentación de pantallas y el uso excesivo de cards de la primera propuesta. El diseño resultante prioriza tablas, detalles contextuales, diálogos, drawers, comboboxes y color semántico.

## Revisión v3: alineación con MA

Los siete SVG se alinearon con los tokens semánticos de tema claro de MA, conservando el alcance y los contratos de producto definidos para v2.

Los 19 indicadores de estado, ciclo de vida y decisión de política usan la anatomía canónica de `.ma-badge`: píldora de 24 px, punto de 6.72 px, separación de 6 px, padding horizontal de 8.8 px y etiqueta monoespaciada vectorizada. Los tonos continúan siendo semánticos por contexto (`success`, `warning`, `critical`, `info`, `allow` y `deny`).

La revisión validó el XML de los siete SVG, renders a 1600×900, aislamiento de cambios, inventario de color/tipografía y ausencia de solapamientos de badges o elementos de primer plano.

## Arquitectura de información revisada

Las superficies principales del producto quedan reducidas a cuatro:

1. **Principals**
   - listado de Principals;
   - detalle contextual mediante fila expandida;
   - tabs `Overview`, `Credentials`, `Grants` y `Audit`;
   - no existe una página `Principal Detail` independiente.

2. **Resources & aliases**
   - catálogo de recursos;
   - aliases LLM administrados en la misma ruta;
   - creación de recursos mediante dropdown + dialog;
   - detalle de alias mediante side panel.

3. **Grants**
   - filtros por Principal y Resource mediante comboboxes;
   - tabla de grants;
   - creación mediante dialog;
   - estado de denegación explícito.

4. **Audit & consumption**
   - KPIs relevantes;
   - filtros;
   - tabla de eventos;
   - metadata contextual del evento seleccionado.

`Limits & Budget` permanece como superficie futura/documental y no se representa como una ruta funcional de Sprint 1.

---

# Wireframes

## 00 — Review summary

Resumen de los cambios de diseño introducidos por la revisión.

![Review summary](./00-review-summary-v2.svg)

### Cambios principales

Se eliminaron:

- `Overview` como pantalla funcional;
- `Principal Detail` como página independiente;
- el row de cards para tipos de recursos;
- `Limits & Budget` como pantalla independiente;
- el formulario inline de creación de grants.

Se consolidaron:

- credenciales dentro del contexto del Principal;
- alias detail en side panel;
- auditoría, consumo, filtros y tabla en una sola superficie.

Se hicieron explícitos:

- dialog de emisión de API key;
- drawer de metadata de credencial;
- dropdown + dialog para creación de recursos;
- dialog de creación de grants;
- comboboxes para entidades buscables.

---

## 01 — Principals

Listado administrativo de Principals humanos y agénticos.

![Principals](./01-principals-inline-v2.svg)

### Comportamiento

Al seleccionar una fila, el detalle se expande en la propia tabla.

La fila expandida permite navegar contextualmente entre:

- `Overview`
- `Credentials`
- `Grants`
- `Audit`

No se abre una nueva página para `Principal Detail`.

### Datos

- `principal_id`
- `kind = human | agent`
- `display_name`
- `status`
- timestamps

### Reglas visuales

- `principal_id` debe representarse en monospace;
- `kind` usa patrón `[icono] Human` / `[icono] Agent`;
- `status` usa color semántico;
- acciones destructivas como `Deactivate` o `Revoke` deben resolverse mediante dialogs u overflow menus.

### API

- `GET /v1/principals`
- `POST /v1/principals`
- `GET /v1/principals/{id}`
- `PUT /v1/principals/{id}/status`

---

## 02 — Credential management

Gestión de API keys para el Principal seleccionado.

![Credential management](./02-credentials-dialogs-v2.svg)

### Acciones

- emitir API key;
- rotar credencial;
- revocar credencial;
- consultar metadata.

### Emisión de API key

La emisión se representa mediante un **Dialog**, no mediante una card persistente.

El secreto se muestra una única vez:

```text
Issue API key
→ mostrar secreto
→ copiar / confirmar almacenamiento
→ cerrar
```

Las vistas posteriores muestran únicamente metadata.

### View metadata

La acción `View metadata` abre un **drawer** que muestra, entre otros:

- `credential_id`
- fecha de creación;
- fecha de expiración;
- última utilización;
- status;
- credencial de origen en caso de rotación.

### Estados de expiración

La columna `Expires` diferencia visualmente:

- `never` / `never expires`: azul;
- `expiring soon`: amarillo/ámbar;
- `expired`: rojo.

### Status

El estado de la credencial usa color semántico:

- `active`: verde;
- `revoked`: rojo;
- estados preventivos: amarillo/ámbar cuando corresponda.

### API

- `GET /v1/principals/{id}/credentials`
- `POST /v1/principals/{id}/credentials`
- `POST /v1/credentials/{id}/rotation`
- `DELETE /v1/credentials/{id}`

---

## 03 — Resources & aliases

Catálogo de recursos gobernados y configuración de aliases LLM.

![Resources & aliases](./03-resources-aliases-v2.svg)

## Resources

Los recursos se representan en una tabla.

Tipos considerados:

- LLM
- Skill
- MCP
- BoK

### Reglas visuales

La columna Type usa:

```text
[icono] LLM
[icono] Skill
[icono] MCP
[icono] BoK
```

Los `resource_id` se muestran en monospace.

El status utiliza color semántico.

La columna previamente denominada `Source` se interpreta como **Registry**, para representar el origen/registro del recurso de forma más clara.

### Crear recurso

El botón `New resource` abre un dropdown que permite elegir el tipo de recurso.

Ejemplo:

```text
New resource
├── LLM model
├── MCP server
├── MCP tool
├── Skill
└── BoK collection
```

Una vez seleccionado el tipo, se abre el dialog correspondiente de creación.

## Model aliases

Los aliases comparten la ruta con Resources.

El detalle del alias seleccionado se muestra mediante un side panel.

### Alias `triage-agent`

Se representa como alias lógico administrado, no como Principal.

El formulario distingue:

- alias;
- provider;
- effective model;
- status.

### Effective model

`Effective model` debe ser un **combobox**, no un input de texto libre.

El catálogo de modelos debe depender del provider seleccionado, por ejemplo mediante una fuente equivalente a:

```text
provider → /models → lista de modelos disponibles
```

### API

- `GET /v1/model-aliases`
- `GET /v1/model-aliases/{id}`
- `PUT /v1/model-aliases/{id}/assignment`
- `PUT /v1/model-aliases/{id}/status`

---

## 04 — Grants

Administración de autorización directa.

![Grants](./04-grants-v2.svg)

La autorización mantiene explícitamente separadas las dimensiones:

```text
Principal + Action + Resource
```

### Filtros

Principal y Resource se representan como comboboxes porque son entidades buscables.

### Crear grant

La creación se inicia mediante el botón:

```text
Create grant
```

y abre un dialog con:

- Principal;
- Action;
- Resource type;
- Resource ID.

No se utiliza un formulario/card inline permanente.

### Estado de denegación

Se incluye un caso de error explícito:

```text
Access unavailable
No active grant matches
Principal = mario-admin
Action = query
Resource = runbooks-core
```

La ausencia de grant aplicable implica `deny`.

### Reglas visuales

- `grant_id` y `resource_id` se muestran en monospace;
- status usa color semántico;
- acciones finales deben convertirse en botones, menu items o dialogs reales.

### API

- `GET /v1/grants?principal_id=...`
- `GET /v1/grants?resource_id=...`
- `POST /v1/grants`
- `DELETE /v1/grants/{id}`

---

## 05 — Audit & consumption

Vista administrativa de auditoría y consumo.

![Audit & consumption](./05-audit-consumption-v2.svg)

### KPI strip

Los KPIs se muestran sobre los filtros.

Solo se utiliza color cuando existe un insight relevante.

Ejemplos:

- Requests: estado neutral;
- Tokens cercanos al guardrail: amarillo/ámbar;
- Latency dentro de baseline: verde;
- costo: neutral salvo que requiera atención.

Las cards/KPIs sin insight deben mantenerse visualmente ligeras.

### Filtros

- Principal
- Decision
- Alias
- `incident_id`

### Tabla

La tabla distingue:

- Time
- Principal
- Decision
- Alias
- Model
- Provider
- `incident_id`

### Reglas visuales

- `Decision` usa color semántico:
  - `allow`: verde;
  - `deny`: rojo.
- Alias, model e `incident_id` se muestran en monospace.
- La vista es `metadata-only`.

### Metadata del evento

Al seleccionar un evento se muestran datos como:

- `request_id`
- `run_id`
- `task_id`
- provider
- routing evidence
- timestamps

No se muestra contenido raw del prompt/respuesta.

### API

- `GET /v1/audit-events`
- `GET /v1/audit-events/{id}`

---

## 06 — Supporting dialogs & future note

Lámina auxiliar que documenta dialogs reutilizados por las otras superficies.

![Supporting dialogs](./06-supporting-dialogs-future-note-v2.svg)

### New resource dialog

Incluye campos como:

- Resource type
- Name
- Resource ID
- Registry source
- Description

### Create Principal dialog

Incluye:

- Kind
- Principal ID
- Display name

### Limits & Budget

`Limits & Budget` queda documentado como superficie futura.

No es una ruta activa de Sprint 1.

Posibles configuraciones futuras:

- límite por sesión de incidente, scoped por `incident_id`;
- presupuesto mensual del workspace.

No se deben introducir cuotas basadas en roles.

---

# Estados UX incluidos

## Estado vacío

Cuando un Principal no tiene credenciales:

```text
No credentials issued yet
[ Issue API key ]
```

Debe mostrarse como mensaje compacto, sin una card de empty state innecesaria.

## Estado de denegación

En Grants:

```text
Access unavailable
No active grant => deny
```

## Expiración de credenciales

Se distinguen:

```text
never expires     → azul
expiring soon     → amarillo
expired           → rojo
```

---

# Principios visuales

La revisión v2 aplica estas reglas:

1. Evitar cards utilizadas únicamente como relleno.
2. No anidar cards dentro de cards.
3. Preferir tablas para entidades comparables.
4. Preferir whitespace y dividers para separar secciones.
5. Utilizar dialogs y drawers para acciones transitorias.
6. Utilizar side panels para detalles contextuales pequeños.
7. Utilizar color únicamente con significado semántico.
8. Utilizar monospace para identificadores técnicos.
9. Utilizar iconos cuando ayudan a distinguir tipos de entidad.
10. Evitar crear nuevas rutas cuando el detalle puede resolverse inline.

---

# Trazabilidad con criterios de aceptación de #57

| Criterio | Evidencia |
| --- | --- |
| Cubre recorridos de #56 | Principals, Resources & aliases, Grants, Audit & consumption |
| No aparecen roles/organizaciones/SSO | Todas las superficies |
| `triage-agent` se representa como alias lógico | Resources & aliases |
| Muestra modelo efectivo + provider | Alias side panel |
| Grants distingue Principal/action/resource | Grants |
| Audit distingue Principal/alias/model/provider/sesión | Audit & consumption |
| Existe estado vacío | Credentials |
| Existe error/denegación | Grants |
| Existen anotaciones de API/UX | Todas las superficies |
| Sirve para Sprint 2 | Conjunto completo de wireframes |

---

## Archivos del artefacto

```text
docs/design/ht-ctrl-02-v2/
├── 00-review-summary-v2.svg
├── 01-principals-inline-v2.svg
├── 02-credentials-dialogs-v2.svg
├── 03-resources-aliases-v2.svg
├── 04-grants-v2.svg
├── 05-audit-consumption-v2.svg
└── 06-supporting-dialogs-future-note-v2.svg
```

Versión del artefacto: `2.0`.
