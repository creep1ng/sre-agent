# Mario: revisión, Grants y guion de pruebas para la demo del lunes 19

Demo: lunes 2026-10-19 a las 17:00 (Bogotá). Pruebas humanas E2E: desde el domingo 2026-10-18.
Tres tareas: una revisión humana, un arreglo pequeño y el guion de pruebas.

## T1, viernes 17 y sábado hasta mediodía: revisión humana de la consola (#487)

PRs: #645, #646, #647 y #648, en ese orden de apilado. Ricardo es el autor, así que la
aceptación humana tiene que ser tuya.

Pasos:

1. Worktree desde `feat/ht-web-shell-review-feedback` y `python scripts/setup_sre.py`.
2. Recorre con tus propios ojos: entrada en `/`, Alertas, Triage declarando una alerta,
   war room, Decisiones, Postmortem.
3. Cambio de plano Operaciones/Administración con `admin-human`.
4. Identidad restringida: `restricted-harness` no ve datos protegidos.
5. Recarga, enlace directo y Back/Forward conservan incidente y run.
6. La key no aparece en URL, historial ni DOM.
7. Contrasta cada CA1 a CA8 del issue #487.

Resultado verificable: un comentario por PR con SHA probado, tabla CA / observado / veredicto y
capturas tuyas, no las del autor. Si hay hallazgos, pasos para reproducir. Con eso Ricardo
aprueba la excepción de tamaño y mergea el sábado.

## T2, sábado: la UI de Grants no deja crear un operador de triage

`public/admin/grants.js` línea 57 solo ofrece `run.*` para `incident_workflow`. El backend, en
`src/sre_agent/control/service.py` (`GRANT_ADMITTED_ACTIONS`), admite además `alert.read`,
`alert.triage`, `alert.dismiss`, `alert.associate` e `incident.declare`. Actualiza el espejo
y `tests/browser/grants.spec.js`.

Resultado verificable: desde Grants, `admin-human` crea un grant `alert.triage` sobre
`incident_workflow/incident-response` para un principal nuevo, y ese principal abre triage con
200 donde antes recibía 403. Captura y PR de menos de 100 líneas, `Refs #21`.

## T3, sábado tarde: guion de pruebas humanas y runbook de demo (#49, #47)

Documento `docs/demo-runbook.md` con:

- Preparación exacta: `demo_env.py up`, `fail`, `reset`, `setup_sre.py`, flag de LLM pagado.
  Sin valores de claves.
- Identidades y qué puede cada una: `admin-human`, `demo-human`, `incident-harness`,
  `restricted-harness`.
- Recorrido paso a paso con URL o comando, resultado esperado y cómo verificarlo con un `GET`
  autoritativo.
- Cómo resetear entre evaluadores.
- Plantilla de fallo: paso, esperado, observado, SHA, captura.
- Plan del domingo: tú, Daniel y Camilo como evaluadores (#49 exige tres), horarios y quién
  anota.

Resultado verificable: Ricardo ejecuta el runbook el sábado en la noche sin preguntarte nada.
El domingo en la noche #49 tiene tasa de éxito por evaluador y lista de fallos críticos.
