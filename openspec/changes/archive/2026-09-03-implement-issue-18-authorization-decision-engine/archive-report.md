# Archive Report: Reusable Authorization Decision Engine

## Final State

- **Change**: `implement-issue-18-authorization-decision-engine`
- **Archive date**: 2026-09-03
- **Verification verdict**: PASS WITH WARNINGS
- **Spec compliance**: 8/8 requirements and 16/16 scenarios
- **Task completion**: 9/9 complete; no unchecked implementation tasks remain.

The final independent verification passed with 432 tests passed and 1 skipped, the issue-14 Responses harness passed 14 tests, and immutable release 1.3.0 validated 145 artifacts and 8 checks. CI is fully green for PR #154 and PR #155, including Python, contracts, PostgreSQL, static web, Compose smoke, and security checks.

The post-verification readiness failure was fixed by commit `cb3fa80`: the readiness migration head was updated for the audit migration, and PR #155 was rebased onto that fix. The initial inactive-Principal verification gap was remediated before the final verification: Responses now preserves a valid credential's inactive Principal for the reusable engine while generic authentication retains its 401 behavior.

`openspec/config.yaml` remains stale repository-context debt and is intentionally tracked separately as issue #144. It is the sole non-blocking warning; it does not contradict the shipped authorization contract.

## Source of Truth Sync

| Domain | Action | Details |
|---|---|---|
| `authorization-decision-engine` | Created | Added the complete four-requirement engine specification from the full delta. |
| `governed-llm-responses` | Updated | Replaced one requirement and added one requirement: engine authority before routing, inactive-Principal denial, and unchanged non-enumeration. |
| `runtime-audit-evidence` | Updated | Replaced one requirement and added one requirement: exact audit-only denial cause with public decision isolation. |

The sync preserved all unrelated requirements in the two existing main specifications.

## Mechanical Archive Evidence

### New Main Spec Copy Readback

Command: `diff -r openspec/changes/implement-issue-18-authorization-decision-engine/specs/authorization-decision-engine/spec.md <temporary-main-spec>`

Verbatim output:

```text
```

Result: empty output; the copied new main specification was byte-identical before installation.

### Archive Move Readback

Command: `diff -r <pre-move-recursive-snapshot> openspec/changes/archive/2026-09-03-implement-issue-18-authorization-decision-engine`

Verbatim output:

```text
```

Result: empty output; the archived tree was byte-identical to the complete pre-move snapshot. This report is additive and was created after the readback.

## Archive Contents

- `exploration.md`
- `proposal.md`
- `design.md`
- `tasks.md` (9/9 complete)
- `apply-progress.md`
- `verify-report.md`
- `specs/authorization-decision-engine/spec.md`
- `specs/governed-llm-responses/spec.md`
- `specs/runtime-audit-evidence/spec.md`

## Closure

The active change directory is absent. The OpenSpec source of truth now records the reusable generic authorization authority, deterministic internal denial precedence, audit-only exact causes, and Responses integration without public enumeration.
