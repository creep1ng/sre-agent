# Issue 711: the agent's postmortem draft, «Aprobar y cerrar» and the closing summary

Captured by `web/incident-console/e2e/incident-live.spec.ts` on the stack of `scripts/run_incident_console_e2e.sh`
(real API, PostgreSQL, investigator, web proxy and deploy-executor; scripted model and Grafana MCP), at the top of
the stack, tested SHA 55ba7430 (`journeys.txt`: 10 passed). The incident was resolved with «El servicio está estable»;
the API opened its postmortem and wrote the draft `draft.seconds` after the resolution, as the server stamped both
(`verification.json`).

| File | What it shows |
| --- | --- |
| `postmortem-es-1280-{noche,dia}.png`, `postmortem-en-1280-{dia,noche}.png` | The read-only draft in its sections, «Aprobar y cerrar» in amber |
| `postmortem-es-390-dia.png`, `postmortem-en-390-noche.png` | The same at 390 px |
| `cierre-es-1280-{dia,noche}.png`, `cierre-en-390-noche.png` | «Resumen de cierre» after the close: five milestones with their times |
| `cierre-pagina-es-dia.png` | The closed incident's whole page: stepper with every stage's time, summary, timeline, approved draft |
| `verification.json` | The journeys' record: `draft` (seconds, cited moments, author), `closing` (the summary's text) |

The 390 px element captures include the page's sticky mobile header where it overlaps the element.

Repeat: `COMPOSE_PROJECT_NAME=close-711 scripts/run_incident_console_e2e.sh`.
