# Sprint 2 feature branch chain

This branch is the draft integration tracker for Sprint 2. It is **not mergeable** until every
child is reviewed, verified, and integrated in order. Each child targets its immediate predecessor.

```text
codex/sprint2-integration
  -> codex/sprint2-01-runtime       #26 incident runtime, ports, workflow, tests, and docs
  -> codex/sprint2-02-schema        #146 incident schema migration and readiness
  -> codex/sprint2-03-persistence   #146 PostgreSQL incident adapter and integration tests
  -> codex/sprint2-04-routing       #24/#163 deterministic routing and remediation seed
  -> codex/sprint2-05-proxy         #148 Nginx proxy and isolated API test infrastructure
  -> codex/sprint2-06-browser       #148 browser API consumer and CI activation
  -> codex/sprint2-07-scope         #151 integrated architecture and Sprint scope
```

## Boundaries

- Review and merge children only in the order above; do not merge this tracker independently.
- Each child contains one cohesive work unit with its tests and user-facing documentation.
- Units 1, 3, 4, and 6 carry approved review-size exceptions; no evidence is compressed or removed.
- Database integration tests require an explicitly dedicated PostgreSQL DSN and must never use
  port 5432 implicitly during local packaging.
- Browser CI activation belongs to unit 6, after the unit 5 proxy infrastructure and browser
  consumer files both exist.

## Scope

The chain packages the frozen Sprint 2 source snapshot only. It adds no new product behavior,
does not merge any child, and preserves rollback at each child branch boundary.
