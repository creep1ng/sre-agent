# HU-OPS-01 — Contrato pendiente: umbral de auto-triage (#15 / PR #105)

> Estado: **bloqueado por falta de contrato**. Este archivo documenta el
> bloqueo para el reviewer/owner. No implementa auto-triage.

## Comentario que lo origina

> "Cuando se genera una alerta cuya criticidad sea igual o superior al umbral
> establecido en el plano control, el triage debe iniciarse automáticamente."

## Verificación realizada (rama `feat/hu-ops-01-alert-inbox`)

| Búsqueda | Resultado |
| --- | --- |
| `threshold / umbral / auto-triage` en el repo | Sin regla: solo metadata de display (`public/fixtures/alerts.json`, `"threshold": "5%"` en 1 de 4 alertas), texto del wireframe, muestra del timeline (`index.html`) e `IntersectionObserver` (`scripts/showcase.js`) |
| `control plane` | Solo administra principals/credenciales/grants/auditoría (`schemas/releases/*/openapi/control-plane.yaml`); **cero** conceptos de severidad, triage o policy. `src/sre_agent/control/` es un boundary vacío por diseño |
| Escala de severidad | Solo existe la escala UI-local `critical \| warning \| info` (`docs/hu-ops-01-alert-inbox.md`, `severityMeta` en `alerts.js`); sin mapeo a `sev1..sev4` del gateway |
| Mecanismo de triage | Único real: evento DOM `midnight:triage-requested` (acción manual, contrato Sprint 1) |

## Contrato faltante (4 decisiones, ninguna en el repo)

1. **Valor del umbral** (¿`critical`? ¿`warning`?).
2. **Escala canónica** (¿fixture `critical|warning|info` o gateway `sev1..sev4`? ¿mapeo?).
3. **Fuente de verdad** (¿config/policy nueva del control-plane, hoy inexistente, o `decision_point` del workflow de #16?).
4. **Dueño del comportamiento** (¿UI en Sprint 1 o runtime de #26?; #15 firma triage **manual**).

## Por qué no se implementa sin contrato

Hardcodear un threshold en `alerts.js` crearía una falsa implementación: aparenta
cumplir sin responder a ningún control real, rompe el contrato reproducible de
fixtures y habría que revertirlo al llegar la policy verdadera.

## Desbloqueo propuesto

ADR o issue de policy (dueño + aceptación verificable) que fije escala, valor,
semántica de `>=` y fuente; con eso, el cambio UI es mínimo (elegibilidad +
reutilizar el emisor existente con idempotencia por `alert_id`) con sus tests.
