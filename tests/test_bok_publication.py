"""Real HTTP and PostgreSQL evidence for governed BoK collection publication (#33).

Failure modes listed before implementation:
- a published version is stored but not activated or projected, so an exact grant finds nothing;
- an exact replay writes a second version, catalog row or chunk, or answers 201 again;
- different content under a published version replaces or merges into the original;
- a caller without admin.write on the catalog stores content before being refused;
- an agent holding admin.write publishes directly instead of proposing to a human author;
- an oversized or malformed body (too many documents/chunks, long chunk, blank content,
  duplicate ids, unknown fields such as owner_id) reaches the database;
- the audit event or the idempotency record carries the published content;
- the owner read leaks to a caller without admin.read, or answers 200 for an absent version;
- the owner read loses who published a version and from where, a replay by another human
  rewrites them, or a seeded version claims an author it never had.
"""

import asyncio
import json
from typing import Any

import psycopg
from fastapi.testclient import TestClient
from test_control_acceptance import (
    ADMIN_KEY,
    DATABASE_URL,
    RESTRICTED_KEY,
    SEED_ENV,
    audit_key,  # noqa: F401 — pytest registers the imported fixture
    headers,
    migrated_acceptance_database,  # noqa: F401 — module-scoped autouse fixture
)

from sre_agent.bok.owner import seed_bok_demo
from sre_agent.persistence.database import Database

ROUTE = "/v1/bok/collections/versions"
MARKER = "Quiesce the payments queue before rotating its signing key"


def bundle(collection_id: str = "freelancer-runbooks", content: str = MARKER) -> dict[str, Any]:
    return {
        "collection_id": collection_id,
        "version": "1.0.0",
        "display_name": "Freelancer runbooks",
        "description": "Runbooks a freelancer keeps for their own services.",
        "documents": [
            {
                "document_id": "payments-key-rotation",
                "title": "Payments key rotation",
                "source_ref": "https://example.invalid/runbooks/payments",
                "chunks": [{"section_id": "steps", "chunk_index": 0, "content": content}],
            }
        ],
    }


def stored(collection_id: str) -> tuple[int, int, int, list[str]]:
    with psycopg.connect(DATABASE_URL) as connection:
        versions, resources, chunks = connection.execute(
            "SELECT (SELECT count(*) FROM bok_collection_versions WHERE collection_id=%(c)s),"
            " (SELECT count(*) FROM resources WHERE resource_type='bok_collection'"
            "  AND resource_id LIKE %(c)s || '@%%'),"
            " (SELECT count(*) FROM bok_section_chunks WHERE collection_id=%(c)s)",
            {"c": collection_id},
        ).fetchone()
        contents = [
            row[0]
            for row in connection.execute(
                "SELECT content FROM bok_section_chunks WHERE collection_id=%s", (collection_id,)
            )
        ]
    return versions, resources, chunks, contents


def test_published_version_is_searchable_under_an_exact_grant_and_replays_without_writes(
    client: TestClient,  # noqa: F811 — pytest fixture binding
) -> None:
    body = bundle()
    first = client.post(ROUTE, json=body, headers=headers(idempotency_key="bok-publish-33-first"))
    assert first.status_code == 201, first.text
    assert first.json()["resource_id"] == "freelancer-runbooks@1.0.0"
    assert first.json()["status"] == "active"
    assert MARKER not in first.text

    grant = client.post(
        "/v1/grants",
        json={
            "grant_id": "grant-bok-publish-33",
            "principal_id": "demo-human",
            "action": "bok.search",
            "resource": {
                "resource_type": "bok_collection",
                "resource_id": "freelancer-runbooks@1.0.0",
            },
            "effect": "allow",
        },
        headers=headers(idempotency_key="bok-publish-33-grant"),
    )
    assert grant.status_code == 201, grant.text
    search = client.post(
        "/v1/bok/collections/freelancer-runbooks/versions/1.0.0/search",
        json={"query": "rotating signing key"},
        headers=headers(SEED_ENV["DEMO_HUMAN_API_KEY"]),
    )
    assert search.status_code == 200, search.text
    assert [result["content"] for result in search.json()["results"]] == [MARKER]

    before = stored("freelancer-runbooks")
    same_key = client.post(
        ROUTE, json=body, headers=headers(idempotency_key="bok-publish-33-first")
    )
    new_key = client.post(ROUTE, json=body, headers=headers(idempotency_key="bok-publish-33-new"))
    assert same_key.status_code == new_key.status_code == 200, (same_key.text, new_key.text)
    assert same_key.json() == new_key.json() == first.json()
    assert stored("freelancer-runbooks") == before == (1, 1, 1, [MARKER])

    # Another human publishing the same content replays; the first author stays on record.
    other = client.post(
        "/v1/grants",
        json={
            "grant_id": "grant-bok-publish-33-other",
            "principal_id": "demo-human",
            "action": "admin.write",
            "resource": {"resource_type": "administrative_control", "resource_id": "catalog"},
            "effect": "allow",
        },
        headers=headers(idempotency_key="bok-publish-33-other-grant"),
    )
    assert other.status_code == 201, other.text
    replay = client.post(
        ROUTE,
        json=body,
        headers=headers(SEED_ENV["DEMO_HUMAN_API_KEY"], "bok-publish-33-other"),
    )
    assert replay.status_code == 200, replay.text

    read = client.get(
        "/v1/bok/collections/freelancer-runbooks/versions/1.0.0", headers=headers(ADMIN_KEY)
    )
    assert read.status_code == 200, read.text
    assert read.json()["status"] == "active"
    assert read.json()["published_by"] == "admin-human"
    assert read.json()["origin"] == "console"
    assert read.json()["documents"] == body["documents"]

    with psycopg.connect(DATABASE_URL) as connection:
        evidence = connection.execute(
            "SELECT to_jsonb(audit_events)::text FROM audit_events "
            "WHERE operation IN ('catalog.create', 'catalog.read')"
        ).fetchall()
        idempotency = connection.execute(
            "SELECT to_jsonb(idempotency_records)::text FROM idempotency_records "
            "WHERE canonical_path=%s",
            (ROUTE,),
        ).fetchall()
    assert evidence and idempotency
    assert all(MARKER not in row[0] for row in (*evidence, *idempotency))


def test_different_content_under_a_published_version_conflicts_and_keeps_the_original(
    client: TestClient,  # noqa: F811 — pytest fixture binding
) -> None:
    original = bundle("collision-runbooks")
    assert (
        client.post(ROUTE, json=original, headers=headers(idempotency_key="bok-collision-first"))
    ).status_code == 201
    changed = client.post(
        ROUTE,
        json=bundle("collision-runbooks", "Rotate the key without draining the queue."),
        headers=headers(idempotency_key="bok-collision-second"),
    )
    assert changed.status_code == 409, changed.text
    assert stored("collision-runbooks") == (1, 1, 1, [MARKER])


def test_publication_without_catalog_write_or_with_an_invalid_body_stores_nothing(
    client: TestClient,  # noqa: F811 — pytest fixture binding
) -> None:
    denied = client.post(
        ROUTE,
        json=bundle("denied-runbooks"),
        headers=headers(RESTRICTED_KEY, "bok-publish-denied-0001"),
    )
    unauthenticated = client.post(
        ROUTE,
        json=bundle("denied-runbooks"),
        headers={"Idempotency-Key": "bok-publish-denied-0002"},
    )
    grant = client.post(
        "/v1/grants",
        json={
            "grant_id": "grant-bok-publish-agent",
            "principal_id": "incident-harness",
            "action": "admin.write",
            "resource": {"resource_type": "administrative_control", "resource_id": "catalog"},
            "effect": "allow",
        },
        headers=headers(idempotency_key="bok-publish-agent-grant"),
    )
    assert grant.status_code == 201, grant.text
    agent = client.post(
        ROUTE,
        json=bundle("denied-runbooks"),
        headers=headers(SEED_ENV["INCIDENT_HARNESS_API_KEY"], "bok-publish-denied-0003"),
    )
    assert denied.status_code == agent.status_code == 403, (denied.text, agent.text)
    assert unauthenticated.status_code == 401, unauthenticated.text

    document = bundle()["documents"][0]
    chunk = document["chunks"][0]
    invalid: list[dict[str, Any]] = [
        {**bundle("invalid-runbooks"), "owner_id": "someone-else"},
        {**bundle("invalid-runbooks"), "version": "latest"},
        {**bundle("Invalid_Runbooks")},
        {
            **bundle("invalid-runbooks"),
            "documents": [{**document, "document_id": f"doc-{index}"} for index in range(21)],
        },
        {
            **bundle("invalid-runbooks"),
            "documents": [{**document, "chunks": [{**chunk, "chunk_index": i} for i in range(51)]}],
        },
        bundle("invalid-runbooks", "x" * 4001),
        bundle("invalid-runbooks", "   "),
        {**bundle("invalid-runbooks"), "documents": [document, document]},
        {**bundle("invalid-runbooks"), "documents": []},
    ]
    responses = [
        client.post(ROUTE, json=body, headers=headers(idempotency_key=f"bok-invalid-{index:04d}"))
        for index, body in enumerate(invalid)
    ]
    assert [response.status_code for response in responses] == [422] * len(invalid)
    assert stored("denied-runbooks") == stored("invalid-runbooks") == (0, 0, 0, [])
    assert stored("Invalid_Runbooks") == (0, 0, 0, [])


def test_owner_read_requires_catalog_read_and_reports_absent_versions(
    client: TestClient,  # noqa: F811 — pytest fixture binding
) -> None:
    path = "/v1/bok/collections/demo-absent/versions/9.9.9"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=headers(RESTRICTED_KEY)).status_code == 403
    assert client.get(path, headers=headers(ADMIN_KEY)).status_code == 404
    malformed = client.get("/v1/bok/collections/Bad_Id/versions/1.0.0", headers=headers())
    assert malformed.status_code == 422
    assert json.loads(malformed.text)["error"]["code"] == "validation_error"


def test_owner_read_of_a_seeded_version_names_no_author(
    client: TestClient,  # noqa: F811 — pytest fixture binding
) -> None:
    async def seed_demo() -> None:
        database = Database(DATABASE_URL)
        try:
            async with database.transaction() as session:
                await seed_bok_demo(session)
        finally:
            await database.dispose()

    asyncio.run(seed_demo())
    read = client.get(
        "/v1/bok/collections/demo-incident-response/versions/1.0.0", headers=headers(ADMIN_KEY)
    )
    assert read.status_code == 200, read.text
    assert (read.json()["published_by"], read.json()["origin"]) == (None, None)
