# HT-INC-08 — OTel demo → alerta canónica (issue #149)

Adapter puro en `src/sre_agent/incident/signals.py` (sin runtime, sin DB).
Contrato de mapeo versionado: `agent/signals/otel-mapping.yaml` (1.0.0).

## Patrón adoptado (Rootly / incident.io)

* **Rootly Alert Fields**: el payload crudo se normaliza en la capa de ingesta
  mediante un mapeo explícito por fuente. Built-ins primero (`severity`,
  `service`, `summary`); el resto es metadata o se descarta.
* **incident.io**: la ingesta (`detected`) es distinta de la declaración. Este
  adapter nunca inventa `incident_id`; el triage (#23) decide
  descartar/asociar/declarar.

## Tabla de mapeo (subconjunto demo soportado)

| OTel demo | Alerta canónica 1.0.0 |
| --- | --- |
| `resource.attributes[service.name]` | `alert.service` (requerido) |
| `severity_hint` (`sev1..sev4`) | `alert.severity` (requerido, sin inferencia) |
| `span.timestamp` (RFC 3339) | `alert.observed_at` + `origin.observed_at` |
| `span.name` | `alert.summary` (prefijo) + `origin.signal` |
| `span.status.message` | `origin.condition` (fallback `otel span error`) |
| constante `opentelemetry-demo` | `alert.source`, `origin.detector` |
| constante `new` | `alert.status` |

Correlación (`trace_id`, `span_id`, `resource` permitida) viaja en un envelope
versionado (`otel-correlation 1.0.0`) **fuera** de `alert.origin`, que permanece
cerrado por `incident-state 1.0.0` (auditoría C03/C04). Sin entidad Anomalía.
Solo sobreviven valores escalares de resource; un objeto/arreglo anidado bajo
una clave permitida se descarta completo.

Identidad e idempotencia: `alert_id =
alt-{slug}-{sha256(trace_id:span_id:service:span.name)[:12]}`. Usa los
identificadores completos, nunca el prefijo de `trace_id`: reintentos de la
misma señal producen el mismo id; señales distintas divergen.

Temporal: se exige RFC 3339 completo con zona explícita. Fecha sola, timestamp
sin zona y valores que desbordan la normalización se rechazan (`invalid_format`);
nunca se inventa hora ni zona.

## Política de descarte

Claves desconocidas o sensibles (`password|secret|token|authorization|cookie|
api_key|set-cookie`, incluso anidadas) se listan en `dropped` y jamás entran al
dominio ni a la correlación.

## Errores tipados (`SignalRejected`)

`missing_field` | `invalid_format` | `unsupported_severity`. Deterministas y
observables (`"{code}: {detail}"`).

## Cómo ejecutar

```bash
python scripts/validate_incident_contracts.py
python scripts/adapt_otel_signal.py
pytest tests/test_otel_signal_adapter.py -q
```

## Compatibilidad

No muta `incident-state 1.0.0` ni `incident-response 1.0.0`. El fixture
`agent/fixtures/incidents/otel-payment-failure/adapted-signal-state.yaml` valida
como estado `detected` con `incident_id: null` y alimenta el triage de #23. La
persistencia durable (`alert_id` antes de `incident_id`) la define #145/#146.
