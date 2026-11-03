# The agent investigates again after a failed verification (#710), 2026-11-03

Maintainer decision (2026-11-03): after a failed verification, the agent's (#958) or a person's
«Sigue fallando» (#991), the agent investigates again on its own, at most twice per incident, told
what ran and failed; then it stops and a person is woken.

`run.sh` starts the local flow (scripted model, EC2 flag catalog and stand-in, fake Bot API with
one linked chat), runs one scenario with `drive.py` against the real API, captures the incident
page and tears the project down. The agent verifies 10 s after an approval
(`VERIFICATION_DELAY_SECONDS=10`; the demo uses 150 s).

| Scenario | What happens | Artifacts |
|---|---|---|
| `retry`: `checkout`, `paymentFailure` and `paymentUnreachable` on | proposal `paymentFailure`, approved, runs; the agent's verification fails (`paymentUnreachable` still breaks checkout); a run starts on its own with the failed attempt in its state, searches the BoK, proposes `paymentUnreachable`; approved, runs; the verification resolves the incident | `retry/drive.json`, `retry/incident.png` |
| `exhausted`: `sre-checkout` alert firing, simulated rollbacks | three times: proposal, approval, a person says it still fails; the first two start a run on their own, the third does not, and the chat gets «Necesita a una persona» | `exhausted/drive.json`, `exhausted/incident.png` |

```sh
OUT=/tmp/reinvestigate-retry SCENARIO=retry docs/evidence/reinvestigate-2026-11-03/run.sh
OUT=/tmp/reinvestigate-exhausted SCENARIO=exhausted docs/evidence/reinvestigate-2026-11-03/run.sh
```
