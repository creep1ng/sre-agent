## Exploration: [HT-01] Definir contratos, límites del sistema y ADRs iniciales

### Current State — snapshot al cierre de la fase de exploración

**Conclusión final:** la exploración de #9 quedó cerrada y lista para proposal, sin bloqueos P0 atribuibles a las decisiones investigadas. El contrato usa `ModelAlias`; `model: "triage-agent"` selecciona el alias gobernado, autorización ocurre antes de routing y la respuesta expone modelo/metadata efectiva. También quedaron aprobadas la taxonomía 502/503/504, Trace Context, default deny y bootstrap offline. Solo permanecían detalles de contrato diferibles: matriz exacta de endpoints, idempotencia por operación y retención/acceso de contenido redactado. En ese cierre no se avanzó de fase; fases posteriores sí crearon los artefactos downstream.

**Leyenda de evidencia:** **Hecho** reproduce una fuente; **Inferencia** conecta hechos sin convertirlos en requisito; **Recomendación** propone una decisión todavía no aprobada.

#### Decisiones explícitas del usuario — continuación de la exploración

Estas decisiones tienen precedencia para el futuro proposal. Cuando tensionan #9 o Notion, la contradicción se conserva hasta sincronizar las fuentes ejecutables; no se reescribe como si siempre hubiera sido así.

| Tema | Estado | Decisión vigente |
| --- | --- | --- |
| Plano de control | **Aprobado** | #9 define endpoints y operaciones para Principals, credenciales, `ModelAlias`, grants y auditoría. Sin paginación en este corte; con idempotencia y errores normalizados. |
| Selección LLM | **Aprobado** | El request usa `model: "triage-agent"` o alias equivalente. El valor es un recurso lógico gobernado; tras allow, el gateway lo resuelve al modelo concreto, router y provider. Cualquier selector wire alternativo queda reemplazado. |
| Entidad de dominio | **Aprobado** | `ModelAlias` para #9. `AgentProfile` queda fuera del cambio como posible concepto futuro si agrupa instrucciones, tools u otras capacidades. |
| OpenRouter | **Aprobado** | Debe soportarse desde el día 1 como integración gateway/provider LLM para demostrar independencia del harness. OpenRouter expone `POST /api/v1/responses`, recibe `model` e `input`, usa slugs `<laboratorio>/<modelo>` y permite controlar routing de provider por separado. |
| Response y metadata | **Aprobado** | Response.`model` contiene el modelo concreto empleado. Metadata plana string expone `requested_model_alias`, `router` e `inference_provider`; control plane y AuditEvent preservan la asignación/dimensiones por separado. |
| Campos fuera del subset | **Aprobado** | Se rechazan con HTTP 422; no se ignoran silenciosamente. |
| Correlación de dominio | **Aprobado** | `incident_id`, `run_id` y `task_id` viajan en el body. `request_id` lo genera el servidor. |
| No enumeración | **Aprobado** | La respuesta pública no distingue recurso inexistente de recurso existente sin grant. Para el plano de ejecución se recomienda 403 uniforme con código seguro `resource_unavailable`; 404 queda reservado para consultas de catálogo donde el Principal ya esté autorizado a conocer existencia. |
| Redacción | **Aprobado** | El pipeline cubre logs MCP, outputs del sandbox/comandos, outputs LLM, registros y outputs versionados de tool calls, prompts/inputs y cualquier contenido libre potencialmente sensible. No se decide retención todavía. |
| Versionado/ubicación | **Aprobado** | Contratos bajo `/schemas` en la raíz, con versión inicial `1.0.0` y evolución según el estándar Semantic Versioning 2.0.0. Esto es distinto de `openspec/config.yaml: schema: spec-driven`. |
| Default deny | **Aprobado** | `reason_code: "no_matching_grant"` y `policy_id: null`. `policy_id` identifica un grant/policy persistido solo cuando existe. |
| Bootstrap/control plane | **Aprobado** | Seed/CLI offline e idempotente, coherente con los archivos seed requeridos: crea primer Principal, credencial y grants, muestra la key una sola vez y persiste solo hash/prefijo. |
| Errores upstream | **Aprobado** | 502 respuesta inválida/no adaptable; 503 indisponibilidad temporal o sin ruta saludable; 504 timeout. Body seguro con código normalizado, mensaje, `request_id` y retryability. |
| W3C Trace Context | **Aprobado** | Aceptar `traceparent` válido; generar uno nuevo cuando falte o sea inválido; crear/propagar un span actualizado, con límites de sampling y fronteras de confianza. |

#### Compatibilidad preservada por `model` como alias lógico

OpenAI Responses request/response y OpenRouter `/api/v1/responses` usan `model`; OpenRouter requiere además `input` y espera upstream un slug `<laboratorio>/<modelo>`. Usar `model: "triage-agent"` conserva la forma estándar para clientes/SDKs. El alias no tiene por qué existir en OpenRouter: el adaptador del gateway debe resolverlo **antes** del request upstream y enviar el modelo concreto.

El riesgo previo de un selector custom top-level no tipado queda eliminado. Los campos de correlación de dominio continúan siendo extensiones documentadas del subset y deben enviarse por el mecanismo de campos extra que soporte el SDK, sin cambiar la semántica de `model`.

#### Issue rector y resultado verificable

- **Hecho — título:** `[HT-01] Definir contratos, límites del sistema y ADRs iniciales` ([GitHub #9](https://github.com/creep1ng/sre-agent/issues/9)).
- **Hecho — objetivo:** producir un lenguaje común para gateway, harness, UI y persistencia antes de implementar autenticación, autorización, routing o auditoría. El resultado observable es un contrato de frontera que permita implementar sin reinterpretación a #11, #13, #14 y a los consumidores adicionales enumerados en #9.
- **Hecho — estado actual verificado el 17 de agosto de 2026:** abierto con `status:approved`, `priority: critical`, Sprint 1, 5 SP, milestone `MVP funcional` y sin comentarios. Su parent nativo es [#1 — EP-0 Fundamentos y contratos](https://github.com/creep1ng/sre-agent/issues/1); #9 tiene diez subissues nativos, #58–#67.
- **Hecho — superficies:** plano de ejecución compatible con un subset de `POST /v1/responses`; plano de control propio para Principals, credenciales, recursos/aliases, grants y auditoría.

Los criterios de aceptación publicados en #9 y su especificación enlazada, **antes de las decisiones de esta continuación**, son:

1. Documento/OpenAPI del subset de `/v1/responses`, con ejemplos de request, response y error.
2. Schema de identidad para `Principal.kind = human | agent`, sin `organization_id` obligatorio y separado de la selección de modelo.
3. Schema de decisión `principal-action-resource-context -> allow/deny`, con `reason_code` y `policy_id`.
4. Schema de auditoría que correlacione Principal, credencial segura por ID, recurso, decisión, alias/modelo/provider y ejecución mediante `request_id` y, cuando apliquen, `incident_id`, `run_id` y `task_id`.
5. Errores normalizados para 401, 403, 404, 422 y fallos upstream 502/503.
6. Matriz explícita Git vs DB vs secretos.
7. ADR-001 a ADR-005 registrados como aceptados.
8. Evidencia de que los consumidores pueden implementar contra los contratos sin reinterpretarlos.

Fuentes: [GitHub #9](https://github.com/creep1ng/sre-agent/issues/9) y Notion, **“HT-01 — Definir contratos, límites del sistema y ADRs iniciales”**, secciones “Entregables” y “Criterios de aceptación refinados” ([página](https://app.notion.com/p/3bae4205157e81b48c1bc797fb8f61b5)).

Las decisiones del usuario conservan `model` como selector wire del alias lógico y modifican la semántica 403/404, el transporte de correlación, los campos desconocidos, el alcance del plano de control y la ubicación/versionado. GitHub/Notion deben sincronizarse en una fase autorizada donde todavía permanezcan contradicciones.

#### Precedencia de fuentes vigente

1. **Decisiones aprobadas el 14 de agosto de 2026:** Notion, **“Decisiones de gobernanza del MVP — 14 ago 2026”** ([página](https://app.notion.com/p/3bde4205157e81d8b56fc35a0b852ddc)) y **“Cambio de alcance aprobado — Principals y artefactos del harness”** ([página](https://app.notion.com/p/3bbe4205157e81b0a847d470de8c650f)).
2. **Trabajo ejecutable actual:** GitHub #9, #10, #11, #13 y #14. La página **“Proyecto TIC2”**, sección “Fuentes de verdad”, declara Notion como fuente de producto/arquitectura/gobernanza y GitHub como fuente del trabajo ejecutable ([página](https://app.notion.com/p/3aee4205157e809980b9d32575b5228d)).
3. **Diseño rector consolidado:** **“Diseño de solución — Plataforma gobernada…”**, especialmente “Decisiones de diseño aprobadas”, “Plano de ejecución”, “Auditoría y medición” y “Fuera de alcance” ([página](https://app.notion.com/p/3b4e4205157e818b83cfe9877b41f16a)).
4. **Antecedentes/Engram:** observaciones #2324 y #2330 son compatibles donde las fuentes actuales no las reemplazan, pero no crean requisitos nuevos.

#### Contrato, consumidores y dependencias

| Consumidor | Relación comprobada | Qué necesita de #9 |
| --- | --- | --- |
| [#10 — HT-02](https://github.com/creep1ng/sre-agent/issues/10) | Parent nativo #1; puede avanzar en paralelo y depende de #9 solo para convenciones mínimas | Nombres/puertos/estructura y stubs/fixtures contractuales; no consume todavía modelos de dominio implementados. |
| [#11 — HT-03](https://github.com/creep1ng/sre-agent/issues/11) | Parent nativo #1; dependencia directa de #9 | Schemas de Principal, Credential, Resource, Grant y AuditEvent para DTO/Pydantic, persistencia, migraciones y seeds. |
| [#13 — HT-04](https://github.com/creep1ng/sre-agent/issues/13) | Parent nativo #2; depende formalmente de #11 e indirectamente de #9 | `Authorization: Bearer`, `PrincipalContext` y error 401; autenticación debe quedar separada de grants/autorización. |
| [#14 — HT-05](https://github.com/creep1ng/sre-agent/issues/14) | Parent nativo #3; depende de #9, #11 y #13 | `/v1/responses`, lookup de alias, decisión allow/deny, normalización upstream y auditoría allow/deny. |
| Harness reemplazable | Consumidor externo del plano de ejecución | Solo URL base, API key del gateway, alias lógico y correlación; nunca secretos ni APIs del proveedor. |
| UI/plano de control | Consumidor futuro de API propia | Principals, credenciales, recursos/perfiles agénticos, grants y auditoría mediante endpoints definidos por #9, idempotentes y con errores normalizados; no requieren paginación en este corte. |

**Inferencia:** #10 no es un consumidor semántico fuerte, pero sus fixtures deben quedar alineados con #9 para evitar que la infraestructura cristalice contratos inventados. #11 materializa el contrato; #13 resuelve identidad; #14 prueba la composición completa.

#### Frontera mínima del plano de control ahora requerida

La decisión de alcance está cerrada; los paths exactos y la semántica de idempotencia se congelarán en proposal/spec. La exploración recomienda cubrir estas operaciones, sin paginación en el corte de #9:

| Recurso | Operaciones mínimas a contratar |
| --- | --- |
| Principals | crear, obtener, listar y desactivar/reactivar según estados admitidos; nunca convertir `kind` en rol. |
| Credenciales | emitir mostrando el secreto una sola vez, listar metadata/prefijo, revocar y rotar sin devolver el valor original. |
| Recursos/aliases de modelo | crear, obtener, listar, actualizar asignación `model alias -> concrete model/router/provider` y desactivar. |
| Grants | asignar allow directo, listar por Principal/recurso y revocar; ausencia implica deny. |
| Auditoría | obtener por ID y consultar mediante filtros de Principal, decisión, alias solicitado y correlación; no exponer secretos ni contenido sin autorización. |

**Idempotencia — recomendación pendiente de detalle:** usar una clave de idempotencia para mutaciones de creación/asignación/rotación y devolver la misma representación ante replay del mismo payload; misma clave con payload distinto debe producir conflicto normalizado. Deben definirse scope, duración y almacenamiento antes de design. GET/list son naturalmente idempotentes; revocar/desactivar debe converger al mismo estado sin duplicar eventos de negocio, conservando auditoría del intento según el contrato que se apruebe.

#### Terminología canónica

| Término | Significado vigente | No significa |
| --- | --- | --- |
| `Principal` | Identidad interna común del solicitante, con `kind = human | agent`, ID, nombre y estado. Es el sujeto de autorización. | Usuario + rol, organización, modelo LLM o harness genérico sin identidad. |
| Identidad/autenticación | API key Bearer -> Credential válida -> `PrincipalContext`. La credencial identifica/autentica; el Principal es la identidad resultante. | Autorización, OAuth/OIDC, SSO, JWT o scopes embebidos. |
| Actor/sujeto | Para acceso, el término canónico es `Principal`. “Actor” puede describir quién produce una transición o aprobación runtime, pero las fuentes no definen un segundo modelo de identidad. | Una entidad paralela a Principal. |
| `model` en el request | Campo estándar Responses que contiene el alias lógico gobernado solicitado, por ejemplo `triage-agent`. | Principal, modelo concreto o proveedor. |
| Alias lógico | Recurso estable sobre el que se autoriza `invoke`; su asignación puede cambiar sin modificar grants. | Identidad del harness o ruta upstream. |
| `ModelAlias` | **Entidad de dominio aprobada para #9:** representa el alias lógico `llm_model` estable y evita colisión con `Principal.kind=agent`. | Modelo concreto o Principal. |
| `AgentProfile` | Concepto futuro fuera de #9 si una entidad llega a agrupar instrucciones, tools u otras capacidades además del modelo. | Entidad del alcance actual. |
| Modelo concreto | Slug `<laboratorio>/<modelo-especifico>`, por ejemplo `openai/<modelo>`, enviado a OpenRouter/upstream solo después de allow. | Alias estable usado por grants. |
| Router | Integración de routing, inicialmente `openrouter`. | Provider de inferencia efectivo. |
| Inference provider | Proveedor final que ejecuta inferencia, separado del router cuando esté disponible. | Alias lógico o Principal. |
| Harness | Cliente de ejecución modular y reemplazable. | Fuente de autorización, selector directo de proveedor o custodio de secretos upstream. |
| Tenant/workspace | El MVP tiene un único workspace implícito. | `organization_id`, aislamiento multi-tenant o una dimensión tenant obligatoria en cada schema. |
| Roles/scopes | No forman parte del modelo de autorización del MVP. Las capacidades se expresan mediante `action` y grants. | RBAC, roles heredados o scopes de token/JWT. |
| Grant | Relación directa `principal-action-resource`, inicialmente `effect=allow`; ausencia de grant implica deny. | Policy engine externo o regla por organización/rol. |
| Policy input | `principal_id`, `action`, `resource_type`, `resource_id` y `context` opcional. | Código HTTP; este es solo la traducción externa de una decisión. |
| Policy output | `decision = allow | deny`, `reason_code` y referencia `policy_id`/grant cuando exista; default deny usa `no_matching_grant` + `policy_id=null`. | Respuesta del proveedor o información de routing. |
| Recurso | Entidad gobernada de tipo `llm_model`, `mcp_server`, `mcp_tool`, `skill` o `bok_collection`. | Secreto de conexión o contenido BoK necesariamente almacenado en Git. |
| Correlación de dominio | `incident_id`, `run_id` y `task_id` viajan en el body; `request_id` lo genera el servidor. Deben validarse contra el Principal/contexto y no conceden acceso. | Distributed tracing, tenancy o autorización implícita. |
| `traceparent` | Header estándar W3C para correlación técnica distribuida (`trace-id`, parent/span ID y flags) entre gateway, OpenRouter/proveedor y otros servicios. | `request_id`, `incident_id`, `run_id` o `task_id`; no transporta identidad ni permisos. |

Fuentes: Notion **“Decisiones de gobernanza…”**, secciones “Identidad y autorización”, “Sesión y límites de consumo” y “Auditoría”; **“Cambio de alcance aprobado…”**, secciones “Distinción obligatoria” y “Artefactos del flujo”; [GitHub #9](https://github.com/creep1ng/sre-agent/issues/9), [#11](https://github.com/creep1ng/sre-agent/issues/11), [#13](https://github.com/creep1ng/sre-agent/issues/13) y [#14](https://github.com/creep1ng/sre-agent/issues/14).

#### Explicación: `traceparent`

W3C Trace Context define los headers `traceparent` y `tracestate` para que una transacción conserve una traza técnica a través de servicios y vendors. `traceparent` contiene versión, `trace-id`, parent/span ID y flags de muestreo. No reemplaza los IDs del body: `incident_id` expresa la sesión de negocio, `run_id`/`task_id` la ejecución del harness y `request_id` una solicitud del gateway; `traceparent` enlaza spans técnicos entre procesos.

**Decisión aprobada:**

1. aceptar un `traceparent` válido de clientes autenticados, pero tratar sus flags como no confiables y aplicar límites de sampling;
2. generar una traza nueva cuando falte o sea inválido;
3. crear un span del gateway y propagar un `traceparent` actualizado hacia OpenRouter/proveedor y otros recursos;
4. no persistir PII/secrets en `tracestate` y poder reiniciar la traza en fronteras de confianza.

**Guardrail:** preservarlo mejora diagnóstico end-to-end y evita acoplarse a Langfuse u otro vendor; aceptarlo ciegamente permitiría forjar colisiones o forzar sampling/costo, por eso se validan formato, sampling y frontera de confianza. Fuente: [W3C Trace Context](https://www.w3.org/TR/trace-context/), secciones “Design Overview”, “Processing Model” y “Security Considerations”.

#### Default deny aprobado

`reason_code` explica **por qué** se tomó la decisión; `policy_id` identifica **qué regla/grant persistido** la produjo. Cuando no existe grant, el deny es precisamente consecuencia de no encontrar un registro: obligar un `policy_id` inventaría evidencia.

**Decisión aprobada:** usar `reason_code: "no_matching_grant"` y `policy_id: null`. El schema debe declarar `policy_id` nullable: solo referencia el grant/policy persistido que produjo la decisión cuando existe. Esto evita inventar una policy sintética y mantiene trazabilidad semánticamente honesta.

#### Bootstrap del plano de control aprobado

El problema es circular: si crear Principals, credenciales y grants exige autorización, todavía no existe un Principal autorizado para crear el primero.

**Decisión aprobada:** seed/CLI offline, determinista e idempotente, usando los mismos archivos seed exigidos por #11. Crea el primer Principal, su credencial y grants directos, sin rol ni endpoint bootstrap. La key completa se muestra una sola vez; se persisten solo hash y prefijo.

En reejecuciones, el seed no revela ni rota silenciosamente una credencial existente y converge al mismo estado de Principal/grants. La operación debe fallar de forma segura ante estado parcial incompatible y dejar evidencia sin serializar la key.

#### Taxonomía upstream aprobada

- **502 Bad Gateway:** respuesta upstream inválida, ininterpretable o no adaptable al contrato.
- **503 Service Unavailable:** OpenRouter/provider temporalmente indisponible o ninguna ruta saludable disponible.
- **504 Gateway Timeout:** el upstream no respondió dentro del timeout contractual.

El body público contiene código normalizado, mensaje seguro, `request_id` y `retryability`. Puede incluir `Retry-After` cuando exista una estimación confiable. Nunca expone body upstream, URLs internas, credenciales, stack traces ni IDs sensibles. Los clientes deben aplicar backoff a fallas retryable para evitar retry storms. Fuentes: [MDN 502](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/502), [MDN 503](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/503) y [MDN 504](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/504), basados en RFC 9110.

#### Separación obligatoria: autorización antes de routing

```text
API key -> Principal
request.model = triage-agent
  -> authorize(Principal, invoke, logical alias, context)
  -> deny: respuesta segura + auditoría; sin resolución ni tráfico upstream
  -> allow: resolver alias -> concrete model -> router=openrouter -> inference provider
  -> invocar upstream -> normalizar response -> auditar ruta efectiva
```

El `Grant` y `PolicyDecision` referencian el `ModelAlias` estable solicitado, no el modelo concreto, OpenRouter ni el provider. Por eso cambiar la asignación detrás de `triage-agent` no exige modificar grants mientras el alias permanezca igual.

**Decisión de exposición aprobada:**

- el plano de control protegido expone la asignación vigente del `ModelAlias`;
- el response estándar usa `model` para el modelo concreto efectivamente empleado;
- `Response.metadata` usa claves planas con valores string: `requested_model_alias`, `router` e `inference_provider`;
- AuditEvent registra por separado alias solicitado, modelo concreto, router (`openrouter`) e inference provider efectivo;
- `Principal`, `Grant` y `PolicyDecision` no incorporan routing;
- no se usa un objeto metadata nested incompatible.

#### Artefactos del harness y dominio de incidentes

**Hecho — alcance aprobado:** los objetos visibles de primer nivel son alerta, hipótesis, estrategia de mitigación y postmortem. El harness genera los últimos tres; la alerta proviene de fixture/sistema externo. `Incident` es contenedor/runtime record. Evidencia, decisiones tomadas, aprobaciones, impacto/severidad y timeline son registros de soporte. Anomalía es metadata de la alerta, no entidad propia. El postmortem mínimo es obligatorio para cerrar la sesión. Los decision points viven inline en `incident-response.yaml`; las decisiones ejecutadas se persisten como eventos runtime.

Fuente: Notion **“Cambio de alcance aprobado…”**, sección “Cambio 2 — Artefactos del flujo de incidentes”, y **“Mapa de artefactos de incidentes — alcance y coste”**, secciones “Regla de alcance” y “Registros de soporte” ([página](https://app.notion.com/p/3bae4205157e813f80fecfb6c1056c6a)).

**Relevancia para #9:** AuditEvent debe correlacionar recursos del gateway con sesión/run/tarea sin convertir esos registros de soporte en recursos IAM ni nuevas entidades de producto.

#### Gobernanza obligatoria y límites del MVP

**Dentro de #9:**

- subset textual, no streaming, de `/v1/responses` con `model` como alias lógico gobernado e `input` textual; tras allow, el gateway resuelve modelo concreto/router/provider;
- `ModelAlias` como entidad de dominio del alcance actual; `AgentProfile` fuera de #9;
- plano de control con endpoints/operaciones idempotentes para Principals, credenciales, ModelAliases, grants y auditoría, sin paginación en este corte;
- contratos de Principal/PrincipalContext, Resource, decisión y AuditEvent;
- default deny contractual con `reason_code="no_matching_grant"` y `policy_id=null`;
- bootstrap mediante seed/CLI offline idempotente, con key visible una sola vez y persistencia exclusiva de hash/prefijo;
- W3C Trace Context aceptado/generado/propagado con límites de sampling y fronteras de confianza;
- errores normalizados 401/403/404/422/502/503/504, con 422 para todo campo fuera del subset y sin distinguir públicamente recurso ausente de recurso no autorizado en el plano de ejecución;
- matriz Git/DB/secretos;
- ADR-001 `/v1/responses`, ADR-002 single-workspace/Principal, ADR-003 API key, ADR-004 grants directos/interfaz independiente y ADR-005 auditoría de contenido;
- prompts/inputs y respuestas completos por defecto **después** de redacción; también logs MCP, outputs de comandos/sandbox, tool calls y cualquier output libre; credenciales y secretos nunca se serializan;
- OpenRouter soportado desde el día 1 mediante su Responses API/adaptador, preservando `<laboratorio>/<modelo-especifico>` y `provider` separado;
- response `model` con modelo concreto efectivo y metadata plana string `requested_model_alias`/`router`/`inference_provider`; AuditEvent conserva las cuatro dimensiones de ruta por separado;
- contratos compartidos futuros en `/schemas`, inicialmente en `1.0.0` y evolucionados según el estándar Semantic Versioning 2.0.0;
- contrato independiente de OPA, Casbin, Keycloak, Langfuse o un proveedor LLM concreto.

**Fuera de #9/MVP inmediato:** implementación FastAPI/Pydantic, tablas, lógica real, OAuth/OIDC/SSO/JWT/Keycloak, organizaciones/multi-tenancy, roles, cuotas/presupuestos, routing multiproveedor propio, streaming, conversaciones persistentes, tool calling dentro de Responses y gobierno ejecutable de MCP/Skills/BoK. Integrar OpenRouter desde el día 1 no equivale a implementar routing multiproveedor propio: el gateway conserva un adaptador y OpenRouter puede resolver su routing internamente. El MVP global sí incorpora límites y recursos adicionales en incrementos posteriores, pero no son entregables de #9.

#### Pipeline de redacción aprobado

Todo dato libre debe pasar por redacción **antes de cualquier sink** de logs, auditoría o persistencia:

1. clasificar la fuente (`llm_input`, `llm_output`, `mcp_log`, `sandbox_output`, `tool_call`, `tool_output`, metadata libre u otra);
2. eliminar campos prohibidos estructuralmente: headers Authorization, credenciales, variables secretas y configuración upstream sensible;
3. reemplazar coincidencias exactas contra secretos conocidos cargados por la aplicación;
4. aplicar detectores configurables de patrones y formatos sensibles;
5. escanear contenido libre y producir únicamente la versión redactada;
6. persistir metadata segura del proceso: resultado, versión de política y categorías/conteos, nunca el valor original;
7. si el pipeline falla o no puede garantizar redacción, **fail closed**: descartar el contenido bruto y persistir solo metadata segura que indique el fallo.

La retención, expiración y acceso al contenido redactado siguen deliberadamente sin decidir. Versionar el schema de tool calls no vuelve seguro su contenido: tanto argumentos como outputs se redactan antes de persistir.

**Verificación de Engram #2324/#2330:**

- Harness reemplazable: ratificado por el diseño vigente.
- Python/FastAPI/Pydantic: ratificado como dirección de implementación por #10, #11 y #13, aunque #9 prohíbe implementarlos y sus contratos deben ser portables.
- Langfuse solo observabilidad: no fue reemplazado, pero tampoco fue seleccionado por las fuentes vigentes; no debe entrar como dependencia, policy engine ni fuente de verdad del contrato.
- Alcance HT-01: ratificado y refinado por #9 y las decisiones del 14 de agosto.

#### Contradicciones registradas y resolución por precedencia

| Contradicción | Resolución vigente |
| --- | --- |
| El diseño rector aún contiene `Organization`, `User`, `Role`, “Usuario, rol y contexto”, rol heredado y `organization_id` en secciones históricas. | Las decisiones aprobadas del 14 de agosto y #9–#14 las reemplazan: single-workspace, Principal y grants directos, sin roles/organizaciones. |
| El diseño rector presenta a la vez `incident-decisions.yaml` y la ubicación de decision points como abierta. | “Decisiones de gobernanza…” cierra la decisión: inline en `incident-response.yaml`; runtime decisions en DB. |
| Una matriz histórica propone deny explícito > allow > rol heredado > default deny. | Sprint 1 usa solo grants directos allow; ausencia de grant = deny. El motor reusable se difiere. |
| Un requisito no funcional/riesgo histórico sugiere no guardar contenido sensible por defecto o guardar solo metadata salvo demo. | La política vigente ordena prompts/respuestas completos por defecto, siempre tras redacción; ante fallo de redacción sobre contenido sensible se conserva solo metadata segura. |
| El diseño general deja framework backend abierto. | GitHub ejecutable #10/#13 y sus specs actuales fijan FastAPI; #11 fija DTO/Pydantic. Esto guía consumidores, pero no cambia que #9 sea contract-first y framework-agnostic. |
| Una decisión transitoria de exploración había cambiado el selector wire a `agent`. | La última decisión la reemplaza: `model` vuelve a contener el alias lógico (`triage-agent`), alineado estructuralmente con #9, OpenAI y OpenRouter. |
| #9 exige 403 sin grant y 404 para alias inexistente. | La decisión posterior prohíbe revelar existencia. Se recomienda 403 uniforme `resource_unavailable` en ejecución; la tensión debe sincronizarse en #9 antes del DoD. |

Fuente adicional de seguridad: Notion **“Política de auditoría y redacción de secretos”**, secciones “Pipeline mínimo” y “Criterios mínimos” ([página](https://app.notion.com/p/3bde4205157e810ea91df0b490bd31db)).

#### Snapshot del repositorio y la validación al cierre de exploración

- **Hecho en ese cierre:** `main` contenía un catálogo de design system en HTML/CSS/JavaScript y assets; no existía backend Python, gateway, persistencia, harness ni API de producto. `README.md` declaraba que el framework frontend no fue seleccionado.
- **Hecho en ese cierre:** no existían OpenAPI, JSON Schema, ADRs, tests de contrato, CI ni configuración de contenedores.
- **Hecho en ese cierre:** `openspec/changes/` y `openspec/specs/` existían; `openspec/specs/` estaba vacío. El usuario confirmó que había borrado `openspec/config.yaml` y autorizó reconstruirlo. Se restauró un config mínimo oficial con `schema: spec-driven`; no se reinicializó OpenSpec. Fases posteriores crearon localmente proposal, cinco delta specs, design y tasks, aún unstaged para S2–S4.
- **Hecho:** el catálogo visual conserva vocabulario anterior (`Access role`, `incident-responder`, `restricted-observer`, `service-account`) en `index.html:767-774` y `index.html:1388-1469`. Es una maqueta, no un contrato, pero puede inducir drift frente a Principal/grants.
- **Hecho:** la auditoría visual muestra request, identidad, recurso, decisión y correlación incidente/run, pero no representa reason code, alias vs modelo efectivo/provider, credential ID segura ni redacción.
- **Validación operativa en ese cierre:** OpenSpec 1.7.0 reportó raíz saludable, contexto resoluble y schema `spec-driven` válido; `openspec status` mostró proposal listo y los demás artefactos bloqueados porque todavía no se había creado ninguno. Fases posteriores crearon proposal/specs/design/tasks; aun así, el árbol aislado de S1 permanece partial y strict falla esperadamente con `Change must have at least one delta` hasta publicar S2.

#### Contrato mínimo que debe congelarse

1. **Wire LLM:** `POST /v1/responses`, JSON, `model` alias lógico + `input` string + IDs de dominio opcionales, `stream=false` y envelope de error estable. Campos adicionales al subset se rechazan con 422. El adaptador reemplaza el alias antes de OpenRouter; response `model` expone el concreto y metadata plana expone alias/router/provider ([OpenAI OpenAPI](https://github.com/openai/openai-openapi/blob/main/openapi.yaml), [OpenRouter Responses](https://openrouter.ai/docs/api_reference/responses/overview)).
2. **Domain identity:** Principal, Credential reference y PrincipalContext separados del wire OpenAI.
3. **Resource resolution:** wire `model`, dominio `ModelAlias` aprobado, modelo `<laboratorio>/<modelo-especifico>`, router, provider efectivo y secretos upstream estrictamente separados.
4. **Policy seam:** autorización sobre Principal + acción + alias lógico; solo allow habilita resolución/routing. Default deny usa `no_matching_grant` + `policy_id=null`.
5. **Audit:** evento append-only lógico con decisión, correlación, resultado y todas las clases de output pasando por el pipeline fail-closed; nunca headers Authorization ni secretos.
6. **Errors:** body público con códigos normalizados/detalles seguros, no enumeración en ejecución, 422 para campos desconocidos, 502 upstream inválido, 503 indisponible/sin ruta y 504 timeout.
7. **Control plane:** endpoints/operaciones idempotentes para Principals, credenciales, ModelAliases, grants y auditoría; sin paginación por ahora; bootstrap offline por seed/CLI.
8. **Ownership/versioning:** `/schemas` en Git, versión inicial `1.0.0` y evolución según el estándar Semantic Versioning 2.0.0; DB para estado runtime; secret store/env para secretos.

### Affected Areas

- `openspec/changes/issue-9-gateway-boundary-contracts-and-adrs/exploration.md` — fue el único artefacto creado en esta fase.
- `openspec/specs/` — estaba vacío; fases posteriores crearon delta specs bajo el change, todavía unstaged para S2/S3.
- `openspec/config.yaml` — permaneció materialmente consistente; se inspeccionó pero no se modificó en esa continuación.
- `index.html` — vocabulario visual de roles/identidades que deberá revisarse cuando exista un cambio autorizado; no se modifica aquí.
- `README.md` — documenta solo el design system, no el producto/gateway; no se modifica aquí.
- `/schemas/` — ubicación canónica aprobada para futuros OpenAPI, JSON Schemas y fixtures comunes; no se crea en exploración.
- Consumidores externos — #10, #11, #13 y #14, más harness/UI; deben validar compatibilidad sin compartir modelos internos por accidente.

### Approaches

1. **Contract-first con núcleo de dominio neutral y adaptador OpenAI-compatible** — OpenAPI/JSON Schema son la frontera; FastAPI/Pydantic implementan esos contratos después.
   - Pros: separa wire, dominio y persistencia; minimiza lock-in; permite fixtures y validación por #10/#11/#13/#14; mantiene reemplazables harness, policy engine y proveedor.
   - Cons: exige mapeos explícitos y disciplina de versionado; hay que resolver qué campos OpenAI se soportan/rechazan.
   - Effort: Medium.

2. **FastAPI/Pydantic-first como fuente del contrato** — DTOs Python generan OpenAPI y se comparten con persistencia.
   - Pros: rapidez inicial, validación y documentación automáticas, alineación directa con #10/#11/#13.
   - Cons: acopla frontera, framework y modelos internos; puede filtrar semántica de Pydantic/FastAPI (incluido 422) y provocar que cambios de DB rompan clientes. Además, implementarlo pertenece a #11/#13, no a #9.
   - Effort: Low initially / High evolution.

3. **Espejar toda Responses API y tipos OpenAI dentro del dominio** — el gateway actúa como proxy casi transparente.
   - Pros: máxima familiaridad para SDKs y menor traducción inicial.
   - Cons: superficie muy superior al Sprint 1, alto lock-in, campos no soportados ambiguos, semántica de proveedores filtrada y policy/audit subordinados al contrato de un vendor.
   - Effort: High.

### Recommendation

Adoptar **Approach 1**. Tratar OpenAI/OpenRouter Responses como adaptadores de entrada/salida, no como modelo interno. Congelar primero vocabulario e invariantes, luego wire LLM/plano de control y finalmente auditoría/correlación. Usar Pydantic/FastAPI después como implementación y pruebas de conformidad, no como autoridad exclusiva del contrato.

**Guardrails recomendados:**

- contratos bajo `/schemas`, OpenAPI `info.version: 1.0.0` inicial, JSON Schema con `$id` inicial `1.0.0` estable y evolución según el estándar Semantic Versioning 2.0.0;
- `model` como campo wire estándar con alias gobernado; `ModelAlias` es la entidad de dominio aprobada y `AgentProfile` queda fuera de #9;
- autorización sobre el alias antes de routing; adaptador OpenRouter traduce el alias permitido a modelo concreto + routing/provider sin exponer credenciales;
- allowlist explícita de campos soportados y 422 para cualquier campo fuera del subset;
- envelope de error OpenAI-compatible desacoplado del payload de decisión interno;
- adaptadores separados para alias -> modelo/provider y provider -> Response;
- IDs de dominio en body y `request_id` generado por servidor; W3C Trace Context aceptado/generado/propagado en headers separados;
- response `model` con modelo efectivo; metadata plana string `requested_model_alias`/`router`/`inference_provider`; plano de control y AuditEvent con dimensiones separadas;
- 502 para upstream inválido/no adaptable, 503 para indisponibilidad/sin ruta saludable y 504 para timeout, siempre con body normalizado seguro;
- 403 público uniforme para recurso ausente/no autorizado en ejecución, con razones internas diferenciadas solo en auditoría protegida;
- policy/audit interfaces sin dependencias de Langfuse, OPA, Casbin, Keycloak o proveedor;
- fixtures positivos/negativos versionados para evitar reinterpretación entre consumidores.

#### Cortes iniciales `stacked-to-main` — no son tareas definitivas

La estrategia es obligatoriamente `force-chained` + `stacked-to-main`. El presupuesto solicitado es 800 líneas por revisión, pero el skill de encadenado exige dividir PRs por encima de 400 líneas; por eso cada corte debe apuntar a **<=400 líneas cambiadas** y nunca superar 800 sin excepción explícita.

```text
main
  <- Slice 1: vocabulary + Principal/ModelAlias/Policy + ADR-002/003/004
  <- Slice 2: control-plane endpoints/idempotency/errors
  <- Slice 3: /v1/responses model alias + OpenRouter adapter contract + ADR-001
  <- Slice 4: AuditEvent + correlation/redaction + ADR-005 + ownership matrix
  <- Slice 5: cross-consumer fixtures/conformance for #10/#11/#13/#14
```

Cada slice debe ser integrable a `main` en ese orden, mantener juntos contrato y evidencia que lo verifica, y declarar explícitamente lo que queda para el slice siguiente. La cantidad final de cortes debe confirmarse con el diff real en fase de tareas/apply.

### Risks

- **Resolución upstream:** `triage-agent` no es un slug OpenRouter; enviarlo sin resolver después del allow fallará o seleccionará un recurso incorrecto.
- **Retries:** aunque 502/503/504 ya están definidos, `retryability` y `Retry-After` deben implementarse con backoff para evitar tormentas de reintentos.
- **Correlación no confiable:** `incident_id`/`run_id`/`task_id` en el body pueden falsificarse si no se validan contra el Principal y el estado runtime.
- **Auditoría sensible:** el alcance de redacción incluye sinks heterogéneos; cualquier camino que loguee antes del pipeline puede filtrar secretos aunque AuditEvent sea correcto.
- **P1 — idempotencia incompleta:** se aprobó exigirla, pero faltan operaciones cubiertas, clave, scope, ventana de replay y comportamiento ante payload distinto con la misma key.
- **P1 — tracing no confiable:** aunque `traceparent` está aprobado, formatos, sampling y `tracestate` entrantes deben validarse para evitar abuso/costo o propagación de información sensible.
- **P1 — lock-in de wire:** `/v1/responses` es una decisión aprobada, pero copiar toda la semántica OpenAI/OpenRouter al dominio impediría adaptar otros proveedores/harnesses.
- **P1 — drift entre fuentes/UI:** referencias residuales a organization/user/role pueden reintroducir RBAC y multi-tenancy accidentalmente.
- **P1 — acoplamiento de schemas:** reutilizar el mismo modelo para wire, dominio y DB haría que #11 condicione el contrato externo.
- **Operativo:** `openspec validate --all --strict` seguirá fallando hasta que una fase autorizada cree deltas/specs; el directorio legado vacío también aparece inválido. No debe “arreglarse” creando specs durante exploración.

#### Open questions

1. **Endpoint matrix:** concretar paths y operaciones exactas del plano de control dentro del alcance ya aprobado.
2. **Idempotencia:** definir operaciones cubiertas, formato/scope de key, ventana de replay, persistencia y conflicto ante misma key con payload distinto.
3. **Diferida:** definir retención y acceso a contenido redactado cuando el incremento de auditoría lo requiera; no inventarlos en #9.

### Ready for Proposal

**Yes — sin bloqueos P0:** la exploración quedó cerrada y contiene decisiones suficientes para redactar un proposal acotado a #9. Las preguntas restantes son detalles contractuales de endpoints/idempotencia o una política de retención deliberadamente diferida; no reabren arquitectura, seguridad ni wire compatibility. En esta fase no se avanzó a proposal, specs, design, tasks ni código; fases posteriores ya crearon esos artefactos SDD localmente.

#### Source traceability

**GitHub**

- [#9 — HT-01](https://github.com/creep1ng/sre-agent/issues/9): objetivo, entregables, criterios, negativos, alcance y dependencias.
- [#10 — HT-02](https://github.com/creep1ng/sre-agent/issues/10): infraestructura paralela y fixtures.
- [#11 — HT-03](https://github.com/creep1ng/sre-agent/issues/11): consumidor persistente de contracts.
- [#13 — HT-04](https://github.com/creep1ng/sre-agent/issues/13): API key -> PrincipalContext.
- [#14 — HT-05](https://github.com/creep1ng/sre-agent/issues/14): vertical allow/deny LLM.
- En el snapshot de exploración, #9 todavía no tenía subissues; al 17 de agosto de 2026 sigue sin comentarios y tiene diez subissues nativos, #58–#67, creados por fases posteriores.

**Notion**

- [Diseño de solución](https://app.notion.com/p/3b4e4205157e818b83cfe9877b41f16a): resumen, decisiones aprobadas, planos, arquitectura, autorización, auditoría y límites.
- [Proyecto TIC2](https://app.notion.com/p/3aee4205157e809980b9d32575b5228d): “Fuentes de verdad” y “Documentos definitivos”.
- [Decisiones de gobernanza — 14 ago 2026](https://app.notion.com/p/3bde4205157e81d8b56fc35a0b852ddc): identidad, Responses, sesión, incidentes y auditoría.
- [Cambio de alcance aprobado](https://app.notion.com/p/3bbe4205157e81b0a847d470de8c650f): Principals, aliases y artefactos del harness.
- [HT-01 refinada](https://app.notion.com/p/3bae4205157e81b48c1bc797fb8f61b5): contrato y criterios exactos.
- [Política de auditoría/redacción](https://app.notion.com/p/3bde4205157e810ea91df0b490bd31db): redacción y fail-closed.
- [Mapa de artefactos de incidentes](https://app.notion.com/p/3bae4205157e813f80fecfb6c1056c6a): objetos visibles, runtime y registros de soporte.

**Repositorio local**

- `README.md`, `index.html`, `scripts/`, `styles/`, `openspec/`, historial/status Git y ausencia de backend/tests/contracts de producto.
- `openspec/config.yaml` reconstruido con formato oficial mínimo (`schema`, `context`) y validado con OpenSpec 1.7.0.

**Estándares y proveedores consultados para esta continuación**

- [OpenRouter Responses API](https://openrouter.ai/docs/api_reference/responses/overview) y [provider routing](https://openrouter.ai/docs/guides/routing/provider-selection).
- [W3C Trace Context](https://www.w3.org/TR/trace-context/).
- [MDN 502](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/502), [MDN 503](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/503) y [MDN 504](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/504), basados en RFC 9110.
- [OpenSpec project configuration](https://github.com/Fission-AI/OpenSpec/blob/main/docs/opsx.md), más CLI local 1.7.0.
