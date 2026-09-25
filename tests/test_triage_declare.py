"""Issue #23 C2a declare: triage_declare creates exactly one incident."""

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from sre_agent.governance.dto import Principal
from sre_agent.incident.workflow import load_incident_workflow
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import GrantRepository
from sre_agent.triage.service import TriageError, TriageService

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
NOW = datetime(2026, 9, 23, tzinfo=UTC)
REASON = "Sustained 5xx spike on checkout."
SERVICE: TriageService | None = None


def _principal(pid: str) -> Principal:
    return Principal(
        principal_id=pid,
        kind="human",
        display_name=pid,
        status="active",
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.fixture(scope="module", autouse=True)
def triage_declare_database() -> None:
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
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO principals VALUES "
            "('op-human','human','Operator','active',now(),now()),"
            "('bystander-human','human','Bystander','active',now(),now())"
        )
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status, updated_at,"
            " owner_id, source, source_ref, display_name, visibility, description,"
            " tags) VALUES ('incident_workflow','incident-response','active',now(),"
            " 'papiarcacamilo','incident_workflow','incident-response@1.0.0',"
            " 'Incident response workflow','private','','[]')"
        )
    database = Database(DATABASE_URL)

    async def _setup() -> TriageService:
        async with database.transaction() as session:
            grants = GrantRepository(session)
            for index, action in enumerate(
                ("alert.triage", "alert.dismiss", "alert.associate", "run.read", "incident.declare")
            ):
                await grants.create(
                    f"grant-op-human-{index}",
                    "op-human",
                    action,
                    "incident_workflow",
                    "incident-response",
                )
        workflow = load_incident_workflow(
            Path(__file__).parents[1] / "agent" / "workflows" / "incident-response.yaml"
        )
        return TriageService(database, workflow)

    global SERVICE
    SERVICE = asyncio.run(_setup())
    asyncio.run(database.dispose())


async def _count(table: str, where: str = "", params: dict | None = None) -> int:
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            result = await session.execute(
                text(f"SELECT count(*) FROM {table} {where}"), params or {}
            )
            return int(result.scalar())
    finally:
        await database.dispose()


async def _row(table: str, where: str, params: dict) -> dict:
    database = Database(DATABASE_URL)
    try:
        async with database.transaction() as session:
            result = await session.execute(text(f"SELECT * FROM {table} {where}"), params)
            return dict(result.mappings().one())
    finally:
        await database.dispose()


async def _declare(alert_id: str, key: str, principal: Principal | None = None, **kwargs):
    assert SERVICE is not None
    kwargs.setdefault("severity", "sev2")
    return await SERVICE.execute(
        principal or _principal("op-human"),
        alert_id=alert_id,
        operation="triage_declare",
        expected_version=1,
        reason=REASON,
        idempotency_key=key,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_declare_creates_exactly_one_incident() -> None:
    before = await _count("incident.incidents")
    declared = await _declare("al-declare", "k-declare-123456789")
    assert (declared.status, declared.http_status, declared.replayed) == ("declared", 201, False)
    assert declared.incident_id is not None and declared.actor == "op-human"
    assert datetime.fromisoformat(declared.decided_at) >= NOW
    assert await _count("incident.incidents") == before + 1
    params = {"id": declared.incident_id}
    assert await _count("incident.runs", "WHERE incident_id=:id", params) == 1
    stored = await _row("incident.incidents", "WHERE incident_id=:id", params)
    assert stored["state"]["state"] == "active"
    assert (stored["state"]["severity"], stored["state"]["impact"]) == ("sev2", None)
    triage = await _row("alert_triage", "WHERE alert_id='al-declare'", {})
    assert (triage["status"], triage["severity"], triage["actor"]) == (
        "declared",
        "sev2",
        "op-human",
    )
    assert triage["incident_id"] == declared.incident_id


@pytest.mark.asyncio
@pytest.mark.parametrize("severity", ["sev1", "sev3", "sev4"])
async def test_declare_accepts_every_contract_severity(severity: str) -> None:
    declared = await _declare(f"al-sev-{severity}", f"k-sev-{severity}-123456", severity=severity)
    assert (declared.http_status, declared.status) == (201, "declared")
    stored = await _row("incident.incidents", "WHERE incident_id=:id", {"id": declared.incident_id})
    assert stored["state"]["severity"] == severity


@pytest.mark.asyncio
async def test_declare_rejects_missing_invalid_severity_and_impact() -> None:
    before = await _count("incident.incidents")
    cases = [
        ("al-nosev", {"severity": None}, "k-nosev-12345678901", "invalid_severity"),
        ("al-sev9", {"severity": "sev9"}, "k-sev9-123456789012", "invalid_severity"),
        (
            "al-impact",
            {"severity": "sev2", "impact": "checkout down"},
            "k-impact-1234567890",
            "invalid_impact",
        ),
    ]
    for alert_id, extra, key, code in cases:
        with pytest.raises(TriageError) as error:
            await _declare(alert_id, key, **extra)
        assert (error.value.http_status, error.value.code) == (422, code)
    assert await _count("incident.incidents") == before


@pytest.mark.asyncio
async def test_declare_replay_returns_original_without_second_incident() -> None:
    before = await _count("incident.incidents")
    first = await _declare("al-replay", "k-replay-1234567890", severity="sev1")
    assert await _count("incident.incidents") == before + 1
    second = await _declare("al-replay", "k-replay-1234567890", severity="sev1")
    assert (second.replayed, second.http_status) == (True, 201)
    assert (second.incident_id, second.expected_version) == (
        first.incident_id,
        first.expected_version,
    )
    assert await _count("incident.incidents") == before + 1
    assert SERVICE is not None
    with pytest.raises(TriageError) as conflict:
        await SERVICE.execute(
            _principal("op-human"),
            alert_id="al-replay",
            operation="triage_dismiss",
            expected_version=1,
            reason=REASON,
            idempotency_key="k-replay-1234567890",
        )
    assert (conflict.value.http_status, conflict.value.code) == (409, "idempotency_conflict")


@pytest.mark.asyncio
async def test_declare_rejects_stale_version_without_side_effects() -> None:
    before = await _count("incident.incidents")
    assert SERVICE is not None
    with pytest.raises(TriageError) as stale:
        await SERVICE.execute(
            _principal("op-human"),
            alert_id="al-stale",
            operation="triage_declare",
            expected_version=2,
            reason=REASON,
            severity="sev2",
            idempotency_key="k-stale-12345678901",
        )
    assert (stale.value.http_status, stale.value.code) == (409, "stale_version")
    assert await _count("incident.incidents") == before


@pytest.mark.asyncio
async def test_declare_race_creates_single_incident() -> None:
    assert SERVICE is not None
    await SERVICE.execute(
        _principal("op-human"),
        alert_id="al-race",
        operation="open_triage",
        expected_version=1,
        idempotency_key="k-race-open-1234567",
    )
    before = await _count("incident.incidents")
    first, second = await asyncio.gather(
        _declare("al-race", "k-race-a-12345678901"),
        _declare("al-race", "k-race-b-12345678901"),
        return_exceptions=True,
    )
    outcomes = []
    for outcome in (first, second):
        if isinstance(outcome, TriageError):
            outcomes.append((outcome.http_status, outcome.code))
        else:
            outcomes.append((outcome.http_status, outcome.status))
    assert sorted(outcomes) == [(201, "declared"), (409, "stale_version")]
    assert await _count("incident.incidents") == before + 1


@pytest.mark.asyncio
async def test_declare_denies_without_leaking_existence() -> None:
    ghosts = (("al-ghost-one", "k-ghost-1-12345678"), ("al-ghost-two", "k-ghost-2-12345678"))
    for alert_id, key in ghosts:
        with pytest.raises(TriageError) as denied:
            await _declare(alert_id, key, principal=_principal("bystander-human"))
        assert (denied.value.http_status, denied.value.code) == (403, "not_authorized")
