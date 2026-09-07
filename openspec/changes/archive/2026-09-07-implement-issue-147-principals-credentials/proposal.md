# Proposal: Complete Administrative Principals + Credentials API (Issue #147)

## Decision

Finish issue #147 from the merged A/B/C baseline and publish an immutable **2.0.0**
full contract snapshot. Release 1.4.0 remains published and unmodified. Contract
package version changes do not create `/v2`: the API path remains `/v1`. The major
release is required because status replacement newly requires `expected_updated_at`.

## Verified Baseline

Slices A/B/C are merged: 1.4.0 control audit evidence and tooling support;
control-audit validation; additive seed convergence; and authenticated,
engine-delegated `POST/GET /v1/principals` plus `GET /v1/principals/{id}`.
The remaining routes and correctness gaps stay in this change; no completed slice
is reimplemented.

## Scope

- Publish `schemas/releases/2.0.0/` as a complete immutable snapshot, copying
  unchanged 1.4.0 artifacts byte-for-byte and changing only 2.0.0 contract,
  fixtures, manifest, compatibility, and evidence artifacts.
- Require closed `{status, expected_updated_at}` bodies for principal status
  replacement; report stale or simultaneous competing writes as 409 without an
  overwrite.
- Complete credential issue/list/revoke/rotate endpoints with one-time-secret,
  metadata-only readback, idempotent POST replay/conflict, and active-only,
  atomic rotation.
- Repair idempotency retention: `at_least_24h` records must persist a concrete
  expiry while `principal_lifetime` records remain unexpired.
- Keep authorization-engine evaluation before every target principal/credential
  lookup or mutation. Bootstrap resources and grants converge additively; seeds
  are never an HTTP bypass.
- Audit every terminal attempt before release. Validation and 401 records have
  no identity; successful authenticated control operations retain authorization
  identity, resource, and policy-decision metadata.

## Out of Scope

Administrative UI, new grant semantics, tenancy/roles, SSO, historical secret
recovery, and changes to immutable releases through 1.4.0.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Lost update | Database atomic compare-and-swap or locked conditional update plus concurrent PG proof. |
| Rotation mints from revoked credential | Lock/read active state and reject inactive rotation without issuance. |
| Secret or policy leakage | First response only; replay/list/audit/log negative tests; HMAC audit refs. |
| Audit shape drift | Separate anonymous pre-auth evidence from authenticated authorization evidence. |

## Rollout and Rollback

Validate and publish the 2.0.0 snapshot, deploy the migration-compatible runtime
slices in order, and preserve 1.4.0. Roll back router/service slices first; retain
append-only audit evidence and published contracts.
