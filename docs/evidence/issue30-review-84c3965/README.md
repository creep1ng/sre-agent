# Issue 30 — review corrections and current acceptance

**Not accepted.** These new records supplement, never replace, the original run.
Observer/reproduction review gaps are corrected; three producer defects remain.

## Exact inputs and actual execution

- Corrected observers and current runtime: `84c3965b03cc4633980831598ad5dc4f189c0f5d`,
  synchronized with main `c3cffb790e0015192908ad95d53ce1489b0403c6`; contract 2.8.0.
- [Current receipts](current-receipts.jsonl): readiness 18:36:01.636662 UTC precedes
  the 2026-10-13 18:36:03.066640–18:36:35.255924 UTC ten-scenario replay.
- [Separate baseline receipts](baseline-receipts.jsonl): fresh 763ccfc/2.7.0 stack,
  readiness 18:34:05.749957 UTC, replay 18:34:07.222097–18:34:39.318401 UTC.
  This verifies portability against the recorded source, not current-main behavior.
- Fresh independent synthetic credentials/databases, unused internal networks,
  no host ports, no paid-provider calls. Actual running and locally built image IDs,
  commands and sanitized configuration are in receipts and the two compose files.
  Built/running API IDs match before results; Python and harness tags were built.
- [Portable recipe](../issue30-763ccfc-08d022/reproduce-review.md) separates absolute
  runtime/delivery checkouts and mounts the whole helper directory. Use unique
  private configuration and writable scratch; never print/source env files.
  Current-version replay uses the actual candidate, contract 2.8.0, and a third
  internal mcp-consumer subnet; pass `SRE_AGENT_CONTRACT_VERSION=2.8.0` to Ajv.

## Current CA1–CA5 matrix

| Criterion | Actual current-candidate evidence | Status |
| --- | --- | --- |
| CA1 | [Replay L11](current-replay.jsonl#L11): normalized 200; one tools/call, one real forward; valid success event. | Satisfied with evidence; human story acceptance pending. |
| CA2 | [L4–L6](current-replay.jsonl#L4-L6): invisible/no grant/invalid credential 403/403/401; zero tool attempts/forwards. | Public behavior passed; partial overall due to CA4 audit failures. |
| CA3 | [L7–L10](current-replay.jsonl#L7-L10): 422/504/503/502; tool attempts 0/1/1/1, actual tool forwards all zero. | Public errors passed; partial overall due to 503/504 audit retryability. |
| CA4 | [Complete SQL](current-sql-storage-full.jsonl), [events](current-audit-events-full.jsonl), [Python](current-audit-schema-results.jsonl), [Ajv](current-audit-ajv-schema-results.jsonl): 4 valid/5 invalid, 401 absent across all operations. | **Failed; not accepted.** Narrow approved 422/stage=validation exception remains valid. |
| CA5 | [L2–L3](current-replay.jsonl#L2-L3): known identifier before discovery, 200/403; attempts/forwards 1/1 and 0/0. | Authorization behavior passed; denied audit event fails CA4. |

Replay retains both allow/deny-by-ID, no-grant/nonvisible variants, unavailable and
malformed upstream variants, and positive control. Cold initialize/notifications
are counted separately from tools/call and actual forwards; no tools/list/discovery.
Full SQL selects exact IDs/half-open UTC windows without an operation filter,
retains all 26 columns, and separately maps optional SQL NULLs to contract absence.

## Review validation and remaining producer work

The unchanged legacy runner passes ten cases but expects zero mcp.invoke rows for
401. [All-operation searches](current-audit-summary.jsonl) find none for its ID,
the entire database, or authentication operations in the replay window. A [separate
401 repeat](current-401-repeat.jsonl) has valid HTTP/zero activity but no event;
the corrected full-event observer therefore exits 1, not green.

OpenSpec runtime-audit-evidence requires a terminal authentication event. ADR-005
and the schema prohibit inventing an unknown identity/resource/decision, not the
event itself. Three 403s still lack authorization_denial_cause; 503/504 still store
retryable=false. [Minimal producer proposals](../issue30-763ccfc-08d022/README.md#401-reproduction-contradictory-requirement-and-minimal-proposals)
remain separate and require explicit approval; runtime/schema/old expectations
and the approved 422 decision are unchanged.

[Pre-code process checks](mock-process-results.jsonl) are **mock-only**: 21 risks,
17 pre-change false positives, all 21 GREEN for releases 2.7.0 and 2.8.0. Published
fixtures certify observer behavior, never an actual positive authentication event.
Lint/format passed. One scratch-UID setup attempt failed, then the same checks
passed with the host owner's UID; no expectation changed. Live valid 401-event
production, audit-store outage/release suppression and paid providers are **not
executed**. Human acceptance of the story remains pending; #30 stays open.
