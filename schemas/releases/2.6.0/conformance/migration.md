# 2.6.0 additive publication

Release 2.6.0 is additive over immutable 2.5.0. It corrects the published audit-detail path parameter to admit the UUID and `cor_` event identifiers allowed by the 2.6.0 audit-event schema and the existing read route. The broader identifier schema is scoped to `/v1/audit-events/{id}`; the shared `Id` parameter for other endpoints remains unchanged. All earlier release directories remain byte-identical.
