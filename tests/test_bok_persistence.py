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

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)


@pytest.fixture(scope="module", autouse=True)
def migrated_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS bok_section_chunks, bok_documents, bok_collection_versions, "
            "audit_events, grants, credentials, resources, principals, idempotency_records, "
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


@pytest.mark.asyncio
async def test_activation_requires_ready_owner_version_and_seed_converges() -> None:
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            assert await seed_bok_demo(session) is True
            await ingest_bundle(session, bundle(collection_id="empty", content=""))
        with pytest.raises(ValueError, match="not_ready"):
            async with database.transaction() as session:
                await activate_version(session, "empty", "1.0.0")
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
