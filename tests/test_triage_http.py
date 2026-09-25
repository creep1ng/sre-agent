"""Issue #23 C2b: triage commands over real HTTP on real PostgreSQL."""

import asyncio
import os
from pathlib import Path

import psycopg
import pytest
import yaml
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from sre_agent.application import create_application
from sre_agent.persistence.database import Database
from sre_agent.persistence.repositories import CredentialRepository, GrantRepository
from sre_agent.settings import Settings

DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:55432/postgres"
)
REASON = "Sustained 5xx spike on checkout."
BEARERS: dict[str, str] = {}
ROOT = Path(__file__).parents[1]
STATE_VALIDATOR = Draft202012Validator(
    yaml.safe_load((ROOT / "agent" / "schemas" / "triage-state.schema.yaml").read_text())
)


@pytest.fixture(scope="module", autouse=True)
def triage_http_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP SCHEMA IF EXISTS incident CASCADE")
        connection.execute(
            "DROP TABLE IF EXISTS audit_events, grants, credentials, resources, "
            "alert_triage, principals, idempotency_records, mcp_tools, mcp_servers, "
            "alembic_version CASCADE"
        )
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
        connection.execute(
            "INSERT INTO incident.incidents (incident_id, state, version, created_at,"
            " updated_at) VALUES ('inc-http-target',"
            " jsonb_build_object('state', CAST('active' AS text)), 1, now(), now())"
        )
    database = Database(DATABASE_URL)

    async def _setup() -> None:
        async with database.transaction() as session:
            creds = CredentialRepository(session)
            issued_op = await creds.issue("op-human")
            issued_by = await creds.issue("bystander-human")
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
        BEARERS["op"] = f"Bearer {issued_op.key}"
        BEARERS["bystander"] = f"Bearer {issued_by.key}"

    asyncio.run(_setup())
    asyncio.run(database.dispose())


def _client(url: str = DATABASE_URL) -> TestClient:
    return TestClient(create_application(Settings(url)))


def _cmd(operation: str, version: int = 1, **kwargs) -> dict:
    return {"operation": operation, "expected_version": version, **kwargs}


def _post(
    client: TestClient,
    alert_id: str,
    body: dict | None,
    key: str | None,
    bearer: str | None,
    raw: bytes | None = None,
):
    headers: dict[str, str] = {}
    if bearer is not None:
        headers["Authorization"] = bearer
    if key is not None:
        headers["Idempotency-Key"] = key
    path = f"/v1/alerts/{alert_id}/triage/commands"
    if raw is not None:
        headers["Content-Type"] = "application/json"
        return client.post(path, content=raw, headers=headers)
    return client.post(path, json=body, headers=headers)


def _incident_count() -> int:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        return int(connection.execute("SELECT count(*) FROM incident.incidents").fetchone()[0])


def test_open_dismiss_link_are_200() -> None:
    client, bearer = _client(), BEARERS["op"]
    opened = _post(client, "aho", _cmd("open_triage"), "k-open-123456789012", bearer)
    assert opened.status_code == 200
    assert (opened.json()["status"], opened.json()["alert_id"]) == ("open", "aho")
    dismissed = _post(
        client, "aho", _cmd("triage_dismiss", reason=REASON), "k-dismiss-12345678", bearer
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"
    linked = _post(
        client,
        "ahl",
        _cmd("triage_link", reason=REASON, target_incident_id="inc-http-target"),
        "k-link-12345678901",
        bearer,
    )
    assert linked.status_code == 200
    assert linked.json()["incident_id"] == "inc-http-target"


def test_declare_is_201_with_contract_shape() -> None:
    response = _post(
        _client(),
        "ahd",
        _cmd("triage_declare", reason=REASON, severity="sev2"),
        "k-declare-1234567890",
        BEARERS["op"],
    )
    assert response.status_code == 201
    body = response.json()
    assert STATE_VALIDATOR.is_valid(body), body
    assert (body["status"], body["alert_id"], body["actor"]) == ("declared", "ahd", "op-human")
    assert isinstance(body["incident_id"], str) and isinstance(body["decided_at"], str)


def test_declare_replay_returns_original_without_second_incident() -> None:
    client = _client()
    body = _cmd("triage_declare", reason=REASON, severity="sev1")
    before = _incident_count()
    first = _post(client, "ahr", body, "k-replay-12345678901", BEARERS["op"])
    assert first.status_code == 201
    assert _incident_count() == before + 1
    second = _post(client, "ahr", body, "k-replay-12345678901", BEARERS["op"])
    assert second.status_code == 201
    assert second.json()["incident_id"] == first.json()["incident_id"]
    assert second.json()["expected_version"] == first.json()["expected_version"]
    assert _incident_count() == before + 1


def test_unauthenticated_is_401() -> None:
    client = _client()
    body = _cmd("open_triage")
    missing = _post(client, "al-http-401", body, "k-http-401-1234567890", None)
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "authentication_failed"
    assert missing.headers["WWW-Authenticate"] == "Bearer"
    bad = _post(
        client, "al-http-401", body, "k-http-401-1234567890", "Bearer sre_admn_0123456789abcdefghij"
    )
    assert bad.status_code == 401


def test_forbidden_hides_existence() -> None:
    client = _client()
    for alert_id in ("al-http-ghost-one", "al-http-ghost-two"):
        response = _post(
            client, alert_id, _cmd("open_triage"), "k-http-403-1234567890", BEARERS["bystander"]
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "not_authorized"
        assert alert_id not in response.text
        assert REASON not in response.text


def test_status_table() -> None:
    client, bearer = _client(), BEARERS["op"]
    open_v1 = _cmd("open_triage")
    dec = {"reason": REASON, "severity": "sev2"}
    V, S, N = "validation_error", "stale_version", "incident_not_found"
    nosev = _cmd("triage_declare", reason=REASON)
    sev9 = _cmd("triage_declare", reason=REASON, severity="sev9")
    nolink = _cmd("triage_link", reason=REASON, target_incident_id="inc-absent")
    cases = [
        ("ahk", open_v1, None, None, 400, "invalid_idempotency_key"),
        ("ahk", open_v1, "short", None, 400, "invalid_idempotency_key"),
        ("ahk", None, "k-malformed-123456", b"{not json", 400, "invalid_command"),
        ("ahk", _cmd("nope"), "k-unknown-123456789", None, 422, V),
        ("ahk", nosev, "k-nosev-12345678901", None, 422, "invalid_severity"),
        ("ahk", sev9, "k-sev9-12345678901", None, 422, "invalid_severity"),
        ("ahs", _cmd("triage_declare", version=2, **dec), "k-stale-12345678901", None, 409, S),
        ("ahi", _cmd("triage_declare", **dec, impact="down"), "k-impact-123456789", None, 422, V),
        ("ahn", nolink, "k-404-1234567890123", None, 404, N),
        ("BAD ID!", open_v1, "k-badid-12345678901", None, 400, "invalid_command"),
    ]
    for alert_id, body, key, raw, status, code in cases:
        response = _post(client, alert_id, body, key, bearer, raw=raw)
        assert response.status_code == status, (alert_id, body)
        assert response.json()["error"]["code"] == code, (alert_id, body)


def test_storage_outage_is_503() -> None:
    client = _client("postgresql://postgres:postgres@127.0.0.1:1/postgres")
    response = _post(
        client,
        "al-http-down",
        _cmd("open_triage"),
        "k-http-down-1234567890",
        "Bearer sre_admn_0123456789abcdefghij",
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "storage_unavailable"
    assert response.headers["Retry-After"] == "5"
