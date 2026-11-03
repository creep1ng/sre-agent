# The 2026-11-04 demo path on the merged candidate, 2026-11-02

The one path of the demo script that no stack tested alone: **fault → incident → proposal naming
`flag.set` → one tap in Telegram → the API's tap worker runs `flag.set` → receipt on the RC-2
incident page → decision message edited → alert resolved → verification → recovery edit**, and
`/app/acciones` listing `checkout · flag.set` with its run.

## What ran

The candidate is `main` at `4aed175c` with the five demo stacks merged in their merge order:
A (#946), B (#928 → #931, #947, #948, and #932), C (#933, #934, #943 → #945), D (#937, #938,
#939, #941, #940) and E (#950 → #954). Every service is real except the stand-ins of the local
flow ([docs/local-flow](../../local-flow/README.md)): the scripted model, Grafana and its MCP,
and the fake Bot API. D's stand-in adds the instance's own flag listener (`otel-flags`) and
flagd 0.16.0. No real LLM, no EC2.

`run.sh` drives it: it starts the stack, links the fake chat `424242` to `demo-human`, injects
`paymentUnreachable`, runs D's driver (`scripts/flag_set_e2e.py flow` with `DECIDE=telegram` and
flagd's stream held open), records the verification (`verify.py`), and captures the pages
(`capture.spec.ts` in `incident-console-e2e`).

## Result (2026-11-03 01:13–01:15 UTC)

| Step | Time | File |
| --- | --- | --- |
| Stack up, seeded, chat linked | 68 s | `timings.txt` |
| Fault on → incident declared by Grafana's alert | 2.2 s | `flow.json` |
| Proposal `flag.set {flag: paymentUnreachable, variant: off}` on `checkout`; no prompt showed a flag's value | 11.0 s | `flow.json` |
| Decision message in the chat, «Aprobar» tapped in the fake Bot API | 13.1 s | `telegram.json` |
| Tap queued by the gateway, run by the API's tap worker: receipt `exe_e8f83ab299d0fd10`, `flag_set`, `on → off`, 28 ms; incident `verifying` | 15.6 s | `flow.json` |
| flagd served `off` with its stream open (no restart); alert resolved | 15.7 s | `flow.json` |
| Message edited: «Aprobada por Demo human desde Telegram, 01:14 UTC.», buttons gone | 01:14:44 | `telegram.json` |
| `verification_passed` by `demo-human` (202), incident `resolved` | 01:14:47 | `verification.json` |
| Message edited again: «Resuelto a las 01:14 UTC · 3 s tras la mitigación que aprobaste · ver la consola.» | 01:14:47 | `telegram.json` |

The tap's answer was «Aprobada por Demo human desde Telegram, 2026-11-03 01:14 UTC.» and the bot
sent no other message about the incident: two Bot API edits on the one decision message.

- `incident.png`: the RC-2 page afterwards. The timeline says «Se ejecutó `flag.set` en
  `checkout`: flag cambiado (`paymentUnreachable` → `off`)», the verification step says the signal
  recovered, and «Decisiones tomadas» holds the approval with its receipt.
- `acciones.png`: `/app/acciones` lists `checkout · flag.set · flag ∈ {paymentFailure,
  paymentUnreachable} · variant = off` with one recent run, «Se ejecutó · aprobó Demo human · Ver
  el incidente», and `payment · flag.set` never run.
- `telegram-transcript.png`: the fake Bot API's transcript.

The scripted model's hypothesis blames a deploy while proposing the flag; that is the stand-in's
fixed script, not the real model's reasoning.

## Gap the run shows

Grafana's resolution alone records no `verification_passed`, so the recovery edit only follows a
verification command. Here `verify.py` sends it as `demo-human`. On 2026-11-04 someone has to
record it (API, or the agent's verification once #723 lands), or the message stops at «Aprobada».

## Repeat

From a checkout of the candidate (fetch the stack heads, then `git checkout origin/main` and
`git merge` the tops of A, B (#948 and #932), C (#945), D (#940) and E (#954) in that order), with
`.env` from `.env.example` with local keys as in [the local flow](../../local-flow/README.md):

```sh
OUT=/tmp/demo-candidate docs/evidence/demo-candidate-2026-11-02/run.sh
```

It writes the same files under `$OUT` (`shots/` holds the screenshots and `telegram.json`) and
removes its Compose project on exit.
