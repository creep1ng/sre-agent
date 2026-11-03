# Demo polish, part A (2026-11-03, #870, #711, #995)

Three fixes the maintainer asked for on the morning review of 2026-11-03, captured by the
incident-console journeys (`scripts/run_incident_console_e2e.sh`, real API and database, scripted
model and Grafana MCP, no real LLM):

| Fix | Captures |
| --- | --- |
| A closed incident reads «Cerrado» / "Closed", a recovered one «Resuelto», never «en curso» | `estado-cerrado-<es\|en>-*.png` |
| The inbox decision card renders the plan's identifiers as code, no literal backticks | `titulo-bandeja-<es\|en>-*.png` |
| The postmortem and the closing summary carry the incident's title («Fallan los cobros en checkout») | `postmortem-<es-1280\|en-390>-*.png`, `cierre-<es-1280\|en-390>-*.png` |

Reproduce: `COMPOSE_PROJECT_NAME=polish-a-870 scripts/run_incident_console_e2e.sh` from this
branch; captures land in `web/incident-console/e2e/artifacts/incident-live/`.
