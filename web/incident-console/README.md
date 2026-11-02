# Incident console (`/app`)

The new operator console for the incident journey: alert → declared incident → agent
investigation → human decision → recovery → postmortem → closure. It replaces the current
console's incident pages step by step; the current console keeps its routes (`/`) meanwhile.
It answers the UX review of the current console (thread "Simplificar UX de alertas y triage",
2026-10-19) and the known gaps of the 2026-10-19 demo runbook (#700, EP-8 #732).

The inbox runs against the real API. `GET /v1/alerts` through the same-origin `/api` proxy feeds
the list, every 15 s, with service, severity, local time and triage state. The remaining screens
still use the **mock mode** simulator, which follows `agent/workflows/incident-response.yaml` and
plays the agent with timed steps. The content (evidence, hypothesis, mitigation, postmortem)
mirrors the OpenTelemetry demo store and its `paymentUnreachable` flag, written at the quality the
agent should reach. It is not what the current agent produces. Each remaining screen is connected
to the API in its own follow-up PR, using the map below.

## Live inbox

- **Credential.** The key lives only in memory for the tab. Paste it in **Conectar API** (account
  menu, bottom of the sidebar, or the inbox state card). It is never written to the URL, cookies,
  Web Storage, logs or telemetry, and a reload clears it. The dialog is the only way in: there is
  no fixture or test hook that injects a token.
- **Polling.** The first request runs when the key is connected; the next one starts 15 s after
  each answer finishes. A 503 `Retry-After` is honored.
- **Failures.** A transient failure keeps the last list and shows a retry banner. An invalid key
  (401) clears the list and stops polling until another key is connected; a missing `alert.read`
  grant (403) clears the list but keeps polling, because grants can change while the tab is open.
- **Triage.** Cards show `Nueva`, `En triage`, `Declarada`, `Vinculada` or `Descartada`. Only
  `new` and `triaging` count toward the headline; the card actions belong to the triage story.
- **Mock mode.** Append `?mock` once per tab to run the simulator instead (`/app/?mock`). The flag
  is stored in `sessionStorage` and the query is removed. The two modes share the same UI shell.

## Run it

From the repository root, with the usual `.env` (see `.env.example`):

```sh
docker compose up -d --build --wait
# new console:     http://127.0.0.1:8080/app/
# current console: http://127.0.0.1:8080/
```

The `incident-console` service builds this folder (`Dockerfile`, target `serve`) and the `web`
proxy forwards `/app/` to it (`docker/nginx.conf.template`). The proxy resolves the console per
request, so `/` and `/api/` keep working when the console container is absent.

- Browser journeys (Playwright 1.63, pinned image), through the proxy:
  `HOST_UID=$(id -u) HOST_GID=$(id -g) docker compose --profile e2e run --build --rm incident-console-e2e`.
  Screenshots (`screens/`, `design/`, `proxy/`, `live/`), videos and the HTML report land in
  `web/incident-console/e2e/artifacts/`. The journeys also check that no screen shows protocol
  details (`open_triage`, `run_`, `evt_`, «Versión esperada», …).
- The suite has two modes. The design and journey specs opt into the simulator with `?mock`; the
  live specs answer `GET /api/v1/alerts` with Playwright routes or, when `LIVE_INBOX=1` and
  `DEMO_HUMAN_API_KEY` are set, connect the real key to the stack started by `setup_sre.py` and
  wait for the injected OTel failure. Authentication specs disable video and traces.
- Demo controls live in the account menu (bottom of the sidebar) → **Escenario de demostración**,
  only in mock mode: simulate a new alert, make the agent fail, or reset the scenario. State
  persists in `localStorage`, so reloads keep the incident where it was.

## Design decisions

Chosen by the maintainer on 2026-10-19 among live alternatives:

| Decision | Choice |
|---|---|
| Service filter (inbox) | One menu button beside the headline, each service with its worst severity and count. |
| Story (incident) | An integrated column beside the incident, one hairline apart, no card. |
| Findings and decisions | Inside the story: findings, the hypothesis and proposals unfold in place. |
| Closure summary | Hero time to resolve plus a phase bar (ordinal ramp) with its table twin; no stat cards or lists. |
| Agent identity | Nocturno mist (`--mist`): "Agente" in that color, "Tú" in ink, "Sistema" in gray. |

## The journey in 7 clicks

| # | Where | Click | What happens |
|---|---|---|---|
| 1 | Inbox card | Declarar incidente | Dialog prefilled from the alert: severity preselected, customer impact suggested. |
| 2 | Dialog | Declarar e investigar | Incident page opens; the agent starts investigating on its own. |
| 3 | Proposal card | Aprobar mitigación | Hypothesis, evidence and steps are in the same card as the decision. |
| 4 | Recovery card | Ya la apliqué | The agent watches the signal and says when it is stable. |
| 5 | Recovery card | El servicio está estable | Resolved; the agent drafts the postmortem on its own. |
| 6 | Postmortem card | Aprobar y cerrar incidente | Inline-editable document; approval and closure in one step. |
| 7 | Confirmation | Aprobar y cerrar | Closed, with time to detect, mitigate and resolve. |

The current console needs about 24 clicks across five pages (Alertas, Triage, War room,
Decisiones, Postmortem) for the same outcome, two of them only to start agent work.

## Design principles

1. **One incident, one page.** Triage, war room, decisions and postmortem become phases of a
   single page with a stepper. The incident list replaces the run picker.
2. **The page always answers three questions:** what is happening, what the agent is doing,
   and what you need to do now. The "now" card holds the only primary action.
3. **The agent starts on its own** (investigation after declaring, postmortem after resolving)
   and narrates real steps in plain Spanish. It never shows a fake plan.
4. **Evidence as findings:** a sentence plus what it means for the hypothesis. The query stays one
   click away under "Ver la consulta".
5. **Protocol stays out of the way:** no ids, versions, operation codes, snapshots or runs.
   They live in "⋯ → Detalles técnicos" for audit and support.
6. **Failures explain the cause and the fix,** and recover in the same incident.
7. **Brand tokens** from `palette.css` / `styles/tokens.css`, with Offside, Spline Sans and
   Monaspace Neon, in light and dark themes.

## UX review findings and how the new console handles them

| Finding (current console) | New console |
|---|---|
| Eyebrows, fixture/developer notes, "En vivo" badge, empty detail placeholder | Removed; the inbox header says what needs attention and when it was updated. |
| "Iniciar triage" at the bottom of a long detail panel | Declare, dismiss and link sit on each alert card. "Qué detectamos" opens inline. |
| Alert ID, "Versión esperada", `open_triage`/`triage_*` operation picker | Hidden. The card's button is the operation, and the version travels underneath. |
| Re-typing alert context, RFC 3339 time, "Confirmo…" checkbox | Read-only summary, local time, no checkbox. |
| Motivo vs. impacto | Impact only when declaring ("¿Qué notan tus clientes?"), reason only when dismissing or rejecting. |
| "Resultado" panel after declaring | Goes straight to the incident. |
| "Iniciar investigación" button; nothing shown while there is no hypothesis | Starts automatically; live step list with a timer and an estimated duration. |
| Run ids, "Snapshot v1 (seq 0)", "Contexto autoritativo", backend wording | A status pill ("Esperando tu decisión") and the stepper. Ids are in "Detalles técnicos". |
| Evidence as raw queries, "Solicitud MCP: uuid" | Findings with verdicts ("Respalda la hipótesis", "No encontró nada"). |
| Mitigation steps in English, small; actions in a separate list | Spanish, numbered, large steps; the decision buttons are inside the proposal card. |
| Postmortem full of `evt_…` ids | Narrative sections, local times, editable inline, Markdown export. |
| Dispatch failure without a reason (#692); restart needs a new incident | The failure card says why and how to fix it; "Ya lo corregí, reintentar" keeps the same incident. |
| Inbox card stays "Nueva" after declaring (#693) | The alert becomes the incident card with its live status. |
| Paragraph-long titles (#694) | Short title plus a one-line summary. |

## Button → API call

Each UI action maps to calls the API already has (see `public/api/client.js` for the current
console's client). The backend gaps are listed after the table.

| Screen · button | Real calls |
|---|---|
| Bandeja (read) | `GET /v1/alerts` |
| Alert card · Qué detectamos | `GET /v1/alerts/{id}/triage/context` |
| Alert card · Declarar incidente → Declarar e investigar | `POST /v1/alerts/{id}/triage/commands` (`open_triage`, then `triage_declare`), then `POST /v1/incidents/{id}/runs` (`objective: investigate`) |
| Alert card · Descartar | Triage commands `open_triage`, then `triage_dismiss` with the reason |
| Alert card · Vincular | `GET /v1/alerts/{id}/triage/eligible-incidents`, then `triage_link` |
| Incident page (read) | `GET /v1/incidents/{id}`, `GET …/snapshot`, `GET …/timeline` |
| Investigation card (live steps) | `GET /v1/incidents/{id}/runs/{run}` and `GET …/runs/{run}/events` |
| Agent failure · Ya lo corregí, reintentar | `POST /v1/incidents/{id}/runs` (`objective: investigate`) |
| Proposal · Aprobar mitigación / Pedir cambios / Rechazar | `POST …/runs/{run}/commands`: `approve_mitigation`, `request_changes`, `reject_mitigation` |
| Recovery · El servicio está estable / Sigue fallando | `POST …/runs/{run}/commands`: `verification_passed` / `verification_failed` |
| Postmortem draft (automatic) | `POST /v1/incidents/{id}/runs` (`objective: postmortem`) |
| Postmortem · edit inline | `GET` / `PUT /v1/incidents/{id}/postmortem` |
| Postmortem · Aprobar y cerrar incidente | `PUT …/postmortem`, `POST …/postmortem/reviews` (`approved`), then `close_incident` |
| ⋯ · Detalles técnicos | Ids and versions from the incident, snapshot and run responses |

Backend gaps:

- No incident list: `Incidentes` (open and closed) and the inbox's incident cards need
  `GET /v1/incidents` with state and service.
- No timeline notes: «Añade una nota para la historia» needs a write endpoint for operator notes.

- Start the investigation server-side on `triage_declare`, or have the UI chain it.
- Expose `objective`/ordinal in the run summary (the UI numbers investigations and proposals).
- Ask the investigator for Spanish output (`src/sre_agent/investigator/prompt.py`) and for a
  per-evidence verdict.
- Return a triage status per alert in `GET /v1/alerts` (#693), a short title (#694) and the
  dispatch failure reason (#692).
- "Ya la apliqué" is new: today the workflow goes from approval straight to `verifying`. It can
  be a timeline note, or an agent stability watch on the alert's signal.

## Theme (RC-2, #870)

- **Tokens.** Every colour is a Nocturno token in `src/index.css` (`--night`, `--moon`, `--mist`,
  `--rule`, …), copied from `docs/design/brand-round-1/06-consola-dia-noche.html`. Night is the
  base; without `html.dark` the light theme only reassigns tokens. The shadcn/ui names (`--background`, `--primary`, …)
  are derived from them once, so primitives follow both themes.
- **Amber** lives in `--star` (fills, Tailwind `bg-star`, with `text-on-star`) and `--star-ink`
  (text, `text-star-ink`). Use them only where a human decision is pending; `--warning` is not
  amber.
- **Type.** Fraunces (`font-display`), Newsreader (`font-sans`, the body) and JetBrains Mono
  (`font-mono`), self-hosted through `@fontsource-variable`. `<code>` is mono on `--code`.
- **Hook.** `src/hooks/use-theme.ts`: `useTheme()` holds the preference (`system`, `light`,
  `dark`; stored in `localStorage` as `midnight-theme`) and `setTheme`; `useResolvedTheme()`
  gives the theme on screen and re-renders on OS changes; `useApplyTheme()` is mounted once in
  `App`.

## Languages (RC-2, #870)

Spanish and English. `src/i18n/index.ts` holds `useLanguage()` (`language`, `setLanguage`; stored
as `midnight-language`, else English when `navigator.language` starts with `en`, else Spanish),
`useT(namespace)` and `LOCALES` for `Intl` formatters. The account menu switches the language.

To translate a feature, add one namespace instead of editing shared files:

1. `src/i18n/es/<namespace>.ts` exports the Spanish messages as `default` and registers them with
   `declare module "@/i18n" { interface Namespaces { <namespace>: typeof messages } }`
   (see `es/shell.ts`).
2. `src/i18n/en/<namespace>.ts` exports the English ones with
   `satisfies Messages<typeof messages>`, so a missing or extra key fails the build.
3. In components: `const t = useT("<namespace>")`, then `t("key")` or `t("key", { id })` for
   `{id}` placeholders. Unknown keys fail the build; plural forms are separate keys.

Both files are picked up by `import.meta.glob`; nothing else needs registering.

## Stack

Vite 8, React 19, TypeScript 7, Tailwind CSS 4, shadcn/ui on Radix, lucide icons, sonner,
cmdk, motion and zustand. The UI patterns for agent activity and approvals take inspiration from
beautifului.dev (task rows, approval card).
