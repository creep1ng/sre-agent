# ADR-001: Responses gateway boundary

- **Status:** Accepted
- **Contract version:** 1.0.0

## Context

Consumers need a portable Responses contract before a gateway runtime, provider adapter, or persistence model exists. Parent issue #9 remains the normative authority; this record preserves its accepted boundary as versioned Git evidence.

## Decision

The gateway exposes only the closed text-only non-streaming `POST /v1/responses` subset. Request validation precedes authentication, producing 422 before credential or upstream work. Authentication precedes authorization, and authorization precedes alias and model resolution, preserving the 422→401→403 order and preventing alias enumeration or routing after denial.

After allow, the governed alias resolves to one concrete `<laboratory>/<model>`. OpenRouter is the initial router, while `router=openrouter` and the effective provider remain distinct evidence. One bounded metadata lookup may use only a valid upstream `X-Generation-Id`, never the public Response `id`.

Valid W3C Trace Context creates bounded child context; missing or invalid context creates a new trace without 422, and sensitive `tracestate` does not propagate. Public upstream failures use redacted `502`, `503`, and `504` errors: 502 is non-retryable, 503 and 504 are retryable, and `Retry-After` appears only for a reliable estimate.

## Consequences

Consumers receive one closed portable contract without treating runtime DTOs, persistence records, provider payloads, SDK types, or credentials as authority. Provider ambiguity and malformed output fail closed without exposing upstream bodies, URLs, stacks, secrets, denial causes, or internal identifiers. Accepted text is superseded by a new ADR rather than silently rewritten.

## Alternatives

Streaming, broader OpenAI compatibility, direct provider exposure, authorization after routing, Response-ID-keyed metadata lookup, and provider-native public errors were rejected because they expand the contract, permit enumeration, confuse identifiers, or leak upstream detail.

## Deferred

Runtime implementation, streaming, tools, conversations, provider SDK choice, credentials and secrets, persistence, and broader OpenAI and OpenRouter surfaces are deferred.

## Supersedes

None.

## Links

- `openspec/changes/issue-9-gateway-boundary-contracts-and-adrs/specs/responses-gateway-contract/spec.md`
- `openspec/changes/issue-9-gateway-boundary-contracts-and-adrs/specs/contract-governance-conformance/spec.md`
- `schemas/releases/1.0.0/openapi/responses.yaml`
