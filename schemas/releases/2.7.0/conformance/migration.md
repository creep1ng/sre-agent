# 2.7.0 additive publication

Release 2.7.0 is additive over immutable 2.6.0. It gives `GET /v1/audit-events/{id}` its own event-ID parameter that retains every value accepted by the 2.6 generic `Id` and adds canonical UUIDs. A disjoint schema union avoids narrowing legacy IDs or depending on optional `format: uuid` assertion. It preserves the 2.6.0 grant-create 404 contract and all prior schemas and consumers.
