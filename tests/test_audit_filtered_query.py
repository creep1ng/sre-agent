"""Issue #25 B2a: audit storage filters for the published 2.3.0 list surface."""

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID

import psycopg
import pytest
from alembic import command
from alembic.config import Config

from sre_agent.governance.dto import AuditEvent
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import AuditRepository

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
DAY = datetime(2026, 9, 20, tzinfo=UTC)
DIGEST_P = "a" * 64
DIGEST_Q = "b" * 64
REDACTION = {
    "policy_version": "redaction-1.0.0",
    "result": "success",
    "source_class": "none",
    "categories": [],
    "match_count": 0,
    "sink_eligible": False,
}


def _ref(digest: str) -> dict:
    return {"algorithm": "hmac-sha-256", "key_version": 1, "digest": digest}


def make_event(
    number: int,
    *,
    hours: int = 0,
    allowed: bool = True,
    request: int = 41,
    principal: str = DIGEST_P,
    correlation: dict | None = None,
) -> AuditEvent:
    return AuditEvent(
        event_id=UUID(int=number),
        occurred_at=DAY + timedelta(hours=hours),
        operation="responses.create",
        action="invoke",
        stage="authorization",
        outcome="success" if allowed else "denied",
        reason_code="grant_matched" if allowed else "no_matching_grant",
        response_status=200 if allowed else 403,
        retryable=False,
        latency_ms=number,
        correlation={"request_id": UUID(int=request), **(correlation or {})},
        identity={
            "principal_ref": _ref(principal),
            "principal_kind": "human",
            "principal_status": "active",
            "credential_ref": _ref(principal),
            "authenticated_at": DAY,
        },
        resource={"resource_type": "llm_model", "resource_ref": _ref("c" * 64)},
        model_alias_ref=_ref("d" * 64),
        policy_decision={
            "decision": "allow" if allowed else "deny",
            "reason_code": "grant_matched" if allowed else "no_matching_grant",
            **({"grant_ref": _ref("b" * 64)} if allowed else {}),
        },
        routing=None,
        consumption=None,
        untrusted_input=None,
        redaction=REDACTION,
        content_state="absent",
        redacted_content=None,
        authoritative_acceptance="accepted",
        ordinary_result="released",
        exporter_result="not_attempted",
        correction_of_event_id=None,
    )


@pytest.fixture(scope="module", autouse=True)
def audit_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        tables = connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        ).fetchall()
        for (table,) in tables:
            connection.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")


async def _query(**kwargs):
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            return await AuditRepository(session).query_filtered(**kwargs)
    finally:
        await database.dispose()


async def _seed() -> None:
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            repository = AuditRepository(session)
            await repository.append(make_event(1, hours=1))
            await repository.append(make_event(2, hours=2, allowed=False))
            await repository.append(make_event(3, hours=3, request=42, principal=DIGEST_Q))
            await repository.append(
                make_event(
                    4,
                    hours=4,
                    correlation={
                        "incident_ref": _ref("e" * 64),
                        "run_ref": _ref("1" * 64),
                        "task_ref": _ref("2" * 64),
                        "trace_ref": _ref("f" * 64),
                    },
                )
            )
            await repository.append(make_event(5, hours=30))
    finally:
        await database.dispose()


WINDOW = {"start": DAY, "end": DAY + timedelta(hours=12)}


@pytest.mark.asyncio
async def test_window_ordering_and_bounds() -> None:
    await _seed()
    items, more = await _query(**WINDOW)
    assert [e.latency_ms for e in items] == [4, 3, 2, 1] and more is False
    page, more = await _query(**WINDOW, limit=2)
    assert [e.latency_ms for e in page] == [4, 3] and more is True
    with pytest.raises(ValueError):
        await _query(**WINDOW, limit=0)
    with pytest.raises(ValueError):
        await _query(**WINDOW, limit=101)


@pytest.mark.asyncio
async def test_request_and_decision_filters() -> None:
    requested, _ = await _query(**WINDOW, request_id=str(UUID(int=42)))
    assert [e.latency_ms for e in requested] == [3]
    allowed, _ = await _query(**WINDOW, decision="allow")
    assert [e.latency_ms for e in allowed] == [4, 3, 1]
    denied, _ = await _query(**WINDOW, decision="deny")
    assert [e.latency_ms for e in denied] == [2]


@pytest.mark.asyncio
async def test_reference_digest_filters() -> None:
    mine, _ = await _query(**WINDOW, principal_digest=DIGEST_P)
    assert [e.latency_ms for e in mine] == [4, 2, 1]
    other, _ = await _query(**WINDOW, principal_digest=DIGEST_Q)
    assert [e.latency_ms for e in other] == [3]
    aliased, _ = await _query(**WINDOW, model_alias_digest="d" * 64)
    assert len(aliased) == 4
    incident, _ = await _query(**WINDOW, incident_digest="e" * 64)
    assert [e.latency_ms for e in incident] == [4]
    run, _ = await _query(**WINDOW, run_digest="1" * 64)
    assert [e.latency_ms for e in run] == [4]
    task, _ = await _query(**WINDOW, task_digest="2" * 64)
    assert [e.latency_ms for e in task] == [4]
    trace, _ = await _query(**WINDOW, trace_digest="f" * 64)
    assert [e.latency_ms for e in trace] == [4]
    missing, _ = await _query(**WINDOW, trace_digest="0" * 64)
    assert missing == []


@pytest.mark.asyncio
async def test_combination_and_empty() -> None:
    combined, _ = await _query(
        **WINDOW, decision="allow", principal_digest=DIGEST_P, request_id=str(UUID(int=41))
    )
    assert [e.latency_ms for e in combined] == [4, 1]
    assert (await _query(start=DAY + timedelta(days=9), end=DAY + timedelta(days=10))) == (
        [],
        False,
    )
