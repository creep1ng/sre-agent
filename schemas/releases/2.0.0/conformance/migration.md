# 2.0.0 consumer migration

Relative to immutable 1.4.0, `PUT /v1/principals/{id}/status` now requires both `status` and
`expected_updated_at`. A missing token produces `422 validation_error`; a stale
token produces `409 status_conflict` without a status mutation. The package
version is 2.0.0, while the API path remains `/v1`; consumers do not migrate to
`/v2`. Credential rotation now returns the `CredentialRotation` wrapper on 201 and its typed zero-transition failure form on inactive credentials; rollback-safe unexpected issuance failures return a retryable 500 standard error envelope; idempotency conflicts remain standard error envelopes. Generic `ActiveInactiveStatus` remains unchanged for other status routes.
