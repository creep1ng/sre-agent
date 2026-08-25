import os
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from sre_agent.persistence.api_keys import hash_api_key, verify_api_key
from sre_agent.persistence.database import Database
from sre_agent.persistence.models import CredentialRow, PrincipalRow
from sre_agent.persistence.repositories import CredentialRepository

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
NOW = datetime(2026, 8, 24, 12, tzinfo=UTC)


@pytest.fixture(scope="module")
def persistence_database() -> Database:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, grants, credentials, resources, "
            "principals, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")
    database = Database(DATABASE_URL)

    async def insert_fixture() -> None:
        async with database.transaction() as session:
            session.add(
                PrincipalRow(
                    principal_id="incident-harness",
                    kind="agent",
                    display_name="incident-harness",
                    status="active",
                    created_at=NOW - timedelta(days=1),
                    updated_at=NOW - timedelta(days=1),
                )
            )
            await session.flush()
            session.add(
                CredentialRow(
                    credential_id="credential-incident-harness",
                    principal_id="incident-harness",
                    prefix="sre_inci",
                    key_hash=hash_api_key("sre_inci_0123456789abcdefghijklmnop"),
                    status="active",
                    created_at=NOW - timedelta(days=1),
                    expires_at=None,
                    revoked_at=None,
                )
            )

    import asyncio

    asyncio.run(insert_fixture())
    yield database
    asyncio.run(database.dispose())


@pytest.mark.asyncio
async def test_issued_key_is_revealed_once_and_only_hash_and_prefix_persist(
    persistence_database: Database,
) -> None:
    async with persistence_database.transaction() as session:
        issued = await CredentialRepository(session).issue("incident-harness", now=NOW)
        raw_key = issued.key
        credential_id = issued.credential.credential_id
    async with persistence_database.transaction() as session:
        row = await session.get(CredentialRow, credential_id)
        projected = await CredentialRepository(session).get(credential_id)
    assert row is not None and projected is not None
    assert row.prefix == raw_key[:16]
    assert row.key_hash != raw_key and verify_api_key(raw_key, row.key_hash)
    assert raw_key not in repr(issued)
    assert raw_key not in repr(row.__dict__)
    assert "key_hash" not in repr(projected.model_dump())


@pytest.mark.asyncio
async def test_issuance_retries_prefix_collision_inside_a_savepoint(
    persistence_database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    collision = "sre_collision001_0123456789abcdefghijklmnop"
    replacement = "sre_replaced0001_0123456789abcdefghijklmnop"
    monkeypatch.setattr("sre_agent.persistence.repositories.generate_api_key", lambda: collision)
    async with persistence_database.transaction() as session:
        first = await CredentialRepository(session).issue("incident-harness", now=NOW)
    generated = iter((collision, replacement))
    monkeypatch.setattr(
        "sre_agent.persistence.repositories.generate_api_key", lambda: next(generated)
    )
    async with persistence_database.transaction() as session:
        second = await CredentialRepository(session).issue("incident-harness", now=NOW)
    assert first.key == collision and second.key == replacement
    assert first.credential.prefix != second.credential.prefix


@pytest.mark.asyncio
async def test_revocation_is_idempotent_and_blocks_repository_authentication(
    persistence_database: Database,
) -> None:
    key = "sre_inci_0123456789abcdefghijklmnop"
    async with persistence_database.transaction() as session:
        repository = CredentialRepository(session)
        first = await repository.revoke("credential-incident-harness", now=NOW)
        second = await repository.revoke(
            "credential-incident-harness", now=NOW + timedelta(hours=1)
        )
        context = await repository.authenticate(key, now=NOW)
    assert first is not None and second is not None
    assert first == second and second.revoked_at == NOW
    assert context is None
