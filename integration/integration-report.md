# Seven partial slices integrate cleanly; #390 excluded

**No candidate-caused blocker found in the seven accepted-scope source slices.** Fresh cumulative proof: **1220 Python passed /1 intentional provider skip;27 UI browser passed;31 complete static-browser passed /58 connected skips; all15 Python static/type/migration commands pass.** This is independent automated technical evidence, **not human approval, hosted CI or merge authorization**.

Starting live main: `4b0c8740a042a8654979dd43481c7ad4f9992ea1`. Final prospective tree: `5ee5fd41bfa4c8fb588b147641a04f72d03f9df1`. Final local synthetic commit: `b364498c3c67e654c6f8cd86fa5fd7219243e124`. Source and remote state were not corrected or published. Live refs were rechecked at 2026-09-29T04:13:53.587540+00:00 and match the selected main/heads.

## Exact ordered boundaries

| PR | Exact head | Prospective tree | Lines | Boundary proof |
|---|---|---|---:|---|
| #396 | `c29de01db9820df26a41cde8012db642c633df86` | `20bffa30bd4779ceb17e8f83a3f1838ebf393bc7` | 376 | 31 Python |
| #414 | `141b177d4a47f8da1279571893643f6e2fb7349a` | `d471ea09d7866acd1009872698f99d95163cac6b` | 346 | 12 Python + 21 browser |
| #415 | `d21bdda93ec8a49670387a185195027786a7e0a8` | `16b492d096cf6c9a906fee70c32e8cd0a1088f5d` | 398 | 3 Python + 3 browser |
| #417 | `0d0b876ad3f38506728da9ee00ed4d18a50ffe4c` | `c188e3e455e7907347d4335200b26cdf37684200` | 339 | 2 Python + 3 browser |
| #412 | `fe63f0c1f7d0bb90a46136a57f8c65256fba86ea` | `0a4616a430806e4a6d5cbeaf93fa3d0f4b6df9da` | 397 | 20 Python |
| #371 | `d957c1b0375788e7283ae20e530767ca64f207d1` | `56cdd5b7f487e21158fc58ebb09855af3cc36f2d` | 122 | 1 Python |
| #372 | `c8fd8968d2596b57013ec73c3c6fcaae5a9c1aec` | `5ee5fd41bfa4c8fb588b147641a04f72d03f9df1` | 253 | 4 Python |

All merges used `git merge-tree --write-tree` and two-parent local `git commit-tree` objects, with no conflict resolution. Every boundary was checked independently with a fresh isolated PostgreSQL namespace. Complete parent/head/synthetic identities, changed files and Docker commands are in [integration-summary.json](integration-summary.json). All incremental slices are below400 additions+deletions. Parent must compare the **actual merged tree after every authorized merge**; if main or a head changes, these results no longer select that candidate automatically.

## Scope and safety readback

- **#396:** Service-only atomic run start; no new HTTP route or credential authorization.
- **#414:** Read-only run selector, run-scoped cursor and reload behavior.
- **#415:** Read-only workflow1.0.0 review actions; no command submission.
- **#417:** Explicit fixture-only minimum postmortem presentation; no durable generation/versioning/closure.
- **#412:** Trusted internal human-command translator; no HTTP/credential authority.
- **#371:** Test-only packaged restart/read proof; not the whole incident-read story.
- **#372:** Bounded SQL audit filters/order/limit/has_more; no HTTP/UI or cursor implementation.

No new API route was introduced by combining these slices. In particular, review actions remain read-only despite the newly available internal translator; the postmortem explicitly says it is a fixture without a persisted backend artifact. The run picker keeps a run-specific cursor through pagination/reload and rejects stale responses. The command translator still delegates guards/approval/state reduction to the runtime. Its supplied actor is trusted internal input, not proof of credential-derived authorization.

A separate [combined runtime probe](combined-runtime-probe.log) uses real PostgreSQL: service atomic triage start → translated human declare → replay both idempotency keys → reopen database handle/reconstruct. Observed one run, two events, preserved synthetic actor/comment, no inappropriate approval, state`active`, cursor`seq:1`, identical reconstruction. No provider, HTTP authorization or external remediation was exercised.

## Checks and actual media

- [Python/static/type results](final-checks.json): isolation guard, ShellCheck, Ruff lint and check-only format, offline locked uv check, import boundaries, mypy including new`commands.py`, all five CI validators, full pytest, Alembic upgrade/check: exit0. [Full test log](final-check-13.log):1220passed/1skipped; skip is inherited OpenRouter smoke.
- [Final UI browser log](final-ui-browser.log):27passed; actual Chromium with synthetic intercepted API fixtures. The full-page captures below come from this exact final seven-step tree, not generated artwork or a different candidate.
- [Full static browser log](final-online-browser.log):31passed/58connectedskips with public font assets reachable. Static JS syntax/file checks also pass. No production API credentials were supplied; this is not the production browser topology.
- [Deliberately offline run](final-browser.log):29passed/58skipped/2showcase failures due to external font requests. [Starting-main control](superseded-eight/base-offline-browser.log) reproduces both failures. They are environment-induced inherited failures, not hidden candidate findings. No source correction was made to get the normal-network pass.
- Optional full contract tooling: **bounded_incomplete** (49 completed tests passed, no observed failure; intentionally stopped after approximately12minutes; remaining tests and chained validate/validate:releases/lint:openapi not completed, no PASS claimed); see [contract log](superseded-eight/final-contracts.log). This single run began on the superseded eight-step source. [Input parity](contracts-input-parity.log) proves all its schemas/scripts/harness inputs byte-identical on the seven-step tree; it is not represented as a second run.

| View | Actual full-page capture |
|---|---|
| #414 selected-run timeline | [Run selector](pr-414-final-ui.png) |
| #415 read-only mitigation actions | [Review actions](pr-415-final-ui.png) |
| #417 clearly labeled fixture presentation | [Postmortem fixture](pr-417-final-ui.png) |

## Superseded candidate and remaining governance

Parent excluded **#390** after source-document review: its exact head instructs unscoped `docker compose --profile live-smoke down -v` at`docs/harness-gateway.md:64–65`, plus host-only demonstration steps. Working provider behavior does not repair unsafe authored instructions. No source fix was authorized. The original eight-step identities/logs are preserved in[superseded-eight/integration-summary.json](superseded-eight/integration-summary.json), explicitly superseded; none of its trees are the current merge plan. Its original #414 boundary screenshot directory was overwritten during archival before the runner-directory move completed; original logs and final-eight combined UI screenshots remain. Current seven-step UI evidence was separately regenerated and inspected.

For #371/#372, publish the fresh real evidence and explicitly reassess the historical CHANGES_REQUESTED reviews; this verifier does not dismiss or supersede human review. Every issue remains open for its later slices. No RDD was enabled and no approval was fabricated.

[Reproduction guide](REPRODUCE.md) uses Docker-only acceptance commands, public pinned base images/locked dependencies and fresh isolated databases. It distinguishes cached tool images from a newly built final application. Fresh image builds, complete production Compose/nginx/OTel and connected browser journeys were not rerun here. Parent owns hosted/protection checks, publication, ordinary review policy and final conditional merge decisions.
