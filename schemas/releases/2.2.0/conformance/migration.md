# 2.2.0 consumer migration

Release 2.2.0 is an additive /v1 contract over immutable 2.1.0. Every 1.x, 2.0.0, and 2.1.0 artifact remains byte-identical. The release adds a closed ResourceCatalogEntry projection, bounded authenticated reads, owner-specific lifecycle evidence, and explicit reconciliation fixtures. Resource remains the exact authorization tuple, Grant remains the direct authorization relation, and ModelAlias remains the routing authority.

The active runtime contract remains 2.1.0; publishing 2.2.0 does not activate runtime catalog code or alter persistence, authorization, seed, or UI behavior. Consumers select the release version explicitly and must retain issue-130 consumption coverage while adding the version-aware issue-129 catalog obligation.
