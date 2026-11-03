# The investigator gets the fault flag right on its own (#724), 2026-11-03

The 2026-11-03 EC2 walkthrough's first run (`paymentUnreachable` on, incident on `checkout`)
guessed `paymentFailure` from a span name, had it refused as already off with 1 step left, and
asked for a human. This evidence replays that run on the local stand-in with the scripted model
(`scripts/local_flow_upstreams.py`), and shows what the change does after the refusal:

- the refusal grants steps once per run (`Limits.steps_after_refusal`, at least 4 left after it)
  and tells the model what to do with them: measure what tells the cause apart, search the BoK;
- the run keeps its refusals in the prompt state (`refused_mitigations`);
- with a BoK collection and operations offered, the prompt asks for the BoK before a hypothesis
  that leads to a mitigation, and to cite the fragment.

`run.sh` starts the local flow with the EC2 catalog and flag stand-in, runs one scenario and tears
the project down. `trace.py` prints the run's turns and the incident's timeline and checks them.

| Scenario | What happens, in one run | Artifacts |
|---|---|---|
| `fault`: `paymentUnreachable` on | logs, guess `paymentFailure`, refused with 1 step left, 3 steps granted: BoK search, one more query, hypothesis `paymentUnreachable`, its flag.set approved through the API, the alert resolves | `fault/trace.json`, `fault/incident.png` |
| `no-flag`: alert fires, every flag off | the same until the second proposal, `paymentUnreachable`, which is also refused with no step left: the run ends `needs_human` after 9 turns | `no-flag/trace.json`, `no-flag/incident.png` |

`scripts/flag_set_e2e.py flow` drives the `fault` scenario's approval; on the tested head it
printed:

```text
    2.3s PASS incident declared from the alert
   21.9s PASS the proposal names the catalog operation
   22.0s PASS no prompt showed the agent a flag's current value
   22.0s PASS proposing paymentFailure, already off, was refused at proposal time with the reason
   22.4s PASS approved through the API
   22.6s PASS the executor ran flag.set and the incident is verifying
   22.6s PASS the flag is off on the demo
   24.7s PASS the alert resolved
   24.8s PASS the timeline tells what ran
```

The refused proposal itself does not appear on the timeline (the runtime refuses it before any
event); the prompt of the next turn carries it, as `trace.json`'s `told` shows.

```sh
OUT=/tmp/flag-guess-fault SCENARIO=fault docs/evidence/flag-guess-2026-11-03/run.sh
OUT=/tmp/flag-guess-no-flag SCENARIO=no-flag docs/evidence/flag-guess-2026-11-03/run.sh
```
