import asyncio
import os
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from sre_agent.persistence.database import Database
from sre_agent.persistence.models import CredentialRow, IdempotencyRecordRow
from sre_agent.persistence.repositories import (
    CredentialRepository,
    IdempotencyConflictError,
    IdempotencyOutcome,
    IdempotencyRepository,
    PrincipalRepository,
    StaleWriteError,
)

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55447/postgres"
)


@pytest.fixture(scope="module", autouse=True)
def control_persistence_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, grants, credentials, resources, "
            "principals, idempotency_records, alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")


def outcome(resource_id: str, *, payload: dict[str, object] | None = None) -> IdempotencyOutcome:
    return IdempotencyOutcome(
        response_status=201,
        resource_id=resource_id,
        replayed=False,
        response_payload=payload or {},
    )


class CoordinatedSession:
    """Forces the legacy read/check/flush implementation to race after its read."""

    def __init__(self, session: object, barrier: asyncio.Barrier) -> None:
        self._session = session
        self._barrier = barrier
        self._coordinated_read = False

    async def get(self, *args: object, **kwargs: object) -> object:
        row = await self._session.get(*args, **kwargs)  # type: ignore[attr-defined]
        if not self._coordinated_read:
            self._coordinated_read = True
            await self._barrier.wait()
        return row

    def __getattr__(self, name: str) -> object:
        return getattr(self._session, name)


@pytest.mark.asyncio
async def test_status_replace_allows_exactly_one_concurrent_writer() -> None:
    database = Database(DATABASE_URL)
    original = datetime(2026, 9, 7, tzinfo=UTC)
    async with database.transaction() as session:
        await PrincipalRepository(session).create(
            "cas-principal", "human", "CAS principal", now=original
        )

    barrier = asyncio.Barrier(2)

    async def writer(status: str, updated_at: datetime) -> str:
        async with database.transaction() as session:
            repository = PrincipalRepository(CoordinatedSession(session, barrier))  # type: ignore[arg-type]
            try:
                await repository.replace_status(
                    "cas-principal",
                    status,
                    expected_updated_at=original,
                    now=updated_at,
                )
            except StaleWriteError:
                return "stale"
            return "written"

    results = await asyncio.gather(
        writer("inactive", original + timedelta(seconds=1)),
        writer("active", original + timedelta(seconds=2)),
    )

    assert sorted(results) == ["stale", "written"]
    async with database.transaction() as session:
        stored = await PrincipalRepository(session).get("cas-principal")
    assert stored is not None
    assert stored.updated_at in {original + timedelta(seconds=1), original + timedelta(seconds=2)}
    await database.dispose()


@pytest.mark.asyncio
async def test_idempotency_binds_timed_records_for_24_hours_and_lifetime_records_forever() -> None:
    database = Database(DATABASE_URL)
    created_at = datetime(2026, 9, 7, 8, 0, tzinfo=UTC)
    async with database.transaction() as session:
        repository = IdempotencyRepository(session)
        await repository.claim_or_replay(
            scope="operator|POST|/timed",
            key_digest="a" * 64,
            payload_sha256="b" * 64,
            principal_id="operator",
            method="POST",
            canonical_path="/timed",
            binding="at_least_24h",
            outcome=outcome(
                "timed-first",
                payload={"credential_id": "credential-first", "secret_revealed": False},
            ),
            now=created_at,
        )
        await repository.claim_or_replay(
            scope="operator|POST|/lifetime",
            key_digest="c" * 64,
            payload_sha256="d" * 64,
            principal_id="operator",
            method="POST",
            canonical_path="/lifetime",
            binding="principal_lifetime",
            outcome=outcome("lifetime-first"),
            now=created_at,
            expires_at=created_at + timedelta(days=2),
        )

    async with database.transaction() as session:
        timed = await session.get(IdempotencyRecordRow, ("operator|POST|/timed", "a" * 64))
        lifetime = await session.get(IdempotencyRecordRow, ("operator|POST|/lifetime", "c" * 64))
    assert timed is not None and timed.expires_at is not None
    assert timed.expires_at >= created_at + timedelta(hours=24)
    assert lifetime is not None and lifetime.expires_at is None

    async with database.transaction() as session:
        replay = await IdempotencyRepository(session).claim_or_replay(
            scope="operator|POST|/timed",
            key_digest="a" * 64,
            payload_sha256="b" * 64,
            principal_id="operator",
            method="POST",
            canonical_path="/timed",
            binding="at_least_24h",
            outcome=outcome("not-used"),
            now=created_at + timedelta(hours=23, minutes=59),
        )
    assert replay.replayed is True
    assert replay.outcome.resource_id == "timed-first"
    assert replay.outcome.response_payload == {
        "credential_id": "credential-first",
        "secret_revealed": False,
    }
    async with database.transaction() as session:
        with pytest.raises(IdempotencyConflictError):
            await IdempotencyRepository(session).claim_or_replay(
                scope="operator|POST|/timed",
                key_digest="a" * 64,
                payload_sha256="f" * 64,
                principal_id="operator",
                method="POST",
                canonical_path="/timed",
                binding="at_least_24h",
                outcome=outcome("must-not-transition"),
                now=created_at + timedelta(hours=2),
            )

    async with database.transaction() as session:
        other_scope = await IdempotencyRepository(session).claim_or_replay(
            scope="another-operator|POST|/timed",
            key_digest="a" * 64,
            payload_sha256="e" * 64,
            principal_id="another-operator",
            method="POST",
            canonical_path="/timed",
            binding="at_least_24h",
            outcome=outcome("separate-scope"),
            now=created_at + timedelta(hours=1),
        )
    assert other_scope.replayed is False

    async with database.transaction() as session:
        renewed = await IdempotencyRepository(session).claim_or_replay(
            scope="operator|POST|/timed",
            key_digest="a" * 64,
            payload_sha256="b" * 64,
            principal_id="operator",
            method="POST",
            canonical_path="/timed",
            binding="at_least_24h",
            outcome=outcome("timed-second"),
            now=created_at + timedelta(hours=24, seconds=1),
        )
    assert renewed.replayed is False
    assert renewed.outcome.resource_id == "timed-second"
    await database.dispose()


@pytest.mark.asyncio
async def test_idempotency_concurrent_same_key_converges_without_an_integrity_error() -> None:
    database = Database(DATABASE_URL)
    created_at = datetime(2026, 9, 7, 10, 0, tzinfo=UTC)
    barrier = asyncio.Barrier(2)

    async def claimant(resource_id: str) -> bool:
        async with database.transaction() as session:
            repository = IdempotencyRepository(CoordinatedSession(session, barrier))  # type: ignore[arg-type]
            binding = await repository.claim_or_replay(
                scope="operator|POST|/concurrent",
                key_digest="f" * 64,
                payload_sha256="0" * 64,
                principal_id="operator",
                method="POST",
                canonical_path="/concurrent",
                binding="at_least_24h",
                outcome=outcome(resource_id),
                now=created_at,
            )
        return binding.replayed

    replayed = await asyncio.gather(claimant("first"), claimant("second"))
    assert sorted(replayed) == [False, True]
    async with database.transaction() as session:
        stored = await session.get(IdempotencyRecordRow, ("operator|POST|/concurrent", "f" * 64))
    assert stored is not None and stored.transition_count == 1
    await database.dispose()


@pytest.mark.asyncio
async def test_idempotency_finalizes_secret_free_response_payload_for_replay() -> None:
    database = Database(DATABASE_URL)
    created_at = datetime(2026, 9, 7, 11, 0, tzinfo=UTC)
    scope, key_digest = "operator|POST|/credential", "1" * 64
    async with database.transaction() as session:
        repository = IdempotencyRepository(session)
        binding = await repository.claim_or_replay(
            scope=scope,
            key_digest=key_digest,
            payload_sha256="2" * 64,
            principal_id="operator",
            method="POST",
            canonical_path="/credential",
            binding="principal_lifetime",
            outcome=outcome("credential-first"),
            now=created_at,
        )
        assert binding.replayed is False
        await repository.set_response_payload(
            scope=scope,
            key_digest=key_digest,
            response_payload={
                "credential_id": "credential-first",
                "secret_revealed": False,
            },
        )

    async with database.transaction() as session:
        replay = await IdempotencyRepository(session).claim_or_replay(
            scope=scope,
            key_digest=key_digest,
            payload_sha256="2" * 64,
            principal_id="operator",
            method="POST",
            canonical_path="/credential",
            binding="principal_lifetime",
            outcome=outcome("not-used"),
            now=created_at + timedelta(days=365),
        )
    assert replay.replayed is True
    assert replay.outcome.response_payload == {
        "credential_id": "credential-first",
        "secret_revealed": False,
    }
    await database.dispose()


@pytest.mark.asyncio
async def test_rotation_locks_active_credential_and_rolls_back_on_issuance_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = Database(DATABASE_URL)
    original = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)
    async with database.transaction() as session:
        await PrincipalRepository(session).create(
            "rotate-principal", "human", "Rotate", now=original
        )
        active = await CredentialRepository(session).issue("rotate-principal", now=original)
        expired = await CredentialRepository(session).issue(
            "rotate-principal", now=original, expires_at=original + timedelta(hours=1)
        )
        await CredentialRepository(session).revoke(active.credential.credential_id, now=original)

    async with database.transaction() as session:
        repository = CredentialRepository(session)
        assert await repository.rotate(active.credential.credential_id, now=original) is None
        assert (
            await repository.rotate(
                expired.credential.credential_id, now=original + timedelta(hours=2)
            )
            is None
        )
        count = await session.scalar(
            select(func.count())
            .select_from(CredentialRow)
            .where(CredentialRow.principal_id == "rotate-principal")
        )
    assert count == 2

    async with database.transaction() as session:
        rollback_candidate = await CredentialRepository(session).issue(
            "rotate-principal", now=original
        )

    async def issuance_failure(*args: object, **kwargs: object) -> object:
        raise RuntimeError("injected issuance failure")

    monkeypatch.setattr(CredentialRepository, "issue", issuance_failure)
    with pytest.raises(RuntimeError, match="injected issuance failure"):
        async with database.transaction() as session:
            await CredentialRepository(session).rotate(
                rollback_candidate.credential.credential_id, now=original + timedelta(minutes=1)
            )

    async with database.transaction() as session:
        stored = await session.get(CredentialRow, rollback_candidate.credential.credential_id)
        count = await session.scalar(
            select(func.count())
            .select_from(CredentialRow)
            .where(CredentialRow.principal_id == "rotate-principal")
        )
    assert stored is not None and stored.status == "active" and stored.revoked_at is None
    assert count == 3
    await database.dispose()
