"""Issue #330 A3: starting a run over HTTP, against real PostgreSQL.

Written from the ways the boundary could fail before the route existed: a caller
with no credential, a credential without `run.start`, a key the store cannot
hold, a retried key that opens a second run, one key reused for a different
request, an incident that does not exist, and a resume naming a run that belongs
to a different incident. Every case goes through the real application and the
real store, so a pass means delivery and governance agree, not that a double
answered.
"""

import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from sre_agent.application import create_application
from sre_agent.incident.runtime import ActorReference, IncidentCommand, IncidentRuntime
from sre_agent.incident.workflow import load_incident_workflow
from sre_agent.persistence.database import Database
from sre_agent.persistence.incidents import PostgresIncidentUnitOfWork
from sre_agent.persistence.repositories import CredentialRepository, GrantRepository
from sre_agent.settings import Settings

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from provision_incident_workflow import build_service, provision  # noqa: E402

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
INCIDENT_ID = "inc-a3-http-start"
OTHER_INCIDENT_ID = "inc-a3-http-neighbour"
KEY_INCIDENTS = {8: "inc-a3-http-key-008", 128: "inc-a3-http-key-128", 200: "inc-a3-http-key-200"}
CURSOR_INCIDENT_ID = "inc-a3-http-cursor"
# The range the contract admits, end to end: the store holds the longest key it
# allows, so the boundary has no reason to narrow it.
CONTRACT_MAX_KEY = "k" * 200
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
BEARERS: dict[str, str] = {}
OPENED: dict[str, str] = {}


def _base_state() -> dict[str, Any]:
    return {
        "workflow_id": "incident-response",
        "workflow_version": "1.0.0",
        "state": "detected",
        "severity": None,
        "impact": None,
        "alert": {
            "alert_id": "alt-a3-http",
            "service": "paymentservice",
            "severity": "sev2",
            "status": "new",
            "observed_at": "2026-09-26T11:55:00Z",
            "summary": "Elevated error rate on paymentservice.",
            "source": "grafana-alerting",
        },
        "hypotheses": [],
        "evidence": [],
        "mitigation_strategy": None,
        "postmortem": None,
        "approvals": [],
        "updated_at": NOW.isoformat(),
    }


@pytest.fixture(scope="module", autouse=True)
def authorized_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute("DROP TABLE IF EXISTS consumption_reservations CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS consumption_limit_policies, bok_section_chunks, bok_documents, "
            "bok_collection_versions, "
            "audit_events, skill_versions, grants, credentials, "
            "resources, mcp_tools, mcp_servers, "
            "principals, idempotency_records, "
            "alembic_version CASCADE"
        )
        connection.execute("DROP FUNCTION IF EXISTS reject_audit_mutation() CASCADE")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(config, "head")
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO principals VALUES "
            "('admin-human','human','Admin','active',now(),now()),"
            "('demo-human','human','Demo','active',now(),now()),"
            "('bystander-human','human','Bystander','active',now(),now())"
        )
        connection.execute(
            "INSERT INTO resources (resource_type, resource_id, status, updated_at) VALUES "
            "('administrative_control','catalog','active',now()),"
            "('administrative_control','grants','active',now())"
        )
    database = Database(DATABASE_URL)

    async def _setup() -> None:
        async with database.transaction() as session:
            credentials = CredentialRepository(session)
            admin = await credentials.issue("admin-human")
            demo = await credentials.issue("demo-human")
            bystander = await credentials.issue("bystander-human")
            grants = GrantRepository(session)
            for resource in ("catalog", "grants"):
                await grants.create(
                    f"grant-admin-human-admin-write-{resource}",
                    "admin-human",
                    "admin.write",
                    "administrative_control",
                    resource,
                )
        # The workflow resource comes from the governed catalog; slice A2 makes
        # the starter grant governed too, so here it is only fixture data.
        provisioned = await provision(build_service(database, b"0" * 32), f"Bearer {admin.key}")
        assert provisioned.catalog_status == 201
        async with database.transaction() as session:
            await GrantRepository(session).create(
                "grant-demo-human-run-start-incident-response",
                "demo-human",
                "run.start",
                "incident_workflow",
                "incident-response",
            )
        async with PostgresIncidentUnitOfWork(database) as work:
            await work.incidents.add(INCIDENT_ID, _base_state(), now=NOW)
            await work.incidents.add(OTHER_INCIDENT_ID, _base_state(), now=NOW)
            for identifier in KEY_INCIDENTS.values():
                await work.incidents.add(identifier, _base_state(), now=NOW)
            await work.incidents.add(CURSOR_INCIDENT_ID, _base_state(), now=NOW)
        BEARERS["demo"] = f"Bearer {demo.key}"
        BEARERS["bystander"] = f"Bearer {bystander.key}"

    asyncio.run(_setup())
    asyncio.run(database.dispose())


def _client() -> TestClient:
    return TestClient(create_application(Settings(DATABASE_URL)))


def _body(objective: str = "triage", **extra: Any) -> dict[str, Any]:
    return {"workflow_version": "1.0.0", "objective": objective, **extra}


def _start(
    key: str | None,
    *,
    bearer: str | None = "demo",
    body: Any = None,
    incident: str = INCIDENT_ID,
) -> Any:
    headers = {}
    if bearer is not None:
        headers["Authorization"] = BEARERS[bearer] if bearer in BEARERS else bearer
    if key is not None:
        headers["Idempotency-Key"] = key
    return _client().post(
        f"/v1/incidents/{incident}/runs",
        json=_body() if body is None else body,
        headers=headers,
    )


def _run_ids() -> list[str]:
    with psycopg.connect(DATABASE_URL) as connection:
        rows = connection.execute("SELECT run_id FROM incident.runs ORDER BY created_at")
        return [row[0] for row in rows]


def test_a_request_without_a_usable_credential_is_401() -> None:
    anonymous = _start("key-anonymous-01", bearer=None)
    assert anonymous.status_code == 401
    assert anonymous.headers["WWW-Authenticate"] == "Bearer"
    assert _start("key-badkey-0001", bearer="Bearer not-a-key").status_code == 401
    assert _run_ids() == []


def test_a_credential_without_run_start_is_403_and_opens_nothing() -> None:
    denied = _start("key-bystander-01", bearer="bystander")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "not_authorized"
    assert INCIDENT_ID not in denied.text and "paymentservice" not in denied.text
    assert _run_ids() == []


def test_a_request_the_contract_does_not_admit_is_refused_before_anything_else() -> None:
    """Including an objective whose type the lookup cannot even hash."""
    assert _start("x" * 201).status_code == 422
    assert (
        _start(
            "key-objective-list", body={"workflow_version": "1.0.0", "objective": []}
        ).status_code
        == 422
    )
    assert (
        _start(
            "key-objective-dict", body={"workflow_version": "1.0.0", "objective": {}}
        ).status_code
        == 422
    )
    assert (
        _start("key-objective-int", body={"workflow_version": "1.0.0", "objective": 7}).status_code
        == 422
    )
    assert _start("short").status_code == 422
    assert _start(None).status_code == 422
    assert _start("key-unknown-objective", body=_body("dance")).status_code == 422
    assert _start("key-extra-field-001", body=_body(actor="admin-human")).status_code == 422
    assert _run_ids() == []


def test_retrying_one_key_returns_the_first_run_instead_of_opening_another() -> None:
    created = _start(CONTRACT_MAX_KEY)
    assert created.status_code == 201
    opened = created.json()
    assert opened["incident_id"] == INCIDENT_ID
    assert (opened["status"], opened["current_state"]) == ("running", "triage")
    assert opened["cursor"] == "seq:0"
    OPENED["run_id"] = opened["run_id"]

    replayed = _start(CONTRACT_MAX_KEY)
    assert replayed.status_code == 200
    assert replayed.json()["run_id"] == opened["run_id"]
    assert _run_ids() == [opened["run_id"]]


def test_one_key_reused_for_a_different_request_conflicts() -> None:
    conflict = _start(CONTRACT_MAX_KEY, body=_body("investigate"))
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "run_conflict"
    assert _run_ids() == [OPENED["run_id"]]


def test_an_incident_that_does_not_exist_is_404() -> None:
    absent = _start("key-absent-inc-01", incident="inc-a3-never-declared")
    assert absent.status_code == 404
    assert absent.json()["error"]["code"] == "incident_not_found"
    assert _run_ids() == [OPENED["run_id"]]


def test_resuming_never_reaches_a_run_of_another_incident() -> None:
    resumed = _start("key-resume-0001", body=_body(resume_from_run_id=OPENED["run_id"]))
    assert resumed.status_code == 200
    assert resumed.json()["run_id"] == OPENED["run_id"]

    neighbour = _start("key-neighbour-001", incident=OTHER_INCIDENT_ID)
    assert neighbour.status_code == 201
    stolen = _start("key-resume-0002", body=_body(resume_from_run_id=neighbour.json()["run_id"]))
    assert stolen.status_code == 404
    assert stolen.json()["error"]["code"] == "run_not_found"
    missing = _start("key-resume-0003", body=_body(resume_from_run_id="run_missing00001"))
    assert missing.status_code == 404
    assert _run_ids() == [OPENED["run_id"], neighbour.json()["run_id"]]


def test_every_key_length_the_contract_admits_opens_a_run() -> None:
    """8 and 200 are the contract's edges; 128 was the store's old ceiling."""
    for length, identifier in KEY_INCIDENTS.items():
        key = f"k{length:03d}" + "x" * (length - 4)
        assert len(key) == length
        response = _start(key, incident=identifier)
        assert response.status_code == 201, length
    assert _start("x" * 7, incident=KEY_INCIDENTS[8]).status_code == 422
    assert _start("x" * 201, incident=KEY_INCIDENTS[200]).status_code == 422
    with psycopg.connect(DATABASE_URL) as connection:
        stored = connection.execute(
            "SELECT length(command_id) FROM incident.transition_commits "
            "WHERE incident_id LIKE 'inc-a3-http-key-%' ORDER BY 1"
        ).fetchall()
    assert [row[0] for row in stored] == [8, 128, 200]


def test_resuming_reports_a_cursor_for_the_state_it_returns() -> None:
    """Snapshots lag behind the run, so the cursor cannot come from the snapshot.

    Between two snapshots the run record already reflects events the last
    snapshot does not cover. A consumer continuing from a stale cursor would
    re-apply what the state it just read already shows.
    """

    opened = _start("key-cursor-000001", incident=CURSOR_INCIDENT_ID)
    assert opened.status_code == 201
    run_id = opened.json()["run_id"]
    assert opened.json()["cursor"] == "seq:0"

    async def _advance() -> tuple[int, int]:
        database = Database(DATABASE_URL)
        workflow = load_incident_workflow(
            REPOSITORY_ROOT / "agent/workflows/incident-response.yaml"
        )
        runtime = IncidentRuntime(workflow, lambda: PostgresIncidentUnitOfWork(database))
        await runtime.execute(
            IncidentCommand(
                command_id="cursor-second-transition",
                incident_id=CURSOR_INCIDENT_ID,
                run_id=run_id,
                transition_id="triage_declare",
                actor="human",
                actor_reference=ActorReference(principal_id="demo-human"),
                outcome="declare",
                inputs={"severity": "sev2"},
            )
        )
        async with PostgresIncidentUnitOfWork(database) as work:
            events = await work.events.list_after(run_id, sequence=-1, limit=50)
            snapshot = await work.snapshots.latest(run_id)
        await database.dispose()
        assert snapshot is not None
        return max(event.sequence for event in events), snapshot.event_sequence

    last_event, covered_by_snapshot = asyncio.run(_advance())
    assert last_event > covered_by_snapshot, "the second transition must not take a new snapshot"

    resumed = _start(
        "key-cursor-000002",
        body=_body(resume_from_run_id=run_id),
        incident=CURSOR_INCIDENT_ID,
    )
    assert resumed.status_code == 200
    assert resumed.json()["current_state"] == "active"
    assert resumed.json()["cursor"] == f"seq:{last_event}"
