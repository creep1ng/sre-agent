# Delta for Governed LLM Responses

## MODIFIED Requirements

### Requirement: Resolve bounded routing evidence after allow

After allow, the operation MUST resolve the active alias to one concrete model and configured provider, request that provider without fallback, and accept success only when routing evidence identifies exactly that selected provider. A valid provider result MAY carry consumption evidence, which MUST be normalized by the LLM Consumption Contract; missing usage or cost MUST NOT be inferred and raw provider bodies MUST NOT cross the boundary. Missing, malformed, contradictory, or extra-provider routing evidence MUST be rejected.
(Previously: successful routing normalized text and selected-provider evidence but had no consumption projection.)

#### Scenario: Alias resolves and evidence agrees

- GIVEN an allowed principal and an active alias mapped to one model/provider
- WHEN the provider returns valid text and exactly matching selected-provider evidence
- THEN the operation returns a normalized HT-01 non-streaming response and projects only validated consumption metadata

#### Scenario: Provider evidence is invalid

- GIVEN an allowed principal and a provider response with absent or contradictory routing evidence
- WHEN the response is normalized
- THEN the operation returns non-retryable 502 `provider_evidence_invalid` and performs no fallback call

## ADDED Requirements

### Requirement: Expose consumption only after authorized completion

The operation MUST include the normalized `consumption` projection in a successful public response only after authorization and provider completion. It MUST preserve the existing `invoke` action, `llm_model` resource tuple, zero-call denial, and normalized error taxonomy.

#### Scenario: Authorized completion exposes projection

- GIVEN an authorized request and a completed provider response with valid usage evidence
- WHEN terminal normalization succeeds
- THEN response metadata contains the normalized consumption object and the provider body is absent

#### Scenario: Deny and failure expose no false usage

- GIVEN a pre-routing denial or a timeout/error without explicit provider evidence
- WHEN the endpoint completes
- THEN denial remains 403 with zero provider calls, while the error remains its existing normalized status and no consumption value is inferred
