# 2.3.0 consumer migration

Release 2.3.0 is an additive /v1 contract over immutable 2.2.0. Every prior release remains byte-identical. The release adds `grants.revoke` to the closed AuditEvent operation vocabulary so the existing convergent Grant revocation route can emit authoritative metadata-only evidence. Resource remains the exact authorization tuple, Grant remains the direct authorization relation, and ModelAlias remains the routing authority.

The active runtime contract remains 2.1.0; publishing 2.3.0 does not activate the runtime contract or alter unrelated persistence, authorization, seed, or UI behavior. Consumers select the release version explicitly and retain the inherited issue-130 consumption and issue-129 catalog obligations.
