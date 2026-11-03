# Issue 711: the model writes the postmortem draft, the record is its fallback

Captured by `web/incident-console/e2e/incident-live.spec.ts` on the stack of `scripts/run_incident_console_e2e.sh`
(real API, gateway, PostgreSQL, investigator, web proxy and deploy-executor; the model provider and Grafana MCP are
scripted, each reply 2 s late), at tested SHA 3a8e13af (`journeys.txt`: 12 passed).

| File | What it shows |
| --- | --- |
| `postmortem-es-1280-{noche,dia}.png`, `postmortem-en-390-dia.png` | The model's draft, «Borrador del agente»: its four sections, the record's timeline |
| `postmortem-registro-es-{noche,dia}.png`, `postmortem-registro-en-390-dia.png` | The model answered non-JSON (`[e2e:sin-borrador]`): the record's draft, «Borrador desde el registro» |
| `cierre-pagina-es-dia.png` | The incident closed from the model's draft with «Aprobar y cerrar» |
| `verification.json` | `draft` / `fallbackDraft`: seconds from `resolved` to the stored draft (server timestamps) and its author |

The 390 px element captures include the page's sticky mobile header where it overlaps the element.

Repeat: `COMPOSE_PROJECT_NAME=pm-model-711 SPEC="incident-live -g estable|borrador" scripts/run_incident_console_e2e.sh`.
