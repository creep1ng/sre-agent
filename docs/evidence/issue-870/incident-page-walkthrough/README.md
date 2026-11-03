# The incident page after the maintainer's walkthrough (2026-11-02, #870)

The maintainer read a real incident (`checkout`, fault `paymentUnreachable`) on the EC2 OTel demo
and found seven problems on `/app/incidentes/:id`. These captures are the same page, before and
after, on the stack of `compose.incident-console-e2e.yaml`: the API, database, investigator and web
proxy are real; the model and Grafana MCP are scripted (`scripts/incident_console_upstreams.py`).
The alert carries the walkthrough's real Grafana annotations. The scripted hypothesis is as long as
the real one, and the scripted MCP returns a `span_name` vector and whole log documents, cut at
8000 characters as in a real run. No real LLM and no EC2 were used.

| Walkthrough comment | Before | After |
| --- | --- | --- |
| 1. The title is the whole Grafana summary at 54 px | `antes/` | «Errores en checkout (19 % de spans, umbral 5 %)»; the summary sits behind «Alerta de Grafana» |
| 2. The hypothesis is one 30 px display paragraph | `antes/` | Causa / Mecanismo / La refutaría at body size; cited evidence listed under it |
| 3. The stages have no dates | `antes/` | Each reached stage shows its time, with the full date on hover |
| 4. The query leaves its block and shows no result | `antes/` | The query wraps; the vector is a table, the logs are hits and lines, raw behind a disclosure |
| 5. The timeline's hypothesis is one paragraph | `antes/` | The cause is shown and the rest folds |
| 6. Severity has no colour | `antes/` | A pill on a red-to-dim scale, never amber; contrast 9.9 (night) and 6.1 (day) |
| 7. A bare «22:16» clock | `antes/` | «Declarado 22:07 · Actualizado 22:16» |

Files: `antes|despues/pagina-<es|en>-<1280|390>-<noche|dia>.png` (full page; quantized to 256
colours), `verification.json` (the journeys' record, including measured overflow and severity
contrast at each width), `journeys.txt` (the runs).

The "before" captures come from the base the work started on (`origin/t3/870-catalog-journeys`, 19ea1b9f, since merged into main)
with the same alert and the same scripted upstreams, written in the plain style the prompt used
then. Its capture spec was a throwaway and is not committed.

## Reproduce

```bash
git checkout t3/870-page-4-evidence
COMPOSE_PROJECT_NAME=incident-page-870 scripts/run_incident_console_e2e.sh
# Only the page journey:
COMPOSE_PROJECT_NAME=incident-page-870 SPEC="incident-live -g título" scripts/run_incident_console_e2e.sh
```

The script runs everything through `docker compose` and tears the project down on exit. Captures
land in `web/incident-console/e2e/artifacts/incident-live/`.
