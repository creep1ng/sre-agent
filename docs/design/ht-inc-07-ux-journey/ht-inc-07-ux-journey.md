# HT-INC-07-UX — User journey del operador (issue #150)

- Issue: #150 · Épica EP-5 · Sprint 2 · SP 3
- Tipo: investigación + journey. **No implementa pantallas, runtime ni dominio.**
- Artefactos: `user-journey.mmd` (fuente Mermaid), `user-journey.svg` (imagen renderizada con `mermaid-cli@11 -b white`).

## Objetivo

Mapa validado de las acciones del operador desde la recepción de una alerta
hasta el seguimiento del incidente y de las automatizaciones, sustentado en
referencias verificables y en los contratos vigentes (#16, #26, #15, #23, #36).

## Alcance

Cubre: alerta → triage → declaración → board → war room → timeline →
decisiones → harness/ejecución → seguimiento → cierre. Fuera de alcance:
pantallas, componentes, runtime, máquina de estados nueva, copiar la UX de un
proveedor, convertir esto en fuente de verdad de ejecución.

## Mapa interno de contratos (fuente de verdad)

Estados #16 (`incident-response 1.0.0`): `detected → triage → {dismissed |
linked | active} → investigating → mitigating → verifying → {investigating |
resolved} → postmortem → closed`. Transiciones: 13, todas con actor
(`human|agent|system`) y `requires_approval`; `apply_mitigation` y
`close_incident` exigen aprobación humana. Decision points inline (4):
`triage_outcome` (dismiss|link|declare), `evidence_sufficiency`,
`mitigation_approval` (blocking, solo humano), `stability_check`.
`incident_id` nulo hasta `active`; `linked` usa `linked_incident_id`;
`closed` exige postmortem; severidad obligatoria desde `active`. Cada
transición escribe un timeline event; cada paso agéntico referencia la
decisión de autorización del gateway; la escalada nunca cambia estado sola
(#26 la ejecuta, #146 la persiste, #145 la expone al harness/UI).

Superficies existentes: bandeja+detalle (`#15`, mergeada en PR #105, evento
`midnight:triage-requested`, sin crear incidentes); triage descartar/asociar/
declarar (`#23`, consume `#26`); war room + timeline por `incident_id`
(`#36`, solo lectura, sin push prometido); runs/comandos/eventos del harness
(`#145`, persistencia `#146`); ingesta OTel→alerta (`#149`, mergeada).

## Fuentes y herramientas investigadas

| Herramienta | Área investigada | Evidencia / fuente |
| --- | --- | --- |
| incident.io | Lifecycle (triage→active→post-incident), triage accept/decline/merge, declare, roles, timeline tab, workflows trigger/condición/pasos, postmortems | https://docs.incident.io/incidents/lifecycle, /incidents/triaging, /incidents/declaring, /incidents/incident-roles, /post-incident/timeline, /workflows/getting-started, /post-incident/postmortems-overview |
| PagerDuty | Roles (IC, deputy, scribe, liaison), durante/después del incidente, postmortems, incident workflows con triggers condicionales e historial de ejecución por paso | https://response.pagerduty.com/during/during_an_incident/, /after/after_an_incident/, https://support.pagerduty.com/main/docs/incident-workflows |
| Rootly | Alert fields (normalización en ingesta), severidades SEV0–SEV3 single-select, built-ins vs customs, alert API (labels, urgency, deduplication) | https://docs.rootly.com/alerts/alert-fields, /configuration/severities, /configuration/built-in-fields |
| Atlassian Opsgenie | Alert ack/unack, escalations por estado, responders/on-call schedules, cierre | https://support.atlassian.com/opsgenie/docs/manage-alerts-through-their-lifecycle/, /acknowledge-and-unacknowledge-an-alert/, /how-do-escalations-work-in-opsgenie/ |

No verificado: pricing/planes específicos y detalles de war-room por videollamada
de cada vendor (no necesarios para el journey).

## Patrones: adoptar / adaptar / descartar

| Patrón | Herramientas | Decisión | Justificación y relación |
| --- | --- | --- | --- |
| Alerta → triage explícito (accept/decline/merge) | incident.io | ADAPTAR | Equivale a `triage_outcome` dismiss/link/declare de #16; #23 lo ejecuta |
| Declarar con formulario mínimo ampliable | incident.io | ADOPTAR | #23: `incident_id` + severidad/impacto inicial + evento timeline |
| Lifecycle triage→active→post-incident | incident.io | ADAPTAR | #16 ya lo modela con 11 estados; no duplicar |
| Roles visibles (lead/IC) + instrucciones | incident.io, PagerDuty | ADAPTAR | #36 muestra responsables; instrucciones de rol → brecha (sin issue) |
| War room = canal + estado compartido | incident.io, PagerDuty | ADOPTAR | #36: misma fuente persistida, sin push prometido |
| Timeline auto (cambios) + curado (pins) | incident.io | ADAPTAR | #36: eventos ordenados con actor/secuencia; pins → brecha (sin issue) |
| Workflows trigger→condición→pasos con historial por paso | incident.io, PagerDuty | ADAPTAR | #145 (contrato) + #146 (eventos); UI solo monitorea |
| Severidad single-select que enruta respuesta | Rootly, PagerDuty | ADOPTAR | #16: severidad obligatoria desde `active`; calibrar valores fuera de #150 |
| Escalación por estado no-ack/no-close | Opsgenie | DESCARTAR | Sin runtime de notificaciones en MVP; escalada #16 es bloqueo+a-humano |
| Ack = ownership que detiene escalación | Opsgenie | ADAPTAR | Parcial: `triaged`/`acknowledged` existe en alertas; ownership formal → brecha |
| Postmortem obligatorio, borrador asistido + validación humana | incident.io, PagerDuty | ADOPTAR | #16: `closed` exige postmortem; borrador agente + validación humana |
| Métricas excluyen triage declinado | incident.io | DESCARTAR | Sin motor de métricas en MVP |
| Board de incidentes | mencionado en #150 | BRECHA | Sin issue ejecutable (ver § Brechas) |
| Follow-ups post-cierre | incident.io, PagerDuty | BRECHA | Sin issue ejecutable |

## User journey (15 etapas)

| # | Etapa | Actor | Pantalla | Estado dominio | Automatización | Resultado visible |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Recepción de alerta | sistema | — | `detected` | #149 adapta señal→alerta | alerta con servicio/severidad/timestamp |
| 2 | Identificar señal | humano | Bandeja #15 | `detected` | orden por severidad/hora | lista + contador |
| 3 | Revisar detalle | humano | Detalle #15 | `detected` | — | contexto + origen como metadata |
| 4 | Iniciar triage | humano | Botón #15 | → `triage` | evento `midnight:triage-requested` | feedback `ma-alert`, sin incidente creado |
| 5 | Decidir | humano | Triage #23 | `triage_outcome` | — | dismiss \| link \| declare |
| 6 | Entrada al incidente | humano+sistema | Triage #23 | `active` (`dismissed`/`linked` terminales) | validación #26 | `incident_id` + severidad + evento |
| 7 | Board | humano | Board (brecha) | `active`+ | — | estado agregado |
| 8 | War room | humano | War room #36 | snapshot persistido | refresco documentado (no push) | mismo estado en 2 navegadores |
| 9 | Timeline | humano | Timeline #36 | eventos ordenados | paginación sin duplicados | actor/secuencia/fecha/tipo |
| 10 | Investigar | humano+agente | War room + monitor | `investigating` | run #145, evidencia `trusted:false` | hipótesis con evidencia citada |
| 11 | Decidir mitigación | humano+agente | Monitor #145 | `evidence_sufficiency` | comandos acotados | propuesta con riesgo y verificación |
| 12 | Aprobar y aplicar | humano (bloqueante) | Monitor #145 | `mitigating→verifying` | solo simulado/humano | approval + evento |
| 13 | Verificar | humano+agente | Timeline | `stability_check` | evidencia fresca | estable→`resolved`, si no→`investigating` |
| 14 | Postmortem y cierre | humano+agente | Timeline | `postmortem→closed` | borrador desde timeline | postmortem declarado, sesión cerrada |
| 15 | Seguimiento posterior | humano | (brecha) | `closed` | — | follow-ups (sin issue) |

## Inventario de pantallas y acciones (resumen)

P-01 Bandeja (humano: elegir; auto: ordenar/listar; #15). P-02 Detalle
(humano: revisar, iniciar triage; #15). P-03 Triage (humano: descartar con
razón / asociar a elegible / declarar; decisión `triage_outcome`; #23, dominio
#26 valida). P-04 Board (humano: priorizar; brecha, lee `active`+). P-05 War
room (humano: coordinar/asignar; #36 lectura, #26 confirma cambios). P-06
Timeline (humano: reconstruir/decidir; auto: registrar cada transición; #36).
P-07 Monitor harness (humano: iniciar run, enviar comando, aprobar; auto:
ejecutar pasos, emitir eventos, snapshot; #145/#146; UI jamás ejecuta ni
transiciona local — CA6 de #36). En todos: la UI es interfaz; el dominio
(#26) conserva estado y valida.

## Actores y responsabilidades

Operador: percibir, decidir, aprobar, coordinar, cerrar. UI: mostrar,
capturar intención, pedir confirmación, reflejar estado versionado. Dominio/
runtime (#26 sobre #16): validar transiciones, exigir aprobaciones, emitir
eventos/timeline, correlación gateway. Harness (#145): ejecutar pasos
gobernados, reportar progreso/resultado/fallo; persistencia (#146).

## Decisiones y estados

Únicas decisiones válidas: los 4 decision points de #16 ejecutados por #26.
La UI propone (agente puede proponer salvo `mitigation_approval`) y el humano
dispone o aprueba; el dominio decide la transición. Sin estados ni
transiciones fuera de `incident-response 1.0.0`.

## Mapeo a issues

#15: etapas 2–4. #23: 5–6. #16: 1,5–6,9–14 (contrato). #26: 6,9–14
(ejecución). #36: 8–9 (+7 parcial). #149: 1. #145/#146: 10–12 (contrato/
persistencia; runtime #26 los consume). Brechas sin issue: Board (7),
instrucciones de rol, pins de timeline, ownership formal de ack, follow-ups
(15). Discrepancia documentada: escala de severidad del fixture #15
(`critical|warning|info`) vs `sev1..sev4` de #16 — sin mapeo contractual;
cada contrato rige en su alcance hasta que una policy lo defina (ver
`threshold-contract-pending.md` en `main`).

## Dependencias y riesgos

#36 DoR pendiente (mecanismo de refresco, campos de actor) — el journey no
promete push. #145/#146/#26 abiertos — monitor y runtime son contrato, no
conducta. Riesgo: tratar este doc como spec ejecutable; no lo es.

## Artefactos

Fuente: `docs/design/ht-inc-07-ux-journey/user-journey.mmd` (diagrama
`userJourney`, subgraphs operador/UI/dominio/harness, humano vs automático por
grupo y etiqueta, no solo color). Imagen: `user-journey.svg` generada con
`npx @mermaid-js/mermaid-cli@11 -i user-journey.mmd -o user-journey.svg
-b white`. Convención seguida: `docs/design/<slug>/` como `ht-ctrl-02`.
