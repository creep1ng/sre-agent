# Issue 710: deciding by hand whether an executed mitigation worked

Captured by `web/incident-console/e2e/incident-live.spec.ts` on the stack of `scripts/run_incident_console_e2e.sh`
(real API, PostgreSQL, investigator, web proxy and deploy-executor; scripted model and Grafana MCP), at tested SHA
df66f688 (`journeys.txt`: 9 passed). Each incident's approved `deployment.restart` really ran on the journeys'
`sre-checkout` container.

| File | What it shows |
| --- | --- |
| `verificar-pregunta-es-{noche,dia}.png` | «¿El servicio se recuperó?» in amber after the restart ran, with the plan's check |
| `verificar-pregunta-en-390-{dia,noche}.png` | The same question in English at 390 px |
| `verificacion-fallida-es-{dia,noche}.png` | After «Sigue fallando»: what was not met and what follows |
| `verificacion-fallida-en-390-noche.png` | The same step in English at 390 px |
| `verificacion-fallida-pagina-es-noche.png` | The whole page back in investigation, with «Reintentar la investigación» |
| `verificacion-estable-es-noche.png`, `verificacion-estable-pagina-es-dia.png` | After «El servicio está estable»: resolved |
| `verification.json` | The journeys' record: incident ids (synthetic), the steps' texts |

Repeat: `COMPOSE_PROJECT_NAME=verify-710 SPEC="incident-live -g ejecutar" scripts/run_incident_console_e2e.sh`.
