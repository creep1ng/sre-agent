# 2.7.0 additive publication

Release 2.7.0 is additive over immutable 2.6.0. It gives `GET /v1/audit-events/{id}` its own event-ID parameter accepting canonical UUID or correlation-ID values without widening the shared `Id` parameter used by other routes. It preserves the 2.6.0 grant-create 404 contract and all prior schemas and consumers.
