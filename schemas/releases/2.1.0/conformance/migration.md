# 2.1.0 consumer migration

Release 2.1.0 is an additive /v1 contract over immutable 2.0.0. Every 2.0.0
artifact remains byte-identical. Successful authorized Responses metadata now
includes the closed consumption object. Its availability is explicit:
complete, partial, absent, or unavailable; missing evidence is never converted
to zero. OpenRouter usage and exact decimal billed USD are the only authorities.
Denials make no provider call and carry no consumption projection; timeouts,
upstream errors, cache, and fallback without explicit evidence remain
unavailable. The projection is metadata-only and is shared by public response
metadata and audit persistence.

### Compatibility evidence

The additive compatibility check is a validation-only normalization, not a claim
that unchanged 2.0.0 payload bytes satisfy the stricter 2.1.0 schemas. For the
historical successful Responses response and audit examples that predate this
field, the checker injects an in-memory `consumption` projection with
`availability: absent` and validates the normalized shape. It never rewrites
release files, never adds consumption to denied events, and never treats the
normalized result as raw-schema acceptance. Strict 2.0.0 consumers must update
or tolerate the additive `consumption` field because successful 2.1.0 response
metadata requires it.
