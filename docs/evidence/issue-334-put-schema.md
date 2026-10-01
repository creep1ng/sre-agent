# Consumption-policy PUT schema prerequisite

This unit prepares unpublished migration `20261001_02` (rebased from `20260929_16` during the #441 main integration; BoK already owns that identifier) for the later protected PUT
endpoint. It expands the method constraint for idempotency bindings and adds the
`consumption_limits.replace` audit vocabulary while preserving earlier operations.

- Policy remains a singleton with versioned nullable limits.
- The new `admin.write` grant is seeded for the consumption-limits resource.
- Readiness now requires migration 16.
- Downgrade refuses to discard PUT bindings or consumption-write audit evidence.

This prerequisite does **not** expose a PUT route. The protected HTTP behavior and
its audited transaction are delivered by the dependent audited-PUT unit. Existing
GET behavior remains available. The screenshot captures a real candidate GET response
for the seeded default policy; migration, SQL-constraint, and downgrade behavior are
verified separately by the acceptance and migration tests.

Evidence kind: controlled integration. Screenshot: [default policy GET](issue-334-put-schema.png).
