"""PostgreSQL-backed HTTP acceptance tests for governed BoK retrieval.

Failure modes listed before implementation:
- denied search/read accidentally touches chunk rows or leaks titles/counts;
- catalog-active but owner-unready/revoked versions deliver content;
- a collection ID or exact chunk ID bypasses its version grant;
- FTS uses session-dependent configuration or unstable tie ordering;
- no-match, denial, unready index, and a real PostgreSQL storage fault collapse;
- audit persistence accidentally records the query or returned chunk body.
"""

import asyncio
import json
import os
from collections import Counter
from datetime import UTC, datetime

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy import event

from sre_agent.application import create_application
from sre_agent.bok import retrieval as bok_retrieval
from sre_agent.bok.owner import DEMO_BUNDLES, activate_version, ingest_bundle, seed_bok_demo
from sre_agent.gateway.audit import AuditProjector
from sre_agent.persistence.database import Database
from sre_agent.persistence.models import GrantRow, ResourceRow
from sre_agent.persistence.seeds import SeedSettings, seed
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
DEMO_KEY = "sre_demo_0123456789abcdefghijklmnop"
RESTRICTED_KEY = "sre_rest_0123456789abcdefghijklmnop"
AUDIT_KEY = "issue332-bok-http-audit-key"
SEED_ENV = {
    "ADMIN_HUMAN_API_KEY": "sre_admn_0123456789abcdefghijklmnop",
    "DEMO_HUMAN_API_KEY": DEMO_KEY,
    "INCIDENT_HARNESS_API_KEY": "sre_inci_0123456789abcdefghijklmnop",
    "RESTRICTED_HARNESS_API_KEY": RESTRICTED_KEY,
    "TRIAGE_AGENT_MODEL": "openai/gpt-4o-mini",
    "TRIAGE_AGENT_PROVIDER": "openai",
    "REMEDIATION_AGENT_MODEL": "anthropic/claude-3.5-haiku",
    "REMEDIATION_AGENT_PROVIDER": "anthropic",
}


@pytest.fixture(scope="module", autouse=True)
def migrated_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS bok_section_chunks, bok_documents, bok_collection_versions, "
            "audit_events, skill_versions, grants, credentials, resources, mcp_tools, mcp_servers, "
            "principals, idempotency_records, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")

    async def bootstrap() -> None:
        database = Database(DATABASE_URL)
        try:
            assert await seed(database, SeedSettings.from_environment(SEED_ENV))
            async with database.transaction() as session:
                await seed_bok_demo(session)
                for action in ("bok.search", "bok.read"):
                    session.add(
                        GrantRow(
                            grant_id=f"grant-demo-{action.replace('.', '-')}",
                            principal_id="demo-human",
                            action=action,
                            resource_type="bok_collection",
                            resource_id="demo-incident-response@1.0.0",
                            effect="allow",
                            status="active",
                            created_at=datetime.now(UTC),
                        )
                    )
                for action in ("bok.search", "bok.read"):
                    session.add(
                        GrantRow(
                            grant_id=f"grant-restricted-{action.replace('.', '-')}",
                            principal_id="restricted-harness",
                            action=action,
                            resource_type="bok_collection",
                            resource_id="demo-platform-operations@1.0.0",
                            effect="allow",
                            status="active",
                            created_at=datetime.now(UTC),
                        )
                    )
                alternate = {
                    "collection_id": "demo-incident-response",
                    "version": "2.0.0",
                    "owner_id": "bok-platform",
                    "display_name": "Incident Response Basics v2",
                    "description": "Un-granted synthetic successor version.",
                    "visibility": "private",
                    "documents": [
                        {
                            "document_id": "incident-triage-v2",
                            "title": "Incident triage v2",
                            "source_ref": "synthetic://incident-response/triage-v2",
                            "chunks": [
                                {
                                    "section_id": "severity",
                                    "chunk_index": 0,
                                    "content": "Assign severity using impact and scope.",
                                }
                            ],
                        }
                    ],
                }
                await ingest_bundle(session, alternate)
                await activate_version(
                    session, "demo-incident-response", "2.0.0", expected_bundle=alternate
                )
                session.add(
                    ResourceRow(
                        resource_type="bok_collection",
                        resource_id="demo-incident-response@2.0.0",
                        status="active",
                        owner_id="bok-platform",
                        source="bok",
                        source_ref="demo-incident-response@2.0.0",
                        display_name="Incident Response Basics v2",
                        visibility="private",
                        description="Un-granted synthetic successor version.",
                        tags=["demo"],
                    )
                )
                unready = {
                    "collection_id": "demo-unready",
                    "version": "1.0.0",
                    "owner_id": "bok-platform",
                    "display_name": "Unready collection",
                    "description": "Synthetic indexing fixture.",
                    "visibility": "private",
                    "documents": [
                        {
                            "document_id": "empty-doc",
                            "title": "Not ready",
                            "source_ref": "synthetic://unready/empty",
                            "chunks": [
                                {
                                    "section_id": "empty",
                                    "chunk_index": 0,
                                    "content": "",
                                }
                            ],
                        }
                    ],
                }
                await ingest_bundle(session, unready)
                session.add(
                    ResourceRow(
                        resource_type="bok_collection",
                        resource_id="demo-unready@1.0.0",
                        status="active",
                        owner_id="bok-platform",
                        source="bok",
                        source_ref="demo-unready@1.0.0",
                        display_name="Unready collection",
                        visibility="private",
                        description="Synthetic indexing fixture.",
                        tags=["demo"],
                    )
                )
                await session.flush()
                session.add(
                    GrantRow(
                        grant_id="grant-demo-unready-search",
                        principal_id="demo-human",
                        action="bok.search",
                        resource_type="bok_collection",
                        resource_id="demo-unready@1.0.0",
                        effect="allow",
                        status="active",
                        created_at=datetime.now(UTC),
                    )
                )
                ordered = {
                    "collection_id": "demo-stable-order",
                    "version": "1.0.0",
                    "owner_id": "bok-platform",
                    "display_name": "Stable order collection",
                    "description": "Synthetic deterministic search fixture.",
                    "visibility": "private",
                    "documents": [
                        {
                            "document_id": document_id,
                            "title": f"Document {document_id}",
                            "source_ref": f"synthetic://stable-order/{document_id}",
                            "chunks": [
                                {
                                    "section_id": section,
                                    "chunk_index": index,
                                    "content": "operations stable match",
                                }
                                for section, index in (
                                    ("zulu", 0),
                                    ("operations", 1),
                                    ("operations", 0),
                                )
                            ]
                            if document_id != "weighted-doc"
                            else [
                                {
                                    "section_id": "operations",
                                    "chunk_index": 0,
                                    "content": (
                                        "operations stable match "
                                        "operations stable match operations stable match"
                                    ),
                                }
                            ],
                        }
                        for document_id in ("zeta-doc", "weighted-doc", "alpha-doc")
                    ],
                }
                await ingest_bundle(session, ordered)
                await activate_version(
                    session, "demo-stable-order", "1.0.0", expected_bundle=ordered
                )
                session.add(
                    ResourceRow(
                        resource_type="bok_collection",
                        resource_id="demo-stable-order@1.0.0",
                        status="active",
                        owner_id="bok-platform",
                        source="bok",
                        source_ref="demo-stable-order@1.0.0",
                        display_name="Stable order collection",
                        visibility="private",
                        description="Synthetic deterministic search fixture.",
                        tags=["demo"],
                    )
                )
                await session.flush()
                session.add(
                    GrantRow(
                        grant_id="grant-demo-stable-order-search",
                        principal_id="demo-human",
                        action="bok.search",
                        resource_type="bok_collection",
                        resource_id="demo-stable-order@1.0.0",
                        effect="allow",
                        status="active",
                        created_at=datetime.now(UTC),
                    )
                )
        finally:
            await database.dispose()

    asyncio.run(bootstrap())


@pytest.fixture(autouse=True)
def isolated_mutations(migrated_database):
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("TRUNCATE TABLE audit_events")
    try:
        yield
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute(
                "UPDATE grants SET status='active' WHERE grant_id='grant-demo-stable-order-search'"
            )
            connection.execute(
                "UPDATE bok_collection_versions SET status='active' "
                "WHERE collection_id='demo-incident-response' AND version='1.0.0'"
            )


@pytest.fixture
def client(migrated_database: None):
    application = create_application(Settings(DATABASE_URL, audit_hmac_key=AUDIT_KEY))
    with TestClient(application) as test_client:
        yield test_client


def _url(collection: str, version: str = "1.0.0") -> str:
    return f"/v1/bok/collections/{collection}/versions/{version}"


def test_authorized_search_has_versioned_provenance_and_stable_order(client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {DEMO_KEY}"}
    url = _url("demo-stable-order") + "/search"
    response = client.post(url, headers=headers, json={"query": "operations stable", "limit": 10})
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert [(item["document_id"], item["section_id"], item["chunk_index"]) for item in results] == [
        ("weighted-doc", "operations", 0),
        ("alpha-doc", "operations", 0),
        ("alpha-doc", "operations", 1),
        ("alpha-doc", "zulu", 0),
        ("zeta-doc", "operations", 0),
        ("zeta-doc", "operations", 1),
        ("zeta-doc", "zulu", 0),
    ]
    assert results[0]["score"] > results[1]["score"]
    assert all(item["score"] == results[1]["score"] for item in results[1:])
    assert all(
        item["collection_id"] == "demo-stable-order" and item["version"] == "1.0.0"
        for item in results
    )
    repeated = client.post(url, headers=headers, json={"query": "operations stable", "limit": 3})
    assert repeated.json()["results"] == results[:3]


def test_denied_search_and_direct_id_read_do_not_read_or_enumerate(client: TestClient) -> None:
    service = client.app.state.bok_service
    before = dict(service.content_reads_by_collection)
    denied_search = client.post(
        _url("demo-platform-operations") + "/search",
        headers={"Authorization": f"Bearer {DEMO_KEY}"},
        json={"query": "rollback readiness", "limit": 5},
    )
    denied_read = client.get(
        _url("demo-platform-operations") + "/chunks/deployment-checks/preflight/0",
        headers={"Authorization": f"Bearer {DEMO_KEY}"},
    )
    denied_version = client.post(
        _url("demo-incident-response", version="2.0.0") + "/search",
        headers={"Authorization": f"Bearer {DEMO_KEY}"},
        json={"query": "severity impact", "limit": 5},
    )
    assert denied_search.status_code == denied_read.status_code == denied_version.status_code == 403
    assert denied_search.json()["error"] == denied_read.json()["error"]
    assert denied_version.json()["error"] == denied_search.json()["error"]
    assert "Deployment checks" not in denied_search.text
    assert service.content_reads_by_collection == before


def test_no_match_unready_and_authorized_chunk_read_are_distinct(client: TestClient) -> None:
    headers = {"Authorization": f"Bearer {DEMO_KEY}"}
    no_match = client.post(
        _url("demo-incident-response") + "/search",
        headers=headers,
        json={"query": "nonexistent-needle", "limit": 5},
    )
    assert no_match.status_code == 200
    assert no_match.json()["results"] == []
    unready = client.post(
        _url("demo-unready") + "/search",
        headers=headers,
        json={"query": "anything", "limit": 5},
    )
    assert unready.status_code == 503
    assert unready.json()["error"]["code"] == "index_unavailable"
    assert client.app.state.bok_service.content_reads_by_collection["demo-unready@1.0.0"] == 0
    read = client.get(
        _url("demo-incident-response") + "/chunks/incident-triage/severity/0",
        headers=headers,
    )
    assert read.status_code == 200
    result = read.json()
    assert result["collection_id"] == "demo-incident-response"
    assert result["version"] == "1.0.0"
    assert result["document_id"] == "incident-triage"
    assert result["title"] == "Incident triage"
    assert "Assign severity" in result["content"]


def test_revoked_owner_version_is_not_delivered_and_audit_has_no_content(
    client: TestClient,
) -> None:
    service = client.app.state.bok_service
    database = client.app.state.database

    headers = {"Authorization": f"Bearer {DEMO_KEY}"}
    assert (
        client.post(
            _url("demo-stable-order") + "/search",
            headers=headers,
            json={"query": "operations stable"},
        ).status_code
        == 200
    )
    assert (
        client.get(
            _url("demo-incident-response") + "/chunks/incident-triage/severity/0", headers=headers
        ).status_code
        == 200
    )
    incident_reads_before_revoke = service.content_reads_by_collection[
        "demo-incident-response@1.0.0"
    ]
    stable_reads_before_revoke = service.content_reads_by_collection["demo-stable-order@1.0.0"]

    async def revoke_grant() -> None:
        async with database.transaction() as session:
            row = await session.get(GrantRow, "grant-demo-stable-order-search")
            assert row is not None
            row.status = "revoked"

    asyncio.run(revoke_grant())
    denied_by_grant = client.post(
        _url("demo-stable-order") + "/search",
        headers={"Authorization": f"Bearer {DEMO_KEY}"},
        json={"query": "operations stable", "limit": 5},
    )
    assert denied_by_grant.status_code == 403
    assert (
        service.content_reads_by_collection["demo-stable-order@1.0.0"] == stable_reads_before_revoke
    )

    async def revoke() -> None:
        from sre_agent.persistence.models import BoKCollectionVersionRow

        async with database.transaction() as session:
            row = await session.get(BoKCollectionVersionRow, ("demo-incident-response", "1.0.0"))
            assert row is not None
            row.status = "revoked"

    asyncio.run(revoke())
    denied_by_owner = client.get(
        _url("demo-incident-response") + "/chunks/incident-triage/severity/0",
        headers={"Authorization": f"Bearer {DEMO_KEY}"},
    )
    assert denied_by_owner.status_code == 503
    assert denied_by_owner.json()["error"]["code"] == "index_unavailable"
    assert (
        service.content_reads_by_collection["demo-incident-response@1.0.0"]
        == incident_reads_before_revoke
    )

    with psycopg.connect(DATABASE_URL) as connection:
        events = connection.execute(
            "SELECT operation, content_state, to_jsonb(audit_events)::text "
            "FROM audit_events WHERE operation IN ('bok.search','bok.read')"
        ).fetchall()
    assert events
    assert all(row[1] == "absent" for row in events)
    serialized = " ".join(row[2] for row in events)
    for private_value in (
        "operations stable match",
        "Assign severity from customer impact",
        "nonexistent-needle",
        "rollback readiness",
    ):
        assert private_value not in serialized


def test_postgresql_content_storage_failure_is_not_a_no_match(client: TestClient) -> None:
    async def restore_search_grant() -> None:
        async with client.app.state.database.transaction() as session:
            row = await session.get(GrantRow, "grant-demo-stable-order-search")
            assert row is not None
            row.status = "active"

    asyncio.run(restore_search_grant())
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        try:
            connection.execute("ALTER TABLE bok_section_chunks RENAME TO unavailable_bok_chunks")
            response = client.post(
                _url("demo-platform-operations") + "/search",
                headers={"Authorization": f"Bearer {DEMO_KEY}"},
                json={"query": "rollback readiness", "limit": 5},
            )
            assert response.status_code == 403
            response = client.post(
                _url("demo-stable-order") + "/search",
                headers={"Authorization": f"Bearer {DEMO_KEY}"},
                json={"query": "severity impact", "limit": 5},
            )
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "storage_unavailable"
        finally:
            connection.execute("ALTER TABLE unavailable_bok_chunks RENAME TO bok_section_chunks")


@pytest.fixture
def sql_content_reads(client):
    """Observe real SELECTs independently of service counters; retain no content/query."""
    reads = Counter()
    engine = client.app.state.database.engine.sync_engine

    def record_read(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and any(
            table in statement for table in ("bok_section_chunks", "bok_documents")
        ):
            bound = context.compiled_parameters[0] if context.compiled_parameters else {}
            collection = bound.get("collection_id_1", "unscoped")
            version = bound.get("version_1", "unscoped")
            reads[f"{collection}@{version}"] += 1

    event.listen(engine, "before_cursor_execute", record_read)
    try:
        yield reads
    finally:
        event.remove(engine, "before_cursor_execute", record_read)


def test_both_demo_collections_are_isolated_by_identity_with_complete_provenance(
    client, sql_content_reads
):
    query = "severity OR rollback"
    projector = AuditProjector(AUDIT_KEY.encode())
    for bundle, key, principal in zip(
        DEMO_BUNDLES, (DEMO_KEY, RESTRICTED_KEY), ("demo-human", "restricted-harness"), strict=True
    ):
        collection = bundle["collection_id"]
        document = bundle["documents"][0]
        chunk = document["chunks"][0]
        headers = {"Authorization": f"Bearer {key}"}
        expected = {
            "collection_id": collection,
            "version": "1.0.0",
            "document_id": document["document_id"],
            "title": document["title"],
            "source_ref": document["source_ref"],
            **chunk,
        }
        sql_content_reads.clear()
        first = client.post(_url(collection) + "/search", headers=headers, json={"query": query})
        repeated = client.post(_url(collection) + "/search", headers=headers, json={"query": query})
        assert first.status_code == repeated.status_code == 200
        assert first.json() == repeated.json()
        match = first.json()["results"][0]
        assert match["score"] > 0
        assert {k: v for k, v in match.items() if k != "score"} == expected
        direct = client.get(
            _url(collection) + f"/chunks/{document['document_id']}/{chunk['section_id']}/0",
            headers=headers,
        )
        assert direct.status_code == 200
        assert direct.json() == expected
        missing = client.get(_url(collection) + "/chunks/unknown/unknown/0", headers=headers)
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "resource_not_found"
        assert sql_content_reads == {f"{collection}@1.0.0": 4}

        # The same collection/query under the other principal must not reuse warm authority.
        other_key = RESTRICTED_KEY if key == DEMO_KEY else DEMO_KEY
        other_headers = {"Authorization": f"Bearer {other_key}"}
        denied = client.post(
            _url(collection) + "/search", headers=other_headers, json={"query": query}
        )
        denied_direct = client.get(
            _url(collection) + f"/chunks/{document['document_id']}/{chunk['section_id']}/0",
            headers=other_headers,
        )
        assert denied.status_code == denied_direct.status_code == 403
        assert denied.json()["error"] == denied_direct.json()["error"]
        assert document["title"] not in denied.text and "results" not in denied.json()
        assert sql_content_reads == {f"{collection}@1.0.0": 4}

        with psycopg.connect(DATABASE_URL) as connection:
            rows = connection.execute(
                "SELECT to_jsonb(audit_events) FROM audit_events "
                "WHERE operation IN ('bok.search','bok.read') "
                "AND resource->'resource_ref'->>'digest'=%s",
                (projector.reference("resource", f"bok_collection/{collection}@1.0.0").digest,),
            ).fetchall()
        events = [row[0] for row in rows]
        allowed = [row for row in events if row["response_status"] == 200]
        assert {row["operation"] for row in allowed} == {"bok.search", "bok.read"}
        assert all(
            row["identity"]["principal_ref"]["digest"]
            == projector.reference("principal", principal).digest
            for row in allowed
        )
        assert all(row["policy_decision"]["decision"] == "allow" for row in allowed)
        denied_events = [row for row in events if row["response_status"] == 403]
        assert len(denied_events) >= 2
        assert all(row["policy_decision"]["decision"] == "deny" for row in denied_events)
        assert all(
            row["content_state"] == "absent" and row["redacted_content"] is None for row in events
        )
        serialized = json.dumps(events, default=str)
        for private in (query, chunk["content"], document["title"], key, other_key, principal):
            assert private not in serialized


@pytest.mark.parametrize("change", ["catalog", "grant", "owner"])
def test_committed_authority_change_stops_warm_reads(client, sql_content_reads, change):
    headers = {"Authorization": f"Bearer {RESTRICTED_KEY}"}
    url = _url("demo-platform-operations") + "/search"
    body = {"query": "rollback"}
    assert client.post(url, headers=headers, json=body).status_code == 200
    before = sql_content_reads.copy()
    updates = {
        "catalog": ("resources", "resource_id", "demo-platform-operations@1.0.0", "inactive"),
        "grant": ("grants", "grant_id", "grant-restricted-bok-search", "revoked"),
        "owner": (
            "bok_collection_versions",
            "collection_id",
            "demo-platform-operations",
            "revoked",
        ),
    }
    table, column, value, status = updates[change]
    statement = sql.SQL("UPDATE {} SET status=%s WHERE {}=%s").format(
        sql.Identifier(table), sql.Identifier(column)
    )
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        try:
            connection.execute(statement, (status, value))
            response = client.post(url, headers=headers, json=body)
            assert response.status_code == (503 if change == "owner" else 403)
            assert response.json()["error"]["code"] == (
                "index_unavailable" if change == "owner" else "resource_unavailable"
            )
            assert sql_content_reads == before
        finally:
            connection.execute(statement, ("active", value))
    assert client.post(url, headers=headers, json=body).status_code == 200
    assert sql_content_reads["demo-platform-operations@1.0.0"] == 2


@pytest.mark.parametrize(
    ("change", "expected_cause"),
    [
        ("principal", "principal_inactive"),
        ("resource", "resource_inactive"),
        ("grant", "grant_not_applicable"),
    ],
)
def test_locked_authority_recheck_audits_actual_denial_cause(
    client, sql_content_reads, monkeypatch, change, expected_cause
):
    """A committed change between authorization and locks must retain its real audit cause."""
    headers = {"Authorization": f"Bearer {RESTRICTED_KEY}"}
    collection = "demo-platform-operations"
    resource_id = f"{collection}@1.0.0"
    grant_id = "grant-restricted-bok-search"
    url = _url(collection) + "/search"
    body = {"query": "rollback"}
    assert client.post(url, headers=headers, json=body).status_code == 200
    content_reads_before = sql_content_reads.copy()
    original = bok_retrieval.BoKOwnerRepository.lock_current_authority
    applied = False

    def apply_committed_change() -> None:
        changes = {
            "principal": [
                "UPDATE principals SET status='inactive', updated_at=now() "
                "WHERE principal_id='restricted-harness'",
                "UPDATE grants SET status='revoked' WHERE grant_id=%s",
            ],
            "resource": [
                "UPDATE resources SET status='inactive' "
                "WHERE resource_type='bok_collection' AND resource_id=%s",
                "UPDATE grants SET status='revoked' WHERE grant_id=%s",
            ],
            "grant": ["UPDATE grants SET status='revoked' WHERE grant_id=%s"],
        }
        parameters = {
            "principal": [(), (grant_id,)],
            "resource": [(resource_id,), (grant_id,)],
            "grant": [(grant_id,)],
        }[change]
        with psycopg.connect(DATABASE_URL) as connection:
            for statement, params in zip(changes[change], parameters, strict=True):
                connection.execute(statement, params)

    async def change_before_locked_read(repository, context, action, locked_resource_id):
        nonlocal applied
        if not applied:
            applied = True
            apply_committed_change()
        return await original(repository, context, action, locked_resource_id)

    monkeypatch.setattr(
        bok_retrieval.BoKOwnerRepository,
        "lock_current_authority",
        change_before_locked_read,
    )
    try:
        response = client.post(url, headers=headers, json=body)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "resource_unavailable"
        assert response.json()["retryable"] is False
        assert sql_content_reads == content_reads_before
        with psycopg.connect(DATABASE_URL) as connection:
            event_row = connection.execute(
                "SELECT to_jsonb(audit_events)::text FROM audit_events "
                "WHERE operation='bok.search' AND response_status=403 "
                "ORDER BY occurred_at DESC LIMIT 1"
            ).fetchone()
        assert event_row is not None
        event = json.loads(event_row[0])
        assert event["authorization_denial_cause"] == expected_cause
        assert event["policy_decision"] == {
            "decision": "deny",
            "reason_code": "no_matching_grant",
        }
        serialized = json.dumps(event)
        assert body["query"] not in serialized
        assert RESTRICTED_KEY not in serialized
        for document in DEMO_BUNDLES[1]["documents"]:
            for chunk in document["chunks"]:
                assert chunk["content"] not in serialized
        assert event["content_state"] == "absent"
    finally:
        restores = {
            "principal": [
                "UPDATE principals SET status='active', updated_at=now() "
                "WHERE principal_id='restricted-harness'",
                "UPDATE grants SET status='active' WHERE grant_id=%s",
            ],
            "resource": [
                "UPDATE resources SET status='active' "
                "WHERE resource_type='bok_collection' AND resource_id=%s",
                "UPDATE grants SET status='active' WHERE grant_id=%s",
            ],
            "grant": ["UPDATE grants SET status='active' WHERE grant_id=%s"],
        }
        parameters = {
            "principal": [(), (grant_id,)],
            "resource": [(resource_id,), (grant_id,)],
            "grant": [(grant_id,)],
        }[change]
        with psycopg.connect(DATABASE_URL) as connection:
            for statement, params in zip(restores[change], parameters, strict=True):
                connection.execute(statement, params)
    assert client.post(url, headers=headers, json=body).status_code == 200


def test_unready_unauthenticated_and_wrong_version_read_no_content(client, sql_content_reads):
    headers = {"Authorization": f"Bearer {DEMO_KEY}"}
    for collection, version, auth, expected in (
        ("demo-unready", "1.0.0", headers, 503),
        ("demo-incident-response", "2.0.0", headers, 403),
        ("demo-incident-response", "1.0.0", {}, 401),
    ):
        response = client.post(
            _url(collection, version) + "/search", headers=auth, json={"query": "severity"}
        )
        assert response.status_code == expected
    assert sql_content_reads == {}


@pytest.mark.parametrize("table", ["credentials", "grants"])
def test_authorization_storage_failure_is_safe_and_not_empty(client, sql_content_reads, table):
    rename = sql.SQL("ALTER TABLE {} RENAME TO {}").format(
        sql.Identifier(table), sql.Identifier(f"unavailable_{table}")
    )
    restore = sql.SQL("ALTER TABLE {} RENAME TO {}").format(
        sql.Identifier(f"unavailable_{table}"), sql.Identifier(table)
    )
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        try:
            connection.execute(rename)
            # A real authorization-store outage must be a bounded producer response, not 500.
            with TestClient(client.app, raise_server_exceptions=False) as fault_client:
                response = fault_client.post(
                    _url("demo-incident-response") + "/search",
                    headers={"Authorization": f"Bearer {DEMO_KEY}"},
                    json={"query": "severity"},
                )
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "storage_unavailable"
            assert response.json()["retryable"] is True
            assert "severity" not in response.text and "SELECT" not in response.text
            assert sql_content_reads == {}
        finally:
            connection.execute(restore)


def test_migrated_producer_is_ready(client):
    response = client.get("/health/ready")
    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "body",
    [
        {"query": ""},
        {"query": "x" * 301},
        {"query": "severity", "limit": 0},
        {"query": "severity", "limit": 21},
        {"query": "severity", "limit": "2"},
        {"query": "severity", "evaluation_mode": "shadow"},
    ],
)
def test_search_contract_is_bounded_without_optional_evaluation(client, sql_content_reads, body):
    response = client.post(
        _url("demo-incident-response") + "/search",
        headers={"Authorization": f"Bearer {DEMO_KEY}"},
        json=body,
    )
    assert response.status_code == 422
    assert sql_content_reads == {}


def test_audit_storage_failure_suppresses_authorized_content(client):
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        try:
            connection.execute("ALTER TABLE audit_events RENAME TO unavailable_audit_events")
            response = client.get(
                _url("demo-incident-response") + "/chunks/incident-triage/severity/0",
                headers={"Authorization": f"Bearer {DEMO_KEY}"},
            )
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "audit_unavailable"
            assert "Assign severity" not in response.text
        finally:
            connection.execute("ALTER TABLE unavailable_audit_events RENAME TO audit_events")


def test_persisted_bok_audit_blocks_lossy_downgrade(client):
    response = client.post(
        _url("demo-incident-response") + "/search",
        headers={"Authorization": f"Bearer {DEMO_KEY}"},
        json={"query": "severity"},
    )
    assert response.status_code == 200
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    with pytest.raises(RuntimeError, match="cannot downgrade BoK merge while BoK audit evidence"):
        command.downgrade(config, "20260930_17")
    with psycopg.connect(DATABASE_URL) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260930_21",
        )
        assert connection.execute(
            "SELECT count(*) FROM audit_events WHERE operation='bok.search'"
        ).fetchone() == (1,)
