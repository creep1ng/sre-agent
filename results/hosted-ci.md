# Hosted CI for the exact final main commit

**Status: passed.** Only commit `5b6109bd2c8100455136cf12ce91c52830833c7f` is covered. Earlier intermediate canceled runs are not counted as successful.

Expected source tree: `5ee5fd41bfa4c8fb588b147641a04f72d03f9df1`; GitHub commit tree: `5ee5fd41bfa4c8fb588b147641a04f72d03f9df1`. Tree match: `True`.

Observed from 2026-09-29T04:30:54.116052+00:00 to 2026-09-29T04:52:22.938148+00:00 (maximum 30 minutes). Read-only API observation; no retries, reruns, fixes, pushes or PR mutations.

## Runs and jobs

| Workflow / job | Result | Link |
|---|---|---|
| CI (push) | completed / success | [Run](https://github.com/creep1ng/sre-agent/actions/runs/36521826587) |
| ↳ configuration-lock | completed / success | [Job](https://github.com/creep1ng/sre-agent/actions/runs/36521826587/job/109258606003) |
| ↳ checks-image | completed / success | [Job](https://github.com/creep1ng/sre-agent/actions/runs/36521826587/job/109258676710) |
| ↳ unit | completed / success | [Job](https://github.com/creep1ng/sre-agent/actions/runs/36521826587/job/109258836787) |
| ↳ static-web | completed / success | [Job](https://github.com/creep1ng/sre-agent/actions/runs/36521826587/job/109258836839) |
| ↳ contracts | completed / success | [Job](https://github.com/creep1ng/sre-agent/actions/runs/36521826587/job/109258836878) |
| ↳ compose-smoke | completed / success | [Job](https://github.com/creep1ng/sre-agent/actions/runs/36521826587/job/109260497393) |
| ↳ production-browser | completed / success | [Job](https://github.com/creep1ng/sre-agent/actions/runs/36521826587/job/109260753612) |
| ↳ Quality gate | completed / success | [Job](https://github.com/creep1ng/sre-agent/actions/runs/36521826587/job/109261377274) |

## Explicit skipped checks

No job was skipped. The only skipped step is failure-only diagnostics, whose condition was false after a successful job.

- **compose-smoke**: step **Collect sanitised service state** was skipped, not passed.

Test-level skip counts are **not established from hosted logs**: the earlier read-only unit/static-web log requests returned exit 1 and were not retried. No raw logs were retained, and local test counts were not substituted. All eight hosted job conclusions and their steps were read successfully. There were no failed jobs requiring failure-log investigation.

## Evidence boundary

This hosted report supplements the earlier local integration evidence. It does not erase the optional local contract-tooling run stopped after 49 passing tests, nor turn its unfinished commands into a local PASS. Hosted job results are recorded separately. Source/protection/human acceptance remain separate from CI.

Monitor exited normally after the terminal result. No services were created and no cleanup of shared resources was attempted. `skill_resolution: paths-injected`.
