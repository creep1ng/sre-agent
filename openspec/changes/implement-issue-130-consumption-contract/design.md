# Design: Publish the LLM Consumption Contract (2.1.0)

## Technical Approach

Publish an additive, immutable 2.1.0 snapshot on /v1 while leaving every 2.0.0 artifact byte-identical. Normalize OpenRouter evidence once into the closed consumption object, then pass the same object to public response metadata and metadata-only audit persistence.

Separate **published contract discovery** from the **active runtime contract**. Release tooling discovers and validates every published semantic-version directory. Runtime OpenAPI parity resolves the explicit active `CONTRACT_VERSION`, requires that exact published snapshot and manifest to exist, and compares against that snapshot only. It MUST NOT select the highest directory. This permits a staged 2.1.0 (and later contract-only 2.2.0) to validate independently while the runtime remains explicitly 2.0.0 until the response/audit activation slice; the final integrated #130 runtime MUST be 2.1.0.

The apply baseline MUST contain issue #202's governed flow: validation -> `authorize_governed_access` -> alias resolution -> routing -> provider -> normalization -> audit append -> release. Do not restore the old ResponsesService-local authorization path.

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|---|---|---|---|
| Evidence authority | OpenRouter `usage` is the sole source for token and billed USD values; drop the body after adaptation. | Text, latency, SDK types, inferred estimates | Prevents false zeroes and sensitive-body retention. |
| Normalized shape | One strict closed `Consumption` DTO is reused by response and audit projections. | Separate public/audit JSON or an untyped sidecar | Prevents projection drift and preserves exact decimal text. |
| Billing context | Retain provider observation time as the temporal price snapshot/version; require it for `billed_usd`. | Floating point, receipt-time estimates, user price configuration | The provider is authoritative and no pricing registry is in scope. |
| Published versus active release | Tooling validates every published snapshot; runtime parity uses explicit `CONTRACT_VERSION` and rejects a missing/mismatched manifest. | Deriving runtime version from the maximum directory, skips, or bypasses | Independent green stacks need staged snapshots without silently changing runtime behavior. |
| Activation order | Land the small active-version parity boundary before the 2.1.0 snapshot; activate runtime 2.1.0 only with response/audit wiring. Issue #129 may add contract-only 2.2.0 after verification while runtime stays 2.1.0. | Activating an unpublished snapshot or reverting to 1.x | Keeps activation explicit, ordered, and on the requested 2.x line. |

## Data Flow

```
published releases/* -> validate every manifest/snapshot -> release evidence
explicit CONTRACT_VERSION -> require matching published snapshot
runtime OpenAPI -> compare against that exact snapshot
request -> #202 authn/authz -> route -> OpenRouter -> normalize
       -> public consumption + audit consumption -> audit gate -> response
```

Malformed routing evidence remains non-retryable 502. Invalid consumption evidence remains partial or unavailable; it never becomes zero.

## File Changes

| File | Action | Description |
|---|---|---|
| `src/sre_agent/release.py` | Modify | Keep the explicit active runtime contract identity. |
| `tests/test_responses_openapi.py`, `tests/test_release_metadata.py` | Modify | Test exact active-snapshot parity, missing active snapshot failure, and staged-release independence. |
| `schemas/tooling/lib/release-validation.mjs`, `schemas/tooling/release.mjs`, release tests | Modify | Validate all published snapshots without changing runtime selection. |
| `schemas/releases/2.1.0/` | Create | Immutable 2.1.0 schemas, fixtures, manifests, and evidence after the boundary slice. |
| Runtime gateway/audit/persistence files | Modify | Carry the normalized DTO without changing #202 ordering. |

## Interfaces / Contracts

`CONTRACT_VERSION` is the explicit active runtime release. Runtime parity MUST:

1. Read that value.
2. Require `schemas/releases/{CONTRACT_VERSION}/manifest.yaml` with the same `contract_version`.
3. Compare runtime OpenAPI with that snapshot's `openapi/responses.yaml`.

Published-release validation remains exhaustive and independent of active selection. No user price configuration is introduced.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Boundary prerequisite | Active 2.0.0 with a published 2.1.0 directory | Assert parity uses 2.0.0; assert missing/mismatched active snapshot fails; never use max or skip. |
| Tooling | Every published release | Validate all manifests, evidence, conformance, and 2.0.0 immutability. |
| Runtime 2.1 | Final public/audit activation | Assert parity selects 2.1.0 and consumption/error/ordering tests remain green. |
| Contract | 2.1.0 snapshot | Cover complete, partial, absent, unavailable, invalid, deny, timeout, error, cache, and fallback fixtures without secrets or raw bodies. |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary is added by this release-selection decision.

## Migration / Rollout

First land the small active-version parity boundary with runtime active 2.0.0. Then publish and validate 2.1.0, wire response/audit behavior, switch the explicit runtime active version to 2.1.0, and run independent verification. After that gate, #129 may publish contract-only 2.2.0; it MUST NOT change runtime activation or introduce 1.x behavior. No migration or user price configuration is required.

## Open Questions

None.
