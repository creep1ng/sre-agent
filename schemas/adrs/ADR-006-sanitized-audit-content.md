# ADR-006: Bounded sanitized audit content

- **Status:** Accepted
- **Contract version:** 1.1.0

## Context

ADR-005 made pre-sink redaction fail closed, but its only sink-eligible content representation was `fully_redacted`. That prevents the gateway from retaining complete, useful LLM inputs and responses after sensitive values have been removed.

## Decision

Successful redaction of `llm_input` and `llm_response` MAY persist the complete sanitized text as the closed `sanitized_text` representation. It contains exactly `representation` and a non-empty `text` bounded to 65,536 characters. The redaction pipeline, not the schema, proves that the text is safe before constructing this representation.

`fully_redacted` remains valid when no safe text survives. Unknown properties, missing text, empty text, and `sanitized_text` on non-LLM source classes are invalid. Redaction error or uncertainty remains fail-closed: `redaction_failed` forbids every content representation, including raw, partial, and apparently sanitized text.

Release `1.1.0` is an additive full snapshot. Release `1.0.0` and its immutable identifiers remain unchanged, and every valid `1.0.0` instance remains valid under the corresponding `1.1.0` schema after only its contract identity is advanced.

## Consequences

Audit sinks can retain useful post-redaction LLM text without admitting arbitrary object shapes or weakening failure handling. The character bound controls contract size but is not a byte-limit guarantee; implementations MAY enforce a stricter transport or storage byte limit.

## Alternatives

Rewriting release `1.0.0`, storing arbitrary strings, permitting partially redacted failure output, and using a delta-only release were rejected because they violate immutable identity, weaken sink safety, or break the complete-snapshot release model.

## Deferred

Retention, content-read authorization, runtime redactor implementation, byte-oriented storage limits, redaction token vocabulary, and product sink selection remain deferred.

## Supersedes

ADR-005 for the successful redacted-content representation only. ADR-005 remains authoritative for stage-aware evidence, fail-closed failure behavior, durable acceptance, append-only events, ownership, and downstream exporters.

## Links

- `openspec/changes/issue-9-gateway-boundary-contracts-and-adrs/specs/audit-redaction-contract/spec.md`
- `openspec/changes/issue-9-gateway-boundary-contracts-and-adrs/specs/contract-governance-conformance/spec.md`
- `schemas/releases/1.1.0/json-schema/domain/audit-event.schema.json`
