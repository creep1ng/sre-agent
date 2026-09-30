# Retrieve governed BoK content

BoK exposes bounded PostgreSQL lexical search and exact chunk reads over immutable,
versioned owner content. A catalog entry alone is not a searchable collection: the
owner version must be active and the caller must hold the matching exact-version grant.

## HTTP contract

Both endpoints require a bearer credential and a grant on resource type
`bok_collection`, resource ID `<collection_id>@<version>`:

| Action | Endpoint | Result |
| --- | --- | --- |
| `bok.search` | `POST /v1/bok/collections/{collection_id}/versions/{version}/search` | `{"results": [...]}` |
| `bok.read` | `GET /v1/bok/collections/{collection_id}/versions/{version}/chunks/{document_id}/{section_id}/{chunk_index}` | One chunk |

Search accepts `{"query": "rollback readiness", "limit": 5}`. The query is 1–300
characters; the integer limit is 1–20 (default 10). Unknown fields are rejected.
PostgreSQL English full-text ranking is descending, then document ID, section ID and
chunk index ascending. Each result carries collection ID, version, document ID,
section ID, chunk index, title, source reference and content; search adds a score.
Direct IDs never bypass authorization. Tags and visibility never grant access.

| HTTP status | Meaning |
| --- | --- |
| 200, empty results | Authorized search with no match |
| 401 | Missing or invalid authentication |
| 403 `resource_unavailable` | Exact collection/version access denied; no content/title/count enumeration |
| 404 `resource_not_found` | Authorized collection, absent exact chunk |
| 422 | Invalid path or bounded search request |
| 503 `index_unavailable` | Authorized catalog entry, but owner version is not active/ready |
| 503 `storage_unavailable` | Authorization or content storage failure, not an empty match |
| 503 `audit_unavailable` | Required audit persistence failed; intended content response suppressed |

## Isolation and evidence

Authorization facts and owner readiness are rechecked under shared row locks before
content SELECTs. Every new request rechecks committed catalog/grant/owner changes;
there is no cross-identity content cache. The service exposes metadata-only per-collection
content-operation counters for local diagnostics. HTTP acceptance tests independently
observe real SQL content SELECTs, including zero reads for denied/unready collections.

Persisted `bok.search`/`bok.read` audit events contain HMAC identity/resource references,
operation, decision and outcome, never the query or returned fragments. An authorization
store outage has no completed subject/decision to assert. If audit storage is also
unavailable, the producer fails closed.

## Repeat the controlled integration checks

From a configured checkout with synthetic local values in ignored `.env`:

```sh
docker compose --env-file .env --profile checks run --build --rm python-checks sh -c 'python scripts/assert_test_database_isolated.py && pytest -q tests/test_bok_persistence.py tests/test_bok_http.py tests/test_migrations.py tests/test_governed_authorization.py tests/test_usage_read_acceptance.py'
```

This is real PostgreSQL plus in-process HTTP acceptance, not hosted CI or a network
producer walkthrough. Network captures and human review are separate delivery evidence.
The two demo collections are synthetic; acceptance fixtures assign distinct exact grants.
No live provider, Jev evaluation, vector retrieval or downstream runtime integration is
part of this unit. Schema head is `20260929_16`, following the additive foundation merge.
Downgrade preserves usage audit vocabulary and refuses to discard BoK audit evidence.
