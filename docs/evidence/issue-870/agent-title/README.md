# The investigator writes the incident's short title (2026-11-03, #870)

Maintainer decision of 2026-11-03: the projection policy lets one field of model output through,
`title`, so a person recognises the incident as «Fallan los cobros en checkout» instead of the
alert's metric text. Its exception and its rules live in `agent/api/projection-policy.v1.yaml`
(`model_output_exception`) and `src/sre_agent/incident/title.py`.

Real API, PostgreSQL, investigator, web proxy and deploy-executor; scripted model and Grafana MCP
(`scripts/incident_console_upstreams.py`); fake Telegram Bot API (`tests/fake_telegram.py`).
No real LLM, no EC2.

| What | Capture |
| --- | --- |
| The page names the incident with the investigator's title (ES 1280 night, EN 390 day) | `pagina-es-1280-noche.png`, `pagina-en-390-dia.png` |
| The inbox's decision card shows the same title (ES, EN) | `titulo-bandeja-<es\|en>-<noche\|dia>.png` |
| Before any hypothesis (a run that failed), the alert's words; the retry's hypothesis names it | `titulo-respaldo-es-*.png`, `titulo-agente-es-*.png` |
| A title on two lines and over 60 characters is dropped: page, detail and list fall back | `titulo-invalido-<es\|en>-*.png` |
| Telegram's decision message carries the title; the journey with no title shows the alert's | `telegram-transcript.png`, `telegram-decision-heads.json` |

`verification.json` is the console journeys' record; `journeys.txt` lists both runs.

## Reproduce

```bash
git checkout t3/870-agent-title
COMPOSE_PROJECT_NAME=agent-title-870 scripts/run_incident_console_e2e.sh
COMPOSE_PROJECT_NAME=agent-title-870-tg scripts/run_telegram_e2e.sh
```

Both scripts only drive `docker compose` and remove their project on exit.
