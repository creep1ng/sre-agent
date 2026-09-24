"""PostgreSQL acceptance tests for immutable, versioned BoK owner storage.

Failure modes covered: replay duplicating child rows; changed bytes silently
overwriting an existing collection version; empty/unready activation; and a
demo bootstrap that is not deterministic or does not create two collections.
"""

import os

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from sre_agent.bok.owner import (
    BoKVersionCollision,
    activate_version,
    ingest_bundle,
    seed_bok_demo,
)
from sre_agent.persistence.database import Database
from sre_agent.persistence.models import ResourceRow

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)


@pytest.fixture(scope="module", autouse=True)
def migrated_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS consumption_reservations, consumption_limit_policies, "
            "bok_section_chunks, bok_documents, "
            "bok_collection_versions, "
            "audit_events, skill_versions, grants, credentials, resources, alert_triage, "
            "principals, "
            "idempotency_records, "
            "mcp_tools, mcp_servers, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")


def bundle(collection_id: str = "manual", version: str = "1.0.0", content: str = "alpha"):
    return {
        "collection_id": collection_id,
        "version": version,
        "owner_id": "bok-platform",
        "display_name": "Manual Collection",
        "description": "Synthetic acceptance corpus.",
        "visibility": "private",
        "documents": [
            {
                "document_id": "doc-1",
                "title": "First document",
                "source_ref": "synthetic://manual/doc-1",
                "chunks": [{"section_id": "section-1", "chunk_index": 0, "content": content}],
            }
        ],
    }


@pytest.mark.asyncio
async def test_same_version_replay_is_idempotent_and_changed_bytes_collide() -> None:
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            assert await ingest_bundle(session, bundle()) is True
        async with database.transaction() as session:
            assert await ingest_bundle(session, bundle()) is False
        async with database.sessions() as session:
            rows = await session.execute(
                text("SELECT count(*) FROM bok_section_chunks WHERE collection_id='manual'")
            )
            assert rows.scalar_one() == 1
        with pytest.raises(BoKVersionCollision):
            async with database.transaction() as session:
                await ingest_bundle(session, bundle(content="changed bytes"))
    finally:
        await database.dispose()


@pytest.mark.parametrize(
    "drift",
    [
        "chunk_content_update",
        "chunk_delete",
        "document_metadata_update",
        "document_content_hash_update",
    ],
)
@pytest.mark.asyncio
async def test_exact_replay_rejects_persisted_child_drift_without_repairing(drift: str) -> None:
    """An unchanged owner manifest cannot certify mutated or missing child rows."""
    collection_id = f"replay-integrity-{drift}"
    original = bundle(collection_id=collection_id, content="original content")
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            assert await ingest_bundle(session, original) is True
        async with database.sessions() as session:
            original_manifest = (
                await session.execute(
                    text(
                        "SELECT manifest_sha256 FROM bok_collection_versions "
                        "WHERE collection_id=:collection_id AND version='1.0.0'"
                    ),
                    {"collection_id": collection_id},
                )
            ).scalar_one()

        async with database.transaction() as session:
            if drift == "chunk_content_update":
                result = await session.execute(
                    text(
                        "UPDATE bok_section_chunks SET content='changed child content' "
                        "WHERE collection_id=:collection_id AND version='1.0.0' "
                        "AND document_id='doc-1' AND section_id='section-1' AND chunk_index=0"
                    ),
                    {"collection_id": collection_id},
                )
                assert result.rowcount == 1
            elif drift == "chunk_delete":
                result = await session.execute(
                    text(
                        "DELETE FROM bok_section_chunks WHERE collection_id=:collection_id "
                        "AND version='1.0.0' AND document_id='doc-1' "
                        "AND section_id='section-1' AND chunk_index=0"
                    ),
                    {"collection_id": collection_id},
                )
                assert result.rowcount == 1
            elif drift == "document_metadata_update":
                result = await session.execute(
                    text(
                        "UPDATE bok_documents SET title='changed child metadata' "
                        "WHERE collection_id=:collection_id AND version='1.0.0' "
                        "AND document_id='doc-1'"
                    ),
                    {"collection_id": collection_id},
                )
                assert result.rowcount == 1
            else:
                result = await session.execute(
                    text(
                        "UPDATE bok_documents SET content_sha256=:content_sha256 "
                        "WHERE collection_id=:collection_id AND version='1.0.0' "
                        "AND document_id='doc-1'"
                    ),
                    {"collection_id": collection_id, "content_sha256": "0" * 64},
                )
                assert result.rowcount == 1

        async with database.sessions() as session:
            persisted_manifest = (
                await session.execute(
                    text(
                        "SELECT manifest_sha256 FROM bok_collection_versions "
                        "WHERE collection_id=:collection_id AND version='1.0.0'"
                    ),
                    {"collection_id": collection_id},
                )
            ).scalar_one()
        assert persisted_manifest == original_manifest

        with pytest.raises(BoKVersionCollision, match="collection_version_collision"):
            async with database.transaction() as session:
                await ingest_bundle(session, original)

        async with database.sessions() as session:
            if drift == "chunk_content_update":
                persisted_child = (
                    await session.execute(
                        text(
                            "SELECT content FROM bok_section_chunks "
                            "WHERE collection_id=:collection_id AND version='1.0.0' "
                            "AND document_id='doc-1' AND section_id='section-1' AND chunk_index=0"
                        ),
                        {"collection_id": collection_id},
                    )
                ).scalar_one()
                assert persisted_child == "changed child content"
            elif drift == "chunk_delete":
                chunk_count = (
                    await session.execute(
                        text(
                            "SELECT count(*) FROM bok_section_chunks "
                            "WHERE collection_id=:collection_id AND version='1.0.0'"
                        ),
                        {"collection_id": collection_id},
                    )
                ).scalar_one()
                assert chunk_count == 0
            elif drift == "document_metadata_update":
                persisted_child = (
                    await session.execute(
                        text(
                            "SELECT title FROM bok_documents "
                            "WHERE collection_id=:collection_id AND version='1.0.0' "
                            "AND document_id='doc-1'"
                        ),
                        {"collection_id": collection_id},
                    )
                ).scalar_one()
                assert persisted_child == "changed child metadata"
            else:
                persisted_child = (
                    await session.execute(
                        text(
                            "SELECT content_sha256 FROM bok_documents "
                            "WHERE collection_id=:collection_id AND version='1.0.0' "
                            "AND document_id='doc-1'"
                        ),
                        {"collection_id": collection_id},
                    )
                ).scalar_one()
                assert persisted_child == "0" * 64
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_activation_requires_ready_owner_version_and_seed_converges() -> None:
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            assert await seed_bok_demo(session) is True
            empty_bundle = bundle(collection_id="empty", content="")
            await ingest_bundle(session, empty_bundle)
        with pytest.raises(ValueError, match="not_ready"):
            async with database.transaction() as session:
                await activate_version(session, "empty", "1.0.0", expected_bundle=empty_bundle)
        async with database.transaction() as session:
            assert await seed_bok_demo(session) is False
            rows = await session.execute(
                text(
                    "SELECT collection_id, version, status FROM bok_collection_versions "
                    "WHERE collection_id LIKE 'demo-%' ORDER BY collection_id"
                )
            )
            assert rows.all() == [
                ("demo-incident-response", "1.0.0", "active"),
                ("demo-platform-operations", "1.0.0", "active"),
            ]
    finally:
        await database.dispose()


def two_chunk_bundle(collection_id: str):
    value = bundle(collection_id=collection_id)
    value["documents"] = [
        {
            "document_id": "doc-z",
            "title": "Z document",
            "source_ref": "synthetic://manual/doc-z",
            "chunks": [
                {"section_id": "z-last", "chunk_index": 1, "content": "zeta second"},
                {"section_id": "z-first", "chunk_index": 0, "content": "zeta first"},
            ],
        }
    ]
    return value


def partial_document_bundle(collection_id: str, *, blank_chunk: bool = False):
    value = two_chunk_bundle(collection_id)
    value["documents"].append(
        {
            "document_id": "doc-empty",
            "title": "Empty document",
            "source_ref": "synthetic://manual/doc-empty",
            "chunks": [],
        }
    )
    if blank_chunk:
        value["documents"][0]["chunks"][0]["content"] = "   "
    return value


def unordered_complete_bundle(collection_id: str):
    value = two_chunk_bundle(collection_id)
    value["documents"].append(
        {
            "document_id": "doc-a",
            "title": "A document",
            "source_ref": "synthetic://manual/doc-a",
            "chunks": [
                {"section_id": "a-last", "chunk_index": 1, "content": "alpha second"},
                {"section_id": "a-first", "chunk_index": 0, "content": "alpha first"},
            ],
        }
    )
    return value


async def insert_inactive_catalog_projection(session, collection_id: str, version: str) -> None:
    resource_id = f"{collection_id}@{version}"
    session.add(
        ResourceRow(
            resource_type="bok_collection",
            resource_id=resource_id,
            status="inactive",
            owner_id="bok-platform",
            source="bok",
            source_ref=resource_id,
            display_name="Inactive test projection",
            visibility="private",
            description="Synthetic activation integrity test.",
            tags=["test"],
        )
    )
    await session.flush()


@pytest.mark.parametrize("blank_chunk", [False, True], ids=["partial-document", "blank-chunk"])
@pytest.mark.asyncio
async def test_incomplete_document_children_never_become_ready(blank_chunk: bool) -> None:
    collection_id = f"readiness-gap-{blank_chunk}"
    source = partial_document_bundle(collection_id, blank_chunk=blank_chunk)
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            assert await ingest_bundle(session, source) is True
        async with database.sessions() as session:
            persisted = (
                await session.execute(
                    text(
                        "SELECT status FROM bok_collection_versions "
                        "WHERE collection_id=:collection_id AND version='1.0.0'"
                    ),
                    {"collection_id": collection_id},
                )
            ).scalar_one()
        assert persisted == "indexing"
    finally:
        await database.dispose()


@pytest.mark.parametrize("drift", ["delete", "change"], ids=["missing-chunk", "changed-chunk"])
@pytest.mark.asyncio
async def test_activation_rejects_persisted_chunk_drift_without_lifecycle_changes(
    drift: str,
) -> None:
    collection_id = f"activation-drift-{drift}"
    source = two_chunk_bundle(collection_id)
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            assert await ingest_bundle(session, source) is True
            await insert_inactive_catalog_projection(session, collection_id, "1.0.0")
        async with database.transaction() as session:
            if drift == "delete":
                result = await session.execute(
                    text(
                        "DELETE FROM bok_section_chunks WHERE collection_id=:collection_id "
                        "AND version='1.0.0' AND document_id='doc-z' "
                        "AND section_id='z-last' AND chunk_index=1"
                    ),
                    {"collection_id": collection_id},
                )
            else:
                result = await session.execute(
                    text(
                        "UPDATE bok_section_chunks SET content='changed nonblank content' "
                        "WHERE collection_id=:collection_id AND version='1.0.0' "
                        "AND document_id='doc-z' AND section_id='z-last' AND chunk_index=1"
                    ),
                    {"collection_id": collection_id},
                )
            assert result.rowcount == 1

        async with database.sessions() as session:
            catalog_updated_at_before_rejection = (
                await session.execute(
                    text(
                        "SELECT updated_at FROM resources WHERE resource_type='bok_collection' "
                        "AND resource_id=:resource_id"
                    ),
                    {"resource_id": f"{collection_id}@1.0.0"},
                )
            ).scalar_one()

        rejected = False
        try:
            async with database.transaction() as session:
                await activate_version(session, collection_id, "1.0.0", expected_bundle=source)
        except BoKVersionCollision:
            rejected = True
        assert rejected, "activation must reject missing or changed persisted children"

        async with database.sessions() as session:
            owner_status, catalog_status, catalog_updated_at_after_rejection = (
                await session.execute(
                    text(
                        "SELECT v.status, r.status, r.updated_at "
                        "FROM bok_collection_versions AS v "
                        "JOIN resources AS r ON r.resource_type='bok_collection' "
                        "AND r.resource_id=:resource_id "
                        "WHERE v.collection_id=:collection_id AND v.version='1.0.0'"
                    ),
                    {
                        "collection_id": collection_id,
                        "resource_id": f"{collection_id}@1.0.0",
                    },
                )
            ).one()
            chunks = (
                await session.execute(
                    text(
                        "SELECT section_id, content FROM bok_section_chunks "
                        "WHERE collection_id=:collection_id ORDER BY section_id"
                    ),
                    {"collection_id": collection_id},
                )
            ).all()
        assert owner_status == "ready"
        assert catalog_status == "inactive"
        assert catalog_updated_at_after_rejection == catalog_updated_at_before_rejection
        if drift == "delete":
            assert len(chunks) == 1
        else:
            assert ("z-last", "changed nonblank content") in chunks
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_activation_accepts_valid_arbitrary_document_and_chunk_order() -> None:
    collection_id = "activation-unordered-valid"
    source = unordered_complete_bundle(collection_id)
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            assert await ingest_bundle(session, source) is True
        async with database.transaction() as session:
            await activate_version(session, collection_id, "1.0.0", expected_bundle=source)
        async with database.sessions() as session:
            status = (
                await session.execute(
                    text(
                        "SELECT status FROM bok_collection_versions "
                        "WHERE collection_id=:collection_id AND version='1.0.0'"
                    ),
                    {"collection_id": collection_id},
                )
            ).scalar_one()
        assert status == "active"
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_activation_advances_catalog_timestamp_without_changing_creation_time() -> None:
    collection_id = "activation-catalog-timestamp"
    source = bundle(collection_id=collection_id)
    old_timestamp = "2000-01-01T00:00:00+00:00"
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            assert await ingest_bundle(session, source) is True
            await insert_inactive_catalog_projection(session, collection_id, "1.0.0")
            seeded = await session.execute(
                text(
                    "UPDATE resources SET updated_at=:old "
                    "WHERE resource_type='bok_collection' AND resource_id=:resource_id"
                ),
                {"old": old_timestamp, "resource_id": f"{collection_id}@1.0.0"},
            )
            assert seeded.rowcount == 1
        async with database.sessions() as session:
            owner_created_at = (
                await session.execute(
                    text(
                        "SELECT created_at FROM bok_collection_versions "
                        "WHERE collection_id=:collection_id AND version='1.0.0'"
                    ),
                    {"collection_id": collection_id},
                )
            ).scalar_one()

        async with database.transaction() as session:
            await activate_version(session, collection_id, "1.0.0", expected_bundle=source)

        async with database.sessions() as session:
            status, updated_at = (
                await session.execute(
                    text(
                        "SELECT status, updated_at FROM resources "
                        "WHERE resource_type='bok_collection' AND resource_id=:resource_id"
                    ),
                    {"resource_id": f"{collection_id}@1.0.0"},
                )
            ).one()
            persisted_owner_created_at = (
                await session.execute(
                    text(
                        "SELECT created_at FROM bok_collection_versions "
                        "WHERE collection_id=:collection_id AND version='1.0.0'"
                    ),
                    {"collection_id": collection_id},
                )
            ).scalar_one()
        assert status == "active"
        assert updated_at.isoformat() != old_timestamp
        assert persisted_owner_created_at == owner_created_at
    finally:
        await database.dispose()


@pytest.mark.parametrize("mismatch", ["target", "manifest"], ids=["wrong-target", "wrong-digest"])
@pytest.mark.asyncio
async def test_activation_rejects_bundle_target_or_manifest_mismatch(mismatch: str) -> None:
    collection_id = f"activation-mismatch-{mismatch}"
    source = two_chunk_bundle(collection_id)
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            assert await ingest_bundle(session, source) is True
            await insert_inactive_catalog_projection(session, collection_id, "1.0.0")
        if mismatch == "manifest":
            async with database.transaction() as session:
                result = await session.execute(
                    text(
                        "UPDATE bok_collection_versions SET manifest_sha256=:digest "
                        "WHERE collection_id=:collection_id AND version='1.0.0'"
                    ),
                    {"collection_id": collection_id, "digest": "0" * 64},
                )
                assert result.rowcount == 1

        rejected = False
        try:
            async with database.transaction() as session:
                target_id = f"{collection_id}-wrong" if mismatch == "target" else collection_id
                await activate_version(
                    session,
                    target_id,
                    "1.0.0",
                    expected_bundle=source,
                )
        except BoKVersionCollision:
            rejected = True
        assert rejected, "activation must verify target identifiers and stored manifest digest"

        async with database.sessions() as session:
            owner_status, catalog_status, manifest = (
                await session.execute(
                    text(
                        "SELECT v.status, r.status, v.manifest_sha256 "
                        "FROM bok_collection_versions AS v JOIN resources AS r "
                        "ON r.resource_type='bok_collection' AND r.resource_id=:resource_id "
                        "WHERE v.collection_id=:collection_id AND v.version='1.0.0'"
                    ),
                    {
                        "collection_id": collection_id,
                        "resource_id": f"{collection_id}@1.0.0",
                    },
                )
            ).one()
        assert owner_status == "ready"
        assert catalog_status == "inactive"
        if mismatch == "manifest":
            assert manifest == "0" * 64
    finally:
        await database.dispose()
