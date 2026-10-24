# Camilo: backend y harness para la demo del lunes 19

Demo: lunes 2026-10-19 a las 17:00 (Bogotá). Pruebas humanas E2E: desde el domingo 2026-10-18.
Base de trabajo: `origin/main` (aa789d9 al 2026-10-16). Hoy el flujo HTTP llega hasta `verifying`
y nadie ha corrido una investigación con proveedor real sobre el main actual.

Tres tareas en orden. Cada una tiene su resultado verificable; sin ese resultado la tarea no cuenta.

## T1, viernes 17: investigación real sobre main actual

Checkout limpio de `main`. En tu `.env` ignorado pon `OPENROUTER_API_KEY` y `SRE_ENABLE_PAID_LLM=1`.
Luego, en este orden:

```sh
python scripts/demo_env.py up && python scripts/demo_env.py verify
python scripts/demo_env.py fail      # esperar al menos 150 s antes de investigar
python scripts/setup_sre.py
```

Declara `alert-payment-002` desde la UI de triage con `demo-human` y toma el `incident_id`.
Inicia la corrida con la misma identidad:

```sh
curl -sS -X POST "$API/v1/incidents/$INC/runs" \
  -H "Authorization: Bearer $DEMO_HUMAN_API_KEY" \
  -H "Idempotency-Key: demo-inv-$INC" \
  -H "Content-Type: application/json" \
  -d '{"workflow_version":"1.0.0","objective":"investigate"}'
```

Resultado verificable:

- `GET /v1/incidents/{id}/runs/{run_id}` devuelve `status` `completed` o `awaiting_human`;
  el incidente queda en `investigating` o `mitigating`.
- `GET .../runs/{run_id}/events` contiene al menos un evento `evidence` producido por
  `query_prometheus` o `query_elasticsearch` con procedencia MCP real, y un `state_change`
  `continue_investigation` o `propose_mitigation` con `request_ids`.
- `audit_events` tiene filas correlacionadas por `request_id`, sin prompts ni cuerpos.
- `GET /v1/usage/requests?incident_id=…` muestra el consumo de la corrida.

Entrega: JSON sanitizado de estado, eventos y consumo; SHA; comandos exactos; resultado
observado. Va en #390 rebasada sobre main, con `Tested SHA` igual al head de la PR.
Si falla, reporta el `failure_diagnostic` tal cual; no lo arregles en silencio.

## T2, sábado 18 hasta las 14:00: verificación y cierre por HTTP

Hoy el enum de `agent/schemas/run-command.schema.yaml` no incluye `verification_passed`,
`verification_failed` ni `close_incident`, aunque las transiciones existen en
`agent/workflows/incident-response.yaml`. Alcance:

- Ampliar el contrato con la versión que Ricardo defina.
- `COMMAND_TRANSITIONS` en `src/sre_agent/incident/commands.py`.
- Autorización en `src/sre_agent/gateway/runs.py`: verificación con `run.command`;
  cierre con `run.approve` y aprobación explícita (`requires_approval: true` en el YAML).
- Respetar los guards existentes en `src/sre_agent/incident/runtime.py` líneas 517 a 531:
  evidencia y `mitigation_strategy.verification_check` para verificar; `postmortem_id`
  con prefijo `pm_` para cerrar.
- Primero la lista de fallos, después la prueba HTTP real contra PostgreSQL al estilo de
  `tests/test_incident_investigator_http.py`. Sin unit tests escritos después del código.

Resultado verificable con `curl` sobre un stack de `setup_sre.py`:

- `verification_passed` pasa de `verifying` a `resolved`.
- `verification_failed` vuelve a `investigating`.
- `close_incident` sin postmortem responde con el error de precondición y el estado no cambia.
- `close_incident` con postmortem y aprobación cierra el incidente.
- Replay con la misma `Idempotency-Key` no duplica eventos.
- Versión obsoleta del incidente responde 409.

PR menor de 400 líneas, `Refs #41 #43`, con los campos de la política de evidencia completos.

## T3, sábado tarde y domingo: postmortem mínimo (recorte de #335)

Un artefacto `pm_…` persistido por comando o ruta humana con los campos mínimos de #43 CA2:
resumen, impacto, cronología referenciada, hipótesis con grado de certeza, estrategia,
acciones realmente realizadas, verificación y pendientes, con versión. Lectura con proyección
allow-listed. El guard de cierre ya comprueba el `postmortem_id`.

El borrador generado por LLM queda como extra, solo si T1 y T2 están cerradas.

Resultado verificable:

- El artefacto sobrevive a reiniciar la API; `GET` devuelve el mismo id y versión.
- Editar con versión obsoleta responde 409.
- Una identidad con `run.read` pero sin permiso de contenido no recibe fragmentos.
- Cerrar solo funciona con artefacto presente.

## Coordinación

- Ricardo mergea #649 y luego #650 el viernes; rebasa #650 cuando entre #649.
- Daniel consume tu contrato de T2 desde el sábado a las 14:00; publícalo aunque la PR no
  esté cerrada.
- La cadena de #486 (#583, #585, #586, #641, #642, #643) queda para después de la demo.
- Domingo: valida que tu corrida real de T1 se ve en la war room de Daniel.
