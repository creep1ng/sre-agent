"""Issue #189 A3: authorized HTTP reads on real PostgreSQL.

detail/timeline/snapshot through the real gateway with a real demo-human
credential provisioned via A2. No mocks on the authorized path.
"""

import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

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
INCIDENT_ID = "inc-a3-authorized"
RUN_ID = "run_a3httpdemo01"
NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
BEARERS: dict[str, str] = {}
ALERT = {
    "alert_id": "alt-a3-spike",
    "service": "paymentservice",
    "severity": "sev2",
    "status": "new",
    "observed_at": "2026-09-22T11:55:00Z",
    "summary": "Elevated error rate on paymentservice.",
    "source": "grafana-alerting",
    "origin": {"signal": "error_rate", "condition": "above threshold"},
}
COMMANDS = (
    IncidentCommand(
        command_id="cmd_a3_open",
        incident_id=INCIDENT_ID,
        run_id=RUN_ID,
        transition_id="open_triage",
        actor="system",
    ),
    IncidentCommand(
        command_id="cmd_a3_declare",
        incident_id=INCIDENT_ID,
        run_id=RUN_ID,
        transition_id="triage_declare",
        actor="human",
        actor_reference=ActorReference(principal_id="demo-human", display_name="Demo human"),
        outcome="declare",
        inputs={"severity": "sev2"},
    ),
    IncidentCommand(
        command_id="cmd_a3_investigate",
        incident_id=INCIDENT_ID,
        run_id=RUN_ID,
        transition_id="start_investigation",
        actor="agent",
    ),
)


def _base_state() -> dict:
    return {
        "workflow_id": "incident-response",
        "workflow_version": "1.0.0",
        "state": "detected",
        "severity": None,
        "impact": None,
        "alert": dict(ALERT),
        "hypotheses": [],
        "evidence": [],
        "mitigation_strategy": None,
        "postmortem": None,
        "approvals": [],
        "updated_at": NOW.isoformat(),
    }


@pytest.fixture(scope="module", autouse=True)
def authorized_database() -> None:
    prepare_authorized_database()


def prepare_authorized_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, grants, credentials, resources, "
            "principals, idempotency_records, alembic_version CASCADE"
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
            creds = CredentialRepository(session)
            admin = await creds.issue("admin-human")
            demo = await creds.issue("demo-human")
            bystander = await creds.issue("bystander-human")
            grants = GrantRepository(session)
            for resource in ("catalog", "grants"):
                await grants.create(
                    f"grant-admin-human-admin-write-{resource}",
                    "admin-human",
                    "admin.write",
                    "administrative_control",
                    resource,
                )
        service = build_service(database, b"0" * 32)
        result = await provision(service, f"Bearer {admin.key}")
        assert (result.catalog_status, result.grant_status) == (201, 201)
        workflow = load_incident_workflow(
            REPOSITORY_ROOT / "agent" / "workflows" / "incident-response.yaml"
        )
        async with PostgresIncidentUnitOfWork(database) as work:
            await work.incidents.add(INCIDENT_ID, _base_state(), now=NOW)
            await work.runs.add(
                RUN_ID,
                INCIDENT_ID,
                {"workflow_version": "1.0.0", "current_state": "detected", "status": "running"},
                now=NOW,
            )
        runtime = IncidentRuntime(
            workflow, lambda: PostgresIncidentUnitOfWork(database), clock=lambda: NOW
        )
        for item in COMMANDS:
            await runtime.execute(item)
        BEARERS["demo"] = f"Bearer {demo.key}"
        BEARERS["bystander"] = f"Bearer {bystander.key}"

    asyncio.run(_setup())
    asyncio.run(database.dispose())


def _client() -> TestClient:
    return TestClient(create_application(Settings(DATABASE_URL)))


def test_unauthenticated_reads_are_401() -> None:
    client = _client()
    assert client.get(f"/v1/incidents/{INCIDENT_ID}").status_code == 401
    assert client.get(f"/v1/incidents/{INCIDENT_ID}/timeline").status_code == 401
    assert client.get(f"/v1/incidents/{INCIDENT_ID}/snapshot").status_code == 401
    bad = client.get(f"/v1/incidents/{INCIDENT_ID}", headers={"Authorization": "Bearer not-a-key"})
    assert bad.status_code == 401
    assert bad.headers["WWW-Authenticate"] == "Bearer"


def test_authenticated_without_grant_is_403_without_partials() -> None:
    client = _client()
    headers = {"Authorization": BEARERS["bystander"]}
    for path in ("", "/timeline", "/snapshot"):
        response = client.get(f"/v1/incidents/{INCIDENT_ID}{path}", headers=headers)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "not_authorized"
        assert INCIDENT_ID not in response.text
        assert "paymentservice" not in response.text


def test_authorized_detail_timeline_snapshot_are_200() -> None:
    client = _client()
    headers = {"Authorization": BEARERS["demo"]}
    detail = client.get(f"/v1/incidents/{INCIDENT_ID}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["incident_id"] == INCIDENT_ID
    assert [run["run_id"] for run in body["runs"]] == [RUN_ID]
    timeline = client.get(f"/v1/incidents/{INCIDENT_ID}/timeline", headers=headers)
    assert timeline.status_code == 200
    events = timeline.json()
    assert len(events["events"]) >= 3
    assert isinstance(events["next_cursor"], str) and isinstance(events["has_more"], bool)
    snapshot = client.get(f"/v1/incidents/{INCIDENT_ID}/snapshot", headers=headers)
    assert snapshot.status_code == 200
    snap = snapshot.json()
    assert snap["incident_id"] == INCIDENT_ID and snap["run_id"] == RUN_ID
    assert isinstance(snap["snapshot_id"], str)
    assert snap["version"] < body["version"]


def test_run_scoping_and_snapshot_history() -> None:
    client = _client()
    headers = {"Authorization": BEARERS["demo"]}
    assert (
        client.get(f"/v1/incidents/{INCIDENT_ID}/timeline?run_id=nope", headers=headers).status_code
        == 422
    )
    assert (
        client.get(
            f"/v1/incidents/{INCIDENT_ID}/timeline?run_id=run_missing00001", headers=headers
        ).status_code
        == 404
    )
    first = client.get(f"/v1/incidents/{INCIDENT_ID}/snapshot", headers=headers).json()
    second = client.get(
        f"/v1/incidents/{INCIDENT_ID}/snapshot?run_id={RUN_ID}", headers=headers
    ).json()
    assert first["snapshot_id"] == second["snapshot_id"]
