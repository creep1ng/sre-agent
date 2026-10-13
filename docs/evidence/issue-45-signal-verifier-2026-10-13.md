# Issue #45: two-cycle signal verifier

**Evidence kind: controlled integration plus historical live-report replay.**
This PR adds an offline verifier for CA8's six sanitized gateway captures. It
does not assert current-main runtime acceptance or close #45.

## Scope and reproduction

The verifier reads exactly six bounded reports in baseline/failure/reset order
for two cycles. It checks settlement, source/window, checkout error metrics,
order-progress log counts, proxy statuses and transition chronology. It emits
only a safe summary, never raw report contents. It makes no network calls.

With a safe untracked `.env` from `.env.example` and `.env.worktree` generated
by `scripts/bootstrap-worktree.py`, run the controlled process-level CLI test:

```sh
docker compose --env-file .env --env-file .env.worktree -p issue45-signal-checks --profile checks run --build --rm --no-deps -v "$PWD/tests:/source/tests:ro" harness node --test /source/tests/test_demo_signal_verify.mjs
```

With six **sanitized** real captures, run the offline acceptance check:

```sh
docker compose --env-file .env --env-file .env.worktree -p issue45-signal-checks --profile checks run --build --rm --no-deps -v "$PWD/evidence:/source/evidence:ro" harness node /source/scripts/demo_signal_verify.mjs verify /source/evidence/cycle-1-baseline.json /source/evidence/cycle-1-failure.json /source/evidence/cycle-1-reset.json /source/evidence/cycle-2-baseline.json /source/evidence/cycle-2-failure.json /source/evidence/cycle-2-reset.json
```

The local Docker daemon could not allocate a second Compose network. The
controlled test instead ran in a cached Node 22.14 harness container with
`--network none` and read-only source mounts; it passed 1/1, no skips. Test-first
RED was 0/1 with the script absent. A later real-report replay exposed a
chronology false negative: cycle 2 baseline legitimately reused cycle 1
reset's settled state. A new process-level case failed before the narrow
correction and passed afterward; an unrelated overlapping transition remains
rejected.

## Historical live-report replay

Six reports from two actual failure/reset cycles on the authorized AWS OTel
demo instance were staged read-only inside the Compose harness. Verifier source
SHA-256: `bfbc666e11a68305e1a807fde8a907b1b3a8299ba7f5d7079fd038e3c3795633`.
The SSM result was `Success` and returned:

```json
{"schema":"sre-agent.mcp45-3-cycle-verification/v1","status":"pass","cycles_verified":2,"failures":[],"cycles":[{"cycle":1,"phases":["baseline","failure","reset"]},{"cycle":2,"phases":["baseline","failure","reset"]}]}
```

The successful replay command was `06d7d40a-0e9b-4c8e-a6c1-d9777ffaaae3`;
readback command `cfe69e30-6566-478e-b9e6-84244ec6df36` confirmed the
same sanitized result. The six reports predate this current-main integration.
Thus this proves the verifier can assess real historical captures, **not**
that the integrated current-main gateway/demo stack completed CA8. Fresh
current-main cycles, hosted CI and human review remain pending.
