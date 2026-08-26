# Archive Report: Governed LLM Responses Vertical Slice

- **Change:** `implement-issue-14-governed-llm`
- **Archived:** `2026-08-25`
- **Artifact store:** OpenSpec
- **Final status:** PASS WITH WARNINGS

## Final-State Summary

All 10 implementation tasks were complete in the persisted `tasks.md` artifact before archival. The final verification report recorded 10/10 requirements and 17/17 scenarios compliant, with 308 tests passed and 1 secret-gated live-provider test skipped. The issue-14 deterministic harness passed 11 tests, and contract tooling passed 68 tests. All checks ran in containers; no provider secret was supplied and no real provider traffic was attempted.

The native final verification settlement was complete for evidence revision `sha256:d53d6c5b35c7d632a44138c406b107fe775b6a4ff2aa6ef8e02b43a33cbe4816`. Receipt-driven review was disabled/unmanaged; status contained no `reviewGate`, so archive proceeded under ordinary repository policy.

## Open Follow-up Warning

`VER-01` remains intentionally open and is not claimed as fixed: inactive-resource denial, delayed latency, and terminal-event cardinality were proven by a verifier-only container probe (`sha256:f8b683373fc1b551b7c57e55d2dbbee99a19533272efe7244c212c723890897d`) rather than permanent checked-in harness tests. The probe passed; promoting these assertions into checked-in tests remains a follow-up to prevent CI regression.

## Specs Synced

Both delta specs were new domains and were copied mechanically into the canonical source-of-truth locations:

- `openspec/specs/governed-llm-responses/spec.md`
- `openspec/specs/runtime-audit-evidence/spec.md`

## Archived Contents

The complete change folder was moved to:

`openspec/changes/archive/2026-08-25-implement-issue-14-governed-llm/`

It contains the proposal, exploration, both delta specs, design, tasks, apply progress, and verify report. The active change directory no longer exists. The archived task artifact has no unchecked implementation tasks.

## Structural Readback Evidence

The two mechanical spec-copy `diff -r` commands exited 0 and emitted no output.

```text
[empty output]
```

The pre-move recursive snapshot compared with the archived folder using `diff -r`; it exited 0 and emitted no output.

```text
[empty output]
```
